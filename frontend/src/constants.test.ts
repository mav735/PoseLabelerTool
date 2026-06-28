import { describe, it, expect } from "vitest";
import { NUM_KPTS, KPT_NAMES, SKELETON, FLIP_IDX, GT_COLOR, PRED_COLOR, VIS_COLORS } from "./constants";

describe("constants", () => {
  it("has 15 named keypoints in order", () => {
    expect(NUM_KPTS).toBe(15);
    expect(KPT_NAMES).toEqual(["hd","ch","pl","ls","rs","lh","rh","lw","rw","lf","rf","le","re","lk","rk"]);
  });
  it("has the 14 skeleton edges", () => {
    expect(SKELETON).toHaveLength(14);
    expect(SKELETON).toContainEqual([3, 11]);
    expect(SKELETON).toContainEqual([14, 10]);
  });
  it("has flip_idx", () => {
    expect(FLIP_IDX).toEqual([0,1,2,4,3,6,5,8,7,10,9,12,11,14,13]);
  });
  it("has colors", () => {
    expect(GT_COLOR).toBe("rgb(0,200,200)");
    expect(PRED_COLOR).toBe("rgb(255,0,255)");
    expect(VIS_COLORS[2]).toBe("rgb(0,255,0)");
  });
});
