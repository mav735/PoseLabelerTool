export interface EKpt { x: number; y: number; v: number; }
export type Box = [number, number, number, number];
export interface EInstance { kpts: EKpt[]; box: Box | null; source: "gt" | "pred"; }

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
