import { useCallback, useEffect, useRef, useState } from "react";
import { heartbeat, imageUrl, release, submit } from "./api";
import { GT_COLOR, KPT_NAMES, PRED_COLOR } from "./constants";
import { denormGT, drawOverlay, nearestKpt, type Scene } from "./render";
import { panBy, reset, screenToImage, zoomAt, type Transform } from "./transform";
import { keyToAction, keyToView } from "./keys";
import type { LabelPayload, Task, View } from "./types";

type Active = LabelPayload & { lease_id: number };

export function ReviewView({ user, task, first, onExhausted }: {
  user: { user_id: number; username: string };
  task: Task;
  first: Active;
  onExhausted: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [active, setActive] = useState<Active>(first);
  const [view, setView] = useState<View>(0);
  const [showNames, setShowNames] = useState(false);
  const [popup, setPopup] = useState<{ x: number; y: number; text: string } | null>(null);
  const [error, setError] = useState("");
  const tRef = useRef<Transform>({ scale: 1, tx: 0, ty: 0 });
  const sceneRef = useRef<Scene>({ gt: [], pred: [], imgW: first.width, imgH: first.height });
  const selRef = useRef<{ i: number; k: number } | null>(null);
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const leaseRef = useRef(first.lease_id);
  const busyRef = useRef(false);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const img = imgRef.current;
    const t = tRef.current;
    if (img) ctx.drawImage(img, t.tx, t.ty, img.width * t.scale, img.height * t.scale);
    drawOverlay(ctx, t, sceneRef.current, view, selRef.current);
  }, [view]);

  const loadStem = useCallback((a: Active) => {
    const canvas = canvasRef.current!;
    canvas.focus();
    sceneRef.current = { gt: denormGT(a.instances, a.width, a.height), pred: [], imgW: a.width, imgH: a.height };
    tRef.current = reset(canvas.width, canvas.height, a.width, a.height);
    const img = new Image();
    img.onload = () => { imgRef.current = img; redraw(); };
    img.src = imageUrl(a.stem);
    imgRef.current = null;
    redraw();
  }, [redraw]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
    loadStem(active);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const id = setInterval(() => { heartbeat(active.lease_id).catch(() => {}); }, 30000);
    return () => clearInterval(id);
  }, [active.lease_id]);

  useEffect(() => { leaseRef.current = active.lease_id; }, [active.lease_id]);

  useEffect(() => () => { release(leaseRef.current).catch(() => {}); }, []);

  const advance = useCallback((next: Active | null) => {
    if (!next) { onExhausted(); return; }
    setActive(next);
    loadStem(next);
  }, [loadStem, onExhausted]);

  const doAction = useCallback(async (action: "keep" | "drop" | "clear") => {
    if (busyRef.current) return;
    busyRef.current = true;
    setError("");
    try {
      const r = await submit({ stem: active.stem, task, user_id: user.user_id, action });
      advance(r.next);
    } catch {
      setError("Action failed — please try again.");
    } finally {
      busyRef.current = false;
    }
  }, [active.stem, task, user.user_id, advance]);

  useEffect(() => { redraw(); }, [view, showNames, redraw]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "0") { const c = canvasRef.current!; tRef.current = reset(c.width, c.height, sceneRef.current.imgW, sceneRef.current.imgH); redraw(); return; }
    if (e.key === "h") { setShowNames((s) => !s); return; }
    const vk = keyToView(e.key);
    if (vk) { setView((v) => ((vk === "next" ? v + 1 : v + 2) % 3) as View); return; }
    const action = keyToAction(e.key);
    if (action === "keep" || action === "drop" || action === "clear") { void doAction(action); return; }
    // r/e handled by the editor in Plan 5 (no-op here)
  }

  function onWheel(e: React.WheelEvent) {
    const c = canvasRef.current!; const rect = c.getBoundingClientRect();
    const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.25 : 1 / 1.25;
    tRef.current = zoomAt(tRef.current, sx, sy, factor, c.width, c.height, sceneRef.current.imgW, sceneRef.current.imgH);
    redraw();
  }

  function onMouseDown(e: React.MouseEvent) { dragRef.current = { x: e.clientX, y: e.clientY }; }
  function onMouseUp() { dragRef.current = null; }
  function onMouseMove(e: React.MouseEvent) {
    const c = canvasRef.current!; const rect = c.getBoundingClientRect();
    if (dragRef.current) {
      const dx = e.clientX - dragRef.current.x, dy = e.clientY - dragRef.current.y;
      dragRef.current = { x: e.clientX, y: e.clientY };
      tRef.current = panBy(tRef.current, dx, dy, c.width, c.height, sceneRef.current.imgW, sceneRef.current.imgH);
      redraw();
      return;
    }
    const ip = screenToImage(tRef.current, e.clientX - rect.left, e.clientY - rect.top);
    const hit = nearestKpt(sceneRef.current.gt, ip.x, ip.y, tRef.current.scale);
    selRef.current = hit;
    if (hit && (showNames || true)) {
      const kp = sceneRef.current.gt[hit.i].kpts[hit.k];
      setPopup({ x: e.clientX + 8, y: e.clientY - 8, text: `${KPT_NAMES[hit.k]}:${kp.v}` });
    } else setPopup(null);
    redraw();
  }

  const gtCount = active.instances.length;
  const predCount = 0;
  const VIEW_NAMES = ["GT+PRED", "GT only", "PRED only"];

  return (
    <div className="review">
      <div className="toolbar">
        <span>{active.stem}</span>
        <span style={{ color: GT_COLOR }}>GT({gtCount})</span>
        <span style={{ color: PRED_COLOR }}>PRED({predCount})</span>
        <span>view: {VIEW_NAMES[view]}</span>
        <div className="spacer" />
        <button onClick={() => void doAction("keep")}>keep (k)</button>
        <button onClick={() => void doAction("clear")}>clear (c)</button>
        <button onClick={() => void doAction("drop")}>drop (d)</button>
        {showNames && <span>names on</span>}
        {error && <span className="msg">{error}</span>}
      </div>
      <canvas
        ref={canvasRef} tabIndex={0} onKeyDown={onKeyDown} onWheel={onWheel}
        onMouseDown={onMouseDown} onMouseUp={onMouseUp} onMouseLeave={onMouseUp} onMouseMove={onMouseMove}
      />
      {popup && <div className="popup" style={{ left: popup.x, top: popup.y }}>{popup.text}</div>}
    </div>
  );
}
