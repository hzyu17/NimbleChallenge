## Design Decisions
My App is built on top of the open-sourced sample of the WebApp using WebTransport protocol to transmit video frames and data, available here:
https://github.com/w3c/webtransport/tree/main

### This project chooses python webtransport API at the server side, and Javascript API at the client side.


## How to run the web app

1. Open a terminal, and run
```
cd /path/to/NimbleChallenge/public

python3 -m http.server 8000
```

2. Open another terminal, and run chrome browser with the cert and the key used by the server, using
```
cd /path/to/NimbleChallenge

chromium-browser --origin-to-force-quic-on=localhost:4433 --ignore-certificate-errors-spki-list=FW8whX6LOaDhtXky4WSkBVu6k2XpZNKjs8dQMYXMIRo=
```


3. In the chromium browser, go to the address
```
localhost:8000
```

3. Open another terminal, and run the server using:
```
python3 server_echo.py certificate.pem certificate.key
```

4. In the browser, click "Connect", and then click "Send SDP Offer"