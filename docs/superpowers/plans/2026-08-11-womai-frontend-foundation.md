# WO.M.AI Frontend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `comfest-18`'s Vite/JSX frontend with a port of `wo_m_ai/frontend` (Next.js 16, TypeScript, Bun), wired to the existing `comfest-18` JWT backend for real auth, with dummy in-memory data everywhere else.

**Architecture:** Next.js App Router runs as its own server (no more Nginx). All backend calls happen server-side (Server Actions) — the browser never talks to `comfest-18`'s FastAPI backend directly (BFF pattern). Auth uses an httpOnly cookie holding the raw JWT from `POST /auth/login`; `middleware.ts` only checks the cookie's presence, real validation happens in the backend on each Server Action call.

**Tech Stack:** Next.js 16 (App Router), TypeScript, Bun, Tailwind CSS v4, shadcn/ui, Vitest.

## Global Constraints

- Package manager/runtime: Bun (not npm) — `bun install`, `bun run dev`, `bun run build`, `bun run test`.
- BFF pattern: every call to the `comfest-18` backend happens in a Server Action / Route Handler, never from a Client Component via `fetch`.
- Auth token storage: httpOnly cookie only. No `JWT_SECRET` in the frontend, no client-side token access.
- `middleware.ts` verifies cookie *presence* only — never decodes/verifies the JWT.
- UI language: Indonesian (matches both source projects).
- No persistence for machines/SOP/chat-session data in this plan — in-memory only, resets on server restart. Real persistence is a separate, later migration (not part of this plan).
- Existing `comfest-18/backend/` is **not modified** anywhere in this plan — every task touches only `frontend/`, `docker-compose.yml`, and root `CLAUDE.md`.

---

### Task 1: Replace Vite frontend with a verbatim `wo_m_ai` frontend copy

**Files:**
- Delete: `frontend/src/App.jsx`, `frontend/src/main.jsx`, `frontend/src/index.css`, `frontend/src/api/`, `frontend/src/components/MachineContext.jsx`, `frontend/src/pages/`, `frontend/vite.config.js`, `frontend/index.html`, `frontend/nginx.conf`, `frontend/package-lock.json`, `frontend/Dockerfile`, `frontend/.dockerignore`, `frontend/package.json`
- Create: entire `frontend/` tree copied verbatim from `../wo_m_ai/frontend/` (adjust the source path below if your local checkout of `wo_m_ai` lives elsewhere), minus `frontend/README.md` (generic `create-next-app` boilerplate, no project-specific content worth keeping)

**Interfaces:**
- Produces: a working, self-consistent copy of the `wo_m_ai` Next.js app at `comfest-18/frontend/` — still using Supabase Auth and Drizzle internally at the end of this task (that gets replaced in Tasks 2–3). This is a deliberate checkpoint: verifying the *copy mechanics* succeeded, independent of the *rewrite* work that follows.

- [ ] **Step 1: Remove the old Vite frontend from git**

```bash
git rm -r frontend
```

- [ ] **Step 2: Copy `wo_m_ai/frontend` into `comfest-18/frontend`**

```bash
cp -r ../wo_m_ai/frontend frontend
rm -rf frontend/node_modules frontend/.next frontend/tsconfig.tsbuildinfo frontend/README.md
```

- [ ] **Step 3: Verify the copy landed correctly**

Run: `ls frontend`
Expected: `src`, `public`, `package.json`, `bun.lock`, `Dockerfile`, `next.config.ts`, `tsconfig.json`, `vitest.config.ts`, `CLAUDE.md`, `AGENTS.md`, `components.json`, `postcss.config.mjs`, `eslint.config.mjs`, `.gitignore`, `.dockerignore` — and **no** `vite.config.js`, `index.html`, `nginx.conf`, `package-lock.json`.

- [ ] **Step 4: Install dependencies**

Run: `cd frontend && bun install`
Expected: completes without error (this is still the original `wo_m_ai` dependency set, including `drizzle-orm` and `@supabase/*` — those get removed in Task 3).

- [ ] **Step 5: Typecheck as a baseline sanity check**

