import { useCallback, useEffect, useRef, useState } from "react";
import { imageUrl } from "./api";
import { KPT_NAMES } from "./constants";
import { EyeButton } from "./EyeButton";
import { InstanceCard } from "./InstanceCard";
import { drawEditor, nearestKpt } from "./render";
import { reset, screenToImage, panBy, zoomAt, type Transform } from "./transform";
import {
  cycleVis, deleteInstance, hitInstance, moveInstanceBy, moveKpt,
  placeKpt, promote, skipKpt, startAdd, ADD_ORDER, type AddState, type EInstance,
} from "./editor";

export function PoseEditor({ dataset, stem, imgW, imgH, gt0, pred0, onSave, onCancel }: {
  dataset: string; stem: string; imgW: number; imgH: number;
  gt0: EInstance[]; pred0: EInstance[];
  onSave: (gt: EInstance[]) => void; onCancel: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [gt, setGt] = useState<EInstance[]>(gt0);
  const [add, setAdd] = useState<AddState>({ active: false, idx: 0 });
  const [sel, setSel] = useState<{ i: number; k: number } | null>(null);
  const [hideNames, setHideNames] = useState(true);
  const [showGt, setShowGt] = useState(true);
  const [showPred, setShowPred] = useState(false); // predicted boxes hidden by default in edit
  const [popup, setPopup] = useState<{ x: number; y: number; text: string } | null>(null);
  const tRef = useRef<Transform>({ scale: 1, tx: 0, ty: 0 });
  const dragRef = useRef<{ mode: "kpt" | "box" | "pan"; mx: number; my: number; i: number; k: number } | null>(null);
  const [pred, setPred] = useState<EInstance[]>(pred0);
  const [dragOver, setDragOver] = useState(false);
  const gtRef = useRef(gt); gtRef.current = gt;
  const addRef = useRef(add); addRef.current = add;
  const predRef = useRef(pred); predRef.current = pred;

  const redraw = useCallback(() => {
    const c = canvasRef.current; if (!c) return;
    const ctx = c.getContext("2d"); if (!ctx) return;
    ctx.clearRect(0, 0, c.width, c.height);
    const t = tRef.current;
    if (imgRef.current) ctx.drawImage(imgRef.current, t.tx, t.ty, imgW * t.scale, imgH * t.scale);
    drawEditor(ctx, t, gtRef.current, predRef.current, sel, { gt: showGt, pred: showPred }, !hideNames);
  }, [imgW, imgH, pred, sel, showGt, showPred, hideNames]);

  useEffect(() => {
    const c = canvasRef.current!;
    c.width = c.clientWidth; c.height = c.clientHeight;
    tRef.current = reset(c.width, c.height, imgW, imgH);
    c.focus();
    const img = new Image();
    img.onload = () => { imgRef.current = img; redraw(); };
    img.src = imageUrl(dataset, stem);
    redraw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { redraw(); }, [gt, pred, sel, redraw]);

  function promotePred(i: number) {
    const r = promote(gtRef.current, predRef.current, i);
    setGt(r.gt); setPred(r.pred);
  }

  const toggleHide = (set: typeof setGt, i: number) =>
    set((arr) => arr.map((inst, j) => j === i ? { ...inst, hidden: !inst.hidden } : inst));

  const allOn = showGt || showPred;
  const toggleAll = () => { const v = !allOn; setShowGt(v); setShowPred(v); };

  function imgPt(e: React.MouseEvent) {
    const r = canvasRef.current!.getBoundingClientRect();
    return screenToImage(tRef.current, e.clientX - r.left, e.clientY - r.top);
  }

  function onMouseDown(e: React.MouseEvent) {
    setPopup(null);
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
    const d = dragRef.current;
    if (!d) {
      const p = imgPt(e);
      const hit = nearestKpt(gtRef.current, p.x, p.y, tRef.current.scale);
      if (hit && showGt && !gtRef.current[hit.i].hidden) {
        const kp = gtRef.current[hit.i].kpts[hit.k];
        setPopup({ x: e.clientX + 8, y: e.clientY - 8, text: `${KPT_NAMES[hit.k]}:${kp.v}` });
      } else setPopup(null);
      return;
    }
    const c = canvasRef.current!;
    if (d.mode === "pan") {
      tRef.current = panBy(tRef.current, e.clientX - d.mx, e.clientY - d.my, c.width, c.height, imgW, imgH);
      dragRef.current = { ...d, mx: e.clientX, my: e.clientY }; redraw(); return;
    }
    const p = imgPt(e);
    if (d.mode === "kpt") { setGt(moveKpt(gtRef.current, d.i, d.k, p.x, p.y, imgW, imgH)); }
    else if (d.mode === "box") {
      setGt(moveInstanceBy(gtRef.current, d.i, p.x - d.mx, p.y - d.my, imgW, imgH));
      dragRef.current = { ...d, mx: p.x, my: p.y };
    }
  }

  function onMouseUp() { dragRef.current = null; }
  function onMouseLeave() { dragRef.current = null; setPopup(null); }

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
        {add.active && <span className="addhud">Place: {KPT_NAMES[ADD_ORDER[add.idx]]} <kbd>click</kbd> <kbd>s</kbd> skip <kbd>esc</kbd> end</span>}
        <div className="spacer" />
        <span className="muted mono">drag kpt/box · n add · x del · rclick vis · h names · hover = bone hint · ENTER save · ESC cancel</span>
      </div>
      <div className="canvas-wrap">
        <canvas ref={canvasRef} tabIndex={0} onKeyDown={onKeyDown} onWheel={onWheel}
          onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp}
          onMouseLeave={onMouseLeave} onContextMenu={onContextMenu} />
        {popup && <div className="popup" style={{ left: popup.x, top: popup.y }}>{popup.text}</div>}
      </div>
      <div className="sidebar">
        <div className="side-head">
          <span>Truth instances <span className="mono">{gt.length}</span></span>
          <EyeButton on={showGt} title="GT" onToggle={() => setShowGt((s) => !s)} />
        </div>
        <div className={"dropzone" + (dragOver ? " drop-active" : "")}
             onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
             onDragLeave={() => setDragOver(false)}
             onDrop={(e) => {
               e.preventDefault(); setDragOver(false);
               const i = parseInt(e.dataTransfer.getData("text/plain"), 10);
               if (!Number.isNaN(i)) promotePred(i);
             }}>
          {gt.length === 0 && <div className="side-empty">Drag a predicted instance here</div>}
          {gt.map((inst, i) => (
            <InstanceCard key={i} label={`Player ${i + 1}`} source="gt"
              vs={inst.kpts.map((k) => k.v)} selected={sel?.i === i} onSelect={() => setSel({ i, k: -1 })}
              hidden={inst.hidden} onToggleHide={() => toggleHide(setGt, i)} />
          ))}
        </div>
        <div className="side-head">
          <span>Predicted instances <span className="mono">{pred.length}</span></span>
          <EyeButton on={showPred} title="Predicted" onToggle={() => setShowPred((s) => !s)} />
        </div>
        {pred.length === 0 && <div className="side-empty">No predictions — pick a model</div>}
        {pred.map((inst, i) => (
          <InstanceCard key={i} label={`Pred ${i + 1}`} source="pred" vs={inst.kpts.map((k) => k.v)}
            draggable onDragStart={(e) => e.dataTransfer.setData("text/plain", String(i))}
            hidden={inst.hidden} onToggleHide={() => toggleHide(setPred, i)} />
        ))}
      </div>
      <div className="actionbar">
        <button onClick={() => onSave(gtRef.current)}>Save <kbd>↵</kbd></button>
        <button className="ghost" onClick={onCancel}>Cancel <kbd>esc</kbd></button>
        <span className="vis-all muted">All <EyeButton on={allOn} title="All" onToggle={toggleAll} /></span>
        {hideNames ? null : <span className="muted">names on</span>}
      </div>
    </div>
  );
}
