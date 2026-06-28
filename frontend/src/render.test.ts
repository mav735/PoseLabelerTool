import { describe, it, expect } from "vitest";
import { denormGT, nearestKpt, drawOverlay, type Scene } from "./render";
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
    strokeRect: rec("strokeRect"),
    set fillStyle(_v: string) {}, set strokeStyle(_v: string) {}, set lineWidth(_v: number) {},
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
});
