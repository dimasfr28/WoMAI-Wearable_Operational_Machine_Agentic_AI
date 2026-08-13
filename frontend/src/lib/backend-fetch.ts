import "server-only";
import { redirect } from "next/navigation";
import { clearSessionCookie, requireSession } from "@/lib/auth/session";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8002";

/**
 * fetch() ke backend comfest-18 dengan header Authorization Bearer dari sesi
 * aktif. 401 (token invalid/kadaluarsa) -> hapus cookie sesi & redirect ke
 * /login. 403 (role kurang) -> lempar Error dengan pesan jelas untuk
 * ditampilkan sebagai toast. Response non-2xx lain dikembalikan apa adanya —
 * pemanggil yang menentukan pesan error spesifik per endpoint.
 */
export async function backendFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = await requireSession();
  const resp = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });

  if (resp.status === 401) {
    await clearSessionCookie();
    redirect("/login");
  }
  if (resp.status === 403) {
    throw new Error("Aksi ini butuh role engineer atau lebih tinggi.");
  }
  return resp;
}
