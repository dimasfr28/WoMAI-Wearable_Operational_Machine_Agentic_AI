import {
  createUIMessageStream,
  createUIMessageStreamResponse,
} from "ai";
import { pickScenario } from "@/lib/mock/scenarios";
import type { WomaiMessage } from "@/lib/types";

// URL backend (server-side). Di Docker: http://backend:8000; lokal: localhost.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

// Pipeline penuh (prediksi + SHAP + SOP + sintesis LLM) bisa >30 detik;
// beri margin agar tidak abort di tengah stream.
const BACKEND_TIMEOUT_MS = 120_000;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function lastUserText(messages: WomaiMessage[]): string {
  const lastUser = [...messages].reverse().find((m) => m.role === "user");
  if (!lastUser) return "";
  return lastUser.parts
    .filter((p) => p.type === "text")
    .map((p) => p.text)
    .join(" ");
}

export async function POST(req: Request) {
  let body: { messages?: WomaiMessage[]; id?: string };
  try {
    body = (await req.json()) as { messages?: WomaiMessage[]; id?: string };
  } catch {
    return Response.json({ error: "Body harus JSON valid" }, { status: 400 });
  }
  const messages = body.messages ?? [];
  const text = lastUserText(messages);
  const sessionId = body.id ?? "default";

  // Coba backend deep-agent; fallback ke mock bila tidak terjangkau.
  try {
    const resp = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session_id: sessionId }),
      signal: AbortSignal.timeout(BACKEND_TIMEOUT_MS),
    });
    if (!resp.ok || !resp.body) throw new Error(`backend ${resp.status}`);
    return backendStream(resp.body);
  } catch {
    return mockStream(text);
  }
}

/** Terjemahkan SSE event terstruktur backend → UI message stream frontend. */
function backendStream(body: ReadableStream<Uint8Array>): Response {
  const stream = createUIMessageStream<WomaiMessage>({
    async execute({ writer }) {
      writer.write({ type: "start" });

      const reader = body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let textOpen = false;

      const openText = () => {
        if (!textOpen) {
          writer.write({ type: "text-start", id: "jawaban" });
          textOpen = true;
        }
      };
      const closeText = () => {
        if (textOpen) {
          writer.write({ type: "text-end", id: "jawaban" });
          textOpen = false;
        }
      };

      const handle = (ev: Record<string, unknown>) => {
        switch (ev.type) {
          case "status":
            writer.write({
              type: "data-status",
              data: { message: String(ev.message) },
              transient: true,
            });
            break;
          case "prediction":
            writer.write({ type: "data-prediction", data: ev.data as never });
            break;
          case "shap":
            writer.write({ type: "data-shap", data: ev.data as never });
            break;
          case "sop":
            writer.write({ type: "data-sop", data: ev.data as never });
            break;
          case "downtime":
            writer.write({ type: "data-downtime", data: ev.data as never });
            break;
          case "text":
            openText();
            writer.write({
              type: "text-delta",
              id: "jawaban",
              delta: String(ev.delta),
            });
            break;
          case "needs_input":
            openText();
            writer.write({
              type: "text-delta",
              id: "jawaban",
              delta: String(ev.message),
            });
            break;
          case "error":
            openText();
            writer.write({
              type: "text-delta",
              id: "jawaban",
              delta: `⚠️ ${String(ev.message)}`,
            });
            break;
        }
      };

      try {
        for (; ;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() ?? "";
          for (const chunk of chunks) {
            const line = chunk.trim();
            if (!line.startsWith("data:")) continue;
            try {
              handle(JSON.parse(line.slice(5).trim()));
            } catch {
              // abaikan baris tak valid
            }
          }
        }
      } catch {
        openText();
        writer.write({
          type: "text-delta",
          id: "jawaban",
          delta: "\n\n⚠️ Koneksi ke server terputus sebelum jawaban selesai. Coba lagi.",
        });
      }

      closeText();
      writer.write({ type: "finish" });
    },
  });

  return createUIMessageStreamResponse({ stream });
}

/** Fallback mock lama — dipakai bila backend deep-agent tidak tersedia. */
function mockStream(text: string): Response {
  const scenario = pickScenario(text);
  const stream = createUIMessageStream<WomaiMessage>({
    async execute({ writer }) {
      writer.write({ type: "start" });
      writer.write({
        type: "data-status",
        data: { message: "Menganalisis parameter (mode demo/offline)…" },
        transient: true,
      });
      await sleep(500);
      writer.write({ type: "data-prediction", data: scenario.prediction });
      await sleep(200);
      if (scenario.shap) {
        writer.write({ type: "data-shap", data: scenario.shap });
        await sleep(200);
      }
      writer.write({ type: "text-start", id: "jawaban" });
      for (const word of scenario.responseText.split(/\s+/)) {
        writer.write({ type: "text-delta", id: "jawaban", delta: word + " " });
        await sleep(20);
      }
      writer.write({ type: "text-end", id: "jawaban" });
      if (scenario.sop) {
        writer.write({ type: "data-sop", data: scenario.sop });
        await sleep(200);
      }
      if (scenario.downtime) {
        writer.write({ type: "data-downtime", data: scenario.downtime });
      }
      writer.write({ type: "finish" });
    },
  });
  return createUIMessageStreamResponse({ stream });
}
