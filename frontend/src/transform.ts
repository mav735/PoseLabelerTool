export interface Transform { scale: number; tx: number; ty: number; }
export const ZOOM_MIN = 1;
export const ZOOM_MAX = 16;
export const WHEEL_STEP = 1.25;

export function fitScale(cw: number, ch: number, iw: number, ih: number): number {
  return Math.min(cw / iw, ch / ih);
}

export function imageToScreen(t: Transform, ix: number, iy: number) {
  return { x: ix * t.scale + t.tx, y: iy * t.scale + t.ty };
}

export function screenToImage(t: Transform, sx: number, sy: number) {
  return { x: (sx - t.tx) / t.scale, y: (sy - t.ty) / t.scale };
}

export function clampTransform(t: Transform, cw: number, ch: number, iw: number, ih: number): Transform {
  let { tx, ty } = t;
  const dw = iw * t.scale, dh = ih * t.scale;
  if (dw <= cw) tx = (cw - dw) / 2;
  else tx = Math.min(0, Math.max(cw - dw, tx));
  if (dh <= ch) ty = (ch - dh) / 2;
  else ty = Math.min(0, Math.max(ch - dh, ty));
  return { scale: t.scale, tx, ty };
}

export function reset(cw: number, ch: number, iw: number, ih: number): Transform {
  const scale = fitScale(cw, ch, iw, ih);
  return clampTransform({ scale, tx: 0, ty: 0 }, cw, ch, iw, ih);
}

export function zoomAt(t: Transform, sx: number, sy: number, factor: number,
                       cw: number, ch: number, iw: number, ih: number): Transform {
  const fit = fitScale(cw, ch, iw, ih);
  const newScale = Math.min(fit * ZOOM_MAX, Math.max(fit * ZOOM_MIN, t.scale * factor));
  const p = screenToImage(t, sx, sy);
  const tx = sx - p.x * newScale;
  const ty = sy - p.y * newScale;
  return clampTransform({ scale: newScale, tx, ty }, cw, ch, iw, ih);
}

export function panBy(t: Transform, dx: number, dy: number,
                      cw: number, ch: number, iw: number, ih: number): Transform {
  return clampTransform({ scale: t.scale, tx: t.tx + dx, ty: t.ty + dy }, cw, ch, iw, ih);
}

export function screenVecToImage(t: Transform, dx: number, dy: number) {
  return { x: dx / t.scale, y: dy / t.scale };
}
