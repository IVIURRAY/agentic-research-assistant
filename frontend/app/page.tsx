"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import type { ResearchMessage, RunData, Source, SourcesData, ToolData } from "@/lib/types";

import { NoteViewer } from "./note-viewer";

const SUGGESTIONS = [
  "How has our view on ASML changed since Q1?",
  "Why did we downgrade Novo Nordisk?",
  "Compare our ratings on ASML and TSMC in April 2026.",
  "Can the oil majors sustain buybacks at $65 Brent?",
];

// [note-id], [a, b], and the full-width 【note-id#0】 form some models use; "#n" chunk suffixes
// are dropped so every citation points at a note.
const NOTE_ID = String.raw`[a-z0-9][a-z0-9-]*-[a-z0-9-]+(?:#\d+)?`;
const CITE = new RegExp(String.raw`[\[【]\s*(${NOTE_ID}(?:\s*[,;]\s*${NOTE_ID})*)\s*[\]】]`, "g");

function linkCitations(text: string): string {
  return text.replace(CITE, (_, ids: string) =>
    ids
      .split(/[,;]/)
      .map((raw) => raw.trim().split("#")[0])
      .map((id) => `[${id}](#cite:${id})`)
      .join(" "),
  );
}

function partsOf(m: ResearchMessage) {
  let run: RunData | undefined;
  let sources: SourcesData = {};
  const tools: { id: string; data: ToolData }[] = [];
  let text = "";
  for (const p of m.parts) {
    if (p.type === "text") text += p.text;
    else if (p.type === "data-run") run = p.data;
    else if (p.type === "data-sources") sources = p.data;
    else if (p.type === "data-tool") tools.push({ id: p.id ?? String(tools.length), data: p.data });
  }
  return { run, sources, tools, text };
}

function formatPT(s: Source) {
  if (s.price_target == null) return null;
  return `${s.price_target.toLocaleString()} ${s.currency ?? ""}`.trim();
}

function ToolPill({ tool }: { tool: ToolData }) {
  const filters = Object.entries(tool.input)
    .filter(([k, v]) => k !== "query" && v)
    .map(([k, v]) => `${k}=${v}`);
  const label =
    tool.name === "get_note" ? `read ${tool.input.note_id ?? "note"}` : `search “${tool.input.query ?? ""}”`;
  return (
    <div className={`tool tool-${tool.status}`}>
      <span className="tool-dot" />
      <span className="tool-label">{label}</span>
      {filters.map((f) => (
        <span key={f} className="tool-filter">
          {f}
        </span>
      ))}
      {tool.status === "done" && tool.results != null && (
        <span className="tool-count">{tool.results} hits</span>
      )}
      {tool.status === "error" && <span className="tool-count">{tool.error}</span>}
    </div>
  );
}

function Feedback({ run }: { run?: RunData }) {
  const [sent, setSent] = useState<1 | -1 | null>(null);
  if (!run?.run_id) return null;
  const send = async (score: 1 | -1) => {
    setSent(score);
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ run_id: run.run_id, session_id: run.session_id, score }),
    });
  };
  return (
    <div className="feedback">
      <button aria-label="Helpful" className={sent === 1 ? "on" : ""} disabled={sent !== null} onClick={() => send(1)}>
        ▲
      </button>
      <button aria-label="Not helpful" className={sent === -1 ? "on" : ""} disabled={sent !== null} onClick={() => send(-1)}>
        ▼
      </button>
      {sent !== null && <span className="muted">Thanks — logged to the trace</span>}
    </div>
  );
}

function SourceCard({
  source,
  cited,
  active,
  onView,
}: {
  source: Source;
  cited: boolean;
  active: boolean;
  onView: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active]);
  const pt = formatPT(source);
  return (
    <div ref={ref} id={`src-${source.note_id}`} className={`source ${cited ? "cited" : ""} ${active ? "active" : ""}`}>
      <div className="source-meta">
        <code>{source.note_id}</code>
        <span className={`badge ${cited ? "badge-cited" : "badge-retrieved"}`}>
          {cited ? "Cited" : "Retrieved only"}
        </span>
      </div>
      <div className="source-title">{source.title}</div>
      <div className="source-tags">
        {source.ticker && <span className="tag">{source.ticker}</span>}
        {source.sector && <span className="tag">{source.sector}</span>}
        {source.rating && <span className={`tag rating-${source.rating.toLowerCase()}`}>{source.rating}</span>}
        {pt && <span className="tag">PT {pt}</span>}
        <span className="tag">{source.published_date}</span>
      </div>
      <div className="source-counts muted">
        {source.chunks.length} passage{source.chunks.length === 1 ? "" : "s"} retrieved
      </div>
      {(cited || active) &&
        source.chunks.slice(0, 3).map((c) => (
          <blockquote key={c.chunk_id}>
            {c.heading && <strong>{c.heading}. </strong>}
            {c.content.length > 420 ? `${c.content.slice(0, 420)}…` : c.content}
          </blockquote>
        ))}
      <button className="view-note" onClick={onView}>
        View full note →
      </button>
    </div>
  );
}

