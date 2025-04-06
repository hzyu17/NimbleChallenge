import argparse
import asyncio
import logging
import struct
from urllib.parse import urlparse

from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.h3.connection import H3Connection, H3_ALPN
from aioquic.h3.events import HeadersReceived, DataReceived, DatagramReceived

logger = logging.getLogger("webtransport_client")


class WebTransportClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._http = H3Connection(self._quic, enable_webtransport=True)
        self._waiter = asyncio.get_event_loop().create_future()
        self.session = 77777

    def send_webtransport_session_request(self, path: str, authority: str):
        stream_id = self._quic.get_next_available_stream_id()
        # Send a CONNECT request with the :protocol header set to webtransport.
        headers = [
            (b":method", b"CONNECT"),
            (b":protocol", b"webtransport"),
            (b":scheme", b"https"),
            (b":authority", authority.encode()),
            (b":path", path.encode()),
        ]
        self._http.send_headers(stream_id, headers, end_stream=True)
        self.transmit()

    def send_double_data(self, value: float):
        """Create a WebTransport stream and send a double value."""

        # Create a new stream for sending data.
        stream_id = self._http.create_webtransport_stream(self.session)
        
        # Pack the double value (8 bytes, big-endian) into bytes.
        data = struct.pack("!d", value)
        print(f"Sending double value {value} on stream {stream_id}")
        
        # Send the data and mark the stream as ended.
        self._http.send_datagram(stream_id, data)
        self.transmit()

    def quic_event_received(self, event):
        for http_event in self._http.handle_event(event):
            if isinstance(http_event, HeadersReceived):
                stream_id = http_event.stream_id
                # Check the response status.
                status = None
                for name, value in http_event.headers:
                    if name == b":status":
                        status = value
                        break
                if status == b"200":
                    self.send_double_data(3.14159)
            elif isinstance(http_event, DataReceived):
                print("Received data:", http_event.data.decode())
            elif isinstance(http_event, DatagramReceived):
                print("Received datagram:", http_event.data.decode())
        self.transmit()

    def connection_lost(self, exc):
        if not self._waiter.done():
            self._waiter.set_result(None)

    def wait_closed(self):
        return self._waiter


async def run_client(url: str, configuration: QuicConfiguration):
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or 4433
    path = parsed.path if parsed.path else "/"
    authority = host if parsed.port is None else f"{host}:{port}"

    async with connect(
        host,
        port,
        configuration=configuration,
        create_protocol=lambda quic, **kwargs: WebTransportClientProtocol(quic, **kwargs),
    ) as client:
        # client.send_webtransport_session_request(path, authority)
        client.send_double_data(3.14159)
        # Wait until the connection is closed.
        await client.wait_closed()


async def main():
    parser = argparse.ArgumentParser(
        description="WebTransport client that transmits a double value"
    )
    parser.add_argument(
        "url", type=str, help="URL to connect (e.g., https://localhost:4433/)"
    )
    args = parser.parse_args()

    configuration = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN)
    # For testing with self-signed certificates, disable certificate verification.
    configuration.verify_mode = False
    configuration.max_datagram_frame_size = 65536

    await run_client(args.url, configuration)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())