const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const upstream = await fetch(`${API_URL}/notes/${encodeURIComponent(id)}`);
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
