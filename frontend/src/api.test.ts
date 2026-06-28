import { describe, it, expect, vi, beforeEach } from "vitest";
import { login, lease, submit, imageUrl, isLeased } from "./api";

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
    const r = await lease("model", 7);
    expect(isLeased(r)).toBe(true);
    if (isLeased(r)) expect(r.lease_id).toBe(3);
  });

  it("lease empty pool returns {stem:null}", async () => {
    mockFetchOnce({ stem: null });
    const r = await lease("all", 7);
    expect(isLeased(r)).toBe(false);
  });

  it("submit posts the action and returns next", async () => {
    mockFetchOnce({ next: null });
    const r = await submit({ stem: "100", task: "model", user_id: 7, action: "keep" });
    expect(r.next).toBeNull();
    const call = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(JSON.parse(call.body).action).toBe("keep");
  });

  it("imageUrl builds the path", () => {
    expect(imageUrl("100")).toBe("/api/image/100");
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
    expect(await getPred("100", "best.pt")).toEqual([]);
  });

  it("getPred returns [] without calling fetch when model is empty", async () => {
    const fetchSpy = vi.fn();
    (globalThis.fetch as unknown) = fetchSpy;
    const { getPred } = await import("./api");
    expect(await getPred("100", "")).toEqual([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
