import { describe, it, expect } from "vitest";
import { fitBox, pointInBox, hitInstance, type EInstance } from "./editor";

const kp = (x: number, y: number, v: number) => ({ x, y, v });

describe("editor geometry", () => {
  it("fitBox mirrors the backend (margin 2% of span, clamped)", () => {
    const kpts = [kp(100, 50, 2), kp(200, 150, 2), ...Array.from({ length: 13 }, () => kp(0, 0, 0))];
    expect(fitBox(kpts, 640, 640)).toEqual([98, 48, 202, 152]);
  });
  it("fitBox returns null with no visible keypoints", () => {
    expect(fitBox([kp(10, 10, 0), kp(20, 20, 0)], 640, 640)).toBeNull();
  });
  it("fitBox clamps to image bounds", () => {
    expect(fitBox([kp(0, 0, 2), kp(640, 640, 2)], 640, 640)).toEqual([0, 0, 640, 640]);
  });
  it("pointInBox", () => {
    expect(pointInBox([10, 10, 50, 50], 30, 30)).toBe(true);
    expect(pointInBox([10, 10, 50, 50], 5, 30)).toBe(false);
  });
  it("hitInstance returns the smallest containing box", () => {
    const big: EInstance = { kpts: [], box: [0, 0, 100, 100], source: "gt" };
    const small: EInstance = { kpts: [], box: [40, 40, 60, 60], source: "gt" };
    expect(hitInstance([big, small], 50, 50)).toBe(1);
    expect(hitInstance([big, small], 10, 10)).toBe(0);
    expect(hitInstance([big, small], 200, 200)).toBe(-1);
  });
});
