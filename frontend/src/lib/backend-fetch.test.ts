import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();

vi.mock("server-only", () => ({}));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      cookieStore.has(name) ? { name, value: cookieStore.get(name)! } : undefined,
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

import { backendFetch } from "./backend-fetch";

describe("backendFetch", () => {
  beforeEach(() => {
    cookieStore.clear();
    cookieStore.set("womai_session", "tok123");
    vi.restoreAllMocks();
  });

  it("attaches the Authorization header from the session cookie", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await backendFetch("/machines");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/machines"),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
      }),
    );
  });

  it("clears the session cookie and redirects to /login on 401", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 401 })),
    );
    await expect(backendFetch("/machines")).rejects.toThrow("REDIRECT:/login");
    expect(cookieStore.has("womai_session")).toBe(false);
  });

  it("throws a role-specific message on 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 403 })),
    );
    await expect(backendFetch("/machines")).rejects.toThrow(
      "This action requires an engineer role or higher.",
    );
  });

  it("returns the response unchanged for other statuses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 404 })),
    );
    const resp = await backendFetch("/machines/x");
    expect(resp.status).toBe(404);
  });
});
