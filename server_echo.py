#!/usr/bin/env python3

# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
An example WebTransport over HTTP/3 server based on the aioquic library.
Processes incoming streams and datagrams, and
replies with the ASCII-encoded length of the data sent in bytes.
Example use:
  python3 webtransport_server.py certificate.pem certificate.key
Example use from JavaScript:
  let transport = new WebTransport("https://localhost:4433/counter");
  await transport.ready;
  let stream = await transport.createBidirectionalStream();
  let encoder = new TextEncoder();
  let writer = stream.writable.getWriter();
  await writer.write(encoder.encode("Hello, world!"))
  writer.close();
  console.log(await new Response(stream.readable).text());
This will output "13" (the length of "Hello, world!") into the console.
"""

# ---- Dependencies ----
#
# This server only depends on Python standard library and aioquic 0.9.19 or
# later. See https://github.com/aiortc/aioquic for instructions on how to
# install aioquic.
#
# ---- Certificates ----
#
# HTTP/3 always operates using TLS, meaning that running a WebTransport over
# HTTP/3 server requires a valid TLS certificate.  The easiest way to do this
# is to get a certificate from a real publicly trusted CA like
# <https://letsencrypt.org/>.
# https://developers.google.com/web/fundamentals/security/encrypt-in-transit/enable-https
# contains a detailed explanation of how to achieve that.
#
# As an alternative, Chromium can be instructed to trust a self-signed
# certificate using command-line flags.  Here are step-by-step instructions on
# how to do that:
#
#   1. Generate a certificate and a private key:
#         openssl req -newkey rsa:2048 -nodes -keyout certificate.key \
#                   -x509 -out certificate.pem -subj '/CN=Test Certificate' \
#                   -addext "subjectAltName = DNS:localhost"
#
#   2. Compute the fingerprint of the certificate:
#         openssl x509 -pubkey -noout -in certificate.pem |
#                   openssl rsa -pubin -outform der |
#                   openssl dgst -sha256 -binary | base64
#      The result should be a base64-encoded blob that looks like this:
#          "Gi/HIwdiMcPZo2KBjnstF5kQdLI5bPrYJ8i3Vi6Ybck="
#
#   3. Pass a flag to Chromium indicating what host and port should be allowed
#      to use the self-signed certificate.  For instance, if the host is
#      localhost, and the port is 4433, the flag would be:
#         --origin-to-force-quic-on=localhost:4433
#
#   4. Pass a flag to Chromium indicating which certificate needs to be trusted.
#      For the example above, that flag would be:
#         --ignore-certificate-errors-spki-list=Gi/HIwdiMcPZo2KBjnstF5kQdLI5bPrYJ8i3Vi6Ybck=
#
# See https://www.chromium.org/developers/how-tos/run-chromium-with-flags for
# details on how to run Chromium with flags.

import argparse
import asyncio
import logging
from collections import defaultdict
from typing import Dict, Optional

from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import H3Event, HeadersReceived, WebTransportStreamDataReceived, DatagramReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import stream_is_unidirectional
from aioquic.quic.events import ProtocolNegotiated, StreamReset, QuicEvent

import multiprocessing 
from aiortc import RTCPeerConnection, VideoStreamTrack, RTCSessionDescription
from aiortc import RTCPeerConnection, RTCSessionDescription
import cv2
from av import VideoFrame
import json
import numpy as np

from ball_worker import generate_frames
from asyncio import create_task

BIND_ADDRESS = '::1'
BIND_PORT = 4433

logger = logging.getLogger(__name__)


manager = multiprocessing.Manager()
shared_frame_queue = manager.list()


class BallStreamTrack(VideoStreamTrack):
    def __init__(self, frame_queue):
        super().__init__()
        self.queue = frame_queue

    async def recv(self):        
        while len(self.queue) == 0:
            await asyncio.sleep(0.01)

        # frame_np = self.queue.get()  
        frame_data = self.queue[0]
        frame_np = np.array(frame_data['frame'], dtype=np.uint8)
        
        video_frame = VideoFrame.from_ndarray(frame_np, format="rgb24")
        video_frame.pts, video_frame.time_base = await self.next_timestamp()
        return video_frame


async def handle_offer(sdp_offer: str, frame_queue) -> str:
    pc = RTCPeerConnection()
   
    await pc.setRemoteDescription(RTCSessionDescription(sdp_offer, "offer"))

    has_video_transceiver = False
    for transceiver in pc.getTransceivers():
        if transceiver.kind == "video":
            has_video_transceiver = True
            pc.addTrack(BallStreamTrack(frame_queue))
            print("Added BallStreamTrack")

    if not has_video_transceiver:
        print("No video transceiver detected in offer!")
        
    # pc.addTrack(BallStreamTrack(frame_queue))
    
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    return pc.localDescription.sdp


# CounterHandler implements a really simple protocol:
#   - For every incoming bidirectional stream, it counts bytes it receives on
#     that stream until the stream is closed, and then replies with that byte
#     count on the same stream.
#   - For every incoming unidirectional stream, it counts bytes it receives on
#     that stream until the stream is closed, and then replies with that byte
#     count on a new unidirectional stream.
#   - For every incoming datagram, it sends a datagram with the length of
#     datagram that was just received.
class CounterHandler:

    def __init__(self, session_id, http: H3Connection) -> None:
        self._session_id = session_id
        self._http = http
        self._counters = defaultdict(int)
        self._payloads = defaultdict(bytearray)
        
        # shared_frame_queue = multiprocessing.Manager().list()
        

    async def h3_event_received(self, event: H3Event) -> None:
        if isinstance(event, DatagramReceived):
            try:
                data = event.data.decode()
                message = json.loads(data)
                
                # Compute the error with the current ball center
                x_client, y_client = message["x"], message["y"]

                # Grab latest frame from queue            
                if len(shared_frame_queue) > 0:
                    frame_data = shared_frame_queue[0]
                    # frame_np = np.array(frame_data["frame"], dtype=np.uint8)
                    center = frame_data["center"]

                    x_server, y_server = center[0], center[1]
                    error_x = x_client - x_server   
                    error_y = y_client - y_server
                    
                    # Send the error to the client
                    error_message = {
                        "error_x": error_x,
                        "error_y": error_y
                    }
                    self._http.send_datagram(self._session_id, json.dumps(error_message).encode())
                    print("Error sent to client:", error_message)
                                        
                else:
                    print("No frame available in queue")
                
            except Exception as e:
                print("Failed to decode datagram:", e)
            
        if isinstance(event, WebTransportStreamDataReceived):
            print("WebTransportStreamDataReceived! ")
            self._payloads[event.stream_id] += event.data
            if event.stream_ended:
                sdp_offer = self._payloads[event.stream_id].decode()
                
                if stream_is_unidirectional(event.stream_id):
                    response_id = self._http.create_webtransport_stream(
                        self._session_id, is_unidirectional=True)
                else:
                    response_id = event.stream_id
                                                
                # ------------ Show the bouncing ball locally ------------ 
                # multiprocessing.Process(target=generate_frames, daemon=True).start()
                # print("Bouncing ball process started")
                
                # ------------ Generate bouncing ball frames in a separate process ------------
                process = multiprocessing.Process(target=generate_frames, args=(shared_frame_queue,), daemon=True)
                process.start() 
                
                
                # ------------ Show the bouncing ball locally from the Queue ------------
                # asyncio.create_task(self.consume_frames())
                
                # --------------------- Respond the bouncing ball answer ---------------------
                # answer_sdp = await handle_offer(sdp_offer)
                # self._http._quic.send_stream_data(
                #     response_id, answer_sdp.encode(), end_stream=True
                # )
                
                answer_sdp = await handle_offer(sdp_offer, shared_frame_queue)
                
                response_id = event.stream_id
                self._http._quic.send_stream_data(response_id, answer_sdp.encode(), end_stream=True)
                
                # sdp = event.data.decode()
                # answer_sdp = handle_offer(sdp)
                # self._http._quic.send_stream_data(response_id, answer_sdp.encode(), end_stream=True)
                
                # --------------- send the message back ---------------
                # payload = self._payloads[event.stream_id]
                # self._http._quic.send_stream_data(
                #     response_id, payload, end_stream=True)
                
                
                # self.stream_closed(event.stream_id)


    async def consume_frames(self):
        print("Starting frame consumer")
        while True:
            if len(shared_frame_queue) > 0:
                frame_data = shared_frame_queue[0]
                frame = np.array(frame_data["frame"], dtype=np.uint8)

                cv2.imshow("Server Preview", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            await asyncio.sleep(0.01)
            
            
    def stream_closed(self, stream_id: int) -> None:
        try:
            del self._payloads[stream_id]
        except KeyError:
            pass


# WebTransportProtocol handles the beginning of a WebTransport connection: it
# responses to an extended CONNECT method request, and routes the transport
# events to a relevant handler (in this example, CounterHandler).
class WebTransportProtocol(QuicConnectionProtocol):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._http: Optional[H3Connection] = None
        self._handler: Optional[CounterHandler] = None

    def quic_event_received(self, event: QuicEvent) -> None:
        if isinstance(event, ProtocolNegotiated):
            self._http = H3Connection(self._quic, enable_webtransport=True)
        elif isinstance(event, StreamReset) and self._handler is not None:
            # Streams in QUIC can be closed in two ways: normal (FIN) and
            # abnormal (resets).  FIN is handled by the handler; the code
            # below handles the resets.
            self._handler.stream_closed(event.stream_id)

        if self._http is not None:
            for h3_event in self._http.handle_event(event):
                create_task(self._h3_event_received(h3_event))

    async def _h3_event_received(self, event: H3Event) -> None:
        if isinstance(event, HeadersReceived):
            headers = {}
            for header, value in event.headers:
                headers[header] = value
            if (headers.get(b":method") == b"CONNECT" and
                    headers.get(b":protocol") == b"webtransport"):
                self._handshake_webtransport(event.stream_id, headers)
            else:
                self._send_response(event.stream_id, 400, end_stream=True)

        if self._handler:
            await self._handler.h3_event_received(event)
            

    def _handshake_webtransport(self,
                                stream_id: int,
                                request_headers: Dict[bytes, bytes]) -> None:
        authority = request_headers.get(b":authority")
        path = request_headers.get(b":path")
        if authority is None or path is None:
            # `:authority` and `:path` must be provided.
            self._send_response(stream_id, 400, end_stream=True)
            return
        if path == b"/echo":
            assert(self._handler is None)
            self._handler = CounterHandler(stream_id, self._http)
            self._send_response(stream_id, 200)
        elif path == b"/offer":
            assert(self._handler is None)
            self._handler = CounterHandler(stream_id, self._http)
            self._send_response(stream_id, 200)            
        else:
            self._send_response(stream_id, 404, end_stream=True)

    def _send_response(self,
                       stream_id: int,
                       status_code: int,
                       end_stream=False) -> None:
        headers = [(b":status", str(status_code).encode())]
        if status_code == 200:
            headers.append((b"sec-webtransport-http3-draft", b"draft02"))
        self._http.send_headers(
            stream_id=stream_id, headers=headers, end_stream=end_stream)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('certificate')
    parser.add_argument('key')
    args = parser.parse_args()

    configuration = QuicConfiguration(
        alpn_protocols=H3_ALPN,
        is_client=False,
        max_datagram_frame_size=65536,
    )
    configuration.load_cert_chain(args.certificate, args.key)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        serve(
            BIND_ADDRESS,
            BIND_PORT,
            configuration=configuration,
            create_protocol=WebTransportProtocol,
        ))
    try:
        logging.info(
            "Listening on https://{}:{}".format(BIND_ADDRESS, BIND_PORT))    
        loop.run_forever()
    
    ## Handle close signal
    except KeyboardInterrupt:
        pass
