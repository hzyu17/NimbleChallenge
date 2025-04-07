// Adds an entry to the event log on the page, optionally applying a specified
// CSS class.

let currentTransport, streamNumber, currentTransportDatagramWriter;

// "Connect" button handler.
async function connect() {
  const url = document.getElementById('url').value;
  try {
    var transport = new WebTransport(url);
    addToEventLog('Initiating connection...');
  } catch (e) {
    addToEventLog('Failed to create connection object. ' + e, 'error');
    return;
  }

  try {
    await transport.ready;
    addToEventLog('Connection ready.');
  } catch (e) {
    addToEventLog('Connection failed. ' + e, 'error');
    return;
  }

  transport.closed
      .then(() => {
        addToEventLog('Connection closed normally.');
      })
      .catch(() => {
        addToEventLog('Connection closed abruptly.', 'error');
      });

  currentTransport = transport;
  streamNumber = 1;
  try {
    currentTransportDatagramWriter = transport.datagrams.writable.getWriter();
    addToEventLog('Datagram writer ready.');
  } catch (e) {
    addToEventLog('Sending datagrams not supported: ' + e, 'error');
    return;
  }
  readDatagrams(transport);
  acceptUnidirectionalStreams(transport);
  document.forms.sending.elements.send.disabled = false;
  document.getElementById('connect').disabled = true;

}

// "Send data" button handler.
async function sendData() {
  let form = document.forms.sending.elements;
  let encoder = new TextEncoder('utf-8');
  let rawData = sending.data.value;
  let data = encoder.encode(rawData);
  let transport = currentTransport;
  try {
    switch (form.sendtype.value) {
      case 'datagram':
        await currentTransportDatagramWriter.write(data);
        addToEventLog('Sent datagram: ' + rawData);
        break;
      case 'unidi': {
        let stream = await transport.createUnidirectionalStream();
        let writer = stream.getWriter();
        await writer.write(data);
        await writer.close();
        addToEventLog('Sent a unidirectional stream with data: ' + rawData);
        break;
      }
      case 'bidi': {
        let stream = await transport.createBidirectionalStream();
        let number = streamNumber++;
        readFromIncomingStream(stream.readable, number);

        let writer = stream.writable.getWriter();
        await writer.write(data);
        await writer.close();
        addToEventLog(
            'Opened bidirectional stream #' + number +
            ' with data: ' + rawData);
        break;
      }
    }
  } catch (e) {
    addToEventLog('Error while sending data: ' + e, 'error');
  }
}


function findBallCenter(pixels, width, height) {
  let totalX = 0;
  let totalY = 0;
  let count = 0;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const r = pixels[i];
      const g = pixels[i + 1];
      const b = pixels[i + 2];
      const a = pixels[i + 3];

      // Simple threshold — detect white-ish pixels
      if (r < 50 && g < 50 && b > 200 && a > 200) {
        totalX += x;
        totalY += y;
        count++;
      }
    }
  }

  if (count > 0) {
    const cx = Math.round(totalX / count);
    const cy = Math.round(totalY / count);
    return { x: cx, y: cy };
  } else {
    return null; 
  }
}

