// Proxies GET /machine-report/{id}/pdf so the browser can render the PDF via
// a same-origin URL (avoids CORS/mixed-content concerns of pointing an
// <iframe> straight at BACKEND_URL, and keeps the backend origin out of
// client-visible URLs — the BFF pattern used everywhere else in this app).
// No auth needed — GET /machine-report/* doesn't require it on the backend
// either (same as GET /report/latest).
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8002";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;

  let resp: Response;
  try {
    resp = await fetch(`${BACKEND_URL}/machine-report/${encodeURIComponent(id)}/pdf`, {
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "Gagal menghubungi backend." }, { status: 502 });
  }

  if (!resp.ok) {
    if (resp.status === 404) {
      return Response.json({ error: "Laporan tidak ditemukan." }, { status: 404 });
    }
    return Response.json(
      { error: `Gagal memuat PDF (${resp.status})` },
      { status: resp.status },
    );
  }

  // Buffered (not streamed) — these PDFs are small (tens of KB), and
  // buffering avoids relying on duplex-streaming Response bodies through a
  // Route Handler, which has been unreliable in local testing.
  const buffer = await resp.arrayBuffer();

  // Always `inline`, regardless of what the backend sent — this route backs
  // an <iframe> PDF viewer (Machine Report page), and an `attachment`
  // disposition here would force a download on every page load/report
  // selection instead of rendering in place.
  return new Response(buffer, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": "inline",
    },
  });
}
