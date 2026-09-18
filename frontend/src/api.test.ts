import { describe, it, expect, vi, beforeEach } from "vitest";
import { login, lease, submit, imageUrl, isLeased, listDatasets } from "./api";

function mockFetchOnce(body: unknown) {
  (globalThis.fetch as unknown) = vi.fn().mockResolvedValue({
    ok: true, json: async () => body,
  });
}

describe("api", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("login posts username and returns user", async () => {
    mockFetchOnce({ user_id: 7, username: "alice" });
    const r = await login("alice");
    expect(r.user_id).toBe(7);
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/login", expect.objectContaining({ method: "POST" }));
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(call.body)).toEqual({ username: "alice" });
  });

  it("lease returns payload and isLeased narrows it", async () => {
    mockFetchOnce({ stem: "100", width: 640, height: 640, instances: [], lease_id: 3 });
    const r = await lease("people-v3", "model", 7);
    expect(isLeased(r)).toBe(true);
    if (isLeased(r)) expect(r.lease_id).toBe(3);
  });

  it("lease empty pool returns {stem:null}", async () => {
    mockFetchOnce({ stem: null });
    const r = await lease("people-v3", "all", 7);
    expect(isLeased(r)).toBe(false);
  });

  it("submit posts the action and returns next", async () => {
    mockFetchOnce({ next: null });
    const r = await submit({ dataset: "people-v3", stem: "100", task: "model", user_id: 7, action: "keep" });
    expect(r.next).toBeNull();
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(call.body).action).toBe("keep");
  });

  it("imageUrl builds the path", () => {
    expect(imageUrl("people-v3", "100")).toBe("/api/image/100?dataset=people-v3");
  });

  it("listModels GETs /api/models", async () => {
    mockFetchOnce([{ name: "best.pt", path: "best.pt" }]);
    const { listModels } = await import("./api");
    const r = await listModels();
    expect(r[0].path).toBe("best.pt");
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/models");
  });

  it("getPred passes the model and returns [] on error", async () => {
    (globalThis.fetch as unknown) = vi.fn().mockResolvedValue({ ok: false });
    const { getPred } = await import("./api");
    expect(await getPred("people-v3", "100", "best.pt")).toEqual([]);
  });

  it("getPred returns [] without calling fetch when model is empty", async () => {
    const fetchSpy = vi.fn();
    (globalThis.fetch as unknown) = fetchSpy;
    const { getPred } = await import("./api");
    expect(await getPred("people-v3", "100", "")).toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("startJob posts dataset+type+params", async () => {
    mockFetchOnce({ id: 1, status: "queued" });
    const { startJob } = await import("./api");
    await startJob("people-v3", "oracle", { model: "m.pt" });
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(call.body)).toEqual({ dataset: "people-v3", type: "oracle", params: { model: "m.pt" } });
  });

  it("dedupResolve posts the pair and action", async () => {
    mockFetchOnce({ ok: true });
    const { dedupResolve } = await import("./api");
    await dedupResolve(5, "delete");
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(call.body)).toEqual({ pair_id: 5, action: "delete" });
  });

  it("sends the dataset when leasing", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ stem: null }) });
    vi.stubGlobal("fetch", fetchMock);
    await lease("people-v3", "all", 1);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ dataset: "people-v3", task: "all", user_id: 1 });
  });

  it("puts the dataset in the image url", () => {
    expect(imageUrl("people-v3", "100")).toBe("/api/image/100?dataset=people-v3");
  });

  it("lists datasets", async () => {
    const rows = [{ name: "people-v3", repo: null, revision: "main", local: true, ready: true, size_bytes: 4 }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => rows }));
    await expect(listDatasets()).resolves.toEqual(rows);
  });
});
