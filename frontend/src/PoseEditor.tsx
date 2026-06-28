import { useCallback, useEffect, useRef, useState } from "react";
import { imageUrl } from "./api";
import { KPT_NAMES } from "./constants";
import { drawEditor, nearestKpt } from "./render";
import { reset, screenToImage, screenVecToImage, panBy, zoomAt, type Transform } from "./transform";
import {
  cycleVis, deleteInstance, hitInstance, moveInstanceBy, moveKpt,
  placeKpt, skipKpt, startAdd, type AddState, type EInstance,
} from "./editor";

export function PoseEditor({ stem, imgW, imgH, gt0, pred0, onSave, onCancel }: {
  stem: string; imgW: number; imgH: number;
  gt0: EInstance[]; pred0: EInstance[];
  onSave: (gt: EInstance[]) => void; onCancel: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [gt, setGt] = useState<EInstance[]>(gt0);
  const [add, setAdd] = useState<AddState>({ active: false, idx: 0 });
  const [sel, setSel] = useState<{ i: number; k: number } | null>(null);
  const [hideNames, setHideNames] = useState(true);
  const tRef = useRef<Transform>({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef<{ mode: "kpt" | "box" | "pan"; mx: number; my: number; i: number; k: number } | null>(null);
  const gtRef = useRef(gt); gtRef.current = gt;
  const addRef = useRef(add); addRef.current = add;

  const redraw = useCallback(() => {
    const c = canvasRef.current; if (!c) return;
    const ctx = c.getContext("2d"); if (!ctx) return;
    ctx.clearRect(0, 0, c.width, c.height);
    const t = tRef.current;
    if (imgRef.current) ctx.drawImage(imgRef.current, t.tx, t.ty, imgW * t.scale, imgH * t.scale);
    drawEditor(ctx, t, gtRef.current, pred0, sel);
  }, [imgW, imgH, pred0, sel]);

  useEffect(() => {
    const c = canvasRef.current!;
    c.width = c.clientWidth; c.height = c.clientHeight;
    tRef.current = reset(c.width, c.height, imgW, imgH);
    c.focus();
    const img = new Image();
    img.onload = () => { imgRef.current = img; redraw(); };
    img.src = imageUrl(stem);
    redraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { redraw(); }, [gt, sel, redraw]);

  function imgPt(e: React.MouseEvent) {
    const r = canvasRef.current!.getBoundingClientRect();
    return screenToImage(tRef.current, e.clientX - r.left, e.clientY - r.top);
  }

  function onMouseDown(e: React.MouseEvent) {
    const p = imgPt(e);
    if (addRef.current.active) {
      const r = placeKpt(gtRef.current, addRef.current, p.x, p.y, imgW, imgH);
      setGt(r.insts); setAdd(r.add); return;
    }
    const hit = nearestKpt(gtRef.current, p.x, p.y, tRef.current.scale);
    if (hit) { setSel(hit); dragRef.current = { mode: "kpt", mx: p.x, my: p.y, i: hit.i, k: hit.k }; return; }
    const bi = hitInstance(gtRef.current, p.x, p.y);
    if (bi >= 0) { setSel({ i: bi, k: -1 }); dragRef.current = { mode: "box", mx: p.x, my: p.y, i: bi, k: -1 }; return; }
    dragRef.current = { mode: "pan", mx: e.clientX, my: e.clientY, i: -1, k: -1 };
  }

  function onMouseMove(e: React.MouseEvent) {
    const d = dragRef.current; if (!d) return;
    const c = canvasRef.current!;
    if (d.mode === "pan") {
      tRef.current = panBy(tRef.current, e.clientX - d.mx, e.clientY - d.my, c.width, c.height, imgW, imgH);
      dragRef.current = { ...d, mx: e.clientX, my: e.clientY }; redraw(); return;
    }
    const p = imgPt(e);
    if (d.mode === "kpt") { setGt(moveKpt(gtRef.current, d.i, d.k, p.x, p.y, imgW, imgH)); }
    else if (d.mode === "box") {
      const v = screenVecToImage(tRef.current, (p.x - d.mx) * tRef.current.scale, (p.y - d.my) * tRef.current.scale);
      setGt(moveInstanceBy(gtRef.current, d.i, v.x, v.y, imgW, imgH));
      dragRef.current = { ...d, mx: p.x, my: p.y };
    }
  }

  function onMouseUp() { dragRef.current = null; }

  function onContextMenu(e: React.MouseEvent) {
    e.preventDefault();
    const p = imgPt(e);
    const hit = nearestKpt(gtRef.current, p.x, p.y, tRef.current.scale);
    if (hit) setGt(cycleVis(gtRef.current, hit.i, hit.k, imgW, imgH));
  }

  function onWheel(e: React.WheelEvent) {
    const c = canvasRef.current!; const r = c.getBoundingClientRect();
    const factor = e.deltaY < 0 ? 1.25 : 1 / 1.25;
    tRef.current = zoomAt(tRef.current, e.clientX - r.left, e.clientY - r.top, factor, c.width, c.height, imgW, imgH);
    redraw();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") { onSave(gtRef.current); return; }
    if (e.key === "Escape") { if (addRef.current.active) setAdd({ active: false, idx: 15 }); else onCancel(); return; }
    if (e.key === "0") { const c = canvasRef.current!; tRef.current = reset(c.width, c.height, imgW, imgH); redraw(); return; }
    if (e.key === "h") { setHideNames((s) => !s); return; }
    if (e.key === "n") { const r = startAdd(gtRef.current); setGt(r.insts); setAdd(r.add); return; }
    if (e.key === "s" && addRef.current.active) { const r = skipKpt(gtRef.current, addRef.current); setGt(r.insts); setAdd(r.add); return; }
    if (e.key === "x" && sel) { setGt(deleteInstance(gtRef.current, sel.i)); setSel(null); return; }
  }

  return (
    <div className="review">
      <div className="topbar">
        <span className="chip">EDIT</span>
        <span className="mono">{stem}</span>
        {add.active && <span className="addhud">Place: {KPT_NAMES[add.idx]} <kbd>click</kbd> <kbd>s</kbd> skip <kbd>esc</kbd> end</span>}
        <div className="spacer" />
        <span className="muted mono">drag kpt/box · n add · x del · rclick vis · ENTER save · ESC cancel</span>
      </div>
      <div className="canvas-wrap">
        <canvas ref={canvasRef} tabIndex={0} onKeyDown={onKeyDown} onWheel={onWheel}
          onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp} onContextMenu={onContextMenu} />
      </div>
      <div className="sidebar">
        <div className="side-head">True <span className="mono">{gt.length}</span></div>
        {gt.map((_, i) => <div key={i} className={"inst" + (sel?.i === i ? " sel" : "")} onClick={() => setSel({ i, k: -1 })}>Player {i + 1}</div>)}
      </div>
      <div className="actionbar">
        <button onClick={() => onSave(gtRef.current)}>Save <kbd>↵</kbd></button>
        <button className="ghost" onClick={onCancel}>Cancel <kbd>esc</kbd></button>
        {hideNames ? null : <span className="muted">names on</span>}
      </div>
    </div>
  );
}
