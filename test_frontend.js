const fetch = require('node-fetch');

async function test() {
  const res = await fetch("http://127.0.0.1:8000/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: [{role: "user", content: "hello"}], patient_id: 1 }),
  });

  const decoder = new TextDecoder();
  let buffer = "";

  for await (const chunk of res.body) {
    buffer += decoder.decode(chunk, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") return;
      try {
        console.log("TOKEN:", JSON.parse(data));
      } catch {
        console.log("RAW:", data);
      }
    }
  }
}
test().catch(console.error);
