import { describe, it, expect } from "vitest";
import { moveKpt, moveInstanceBy, cycleVis, deleteInstance, startAdd, placeKpt, skipKpt, promote, type EInstance } from "./editor";

function inst(source: "gt" | "pred" = "gt"): EInstance {
  return { kpts: Array.from({ length: 15 }, (_, i) => ({ x: 100 + i, y: 100 + i, v: 2 })), box: null, source };
}

describe("editor ops", () => {
  it("moveKpt moves and refits the box", () => {
    const out = moveKpt([inst()], 0, 0, 300, 50, 640, 640);
    expect(out[0].kpts[0]).toEqual({ x: 300, y: 50, v: 2 });
    expect(out[0].box).not.toBeNull();
  });
  it("moveInstanceBy shifts all keypoints", () => {
    const out = moveInstanceBy([inst()], 0, 10, 20, 640, 640);
    expect(out[0].kpts[0]).toEqual({ x: 110, y: 120, v: 2 });
  });
  it("cycleVis goes 2->1->0->2", () => {
    let out = cycleVis([inst()], 0, 3, 640, 640);
    expect(out[0].kpts[3].v).toBe(1);
    out = cycleVis(out, 0, 3, 640, 640);
    expect(out[0].kpts[3].v).toBe(0);
    out = cycleVis(out, 0, 3, 640, 640);
    expect(out[0].kpts[3].v).toBe(2);
  });
  it("deleteInstance removes it", () => {
    expect(deleteInstance([inst(), inst()], 0)).toHaveLength(1);
  });
  it("click-to-place walks bones and ends after 15", () => {
    let { insts, add } = startAdd([]);
    expect(add).toEqual({ active: true, idx: 0 });
    expect(insts).toHaveLength(1);
    ({ insts, add } = placeKpt(insts, add, 200, 200, 640, 640)); // hd
    expect(insts[0].kpts[0]).toEqual({ x: 200, y: 200, v: 2 });
    expect(add.idx).toBe(1);
    ({ insts, add } = skipKpt(insts, add)); // skip ch -> stays v=0
    expect(insts[0].kpts[1].v).toBe(0);
    expect(add.idx).toBe(2);
    for (let i = 2; i < 15; i++) ({ insts, add } = placeKpt(insts, add, 200 + i, 200 + i, 640, 640));
    expect(add.active).toBe(false);
  });
  it("promote moves a pred instance into gt", () => {
    const p = inst("pred");
    const { gt, pred } = promote([inst("gt")], [p], 0);
    expect(gt).toHaveLength(2);
    expect(gt[1].source).toBe("gt");
    expect(pred).toHaveLength(0);
  });
  it("promote copies the box array (no shared reference)", () => {
    const p: EInstance = { kpts: Array.from({ length: 15 }, () => ({ x: 1, y: 1, v: 2 })), box: [1, 2, 3, 4], source: "pred" };
    const { gt } = promote([], [p], 0);
    expect(gt[0].box).toEqual([1, 2, 3, 4]);
    expect(gt[0].box).not.toBe(p.box);
  });
});
