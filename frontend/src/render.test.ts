import { describe, it, expect } from "vitest";
import { denormGT, nearestKpt, drawOverlay, drawEditor, type Scene } from "./render";
import type { Instance } from "./types";

function fullInstance(): Instance {
  return { cx: 0.5, cy: 0.5, w: 0.1, h: 0.4, kpts: Array.from({ length: 15 }, () => [0.5, 0.5, 2]) };
}

function mockCtx() {
  const calls: Record<string, number> = {};
  const rec = (k: string) => () => { calls[k] = (calls[k] || 0) + 1; };
  return {
    calls,
    beginPath: rec("beginPath"), moveTo: rec("moveTo"), lineTo: rec("lineTo"),
    arc: rec("arc"), fill: rec("fill"), stroke: rec("stroke"),
    strokeRect: rec("strokeRect"), fillText: rec("fillText"),
    set fillStyle(_v: string) {}, set strokeStyle(_v: string) {}, set lineWidth(_v: number) {},
    set font(_v: string) {}, set textBaseline(_v: string) {},
  } as unknown as CanvasRenderingContext2D & { calls: Record<string, number> };
}

describe("render", () => {
  it("denormGT scales kpts and box to pixels", () => {
    const s = denormGT([fullInstance()], 640, 640);
    expect(s[0].kpts[0]).toEqual({ x: 320, y: 320, v: 2 });
    // box cx0.5 w0.1 -> x1=(0.5-0.05)*640=288, x2=(0.55)*640=352
    expect(s[0].box).toEqual([288, 192, 352, 448]);
  });

  it("nearestKpt finds a kpt within threshold and null otherwise", () => {
    const gt = denormGT([fullInstance()], 640, 640); // single kpt cluster at 320,320
    expect(nearestKpt(gt, 322, 322, 1, 15)).toEqual({ i: 0, k: 0 });
    expect(nearestKpt(gt, 0, 0, 1, 15)).toBeNull();
  });

  it("drawOverlay GT (view=0) draws GT box and dots", () => {
    const scene: Scene = { gt: denormGT([fullInstance()], 640, 640), pred: [], imgW: 640, imgH: 640 };
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawOverlay(ctx, { scale: 1, tx: 0, ty: 0 }, scene, 0, null);
    expect(ctx.calls.arc).toBeGreaterThan(0);   // dots drawn
    expect(ctx.calls.strokeRect).toBe(1);       // one GT box
  });

  it("drawOverlay PRED (view=1) draws nothing when pred is empty", () => {
    const scene: Scene = { gt: denormGT([fullInstance()], 640, 640), pred: [], imgW: 640, imgH: 640 };
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawOverlay(ctx, { scale: 1, tx: 0, ty: 0 }, scene, 1, null);
    expect(ctx.calls.strokeRect ?? 0).toBe(0);
    expect(ctx.calls.arc ?? 0).toBe(0);
  });

  it("drawOverlay Clear (view=2) draws nothing", () => {
    const scene: Scene = { gt: denormGT([fullInstance()], 640, 640), pred: [], imgW: 640, imgH: 640 };
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawOverlay(ctx, { scale: 1, tx: 0, ty: 0 }, scene, 2, null);
    expect(ctx.calls.strokeRect ?? 0).toBe(0);
    expect(ctx.calls.arc ?? 0).toBe(0);
  });

  it("drawEditor draws gt + pred boxes", () => {
    const inst = { kpts: Array.from({ length: 15 }, () => ({ x: 100, y: 100, v: 2 })), box: [90, 90, 110, 110] as [number, number, number, number] };
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawEditor(ctx, { scale: 1, tx: 0, ty: 0 }, [inst], [inst], null);
    expect(ctx.calls.strokeRect).toBe(2); // one gt + one pred box
    expect(ctx.calls.arc).toBeGreaterThan(0);
  });

  const box1 = [90, 90, 110, 110] as [number, number, number, number];
  const e = (hidden?: boolean) => ({ kpts: Array.from({ length: 15 }, () => ({ x: 100, y: 100, v: 2 })), box: box1, hidden });

  it("drawEditor hides pred group when vis.pred=false", () => {
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawEditor(ctx, { scale: 1, tx: 0, ty: 0 }, [e()], [e()], null, { gt: true, pred: false });
    expect(ctx.calls.strokeRect).toBe(1); // only gt box
  });

  it("drawEditor hides gt group when vis.gt=false", () => {
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawEditor(ctx, { scale: 1, tx: 0, ty: 0 }, [e()], [e()], null, { gt: false, pred: true });
    expect(ctx.calls.strokeRect).toBe(1); // only pred box
  });

  it("drawEditor skips per-instance hidden in a visible group", () => {
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawEditor(ctx, { scale: 1, tx: 0, ty: 0 }, [e(), e(true)], [], null, { gt: true, pred: true });
    expect(ctx.calls.strokeRect).toBe(1); // 2 gt, 1 hidden -> 1 box
  });

  it("drawEditor draws keypoint names only when showNames=true", () => {
    const off = mockCtx() as ReturnType<typeof mockCtx>;
    drawEditor(off, { scale: 1, tx: 0, ty: 0 }, [e()], [], null);
    expect(off.calls.fillText ?? 0).toBe(0); // default: no names

    const on = mockCtx() as ReturnType<typeof mockCtx>;
    drawEditor(on, { scale: 1, tx: 0, ty: 0 }, [e()], [], null, { gt: true, pred: true }, true);
    expect(on.calls.fillText).toBe(15); // one label per visible kpt
  });

  it("drawOverlay PRED view skips v=0 keypoints", () => {
    const predInst = { kpts: Array.from({ length: 15 }, (_, i) => ({ x: 10, y: 10, v: i < 3 ? 2 : 0 })), box: [0, 0, 20, 20] as [number, number, number, number] };
    const scene = { gt: [], pred: [predInst], imgW: 640, imgH: 640 };
    const ctx = mockCtx() as ReturnType<typeof mockCtx>;
    drawOverlay(ctx, { scale: 1, tx: 0, ty: 0 }, scene, 1, null); // view 1 = PRED
    expect(ctx.calls.arc).toBe(4); // only the 3 visible kpts drawn (kpt 0 gets 2 arcs: dot + white ring)
  });
});
