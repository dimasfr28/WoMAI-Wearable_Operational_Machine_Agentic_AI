import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";

// Rute yang boleh diakses tanpa login.
const PUBLIC_PATHS = ["/login", "/register"];

function isPublic(pathname: string): boolean {
  if (pathname === "/") return true;
  return PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );
}

/**
 * Cek keberadaan cookie sesi JWT comfest-18 pada setiap request dan lindungi
 * rute privat. TIDAK memverifikasi signature/expiry di sini — itu terjadi di
 * backend comfest-18 saat Server Action lain memanggil REST API dengan token
 * ini; token invalid/kadaluarsa ditangani lewat redirect di masing-masing
 * action, bukan di sini.
 */
export function middleware(request: NextRequest): NextResponse {
  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  const { pathname } = request.nextUrl;

  if (!hasSession && !isPublic(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (hasSession && (pathname === "/login" || pathname === "/register")) {
    const url = request.nextUrl.clone();
    url.pathname = "/chat";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|manifest.webmanifest|icons|sw.js|offline|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