// "Send SDP offer" button handler.
async function sendSDP() {
  addToEventLog("Creating WebRTC peer connection...");

  const pc = new RTCPeerConnection();

  pc.addTransceiver("video", { direction: "recvonly" });

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const fullOfferSdp = pc.localDescription.sdp;

  addToEventLog("Generated SDP offer:\n" + fullOfferSdp);

  const transport = new WebTransport("https://localhost:4433/offer");

  try {
    await transport.ready;
    addToEventLog("WebTransport connected!");

    const stream = await transport.createBidirectionalStream();
    const writer = stream.writable.getWriter();
    await writer.write(new TextEncoder().encode(fullOfferSdp));
    await writer.close();

    addToEventLog("SDP offer sent over WebTransport.");

    // Read response from the server

    pc.ontrack = (event) => {
      const video = document.getElementById("video");
      if (!video.srcObject) {
        const stream = new MediaStream();
        stream.addTrack(event.track);
        video.srcObject = stream;
      }
      addToEventLog("Video track received and displayed.");

    };

    const video = document.getElementById("video");
    const canvas = document.getElementById("canvas");
    const ctx = canvas.getContext("2d");

    function processFrame(now, metadata) {
      // Draw current video frame onto canvas
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Extract pixel data (RGBA)
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const pixels = imageData.data; 
      
      // Find the ball center
      const center = findBallCenter(pixels, canvas.width, canvas.height);

      // Send the ball center coordinates as a datagram to the server
      if (center && currentTransportDatagramWriter) {
        // addToEventLog(`Ball center: (${center.x}, ${center.y})`);

        const message = JSON.stringify({ x: center.x, y: center.y });
        const encoded = new TextEncoder().encode(message);
        currentTransportDatagramWriter.write(encoded);
        
      }


      // Continue listening to the next frame
      video.requestVideoFrameCallback(processFrame);
    }

    // Start the frame capture loop once video is ready
    video.addEventListener("loadedmetadata", () => {
      video.requestVideoFrameCallback(processFrame);
    });

    // Read the SDP answer from the server
    const reader = stream.readable.getReader();
    let answerSdp = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      answerSdp += new TextDecoder().decode(value);
    }

    addToEventLog("Received SDP answer from server.");
    // Show the response in the event log
    addToEventLog(answerSdp);
    await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
    
  } catch (e) {
    addToEventLog("Failed to connect/send via WebTransport: " + e);
  }
}


// // Reads datagrams from |transport| into the event log until EOF is reached.
// async function readDatagrams(transport) {
//   try {
//     var reader = transport.datagrams.readable.getReader();
//     addToEventLog('Datagram reader ready.');
//   } catch (e) {
//     addToEventLog('Receiving datagrams not supported: ' + e, 'error');
//     return;
//   }
//   const decoder = new TextDecoder('utf-8');
//   try {
//     while (true) {
//       const { value, done } = await reader.read();
//       if (done) {
//         addToEventLog('Done reading datagrams!');
//         return;
//       }
//       let data = decoder.decode(value);
//       addToEventLog('Datagram received: ' + data);
//     }
//   } catch (e) {
//     addToEventLog('Error while reading datagrams: ' + e, 'error');
//   }
// }

async function readDatagrams(transport) {
  try {
    const reader = transport.datagrams.readable.getReader();
    const decoder = new TextDecoder("utf-8");  // Make sure this is here
    addToEventLog("Datagram reader ready.");

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        addToEventLog("Datagram stream closed.");
        return;
      }

      const jsonString = decoder.decode(value);  // Now decoder is in scope
      const message = JSON.parse(jsonString);

      addToEventLog(
        `Ball center difference: ${JSON.stringify(message)}`
      );
    }
  } catch (e) {
    addToEventLog("Error while reading datagrams: " + e, "error");
  }
}


async function acceptUnidirectionalStreams(transport) {
  let reader = transport.incomingUnidirectionalStreams.getReader();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        addToEventLog('Done accepting unidirectional streams!');
        return;
      }
      let stream = value;
      let number = streamNumber++;
      addToEventLog('New incoming unidirectional stream #' + number);
      readFromIncomingStream(stream, number);
    }
  } catch (e) {
    addToEventLog('Error while accepting streams: ' + e, 'error');
  }
}

async function readFromIncomingStream(readable, number) {
  const decoder = new TextDecoderStream('utf-8');
  let reader = readable.pipeThrough(decoder).getReader();
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        addToEventLog('Stream #' + number + ' closed');
        return;
      }
      let data = value;
      addToEventLog('Received data on stream #' + number + ': ' + data);
    }
  } catch (e) {
    addToEventLog(
        'Error while reading from stream #' + number + ': ' + e, ' error');
    addToEventLog('    ' + e.message);
  }
}

function addToEventLog(text, severity = 'info') {
  let log = document.getElementById('event-log');
  let mostRecentEntry = log.lastElementChild;
  let entry = document.createElement('li');
  entry.innerText = text;
  entry.className = 'log-' + severity;
  log.appendChild(entry);

  // If the most recent entry in the log was visible, scroll the log to the
  // newly added element.
  if (mostRecentEntry != null &&
      mostRecentEntry.getBoundingClientRect().top <
          log.getBoundingClientRect().bottom) {
    entry.scrollIntoView();
  }
}
