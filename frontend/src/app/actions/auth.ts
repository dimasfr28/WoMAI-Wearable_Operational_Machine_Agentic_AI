"use server";

import { redirect } from "next/navigation";
import { clearSessionCookie, setSessionCookie } from "@/lib/auth/session";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8002";

export interface AuthActionState {
  error?: string;
}

function safeNext(raw: FormDataEntryValue | null): string {
  const value = typeof raw === "string" ? raw : "";
  // Default setelah login: /mesin, bukan /chat — user wajib memilih mesin
  // dulu (rancangan.txt Section 2) sebelum mengakses fitur lain. `next` dari
  // middleware's redirect (mis. ?next=/machine-report) tetap dihormati kalau
  // ada, supaya deep-link yang sempat ditolak middleware balik ke tujuan asal
  // setelah login — bukan dipaksa ke /mesin lagi.
  return value.startsWith("/") && !value.startsWith("//") ? value : "/mesin";
}

export async function loginAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const username = String(formData.get("username") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  if (!username || !password) {
    return { error: "Username and password are required." };
  }

  let token: string;
  try {
    const resp = await fetch(`${BACKEND_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
      signal: AbortSignal.timeout(10_000),
    });
    if (resp.status === 401 || resp.status === 403) {
      const body = (await resp.json().catch(() => null)) as {
        detail?: string;
      } | null;
      return { error: body?.detail ?? "Incorrect username or password." };
    }
    if (!resp.ok) {
      return { error: "Server unreachable, try again." };
    }
    const data = (await resp.json()) as { access_token: string };
    token = data.access_token;
  } catch {
    return { error: "Server unreachable, try again." };
  }

  await setSessionCookie(token);
  redirect(next);
}

export async function registerAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const username = String(formData.get("username") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const fullName = String(formData.get("full_name") ?? "").trim();

  if (!username || !email || !password) {
    return { error: "Username, email, and password are required." };
  }

  try {
    const resp = await fetch(`${BACKEND_URL}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        email,
        password,
        full_name: fullName || undefined,
        role: "viewer",
      }),
      signal: AbortSignal.timeout(10_000),
    });
    if (resp.status === 403) {
      return { error: "Public registration is closed, contact an admin." };
    }
    if (resp.status === 409) {
      return { error: "Username or email is already registered." };
    }
    if (resp.status === 400) {
      const body = (await resp.json().catch(() => null)) as {
        detail?: string;
      } | null;
      return { error: body?.detail ?? "Registration data is invalid." };
    }
    if (!resp.ok) {
      return { error: "Server unreachable, try again." };
    }
  } catch {
    return { error: "Server unreachable, try again." };
  }

  redirect("/login?registered=1");
}

export async function signOutAction(): Promise<void> {
  await clearSessionCookie();
  redirect("/login");
}
