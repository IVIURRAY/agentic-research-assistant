import type { UIMessage } from "ai";

export type Chunk = {
  chunk_id: string;
  heading: string | null;
  content: string;
  score: number | null;
};

export type Source = {
  note_id: string;
  title: string;
  ticker: string | null;
  company: string | null;
  sector: string | null;
  rating: string | null;
  price_target: number | null;
  currency: string | null;
  analyst: string | null;
  published_date: string;
  chunks: Chunk[];
};

export type RunData = { run_id: string | null; session_id: string; cited?: string[] };

export type ToolData = {
  name: string;
  input: Record<string, unknown>;
  status: "running" | "done" | "error";
  results?: number;
  error?: string;
};

export type SourcesData = Record<string, Source>;

export type ResearchMessage = UIMessage<
  never,
  { run: RunData; tool: ToolData; sources: SourcesData }
>;

export type NoteDetail = Omit<Source, "chunks"> & {
  body: string;
  chunks: { chunk_id: string; heading: string | null; content: string }[];
};
