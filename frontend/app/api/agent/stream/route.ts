import { NextRequest } from "next/server"

export const runtime = "nodejs"

/**
 * Proxy SSE stream from the Python agent backend to the frontend.
 * The frontend terminal drawer calls this, which forwards to the
 * Python FastAPI server at AGENT_API_URL (default: localhost:8000).
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const prompt = searchParams.get("prompt") ?? undefined
  const mode = searchParams.get("mode") ?? "multi"

  const agentUrl = process.env.AGENT_API_URL ?? "http://localhost:8000"
  const params = new URLSearchParams({ mode })
  if (prompt) params.set("prompt", prompt)

  try {
    const upstream = await fetch(`${agentUrl}/agent/stream?${params}`, {
      headers: { Accept: "text/event-stream" },
    })

    if (!upstream.ok || !upstream.body) {
      return Response.json(
        { error: `Agent API returned ${upstream.status}` },
        { status: upstream.status },
      )
    }

    // Pipe the SSE stream through
    return new Response(upstream.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    })
  } catch (e) {
    return Response.json(
      { error: "Agent API unavailable", detail: String(e) },
      { status: 503 },
    )
  }
}
