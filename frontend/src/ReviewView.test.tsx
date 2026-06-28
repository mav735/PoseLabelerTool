import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReviewView } from "./ReviewView";
import * as api from "./api";
import type { LabelPayload } from "./types";

function payload(stem: string): LabelPayload & { lease_id: number } {
  return {
    stem,
    width: 640,
    height: 640,
    lease_id: 1,
    instances: [
      { cx: 0.5, cy: 0.5, w: 0.1, h: 0.2, kpts: Array.from({ length: 15 }, () => [0.5, 0.5, 2]) },
    ],
  };
}

const mockStats = { total: 10, done: 3, todo: 7, leased: 0 };

describe("ReviewView", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "getPred").mockResolvedValue([]);
  });

  it("pressing k submits keep and advances to next", async () => {
    vi.spyOn(api, "submit").mockResolvedValue({ next: payload("200") });
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    vi.spyOn(api, "stats").mockResolvedValue(mockStats);
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
    vi.spyOn(api, "stats").mockResolvedValue(mockStats);
    const onExhausted = vi.fn();
    const user = userEvent.setup();

    render(<ReviewView user={{ user_id: 1, username: "b" }} task="all" first={payload("100")} onExhausted={onExhausted} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("d");

    await vi.waitFor(() => expect(onExhausted).toHaveBeenCalled());
  });

  it("shows the instance in the sidebar", async () => {
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    vi.spyOn(api, "stats").mockResolvedValue(mockStats);

    render(<ReviewView user={{ user_id: 1, username: "b" }} task="model" first={payload("100")} onExhausted={() => {}} />);

    expect(await screen.findByText(/Player 1/)).toBeInTheDocument();
    expect(await screen.findByText(/15\/15 vis/)).toBeInTheDocument();
  });

  it("keeps the editor open and shows an error when an edit save fails", async () => {
    vi.spyOn(api, "submit").mockRejectedValue(new Error("boom"));
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    vi.spyOn(api, "getPred").mockResolvedValue([]);
    const user = userEvent.setup();
    render(<ReviewView user={{ user_id: 1, username: "b" }} task="model" first={payload("100")} onExhausted={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("e");                       // open editor
    const save = await screen.findByRole("button", { name: /^save/i });
    await user.click(save);
    expect(await screen.findByText(/save failed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save/i })).toBeInTheDocument(); // editor still open
  });

  it("shows an error when submit rejects and stays put", async () => {
    vi.spyOn(api, "submit").mockRejectedValue(new Error("boom"));
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    vi.spyOn(api, "stats").mockResolvedValue(mockStats);
    const user = userEvent.setup();

    render(<ReviewView user={{ user_id: 1, username: "b" }} task="all" first={payload("100")} onExhausted={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("k");

    expect(await screen.findByText(/action failed/i)).toBeInTheDocument();
  });

  it("fetches PRED for the stem and shows the count", async () => {
    vi.spyOn(api, "heartbeat").mockResolvedValue({ ok: true });
    vi.spyOn(api, "release").mockResolvedValue({ ok: true });
    vi.spyOn(api, "getPred").mockResolvedValue([
      { kpts: Array.from({ length: 15 }, () => [10, 10, 2] as [number, number, number]) },
    ]);
    render(<ReviewView user={{ user_id: 1, username: "b" }} task="model" model="best.pt" first={payload("100")} onExhausted={() => {}} />);
    expect(await screen.findByText("PRED(1)")).toBeInTheDocument();
  });
});
