import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PoseEditor } from "./PoseEditor";
import type { EInstance } from "./editor";

function gtInst(): EInstance {
  return { kpts: Array.from({ length: 15 }, () => ({ x: 100, y: 100, v: 2 })), box: [90, 90, 110, 110], source: "gt" };
}

function predInst(): EInstance {
  return { kpts: Array.from({ length: 15 }, () => ({ x: 50, y: 50, v: 2 })), box: [40, 40, 60, 60], source: "pred" };
}

describe("PoseEditor", () => {
  it("ENTER saves the current gt instances", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<PoseEditor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[]} onSave={onSave} onCancel={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("{Enter}");
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toHaveLength(1);
  });

  it("ESC cancels when not adding", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<PoseEditor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[]} onSave={() => {}} onCancel={onCancel} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalled();
  });

  it("n enters add mode and the HUD shows the head bone", async () => {
    const user = userEvent.setup();
    render(<PoseEditor stem="100" imgW={640} imgH={640} gt0={[]} pred0={[]} onSave={() => {}} onCancel={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("n");
    expect(await screen.findByText(/place:\s*hd/i)).toBeInTheDocument();
  });

  it("dragging a pred card onto Truth promotes it", async () => {
    const onSave = vi.fn();
    const pred: EInstance = { kpts: Array.from({ length: 15 }, () => ({ x: 50, y: 50, v: 2 })), box: [40, 40, 60, 60], source: "pred" };
    render(<PoseEditor stem="100" imgW={640} imgH={640} gt0={[]} pred0={[pred]} onSave={onSave} onCancel={() => {}} />);
    const dt = { getData: () => "0", setData: () => {} };
    const zone = document.querySelector(".dropzone")!;
    fireEvent.drop(zone, { dataTransfer: dt });
    const user = userEvent.setup();
    document.querySelector("canvas")!.focus();
    await user.keyboard("{Enter}");
    expect(onSave.mock.calls[0][0]).toHaveLength(1); // promoted pred is now a saved GT instance
  });

  it("group eyes: GT visible, Predicted hidden by default", () => {
    render(<PoseEditor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[predInst()]} onSave={() => {}} onCancel={() => {}} />);
    expect(screen.getByRole("button", { name: /^All/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /GT — hide/i })).toBeInTheDocument();        // GT shown
    expect(screen.getByRole("button", { name: /Predicted — show/i })).toBeInTheDocument();  // Pred hidden
  });

  it("toggling Predicted group eye flips it to visible", async () => {
    const user = userEvent.setup();
    render(<PoseEditor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[predInst()]} onSave={() => {}} onCancel={() => {}} />);
    await user.click(screen.getByRole("button", { name: /Predicted — show/i }));
    expect(screen.getByRole("button", { name: /Predicted — hide/i })).toBeInTheDocument();
  });

  it("x deletes the selected instance (none selected -> no crash, still 1)", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<PoseEditor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[]} onSave={onSave} onCancel={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("x");
    await user.keyboard("{Enter}");
    // nothing was selected, so the instance remains
    expect(onSave.mock.calls[0][0]).toHaveLength(1);
  });
});
