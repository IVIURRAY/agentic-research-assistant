"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import type { NoteDetail } from "@/lib/types";

/** The full note, rebuilt from its chunks, with the chunks the agent retrieved highlighted. */
export function NoteViewer({
  noteId,
  cited,
  highlight,
  onClose,
}: {
  noteId: string;
  cited: boolean;
  highlight: Set<string>;
  onClose: () => void;
}) {
  const [note, setNote] = useState<NoteDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const firstHit = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/notes/${encodeURIComponent(noteId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((n: NoteDetail) => !cancelled && setNote(n))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [noteId]);

  useEffect(() => {
    firstHit.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [note]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const readWhole = [...highlight].some((id) => id.endsWith("#full"));  // via get_note
  const hits = note?.chunks.filter((c) => highlight.has(c.chunk_id)).length ?? 0;
  let firstAssigned = false;
  return (
    <div className="viewer-backdrop" onClick={onClose}>
      <article className="viewer" role="dialog" aria-modal="true" aria-label={`Note ${noteId}`} onClick={(e) => e.stopPropagation()}>
        <header className="viewer-head">
          <div>
            <code>{noteId}</code>{" "}
            <span className={`badge ${cited ? "badge-cited" : "badge-retrieved"}`}>
              {cited ? "Cited" : "Retrieved only"}
            </span>
            {note && (
              <span className="muted">
                {" "}· {note.published_date}
                {note.analyst && ` · ${note.analyst}`}
                {note.rating && ` · ${note.rating}`}
              </span>
            )}
            {note && <h2>{note.title}</h2>}
          </div>
          <button className="viewer-close" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </header>
        {note && (
          <p className="viewer-legend muted">
            {readWhole ? (
              "The agent read this whole note."
            ) : (
              <>
                <mark>Highlighted</mark>: the {hits} passage{hits === 1 ? "" : "s"} the agent retrieved.
              </>
            )}
            {cited ? " The answer cites this note." : " The answer doesn’t cite this note."}
          </p>
        )}
        {error && <p className="muted">Couldn’t load the note ({error}).</p>}
        {!note && !error && <p className="muted">Loading…</p>}
        {note?.chunks.map((c, i) => {
          const hit = highlight.has(c.chunk_id);
          const isFirst = hit && !firstAssigned;
          if (isFirst) firstAssigned = true;
          const newSection = c.heading && c.heading !== note.chunks[i - 1]?.heading;
          return (
            <section key={c.chunk_id}>
              {newSection && <h3>{c.heading}</h3>}
              <div ref={isFirst ? (el) => { firstHit.current = el; } : undefined} className={hit ? "chunk hit" : "chunk"}>
                <ReactMarkdown>{c.content}</ReactMarkdown>
              </div>
            </section>
          );
        })}
      </article>
    </div>
  );
}
