import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

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

  it("falls back to /mesin when next is not a safe relative path", async () => {
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
    ).rejects.toThrow("REDIRECT:/mesin");
  });

  it("returns a network error message when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    const result = await loginAction(
      {},
      formData({ username: "budi", password: "benar" }),
    );
    expect(result.error).toBe("Server unreachable, try again.");
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
    expect(result.error).toBe("Public registration is closed, contact an admin.");
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
