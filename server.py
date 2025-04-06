import asyncio
from aioquic.asyncio import QuicConnectionProtocol, serve
from aioquic.h3.connection import H3Connection, H3_ALPN
from aioquic.h3.events import HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ProtocolNegotiated, StreamDataReceived

class WebTransportServer(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http = None
        self._webtransport_sessions = set()

    def quic_event_received(self, event):
        if isinstance(event, ProtocolNegotiated):
            self._http = H3Connection(self._quic, enable_webtransport=True)

        if self._http:
            for http_event in self._http.handle_event(event):
                if isinstance(http_event, HeadersReceived):
                    headers = dict(http_event.headers)
                    method = headers.get(b":method", b"").decode()
                    path = headers.get(b":path", b"").decode()
                    stream_id = http_event.stream_id

                    if method == "CONNECT" and path == "/submit":
                        self._http.send_headers(stream_id, [(b":status", b"200")])
                        print(f"Accepted WebTransport session on stream {stream_id}")

        if isinstance(event, StreamDataReceived):
            stream_id = event.stream_id

            # Accept all incoming bidirectional streams as WebTransport
            if stream_id not in self._webtransport_sessions:
                data = event.data.decode()
                print(f"📨 Received from client [stream {stream_id}]: {data}")
                self._quic.send_stream_data(stream_id, b"Server got your message!\n", end_stream=True)

async def main():
    configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=H3_ALPN,
        max_datagram_frame_size=65536
    )
    configuration.load_cert_chain("cert.pem", "key.pem")

    await serve(
        host="localhost",
        port=4433,
        configuration=configuration,
        create_protocol=WebTransportServer
    )
    print("🚀 Server running at https://localhost:4433")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())