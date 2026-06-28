import { describe, it, expect } from "vitest";
import { fitScale, reset, screenToImage, imageToScreen, zoomAt, panBy } from "./transform";

describe("transform", () => {
  it("fitScale contains the image", () => {
    expect(fitScale(800, 800, 640, 640)).toBeCloseTo(1.25);
    expect(fitScale(640, 480, 640, 640)).toBeCloseTo(0.75); // limited by height
  });

  it("reset fits and centers", () => {
    const t = reset(800, 600, 640, 640); // fit = 600/640 = 0.9375
    expect(t.scale).toBeCloseTo(0.9375);
    // image displayed 600x600, centered in 800x600 -> tx=100, ty=0
    expect(t.tx).toBeCloseTo(100);
    expect(t.ty).toBeCloseTo(0);
  });

  it("screen<->image round trip", () => {
    const t = { scale: 2, tx: 10, ty: 20 };
    expect(imageToScreen(t, 5, 5)).toEqual({ x: 20, y: 30 });
    expect(screenToImage(t, 20, 30)).toEqual({ x: 5, y: 5 });
  });

  it("zoomAt keeps the cursor's image point fixed", () => {
    const t0 = reset(640, 640, 640, 640); // scale 1, tx 0, ty 0
    const before = screenToImage(t0, 300, 300);
    const t1 = zoomAt(t0, 300, 300, 1.25, 640, 640, 640, 640);
    const after = screenToImage(t1, 300, 300);
    expect(after.x).toBeCloseTo(before.x);
    expect(after.y).toBeCloseTo(before.y);
    expect(t1.scale).toBeCloseTo(1.25);
  });

  it("zoom clamps to [fit, fit*16]", () => {
    let t = reset(640, 640, 640, 640);
    for (let i = 0; i < 40; i++) t = zoomAt(t, 320, 320, 1.25, 640, 640, 640, 640);
    expect(t.scale).toBeCloseTo(16);
    for (let i = 0; i < 40; i++) t = zoomAt(t, 320, 320, 1 / 1.25, 640, 640, 640, 640);
    expect(t.scale).toBeCloseTo(1);
  });

  it("clamp keeps the zoomed view inside the image", () => {
    let t = reset(640, 640, 640, 640);
    t = zoomAt(t, 320, 320, 4, 640, 640, 640, 640); // scale 4
    t = panBy(t, 100000, 100000, 640, 640, 640, 640); // shove far
    // top-left of view in image coords must stay >= 0
    const tl = screenToImage(t, 0, 0);
    expect(tl.x).toBeGreaterThanOrEqual(-0.001);
    expect(tl.y).toBeGreaterThanOrEqual(-0.001);
    const br = screenToImage(t, 640, 640);
    expect(br.x).toBeLessThanOrEqual(640.001);
    expect(br.y).toBeLessThanOrEqual(640.001);
  });
});
