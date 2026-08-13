import "server-only";
import { cookies } from "next/headers";
import { SESSION_COOKIE_NAME } from "@/lib/auth/constants";

/** Simpan JWT comfest-18 ke httpOnly cookie setelah login berhasil. */
export async function setSessionCookie(token: string): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    // Selaras JWT_EXPIRE_MINUTES default backend comfest-18 (1440 menit = 24 jam).
    maxAge: 60 * 60 * 24,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE_NAME);
}

export async function getSessionToken(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE_NAME)?.value ?? null;
}

/**
 * Ambil token JWT dari cookie atau lempar. Dipakai Server Action yang wajib
 * login. Tidak memverifikasi signature/expiry — itu terjadi di backend
 * comfest-18 saat token ini dipakai memanggil REST API.
 */
export async function requireSession(): Promise<string> {
  const token = await getSessionToken();
  if (!token) throw new Error("UNAUTHENTICATED");
  return token;
}