Run: `cd frontend && bunx tsc --noEmit`
Expected: passes. This confirms the copy is self-consistent (it's verbatim working code from `wo_m_ai`) before any rewriting begins.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "chore: replace Vite frontend with verbatim wo_m_ai Next.js copy"
```

---

### Task 2: Add comfest-18 JWT session helpers and auth flows

**Files:**
- Create: `frontend/src/lib/auth/constants.ts`
- Create: `frontend/src/lib/auth/session.ts`
- Create: `frontend/src/lib/auth/session.test.ts`
- Modify: `frontend/src/app/actions/auth.ts` (full rewrite)
- Create: `frontend/src/app/actions/auth.test.ts`
- Modify: `frontend/src/middleware.ts` (full rewrite)
- Modify: `frontend/src/app/login/page.tsx` (full rewrite)
- Create: `frontend/src/app/register/page.tsx`

**Interfaces:**
- Consumes: `comfest-18` backend contract — `POST /auth/login` `{username, password}` → `200 {access_token, token_type}` | `401/403 {detail}`; `POST /auth/register` `{username, email, password, full_name?, role}` → `201 UserOut` | `403/409/400 {detail}` (see `backend/app/api/routes_auth.py`, `backend/app/schemas/auth.py` — unchanged by this plan).
- Produces (used by Task 3 and by `src/components/app-sidebar.tsx`, unchanged): `requireSession(): Promise<string>` from `src/lib/auth/session.ts` — resolves to the JWT string, or throws `Error("UNAUTHENTICATED")` if no session cookie is set. Also produces `signOutAction(): Promise<void>` in `src/app/actions/auth.ts`, matching the name already imported by `src/components/app-sidebar.tsx` (no edit needed there).
- Note: `frontend/src/lib/supabase/` is **not deleted in this task** — `src/app/actions/machines.ts`, `sop.ts`, and `sessions.ts` still import `requireUser` from it until Task 3 rewrites them. Deleting it here would break the typecheck for files this task doesn't touch. It gets deleted in Task 3, once nothing references it anymore.

- [ ] **Step 1: Create the session cookie name constant**

`frontend/src/lib/auth/constants.ts`:
```ts
export const SESSION_COOKIE_NAME = "womai_session";
```

- [ ] **Step 2: Write the failing test for the session helpers**

`frontend/src/lib/auth/session.test.ts`:
```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      store.has(name) ? { name, value: store.get(name)! } : undefined,
    set: (name: string, value: string) => {
      store.set(name, value);
    },
    delete: (name: string) => {
      store.delete(name);
    },
  }),
}));

import {
  clearSessionCookie,
  getSessionToken,
  requireSession,
  setSessionCookie,
} from "./session";