export default function Page() {
  const [input, setInput] = useState("");
  const [focusId, setFocusId] = useState<string | null>(null);
  const [activeCite, setActiveCite] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Source | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const { messages, sendMessage, status, error, stop } = useChat<ResearchMessage>({
    transport: new DefaultChatTransport({ api: "/api/chat" }),
  });

  const busy = status === "submitted" || status === "streaming";
  const assistant = messages.filter((m) => m.role === "assistant");
  const focused = assistant.find((m) => m.id === focusId) ?? assistant[assistant.length - 1];
  const panel = useMemo(() => (focused ? partsOf(focused) : null), [focused]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const ask = (text: string) => {
    if (!text.trim() || busy) return;
    setFocusId(null);
    setActiveCite(null);
    sendMessage({ text });
    setInput("");
  };

  const cited = new Set(panel?.run?.cited ?? []);
  const sources = panel ? Object.values(panel.sources) : [];
  const citedSources = sources.filter((s) => cited.has(s.note_id));
  const otherSources = sources.filter((s) => !cited.has(s.note_id));
  const card = (s: Source) => (
    <SourceCard
      key={s.note_id}
      source={s}
      cited={cited.has(s.note_id)}
      active={activeCite === s.note_id}
      onView={() => setViewing(s)}
    />
  );

  return (
    <div className="shell">
      <header>
        <div className="brand">
          <span className="logo">◆</span> Research Assistant
        </div>
        <div className="muted">LangGraph agent · pgvector hybrid search</div>
      </header>

      <main className="chat">
        {messages.length === 0 && (
          <div className="empty">
            <h1>Ask the research library</h1>
            <p className="muted">Answers are drawn from the team’s notes, with every claim cited.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => {
          if (m.role === "user") {
            const text = m.parts.map((p) => (p.type === "text" ? p.text : "")).join("");
            return (
              <div key={m.id} className="msg user">
                {text}
              </div>
            );
          }
          const { run, tools, text } = partsOf(m);
          const isFocused = focused?.id === m.id;
          return (
            <div key={m.id} className={`msg assistant ${isFocused ? "focused" : ""}`} onClick={() => setFocusId(m.id)}>
              {tools.length > 0 && (
                <div className="tools">
                  {tools.map((t) => (
                    <ToolPill key={t.id} tool={t.data} />
                  ))}
                </div>
              )}
              <div className="answer">
                <ReactMarkdown
                  components={{
                    a: ({ href, children }) => {
                      if (href?.startsWith("#cite:")) {
                        const id = href.slice(6);
                        return (
                          <button
                            className={`cite ${activeCite === id && isFocused ? "on" : ""}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setFocusId(m.id);
                              setActiveCite(id);
                            }}
                          >
                            {children}
                          </button>
                        );
                      }
                      return (
                        <a href={href} target="_blank" rel="noreferrer">
                          {children}
                        </a>
                      );
                    },
                  }}
                >
                  {linkCitations(text)}
                </ReactMarkdown>
                {busy && m.id === messages[messages.length - 1].id && !text && (
                  <span className="muted thinking">Researching…</span>
                )}
              </div>
              {!busy && <Feedback run={run} />}
            </div>
          );
        })}
        {error && <div className="msg error">Something went wrong: {error.message}</div>}
        <div ref={bottom} />
      </main>

      <aside className="panel">
        <div className="panel-head">
          Sources
          {sources.length > 0 && (
            <span className="muted">
              {cited.size} cited · {sources.length} retrieved
            </span>
          )}
        </div>
        {sources.length === 0 ? (
          <p className="muted">Notes the assistant retrieves will appear here.</p>
        ) : (
          <>
            {citedSources.length > 0 && (
              <h4 className="panel-group">Cited in the answer · {citedSources.length}</h4>
            )}
            {citedSources.map(card)}
            {otherSources.length > 0 && (
              <h4 className="panel-group">Retrieved but not cited · {otherSources.length}</h4>
            )}
            {otherSources.map(card)}
          </>
        )}
      </aside>

      {viewing && (
        <NoteViewer
          noteId={viewing.note_id}
          cited={cited.has(viewing.note_id)}
          highlight={new Set(viewing.chunks.map((c) => c.chunk_id))}
          onClose={() => setViewing(null)}
        />
      )}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about a company, sector or how a view has changed…"
          autoFocus
        />
        {busy ? (
          <button type="button" onClick={() => stop()}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={!input.trim()}>
            Ask
          </button>
        )}
      </form>
    </div>
  );
}
