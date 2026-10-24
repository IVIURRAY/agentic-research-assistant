// Bridges the FastAPI SSE stream into the AI SDK UI message stream that useChat consumes.
// Text deltas become text parts; run ids, tool calls and sources become typed data parts.
import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

import type { ResearchMessage } from "@/lib/types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export const maxDuration = 300;

type BackendEvent = { event: string; data: Record<string, any> };

async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<BackendEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) yield { event, data: JSON.parse(data.join("\n")) };
    }
  }
}

function textOf(message: ResearchMessage): string {
  return message.parts
    .map((p) => (p.type === "text" ? p.text : ""))
    .join("")
    .trim();
}

export async function POST(req: Request) {
  const { id, messages }: { id: string; messages: ResearchMessage[] } = await req.json();
  const last = messages[messages.length - 1];
  const history = messages
    .slice(0, -1)
    .map((m) => ({ role: m.role, content: textOf(m) }))
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.content);

  const stream = createUIMessageStream<ResearchMessage>({
    onError: (error) => (error instanceof Error ? error.message : String(error)),
    execute: async ({ writer }) => {
      const upstream = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify({ message: textOf(last), session_id: id, history }),
        signal: req.signal,
      });
      if (!upstream.ok || !upstream.body) {
        throw new Error(`Research API error ${upstream.status}`);
      }

      writer.write({ type: "start" });
      const textId = "answer";
      let textOpen = false;
      let run: { run_id: string | null; session_id: string } = { run_id: null, session_id: id };
      const toolInputs = new Map<string, Record<string, unknown>>();

      for await (const { event, data } of readSSE(upstream.body)) {
        switch (event) {
          case "run":
            run = { run_id: data.run_id, session_id: data.session_id };
            writer.write({ type: "data-run", id: "run", data: run });
            break;
          case "tool_call":
            toolInputs.set(data.id, data.input ?? {});
            writer.write({
              type: "data-tool",
              id: data.id,
              data: { name: data.name, input: data.input ?? {}, status: "running" },
            });
            break;
          case "tool_result":
            writer.write({
              type: "data-tool",
              id: data.id,
              data: {
                name: data.name,
                input: toolInputs.get(data.id) ?? {},
                status: data.error ? "error" : "done",
                results: data.results?.length,
                error: data.error,
              },
            });
            break;
          case "sources":
            writer.write({ type: "data-sources", id: "sources", data: data.sources });
            break;
          case "text":
            if (!textOpen) {
              writer.write({ type: "text-start", id: textId });
              textOpen = true;
            }
            writer.write({ type: "text-delta", id: textId, delta: data.delta });
            break;
          case "done":
            writer.write({ type: "data-sources", id: "sources", data: data.sources });
            writer.write({ type: "data-run", id: "run", data: { ...run, cited: data.cited } });
            break;
          case "error":
            writer.write({ type: "error", errorText: data.message });
            break;
        }
      }
      if (textOpen) writer.write({ type: "text-end", id: textId });
      writer.write({ type: "finish" });
    },
  });

  return createUIMessageStreamResponse({ stream });
}
