import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-fetch", () => ({
  backendFetch: vi.fn(),
}));

import { backendFetch } from "@/lib/backend-fetch";
import { deleteSopAction, loadSopsAction, saveSopAction } from "./sop";

const mockedBackendFetch = vi.mocked(backendFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("loadSopsAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("maps snake_case steps to camelCase SopStep objects", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse([
        {
          id: "sop-1",
          title: "Penanganan Overheat",
          symptoms: "suhu tinggi",
          body: "deskripsi",
          steps: [
            {
              id: "s-1",
              text: "Turunkan beban",
              priority: "segera",
              estimated_minutes: 10,
            },
          ],
          reference: "Rev.1",
          created_at: "2026-08-01T00:00:00Z",
          updated_at: "2026-08-01T00:00:00Z",
        },
      ]),
    );
    const result = await loadSopsAction();
    expect(result[0].steps).toEqual([
      { id: "s-1", text: "Turunkan beban", priority: "segera", estimatedMinutes: 10 },
    ]);
  });

  it("throws when the backend responds with a non-ok status", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(loadSopsAction()).rejects.toThrow("Gagal memuat daftar SOP (500)");
  });
});

describe("saveSopAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("POSTs to /sops when creating and converts steps to snake_case in the request body", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "sop-2",
        title: "New SOP",
        symptoms: "",
        body: "",
        steps: [],
        reference: "",
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      }),
    );
    await saveSopAction({
      title: "New SOP",
      symptoms: "",
      body: "",
      reference: "",
      steps: [{ id: "s-1", text: "Step", priority: "segera", estimatedMinutes: 5 }],
    });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/sops",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "New SOP",
          symptoms: "",
          body: "",
          steps: [{ id: "s-1", text: "Step", priority: "segera", estimated_minutes: 5 }],
          reference: "",
        }),
      }),
    );
  });

  it("PATCHes to /sops/{id} when updating", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "sop-1",
        title: "Updated",
        symptoms: "",
        body: "",
        steps: [],
        reference: "",
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      }),
    );
    await saveSopAction({
      id: "sop-1",
      title: "Updated",
      symptoms: "",
      body: "",
      reference: "",
      steps: [],
    });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/sops/sop-1",
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});

describe("deleteSopAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("throws on non-ok response", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(deleteSopAction("sop-1")).rejects.toThrow(
      "Gagal menghapus SOP (500)",
    );
  });
});
