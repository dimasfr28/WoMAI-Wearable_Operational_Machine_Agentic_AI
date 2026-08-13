import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("@/lib/backend-fetch", () => ({
  backendFetch: vi.fn(),
}));

import { backendFetch } from "@/lib/backend-fetch";
import {
  deleteMachineAction,
  getMachineAction,
  loadMachinesAction,
  saveMachineAction,
} from "./machines";

const mockedBackendFetch = vi.mocked(backendFetch);

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("loadMachinesAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("maps snake_case backend fields to camelCase Machine objects", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse([
        {
          id: "m-1",
          name: "CNC Mill",
          machine_type: "Haas",
          status: "running",
          created_at: "2026-08-01T00:00:00Z",
          document_count: 2,
          run_count: 5,
        },
      ]),
    );
    const result = await loadMachinesAction();
    expect(result).toEqual([
      {
        id: "m-1",
        name: "CNC Mill",
        machineType: "Haas",
        status: "running",
        documentCount: 2,
        runCount: 5,
        createdAt: "2026-08-01T00:00:00Z",
      },
    ]);
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/machines",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("throws when the backend responds with a non-ok status", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 500));
    await expect(loadMachinesAction()).rejects.toThrow(
      "Gagal memuat daftar mesin (500)",
    );
  });
});

describe("getMachineAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("returns null on 404", async () => {
    mockedBackendFetch.mockResolvedValue(jsonResponse({}, 404));
    const result = await getMachineAction("missing");
    expect(result).toBeNull();
  });
});

describe("saveMachineAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("POSTs to /machines when creating (no id)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "m-2",
        name: "New Machine",
        machine_type: null,
        status: "running",
        created_at: "2026-08-01T00:00:00Z",
        document_count: 0,
        run_count: 0,
      }),
    );
    const result = await saveMachineAction({ name: "New Machine" });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/machines",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.machineType).toBeUndefined();
  });

  it("PATCHes to /machines/{id} when updating (id present)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse({
        id: "m-1",
        name: "Renamed",
        machine_type: "Haas",
        status: "running",
        created_at: "2026-08-01T00:00:00Z",
        document_count: 0,
        run_count: 0,
      }),
    );
    await saveMachineAction({ id: "m-1", name: "Renamed", machineType: "Haas" });
    expect(mockedBackendFetch).toHaveBeenCalledWith(
      "/machines/m-1",
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});

describe("deleteMachineAction", () => {
  beforeEach(() => {
    mockedBackendFetch.mockReset();
  });

  it("throws the backend's detail message on 409 (machine has related data)", async () => {
    mockedBackendFetch.mockResolvedValue(
      jsonResponse(
        {
          detail:
            "Mesin masih punya 2 dokumen dan 1 sensor run — hapus data terkait dulu.",
        },
        409,
      ),
    );
    await expect(deleteMachineAction("m-1")).rejects.toThrow(
      "Mesin masih punya 2 dokumen dan 1 sensor run — hapus data terkait dulu.",
    );
  });
});
