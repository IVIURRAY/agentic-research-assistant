const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function POST(req: Request) {
  const upstream = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await req.text(),
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
