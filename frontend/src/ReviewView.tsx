import { useCallback, useEffect, useRef, useState } from "react";
import { getPred, heartbeat, imageUrl, release, stats as apiStats, submit } from "./api";
import { KPT_NAMES } from "./constants";
import { fitBox, type EInstance } from "./editor";
import { InstanceList } from "./InstanceList";
import { PoseEditor } from "./PoseEditor";
import { denormGT, drawOverlay, nearestKpt, type Scene } from "./render";
import { panBy, reset, screenToImage, zoomAt, type Transform } from "./transform";
import { keyToAction, keyToView } from "./keys";
import type { LabelPayload, Task, View } from "./types";

type Active = LabelPayload & { lease_id: number };
type Stats = { total: number; done: number; leased: number; todo: number };

export function ReviewView({ user, task, first, onExhausted, model = "" }: {
  user: { user_id: number; username: string };
  task: Task;
  first: Active;
  onExhausted: () => void;
  model?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [active, setActive] = useState<Active>(first);
  const [editing, setEditing] = useState<{ gt: EInstance[]; pred: EInstance[] } | null>(null);
  const [view, setView] = useState<View>(0);
  const [showNames, setShowNames] = useState(false);
  const [popup, setPopup] = useState<{ x: number; y: number; text: string } | null>(null);
  const [error, setError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [predCount, setPredCount] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null);
  const tRef = useRef<Transform>({ scale: 1, tx: 0, ty: 0 });
  const sceneRef = useRef<Scene>({ gt: [], pred: [], imgW: first.width, imgH: first.height });
  const selRef = useRef<{ i: number; k: number } | null>(null);
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const leaseRef = useRef(first.lease_id);
  const busyRef = useRef(false);
  const savingRef = useRef(false);
  // Always-current redraw ref so loadStem's img.onload stays up to date
  const redrawRef = useRef<() => void>(() => {});

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const img = imgRef.current;
    const t = tRef.current;
    if (img) ctx.drawImage(img, t.tx, t.ty, img.width * t.scale, img.height * t.scale);
    drawOverlay(ctx, t, sceneRef.current, view, selRef.current, selected);
  }, [view, selected]);

  // Keep redrawRef pointing at the latest redraw closure
  useEffect(() => { redrawRef.current = redraw; });

  const loadStem = useCallback((a: Active) => {
    const canvas = canvasRef.current!;
    canvas.focus();
    sceneRef.current = { gt: denormGT(a.instances, a.width, a.height), pred: [], imgW: a.width, imgH: a.height };
    setPredCount(0);
    if (model) {
      getPred(a.stem, model).then((raw) => {
        const pred = raw.map((p) => {
          const kpts = p.kpts.map(([x, y, v]) => ({ x, y, v }));
          const box = fitBox(kpts.map((k) => ({ x: k.x, y: k.y, v: k.v })), a.width, a.height);
          return { kpts, box };
        });
        sceneRef.current = { ...sceneRef.current, pred };
        setPredCount(pred.length);
        redrawRef.current();
      });
    }
    tRef.current = reset(canvas.width, canvas.height, a.width, a.height);
    const img = new Image();
    img.onload = () => { imgRef.current = img; redrawRef.current(); };
    img.src = imageUrl(a.stem);
    imgRef.current = null;
    redrawRef.current();
  }, []);

  const fetchStats = useCallback(async () => {
    try { setStats(await apiStats(task)); } catch { /* ignore */ }
  }, [task]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    canvas.width = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
    loadStem(active);
    void fetchStats();
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
    setSelected(null);
    loadStem(next);
  }, [loadStem, onExhausted]);

  const doAction = useCallback(async (action: "keep" | "drop" | "clear") => {
    if (busyRef.current) return;
    busyRef.current = true;
    setError("");
    try {
      const r = await submit({ stem: active.stem, task, user_id: user.user_id, action });
      advance(r.next);
      void fetchStats();
    } catch {
      setError("Action failed — please try again.");
    } finally {
      busyRef.current = false;
    }
  }, [active.stem, task, user.user_id, advance, fetchStats]);

  const saveEdit = useCallback(async (gt: EInstance[]) => {
    if (savingRef.current) return;
    savingRef.current = true;
    setSaveError("");
    const instances = gt
      .filter((i) => i.kpts.some((k) => k.v > 0))
      .map((i) => ({ kpts: i.kpts.map((k) => [k.x, k.y, k.v] as [number, number, number]) }));
    try {
      const r = await submit({ stem: active.stem, task, user_id: user.user_id, action: "edit", instances, width: active.width, height: active.height });
      setEditing(null);
      advance(r.next);
      void fetchStats();
    } catch {
      setSaveError("Save failed — please try again.");
    } finally {
      savingRef.current = false;
    }
  }, [active, task, user.user_id, advance, fetchStats]);

  const openEditor = useCallback(async () => {
    const gtPx = denormGT(active.instances, active.width, active.height)
      .map((s) => ({ kpts: s.kpts.map((k) => ({ x: k.x, y: k.y, v: k.v })), box: s.box, source: "gt" as const }));
    const predRaw = await getPred(active.stem, model);
    const predPx: EInstance[] = predRaw.map((p) => {
      const kpts = Array.from({ length: 15 }, (_, k) => {
        const t = p.kpts[k];
        return t ? { x: t[0], y: t[1], v: t[2] } : { x: 0, y: 0, v: 0 };
      });
      return { kpts, box: fitBox(kpts, active.width, active.height), source: "pred" as const };
    });
    setEditing({ gt: gtPx, pred: predPx });
  }, [active, model]);

  useEffect(() => { redraw(); }, [view, showNames, redraw]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "0") {
      const c = canvasRef.current!;
      tRef.current = reset(c.width, c.height, sceneRef.current.imgW, sceneRef.current.imgH);
      redraw(); return;
    }
    if (e.key === "h") { setShowNames((s) => !s); return; }
    const vk = keyToView(e.key);
    if (vk) { setView((v) => ((vk === "next" ? v + 1 : v + 2) % 3) as View); return; }
    const action = keyToAction(e.key);
    if (action === "keep" || action === "drop" || action === "clear") { void doAction(action); return; }
    if (action === "edit") { void openEditor(); return; }
  }

  function onWheel(e: React.WheelEvent) {
    const c = canvasRef.current!;
    const rect = c.getBoundingClientRect();
    const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.25 : 1 / 1.25;
    tRef.current = zoomAt(tRef.current, sx, sy, factor, c.width, c.height, sceneRef.current.imgW, sceneRef.current.imgH);
    redraw();
  }

  function onMouseDown(e: React.MouseEvent) { dragRef.current = { x: e.clientX, y: e.clientY }; }
  function onMouseUp() { dragRef.current = null; }
  function onMouseMove(e: React.MouseEvent) {
    const c = canvasRef.current!;
    const rect = c.getBoundingClientRect();
    if (dragRef.current) {
      const dx = e.clientX - dragRef.current.x, dy = e.clientY - dragRef.current.y;
      dragRef.current = { x: e.clientX, y: e.clientY };
      tRef.current = panBy(tRef.current, dx, dy, c.width, c.height, sceneRef.current.imgW, sceneRef.current.imgH);
      redraw(); return;
    }
    const ip = screenToImage(tRef.current, e.clientX - rect.left, e.clientY - rect.top);
    const hit = nearestKpt(sceneRef.current.gt, ip.x, ip.y, tRef.current.scale);
    selRef.current = hit;
    if (hit) {
      const kp = sceneRef.current.gt[hit.i].kpts[hit.k];
      setPopup({ x: e.clientX + 8, y: e.clientY - 8, text: `${KPT_NAMES[hit.k]}:${kp.v}` });
    } else setPopup(null);
    redraw();
  }

  const pct = stats && stats.total > 0 ? (stats.done / stats.total) * 100 : 0;
  const VIEW_NAMES = ["GT", "PRED", "Clear"] as const;

  return (
    <>
      <div className="review">
        {/* ── Topbar ── */}
        <div className="topbar">
          <span className="task-chip">{task}</span>
          <span className="stem">{active.stem}</span>
          <div className="progress-block">
            <span className="progress-label">
              {stats ? `${stats.done.toLocaleString()} / ${stats.total.toLocaleString()} reviewed` : "—"}
            </span>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <div className="view-control">
            {VIEW_NAMES.map((label, i) => (
              <button
                key={label}
                className={view === i ? "active" : ""}
                onClick={() => setView(i as View)}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="username">{user.username}</span>
        </div>

        {/* ── Canvas wrap ── */}
        <div className="canvas-wrap">
          <canvas
            ref={canvasRef}
            tabIndex={0}
            onKeyDown={onKeyDown}
            onWheel={onWheel}
            onMouseDown={onMouseDown}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
            onMouseMove={onMouseMove}
          />
          {popup && (
            <div className="popup" style={{ left: popup.x, top: popup.y }}>
              {popup.text}
            </div>
          )}
        </div>

        {/* ── Sidebar ── */}
        <div className="sidebar">
          <div className="sidebar-header">
            <span>Instances</span>
            <span className="badge">{active.instances.length}</span>
          </div>
          {active.instances.length === 0 ? (
            <p className="empty-state">No instances — background frame.</p>
          ) : (
            <InstanceList
              instances={active.instances}
              selected={selected}
              onSelect={(i) => { setSelected(i); redrawRef.current(); }}
            />
          )}
        </div>

        {/* ── Action bar ── */}
        <div className="actionbar">
          <button className="action-btn keep" onClick={() => void doAction("keep")}>
            <span className="dot" />Keep<kbd>K</kbd>
          </button>
          <button className="action-btn clear" onClick={() => void doAction("clear")}>
            <span className="dot" />Clear<kbd>C</kbd>
          </button>
          <button className="action-btn drop" onClick={() => void doAction("drop")}>
            <span className="dot" />Drop<kbd>D</kbd>
          </button>
          <span className="action-divider" />
          <button className="ghost-btn" onClick={() => void openEditor()}>Edit <kbd>E</kbd></button>
          <span className="pred-chip">PRED({predCount})</span>
          <div className="spacer" />
          {error && <span className="msg">{error}</span>}
          <span className="hint">← → view · 0 reset · h names</span>
        </div>
      </div>
      {editing && (
        <div className="editor-overlay">
          <PoseEditor
            stem={active.stem} imgW={active.width} imgH={active.height}
            gt0={editing.gt} pred0={editing.pred}
            onSave={saveEdit} onCancel={() => { setEditing(null); canvasRef.current?.focus(); }}
          />
          {saveError && <div className="save-error">{saveError}</div>}
        </div>
      )}
    </>
  );
}
