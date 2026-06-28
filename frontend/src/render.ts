import { GT_COLOR, PRED_COLOR, SKELETON, VIS_COLORS } from "./constants";
import { imageToScreen, type Transform } from "./transform";
import type { Instance, View } from "./types";

export interface SKpt { x: number; y: number; v: number; }
export interface SInstance { kpts: SKpt[]; box: [number, number, number, number] | null; }
export interface Scene { gt: SInstance[]; pred: SInstance[]; imgW: number; imgH: number; }

export const DOT_R = 3;
export const SEL_R = 4;
export const SEL_BOX_COLOR = "rgb(34,211,197)";

export function denormGT(instances: Instance[], w: number, h: number): SInstance[] {
  return instances.map((inst) => {
    const kpts = inst.kpts.map(([x, y, v]) => ({ x: x * w, y: y * h, v }));
    const box: [number, number, number, number] = [
      (inst.cx - inst.w / 2) * w, (inst.cy - inst.h / 2) * h,
      (inst.cx + inst.w / 2) * w, (inst.cy + inst.h / 2) * h,
    ];
    return { kpts, box };
  });
}

export function nearestKpt(gt: SInstance[], ix: number, iy: number, scale: number, thresholdPx = 15): { i: number; k: number } | null {
  let best: { i: number; k: number } | null = null;
  let bestD = thresholdPx / scale;
  gt.forEach((inst, i) => {
    inst.kpts.forEach((kp, k) => {
      const d = Math.hypot(kp.x - ix, kp.y - iy);
      if (d < bestD) { bestD = d; best = { i, k }; }
    });
  });
  return best;
}

function drawInstance(ctx: CanvasRenderingContext2D, t: Transform, inst: SInstance,
                      color: string, gt: boolean, selK: number, isSelected = false) {
  if (inst.box) {
    const a = imageToScreen(t, inst.box[0], inst.box[1]);
    const b = imageToScreen(t, inst.box[2], inst.box[3]);
    ctx.strokeStyle = isSelected ? SEL_BOX_COLOR : color;
    ctx.lineWidth = isSelected ? 2 : 1;
    ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
  }
  ctx.strokeStyle = color; ctx.lineWidth = 1;
  for (const [ai, bi] of SKELETON) {
    const ka = inst.kpts[ai], kb = inst.kpts[bi];
    if ((gt && (ka.v === 0 || kb.v === 0))) continue;
    const pa = imageToScreen(t, ka.x, ka.y), pb = imageToScreen(t, kb.x, kb.y);
    ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
  }
  inst.kpts.forEach((kp, k) => {
    if (gt && kp.v === 0) return;
    const p = imageToScreen(t, kp.x, kp.y);
    const r = k === selK ? SEL_R : DOT_R;
    ctx.fillStyle = gt ? VIS_COLORS[kp.v] : color;
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
    if (k === 0) {
      ctx.strokeStyle = "rgb(255,255,255)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 1, 0, Math.PI * 2); ctx.stroke();
    }
  });
}

export function drawOverlay(ctx: CanvasRenderingContext2D, t: Transform, scene: Scene,
                            view: View, sel: { i: number; k: number } | null,
                            selInst: number | null = null) {
  if (view === 0) {
    scene.gt.forEach((inst, i) =>
      drawInstance(ctx, t, inst, GT_COLOR, true, sel && sel.i === i ? sel.k : -1, i === selInst));
  }
  if (view === 1) {
    scene.pred.forEach((inst) => drawInstance(ctx, t, inst, PRED_COLOR, false, -1, false));
  }
  // view === 2: Clear — draw nothing
}
