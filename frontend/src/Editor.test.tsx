import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Editor } from "./Editor";
import type { EInstance } from "./editor";

function gtInst(): EInstance {
  return { kpts: Array.from({ length: 15 }, () => ({ x: 100, y: 100, v: 2 })), box: [90, 90, 110, 110], source: "gt" };
}

describe("Editor", () => {
  it("ENTER saves the current gt instances", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<Editor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[]} onSave={onSave} onCancel={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("{Enter}");
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toHaveLength(1);
  });

  it("ESC cancels when not adding", async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<Editor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[]} onSave={() => {}} onCancel={onCancel} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("{Escape}");
    expect(onCancel).toHaveBeenCalled();
  });

  it("n enters add mode and the HUD shows the head bone", async () => {
    const user = userEvent.setup();
    render(<Editor stem="100" imgW={640} imgH={640} gt0={[]} pred0={[]} onSave={() => {}} onCancel={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("n");
    expect(await screen.findByText(/place:\s*hd/i)).toBeInTheDocument();
  });

  it("x deletes the selected instance (none selected -> no crash, still 1)", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<Editor stem="100" imgW={640} imgH={640} gt0={[gtInst()]} pred0={[]} onSave={onSave} onCancel={() => {}} />);
    document.querySelector("canvas")!.focus();
    await user.keyboard("x");
    await user.keyboard("{Enter}");
    // nothing was selected, so the instance remains
    expect(onSave.mock.calls[0][0]).toHaveLength(1);
  });
});
