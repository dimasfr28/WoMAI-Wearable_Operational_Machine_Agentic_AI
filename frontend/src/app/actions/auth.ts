"use server";

import { redirect } from "next/navigation";
import { clearSessionCookie, setSessionCookie } from "@/lib/auth/session";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8002";

export interface AuthActionState {
  error?: string;
}

function safeNext(raw: FormDataEntryValue | null): string {
  const value = typeof raw === "string" ? raw : "";
  return value.startsWith("/") && !value.startsWith("//") ? value : "/chat";
}

export async function loginAction(
  _prevState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const username = String(formData.get("username") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  if (!username || !password) {
    return { error: "Username dan password wajib diisi." };
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
      return { error: body?.detail ?? "Username atau password salah." };
    }
    if (!resp.ok) {
      return { error: "Server tidak terjangkau, coba lagi." };
    }
    const data = (await resp.json()) as { access_token: string };
    token = data.access_token;
  } catch {
    return { error: "Server tidak terjangkau, coba lagi." };
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
    return { error: "Username, email, dan password wajib diisi." };
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
      return { error: "Registrasi publik ditutup, hubungi admin." };
    }
    if (resp.status === 409) {
      return { error: "Username atau email sudah terdaftar." };
    }
    if (resp.status === 400) {
      const body = (await resp.json().catch(() => null)) as {
        detail?: string;
      } | null;
      return { error: body?.detail ?? "Data pendaftaran tidak valid." };
    }
    if (!resp.ok) {
      return { error: "Server tidak terjangkau, coba lagi." };
    }
  } catch {
    return { error: "Server tidak terjangkau, coba lagi." };
  }

  redirect("/login?registered=1");
}

export async function signOutAction(): Promise<void> {
  await clearSessionCookie();
  redirect("/login");
}