describe("session cookie helpers", () => {
  beforeEach(() => {
    store.clear();
  });

  it("returns null when no cookie is set", async () => {
    expect(await getSessionToken()).toBeNull();
  });

  it("stores and retrieves the token after setSessionCookie", async () => {
    await setSessionCookie("abc.def.ghi");
    expect(await getSessionToken()).toBe("abc.def.ghi");
  });

  it("clears the token after clearSessionCookie", async () => {
    await setSessionCookie("abc.def.ghi");
    await clearSessionCookie();
    expect(await getSessionToken()).toBeNull();
  });

  it("requireSession returns the token when present", async () => {
    await setSessionCookie("xyz");
    await expect(requireSession()).resolves.toBe("xyz");
  });

  it("requireSession throws when no token is present", async () => {
    await expect(requireSession()).rejects.toThrow("UNAUTHENTICATED");
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && bun run test session.test.ts`
Expected: FAIL — `./session` module not found (it doesn't exist yet).

- [ ] **Step 4: Implement the session helpers**

`frontend/src/lib/auth/session.ts`:
```ts
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && bun run test session.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 6: Write the failing test for the auth Server Actions**

`frontend/src/app/actions/auth.test.ts`:
```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      cookieStore.has(name)
        ? { name, value: cookieStore.get(name)! }
        : undefined,
    set: (name: string, value: string) => {
      cookieStore.set(name, value);
    },
    delete: (name: string) => {
      cookieStore.delete(name);
    },
  }),
}));

vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    throw new Error(`REDIRECT:${path}`);
  },
}));

import { loginAction, registerAction, signOutAction } from "./auth";

function formData(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [key, value] of Object.entries(fields)) fd.set(key, value);
  return fd;
}

describe("loginAction", () => {
  beforeEach(() => {
    cookieStore.clear();
    vi.restoreAllMocks();
  });

  it("returns an error message on wrong credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "Username atau password salah" }),
          { status: 401 },
        ),
      ),
    );
    const result = await loginAction(
      {},
      formData({ username: "budi", password: "salah" }),
    );
    expect(result.error).toBe("Username atau password salah");
  });

  it("sets the session cookie and redirects to next on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ access_token: "tok123", token_type: "bearer" }),
          { status: 200 },
        ),
      ),
    );
    await expect(
      loginAction(
        {},
        formData({ username: "budi", password: "benar", next: "/mesin" }),
      ),
    ).rejects.toThrow("REDIRECT:/mesin");
    expect(cookieStore.get("womai_session")).toBe("tok123");
  });

  it("falls back to /chat when next is not a safe relative path", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ access_token: "tok123" }), {
          status: 200,
        }),
      ),
    );
    await expect(
      loginAction(
        {},
        formData({
          username: "budi",
          password: "benar",
          next: "//evil.example.com",
        }),
      ),
    ).rejects.toThrow("REDIRECT:/chat");
  });

  it("returns a network error message when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    const result = await loginAction(
      {},
      formData({ username: "budi", password: "benar" }),
    );
    expect(result.error).toBe("Server tidak terjangkau, coba lagi.");
  });
});

describe("registerAction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns an escalation message when public registration is closed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 403 })),
    );
    const result = await registerAction(
      {},
      formData({
        username: "budi",
        email: "budi@pabrik.co.id",
        password: "rahasia123",
      }),
    );
    expect(result.error).toBe("Registrasi publik ditutup, hubungi admin.");
  });

  it("redirects to /login?registered=1 on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ id: "1" }), { status: 201 }),
      ),
    );
    await expect(
      registerAction(
        {},
        formData({
          username: "budi",
          email: "budi@pabrik.co.id",
          password: "rahasia123",
        }),
      ),
    ).rejects.toThrow("REDIRECT:/login?registered=1");
  });
});

describe("signOutAction", () => {
  it("clears the cookie and redirects to /login", async () => {
    cookieStore.set("womai_session", "tok123");
    await expect(signOutAction()).rejects.toThrow("REDIRECT:/login");
    expect(cookieStore.has("womai_session")).toBe(false);
  });
});
```

- [ ] **Step 7: Run the test to verify it fails**

Run: `cd frontend && bun run test app/actions/auth.test.ts`
Expected: FAIL — `loginAction`/`registerAction` are not exported by the current (Supabase-based) `./auth`.

- [ ] **Step 8: Rewrite the auth Server Actions**

`frontend/src/app/actions/auth.ts`:
```ts
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
```

- [ ] **Step 9: Run the test to verify it passes**

Run: `cd frontend && bun run test app/actions/auth.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 10: Rewrite the middleware**

`frontend/src/middleware.ts`:
```ts
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
```

- [ ] **Step 11: Rewrite the login page**

`frontend/src/app/login/page.tsx`:
```tsx
"use client";

import { Suspense, useActionState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { loginAction, type AuthActionState } from "@/app/actions/auth";

const initialState: AuthActionState = {};

function LoginForm() {
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/chat";
  const justRegistered = searchParams.get("registered") === "1";
  const [state, formAction, pending] = useActionState(
    loginAction,
    initialState,
  );

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="font-heading">Masuk ke WO.M.AI</CardTitle>
          <CardDescription>
            {justRegistered
              ? "Akun dibuat, silakan masuk."
              : "Masuk untuk mengakses mesin & riwayat percakapan."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={formAction} className="flex flex-col gap-4">
            <input type="hidden" name="next" value={next} />
            <div className="flex flex-col gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                placeholder="nama.pengguna"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Kata sandi</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Kata sandi"
                required
              />
            </div>
            {state.error && (
              <p className="text-sm text-destructive">{state.error}</p>
            )}
            <Button type="submit" disabled={pending}>
              {pending ? "Memproses…" : "Masuk"}
            </Button>
          </form>
          <Link
            href="/register"
            className="mt-4 block w-full text-center text-sm text-muted-foreground hover:text-foreground"
          >
            Belum punya akun? Daftar
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
```

- [ ] **Step 12: Create the register page**

`frontend/src/app/register/page.tsx`:
```tsx
"use client";

import { useActionState } from "react";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { registerAction, type AuthActionState } from "@/app/actions/auth";

const initialState: AuthActionState = {};

export default function RegisterPage() {
  const [state, formAction, pending] = useActionState(
    registerAction,
    initialState,
  );

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="font-heading">Buat akun WO.M.AI</CardTitle>
          <CardDescription>
            Daftar untuk mulai memakai WO.M.AI. Registrasi publik hanya
            terbuka sebelum akun pertama dibuat.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form action={formAction} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="nama@pabrik.co.id"
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="full_name">Nama lengkap (opsional)</Label>
              <Input id="full_name" name="full_name" type="text" autoComplete="name" />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Kata sandi</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                placeholder="Minimal 6 karakter"
                required
                minLength={6}
              />
            </div>
            {state.error && (
              <p className="text-sm text-destructive">{state.error}</p>
            )}
            <Button type="submit" disabled={pending}>
              {pending ? "Memproses…" : "Daftar"}
            </Button>
          </form>
          <Link
            href="/login"
            className="mt-4 block w-full text-center text-sm text-muted-foreground hover:text-foreground"
          >
            Sudah punya akun? Masuk
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 13: Run the full test suite**

Run: `cd frontend && bun run test`
Expected: PASS for `lib/auth/session.test.ts`, `app/actions/auth.test.ts`, and all pre-existing tests (`lib/format.test.ts`, `lib/title.test.ts`, `lib/mock/scenarios.test.ts`).

Also run: `cd frontend && bunx tsc --noEmit`
Expected: passes with zero errors. This task didn't delete `lib/supabase/` or `lib/db/`, so `app/actions/machines.ts`, `sop.ts`, and `sessions.ts` (untouched, still copied from Task 1) still resolve their imports fine — the repo typechecks cleanly already at this point, even though the Drizzle/Supabase code they depend on is about to be deleted in Task 3.

- [ ] **Step 14: Commit**

```bash
git add frontend/src/lib/auth frontend/src/app/actions/auth.ts frontend/src/app/actions/auth.test.ts frontend/src/middleware.ts frontend/src/app/login/page.tsx frontend/src/app/register/page.tsx
git commit -m "feat(frontend): replace Supabase Auth with comfest-18 JWT auth"
```

---

### Task 3: Replace the Drizzle data layer with in-memory dummy stores

**Files:**
- Delete: `frontend/src/lib/db/`, `frontend/drizzle/`, `frontend/drizzle.config.ts`, `frontend/src/lib/supabase/`
- Modify: `frontend/src/app/actions/machines.ts` (full rewrite)
- Modify: `frontend/src/app/actions/sop.ts` (full rewrite)
- Modify: `frontend/src/app/actions/sessions.ts` (full rewrite)
- Modify: `frontend/src/app/(app)/mesin/page.tsx:37-44` (add demo notice)
- Modify: `frontend/src/app/(app)/sop/page.tsx:32-43` (add demo notice)
- Modify: `frontend/package.json` (prune dependencies, rename package)

**Interfaces:**
- Consumes: `requireSession()` from `frontend/src/lib/auth/session.ts` (Task 2); `Machine`, `Sop`, `SopMode`, `SopStep`, `ChatSession` types from `frontend/src/lib/types.ts` (untouched).
- Produces: same exported function names/signatures as the original Drizzle-backed actions, so `frontend/src/lib/machines.ts`, `frontend/src/lib/sops.ts`, `frontend/src/lib/storage.ts`, and every hook/component that calls them need **zero changes**: `loadMachinesAction(): Promise<Machine[]>`, `getMachineAction(id: string): Promise<Machine | null>`, `saveMachineAction(input): Promise<Machine>`, `deleteMachineAction(id: string): Promise<void>`, `loadSopsAction(): Promise<Sop[]>`, `saveSopAction(input): Promise<Sop>`, `deleteSopAction(id: string): Promise<void>`, `loadSessionsAction(): Promise<ChatSession[]>`, `getSessionAction(id: string): Promise<ChatSession | null>`, `saveSessionAction(session: ChatSession): Promise<void>`, `deleteSessionAction(id: string): Promise<void>`, `clearSessionsAction(): Promise<void>`.

- [ ] **Step 1: Delete the Drizzle and Supabase layers**

```bash
cd frontend
rm -rf src/lib/db drizzle drizzle.config.ts src/lib/supabase
```

- [ ] **Step 2: Rewrite the machines Server Actions**

`frontend/src/app/actions/machines.ts`:
```ts
"use server";

import { randomUUID } from "node:crypto";
import { requireSession } from "@/lib/auth/session";
import type { Machine } from "@/lib/types";

// Data contoh in-memory untuk fondasi migrasi frontend WO.M.AI — TIDAK
// persisten (reset saat server Next.js restart). Diganti pemanggilan REST
// API comfest-18 (mis. GET/POST/PATCH/DELETE /machines) di sub-project
// berikutnya (lihat docs/superpowers/specs/2026-08-11-womai-frontend-foundation-design.md).
let machinesStore: Machine[] = [
  {
    id: "m-demo-1",
    name: "CNC Mill 01",
    type: "M",
    line: "Line A",
    createdAt: new Date().toISOString(),
  },
  {
    id: "m-demo-2",
    name: "CNC Lathe 02",
    type: "H",
    line: "Line B",
    notes: "Overhaul terakhir bulan lalu",
    createdAt: new Date().toISOString(),
  },
];

export async function loadMachinesAction(): Promise<Machine[]> {
  await requireSession();
  return machinesStore;
}

export async function getMachineAction(id: string): Promise<Machine | null> {
  await requireSession();
  return machinesStore.find((m) => m.id === id) ?? null;
}

export async function saveMachineAction(input: {
  id?: string;
  name: string;
  type: Machine["type"];
  line?: string;
  notes?: string;
}): Promise<Machine> {
  await requireSession();

  if (input.id) {
    const idx = machinesStore.findIndex((m) => m.id === input.id);
    if (idx >= 0) {
      const updated: Machine = {
        ...machinesStore[idx],
        ...input,
        id: input.id,
      };
      machinesStore = [
        ...machinesStore.slice(0, idx),
        updated,
        ...machinesStore.slice(idx + 1),
      ];
      return updated;
    }
  }

  const machine: Machine = {
    id: input.id ?? randomUUID(),
    name: input.name,
    type: input.type,
    line: input.line,
    notes: input.notes,
    createdAt: new Date().toISOString(),
  };
  machinesStore = [...machinesStore, machine];
  return machine;
}

export async function deleteMachineAction(id: string): Promise<void> {
  await requireSession();
  machinesStore = machinesStore.filter((m) => m.id !== id);
}
```

- [ ] **Step 3: Rewrite the SOP Server Actions**

`frontend/src/app/actions/sop.ts`:
```ts
"use server";

import { randomUUID } from "node:crypto";
import { requireSession } from "@/lib/auth/session";
import type { Sop, SopMode, SopStep } from "@/lib/types";

// Data contoh in-memory — lihat catatan yang sama di actions/machines.ts.
// Isi diadaptasi dari knowledge base SOP nyata comfest-18/wo_m_ai backend.
let sopsStore: Sop[] = [
  {
    id: "sop-demo-hdf",
    mode: "HDF",
    title: "Penanganan Heat Dissipation Failure",
    symptoms:
      "suhu proses tinggi, selisih suhu udara-proses menyempit, mesin terasa panas, overheat",
    body:
      "Heat Dissipation Failure terjadi ketika perbedaan suhu udara dan proses turun di bawah 8.6 K pada kecepatan putar rendah, sehingga panas tidak terbuang.",
    steps: [
      {
        id: "hdf-1",
        text: "Turunkan beban mesin ke <=50% dan pantau tren suhu proses",
        priority: "segera",
        estimatedMinutes: 10,
      },
      {
        id: "hdf-2",
        text: "Periksa dan bersihkan sistem pendingin (kipas, heatsink, saluran udara)",
        priority: "segera",
        estimatedMinutes: 15,
      },
      {
        id: "hdf-3",
        text: "Inspeksi termal menyeluruh pada bearing dan gearbox",
        priority: "terjadwal",
        estimatedMinutes: 45,
      },
    ],
    reference: "SOP Maintenance Termal - Rev.2",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
  {
    id: "sop-demo-osf",
    mode: "OSF",
    title: "Penanganan Overstrain Failure",
    symptoms:
      "torsi tinggi, beban berat, tool wear menumpuk, mesin terasa berat, overstrain",
    body:
      "Overstrain Failure terjadi saat hasil kali tool wear dan torque melewati ambang aman material.",
    steps: [
      {
        id: "osf-1",
        text: "Kurangi torsi operasi di bawah ambang aman tipe material",
        priority: "segera",
        estimatedMinutes: 5,
      },
      {
        id: "osf-2",
        text: "Inspeksi visual tool dan komponen transmisi dari deformasi",
        priority: "segera",
        estimatedMinutes: 20,
      },
      {
        id: "osf-3",
        text: "Ganti tool bila tool wear melebihi 200 menit",
        priority: "terjadwal",
        estimatedMinutes: 30,
      },
    ],
    reference: "SOP Beban & Transmisi - Rev.1",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  },
];

export async function loadSopsAction(): Promise<Sop[]> {
  await requireSession();
  return sopsStore;
}

export async function saveSopAction(input: {
  id?: string;
  mode: SopMode;
  title: string;
  symptoms: string;
  body: string;
  steps: SopStep[];
  reference: string;
}): Promise<Sop> {
  await requireSession();
  const now = new Date().toISOString();

  if (input.id) {
    const idx = sopsStore.findIndex((s) => s.id === input.id);
    if (idx >= 0) {
      const updated: Sop = {
        ...sopsStore[idx],
        ...input,
        id: input.id,
        updatedAt: now,
      };
      sopsStore = [
        ...sopsStore.slice(0, idx),
        updated,
        ...sopsStore.slice(idx + 1),
      ];
      return updated;
    }
  }

  const sop: Sop = {
    id: input.id ?? randomUUID(),
    mode: input.mode,
    title: input.title,
    symptoms: input.symptoms,
    body: input.body,
    steps: input.steps,
    reference: input.reference,
    createdAt: now,
    updatedAt: now,
  };
  sopsStore = [...sopsStore, sop];
  return sop;
}

export async function deleteSopAction(id: string): Promise<void> {
  await requireSession();
  sopsStore = sopsStore.filter((s) => s.id !== id);
}
```

- [ ] **Step 4: Rewrite the chat session Server Actions**

`frontend/src/app/actions/sessions.ts`:
```ts
"use server";

import { requireSession } from "@/lib/auth/session";
import type { ChatSession } from "@/lib/types";

// Data contoh in-memory — lihat catatan yang sama di actions/machines.ts.
// Kosong di awal: riwayat percakapan wajar dimulai kosong untuk user baru.
let sessionsStore: ChatSession[] = [];

export async function loadSessionsAction(): Promise<ChatSession[]> {
  await requireSession();
  return sessionsStore;
}

export async function getSessionAction(
  id: string,
): Promise<ChatSession | null> {
  await requireSession();
  return sessionsStore.find((s) => s.id === id) ?? null;
}

export async function saveSessionAction(session: ChatSession): Promise<void> {
  await requireSession();
  const idx = sessionsStore.findIndex((s) => s.id === session.id);
  if (idx >= 0) {
    sessionsStore = [
      ...sessionsStore.slice(0, idx),
      session,
      ...sessionsStore.slice(idx + 1),
    ];
  } else {
    sessionsStore = [...sessionsStore, session];
  }
}

export async function deleteSessionAction(id: string): Promise<void> {
  await requireSession();
  sessionsStore = sessionsStore.filter((s) => s.id !== id);
}

export async function clearSessionsAction(): Promise<void> {
  await requireSession();
  sessionsStore = [];
}
```

- [ ] **Step 5: Add a demo-mode notice to the Mesin page**

In `frontend/src/app/(app)/mesin/page.tsx`, find this block (around line 38-44):
```tsx
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Mesin</h1>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah Mesin
        </Button>
      </div>
```
Replace it with:
```tsx
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-xl font-semibold">Mesin</h1>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah Mesin
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Mode demo: perubahan data mesin di halaman ini belum tersimpan
        permanen.
      </p>
```

- [ ] **Step 6: Add a demo-mode notice to the SOP page**

In `frontend/src/app/(app)/sop/page.tsx`, find this block (around line 32-43):
```tsx
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-xl font-semibold">SOP File</h1>
          <p className="text-muted-foreground text-sm">
            Knowledge base tindakan yang dipakai chatbot untuk merekomendasikan
            penanganan.
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah SOP
        </Button>
      </div>
```
Replace it with:
```tsx
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <h1 className="text-xl font-semibold">SOP File</h1>
          <p className="text-muted-foreground text-sm">
            Knowledge base tindakan yang dipakai chatbot untuk merekomendasikan
            penanganan.
          </p>
          <p className="text-xs text-muted-foreground">
            Mode demo: perubahan SOP di halaman ini belum tersimpan permanen.
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          Tambah SOP
        </Button>
      </div>
```

- [ ] **Step 7: Prune `package.json`**

`frontend/package.json`:
```json
{
  "name": "comfest-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint",
    "test": "vitest run --passWithNoTests",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@ai-sdk/react": "^4.0.17",
    "@base-ui/react": "^1.6.0",
    "ai": "^7.0.16",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^1.23.0",
    "next": "16.2.10",
    "next-themes": "^0.4.6",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "react-markdown": "^10.1.0",
    "remark-gfm": "^4.0.1",
    "server-only": "^0.0.1",
    "sonner": "^2.0.7",
    "tailwind-merge": "^3.6.0",
    "tw-animate-css": "^1.4.0"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "babel-plugin-react-compiler": "1.0.0",
    "eslint": "^9",
    "eslint-config-next": "16.2.10",
    "shadcn": "^4.13.0",
    "tailwindcss": "^4",
    "typescript": "^5",
    "vitest": "^4.1.10"
  }
}
```

- [ ] **Step 8: Regenerate the lockfile**

Run: `cd frontend && bun install`
Expected: completes without error; `bun.lock` no longer references `drizzle-orm`, `drizzle-kit`, `@supabase/ssr`, `@supabase/supabase-js`, or `postgres`.

- [ ] **Step 9: Typecheck after removing Drizzle/Supabase**

Run: `cd frontend && bunx tsc --noEmit`
Expected: passes with zero errors, confirming the deletions in Step 1 and the rewrites in Steps 2-4 didn't leave any dangling references to `@/lib/db` or `@/lib/supabase/*`.

- [ ] **Step 10: Lint**

Run: `cd frontend && bun run lint`
Expected: passes with zero errors.

- [ ] **Step 11: Build**

Run: `cd frontend && bun run build`
Expected: succeeds, produces `.next/standalone`.

- [ ] **Step 12: Run the full test suite**

Run: `cd frontend && bun run test`
Expected: PASS — `lib/format.test.ts`, `lib/title.test.ts`, `lib/mock/scenarios.test.ts`, `lib/auth/session.test.ts`, `app/actions/auth.test.ts` (16 tests total).

- [ ] **Step 13: Commit**

```bash
git add frontend
git commit -m "feat(frontend): replace Drizzle data layer with in-memory dummy stores"
```

---

### Task 4: Wire `docker-compose.yml` to the new frontend

**Files:**
- Modify: `docker-compose.yml` (frontend service block)

**Interfaces:**
- Consumes: `frontend/Dockerfile` from the Task 1 copy (already correct — Bun multi-stage `dev`/`runner`, `EXPOSE 3000`, no changes needed here).
- Produces: nothing consumed by other tasks — this is the last piece needed for `./up.sh` to build and run the new frontend.

- [ ] **Step 1: Update the frontend service**

In `docker-compose.yml`, find:
```yaml
  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: "http://localhost:8002"
    depends_on:
      - backend
    ports:
      - "3000:80"
```
Replace it with:
```yaml
  frontend:
    build:
      context: ./frontend
    depends_on:
      - backend
    environment:
      BACKEND_URL: "http://backend:8000"
    ports:
      - "3000:3000"
```

- [ ] **Step 2: Validate the compose file**

Run: `docker compose config --quiet`
Expected: exits with no output/errors (confirms valid YAML and service graph).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: point docker-compose frontend service at the new Next.js server"
```

---

### Task 5: Update root `CLAUDE.md` for the new frontend stack

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing code-level — documents the end state produced by Tasks 1–4.

- [ ] **Step 1: Update the Commands section**

Find:
```
**Frontend**, if iterating outside Docker (`cd frontend`): `npm install`, `npm run dev` (Vite dev server), `npm run build`.
```
Replace with:
```
**Frontend**, if iterating outside Docker (`cd frontend`): `bun install`, `bun run dev` (Next.js dev server on `:3000`), `bun run build`, `bun run test` (Vitest).
```

- [ ] **Step 2: Update the Frontend architecture section**

Find:
```
### Frontend (`frontend/src/`)

Plain React 18 + Vite SPA (no Redux/TanStack Query) talking to the backend over REST via `src/api/client.js`, using a JWT bearer token from `POST /auth/login`. `components/MachineContext.jsx` holds the currently selected machine as shared state. Pages: `LoginPage`, `MachineSelectPage`, `DashboardPage` (gauges, sensor charts via Recharts, AI Early Warning panel), `KnowledgebasePage` (PDF upload/list/delete), `ReportPage`.
```
Replace with:
```
### Frontend (`frontend/src/`)

Next.js 16 App Router (TypeScript, Tailwind v4, shadcn/ui, Bun), ported from the sibling `wo_m_ai` project — see `docs/superpowers/specs/2026-08-11-womai-frontend-foundation-design.md` for the full migration rationale. BFF pattern: every backend call happens server-side (Server Actions / Route Handlers under `src/app/actions/`), the browser never calls the FastAPI backend directly. Auth uses an httpOnly cookie holding the JWT from `POST /auth/login` (`src/lib/auth/session.ts`); `src/middleware.ts` only checks the cookie's presence, not its validity. Pages: `/login`, `/register`, `/chat` + `/chat/[id]` (chat UI, currently backed by mock scenarios in `src/lib/mock/` — no real `/chat` backend endpoint exists yet), `/mesin` and `/sop` (CRUD UI over in-memory dummy data, not yet persisted), `/riwayat` (chat history list). PWA-installable (`src/app/manifest.ts`, `public/sw.js`).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for the Next.js frontend"
```

---

### Task 6: Manual end-to-end verification

**Files:** none (verification only, no code changes).

**Interfaces:** none — this task exercises everything produced by Tasks 1–5 together.

- [ ] **Step 1: Start the stack**

Run: `./up.sh`
Expected: all services report healthy/running, including the rebuilt `frontend` service.

- [ ] **Step 2: Confirm a login-capable user exists**

If no user exists yet in the `comfest-18` database, create the bootstrap admin:
```bash
curl -X POST http://localhost:8002/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"changeme123","role":"admin"}'
```
Expected: `201` with a `UserOut` body (only works once, while the `users` table is empty — see `backend/app/api/routes_auth.py`).

- [ ] **Step 3: Verify unauthenticated redirect**

Open `http://localhost:3000/chat` in a browser without being logged in.
Expected: redirected to `http://localhost:3000/login?next=%2Fchat`.

- [ ] **Step 4: Verify login**

On the login page, submit the credentials created in Step 2.
Expected: redirected to `/chat`, sidebar with "Chat Baru / Mesin / SOP File / Riwayat" visible.

- [ ] **Step 5: Verify dummy data pages**

Navigate to `/mesin` — expect 2 demo machines ("CNC Mill 01", "CNC Lathe 02") and the "Mode demo" notice.
Navigate to `/sop` — expect 2 demo SOP entries (HDF, OSF) and the "Mode demo" notice.
Navigate to `/riwayat` — expect "Belum ada percakapan" (empty state).

- [ ] **Step 6: Verify logout and re-protection**

Click "Keluar" in the sidebar footer.
Expected: redirected to `/login`. Attempting to open `/mesin` directly afterward redirects back to `/login?next=%2Fmesin`.

- [ ] **Step 7: Verify register bootstrap-closed behavior**

Open `/register`, submit a new account.
Expected: form shows the inline error "Registrasi publik ditutup, hubungi admin." (since a user already exists from Step 2), confirming the frontend correctly surfaces the backend's real 403 behavior.
