async function sendData() {
    const transport = new WebTransport("https://localhost:4433/submit");
  
    try {
      await transport.ready;
      console.log("✅ WebTransport connected");
  
      const stream = await transport.createBidirectionalStream();
      const writer = stream.writable.getWriter();
      const reader = stream.readable.getReader();
  
      await writer.write(new TextEncoder().encode("Hello from browser!"));
      await writer.close();
  
      const { value, done } = await reader.read();
      if (!done) {
        const text = new TextDecoder().decode(value);
        document.getElementById("response").textContent = text;
        console.log("✅ Server replied:", text);
      }
    } catch (err) {
      console.error("❌ WebTransport failed:", err);
    }
  }