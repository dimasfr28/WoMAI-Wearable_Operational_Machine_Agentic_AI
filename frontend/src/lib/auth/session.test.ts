import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();

vi.mock("server-only", () => ({}));

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
