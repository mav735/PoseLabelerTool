import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewView } from "./ReviewView";
import * as api from "./api";
import type { LabelPayload } from "./types";

function payload(stem: string): LabelPayload & { lease_id: number } {
  return { stem, width: 640, height: 640, lease_id: 1, instances: [
    { cx: 0.5, cy: 0.5, w: 0.1, h: 0.2, kpts: Array.from({ length: 15 }, () => [0.5, 0.5, 2]) },
  ] };
}

describe("ReviewView", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("pressing k submits keep and advances to next", async () => {
    vi.spyOn(api, "submit").mockResolvedValue({ next: payload("200") });
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    const onExhausted = vi.fn();
    const user = userEvent.setup();

    render(<ReviewView user={{ user_id: 1, username: "b" }} task="model" first={payload("100")} onExhausted={onExhausted} />);
    const canvas = document.querySelector("canvas")!;
    canvas.focus();
    await user.keyboard("k");

    expect(api.submit).toHaveBeenCalledWith(expect.objectContaining({ stem: "100", action: "keep", task: "model" }));
    expect(await screen.findByText("200")).toBeInTheDocument();
  });

  it("exhausts the pool when next is null", async () => {
    vi.spyOn(api, "submit").mockResolvedValue({ next: null });
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    const onExhausted = vi.fn();
    const user = userEvent.setup();

    render(<ReviewView user={{ user_id: 1, username: "b" }} task="all" first={payload("100")} onExhausted={onExhausted} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("d");

    await vi.waitFor(() => expect(onExhausted).toHaveBeenCalled());
  });

  it("shows the GT count on the first image", async () => {
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    render(<ReviewView user={{ user_id: 1, username: "b" }} task="model" first={payload("100")} onExhausted={() => {}} />);
    expect(await screen.findByText("GT(1)")).toBeInTheDocument();
  });

  it("shows an error when submit rejects and stays put", async () => {
    vi.spyOn(api, "submit").mockRejectedValue(new Error("boom"));
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<ReviewView user={{ user_id: 1, username: "b" }} task="all" first={payload("100")} onExhausted={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("k");
    expect(await screen.findByText(/action failed/i)).toBeInTheDocument();
  });
});
