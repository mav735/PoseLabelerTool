export interface EKpt { x: number; y: number; v: number; }
export type Box = [number, number, number, number];
export interface EInstance { kpts: EKpt[]; box: Box | null; source: "gt" | "pred"; hidden?: boolean; }

export const ADD_ORDER = [0, 1, 2, 5, 13, 9, 6, 14, 10, 4, 12, 8, 3, 11, 7];

export function fitBox(kpts: EKpt[], W: number, H: number, margin = 0.02): Box | null {
  const xs = kpts.filter((k) => k.v > 0).map((k) => k.x);
  const ys = kpts.filter((k) => k.v > 0).map((k) => k.y);
  if (xs.length === 0) return null;
  const minx = Math.min(...xs), maxx = Math.max(...xs);
  const miny = Math.min(...ys), maxy = Math.max(...ys);
  const mw = (maxx - minx) * margin, mh = (maxy - miny) * margin;
  return [Math.max(0, minx - mw), Math.max(0, miny - mh), Math.min(W, maxx + mw), Math.min(H, maxy + mh)];
}

export function pointInBox(box: Box, ix: number, iy: number): boolean {
  const x1 = Math.min(box[0], box[2]), x2 = Math.max(box[0], box[2]);
  const y1 = Math.min(box[1], box[3]), y2 = Math.max(box[1], box[3]);
  return x1 <= ix && ix <= x2 && y1 <= iy && iy <= y2;
}

export function hitInstance(insts: EInstance[], ix: number, iy: number): number {
  let best = -1;
  let bestArea = Infinity;
  insts.forEach((inst, i) => {
    if (inst.box && pointInBox(inst.box, ix, iy)) {
      const area = Math.abs((inst.box[2] - inst.box[0]) * (inst.box[3] - inst.box[1]));
      if (area < bestArea) { bestArea = area; best = i; }
    }
  });
  return best;
}

export interface AddState { active: boolean; idx: number; }

function refit(inst: EInstance, W: number, H: number): EInstance {
  return { ...inst, box: fitBox(inst.kpts, W, H) };
}

export function moveKpt(insts: EInstance[], i: number, k: number, ix: number, iy: number, W: number, H: number): EInstance[] {
  return insts.map((inst, j) => j !== i ? inst
    : refit({ ...inst, kpts: inst.kpts.map((kp, kk) => kk !== k ? kp : { x: ix, y: iy, v: kp.v }) }, W, H));
}

export function moveInstanceBy(insts: EInstance[], i: number, dx: number, dy: number, W: number, H: number): EInstance[] {
  return insts.map((inst, j) => j !== i ? inst
    : refit({ ...inst, kpts: inst.kpts.map((kp) => ({ x: kp.x + dx, y: kp.y + dy, v: kp.v })) }, W, H));
}

export function cycleVis(insts: EInstance[], i: number, k: number, W: number, H: number): EInstance[] {
  return insts.map((inst, j) => j !== i ? inst
    : refit({ ...inst, kpts: inst.kpts.map((kp, kk) => kk !== k ? kp : { ...kp, v: ((kp.v - 1) + 3) % 3 }) }, W, H));
}

export function deleteInstance(insts: EInstance[], i: number): EInstance[] {
  return insts.filter((_, j) => j !== i);
}

export function startAdd(insts: EInstance[]): { insts: EInstance[]; add: AddState } {
  const blank: EInstance = { kpts: Array.from({ length: 15 }, () => ({ x: 0, y: 0, v: 0 })), box: null, source: "gt" };
  return { insts: [...insts, blank], add: { active: true, idx: 0 } };
}

function advance(idx: number): AddState {
  const next = idx + 1;
  return next >= 15 ? { active: false, idx: 15 } : { active: true, idx: next };
}

export function placeKpt(insts: EInstance[], add: AddState, ix: number, iy: number, W: number, H: number): { insts: EInstance[]; add: AddState } {
  const i = insts.length - 1;
  const out = insts.map((inst, j) => j !== i ? inst
    : refit({ ...inst, kpts: inst.kpts.map((kp, kk) => kk !== ADD_ORDER[add.idx] ? kp : { x: ix, y: iy, v: 2 }) }, W, H));
  return { insts: out, add: advance(add.idx) };
}

export function skipKpt(insts: EInstance[], add: AddState): { insts: EInstance[]; add: AddState } {
  return { insts, add: advance(add.idx) };
}

export function promote(gt: EInstance[], pred: EInstance[], predIdx: number): { gt: EInstance[]; pred: EInstance[] } {
  const p = pred[predIdx];
  if (!p) return { gt, pred };
  const moved: EInstance = { kpts: p.kpts.map((k) => ({ ...k })), box: p.box ? [...p.box] : null, source: "gt" };
  return { gt: [...gt, moved], pred: pred.filter((_, j) => j !== predIdx) };
}
