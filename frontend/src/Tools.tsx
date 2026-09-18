import { useRef, useState, useEffect } from "react";
import { jobStatus, startJob } from "./api";

type Status = { status: string; processed: number; total: number; result?: unknown } | null;

export function Tools({ dataset, model }: { dataset: string; model: string }) {
  const [oracleMode, setOracleMode] = useState("a");
  const [oracleThr, setOracleThr] = useState("0.3");
  const [dedupPool, setDedupPool] = useState("all");
  const [dedupThr, setDedupThr] = useState("3.0");
  const [status, setStatus] = useState<Status>(null);
  const [running, setRunning] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => () => { if (timer.current) window.clearInterval(timer.current); }, []);

  async function pollOnce(id: number) {
    const s = await jobStatus(id);
    setStatus(s);
    if (s.status === "done" || s.status === "error") {
      if (timer.current) window.clearInterval(timer.current);
      setRunning(false);
    }
  }

  function poll(id: number) {
    void pollOnce(id);
    timer.current = window.setInterval(() => void pollOnce(id), 1500);
  }

  async function launch(type: "oracle" | "dedup", params: Record<string, unknown>) {
    if (running) return;
    setRunning(true);
    setStatus({ status: "queued", processed: 0, total: 0 });
    try {
      const { id } = await startJob(dataset, type, params);
      poll(id);
    } catch {
      setStatus({ status: "error", processed: 0, total: 0 });
      setRunning(false);
    }
  }

  const pct = status && status.total ? Math.round((status.processed / status.total) * 100) : 0;
  return (
    <div className="panel">
      <h2>Tools</h2>
      <fieldset>
        <legend>Oracle (flag bad labels)</legend>
        <label>mode
          <select value={oracleMode} onChange={(e) => setOracleMode(e.target.value)}>
            <option value="a">A · find_bad_labels</option>
            <option value="b">B · max-dist</option>
          </select>
        </label>
        <label>threshold <input value={oracleThr} onChange={(e) => setOracleThr(e.target.value)} /></label>
        <button disabled={running || !model} onClick={() => launch("oracle", { model, mode: oracleMode, threshold: parseFloat(oracleThr) })}>Run oracle</button>
      </fieldset>
      <fieldset>
        <legend>Dedup (find duplicates)</legend>
        <label>pool
          <select value={dedupPool} onChange={(e) => setDedupPool(e.target.value)}>
            <option value="all">all</option><option value="model">model_labeled</option><option value="bad">bad_labels</option>
          </select>
        </label>
        <label>thresh <input value={dedupThr} onChange={(e) => setDedupThr(e.target.value)} /></label>
        <button disabled={running} onClick={() => launch("dedup", { pool: dedupPool, thresh: parseFloat(dedupThr) })}>Run dedup</button>
      </fieldset>
      {status && (
        <div className="jobstatus">
          <div className="mono">{status.status} — {status.processed}/{status.total} ({pct}%)</div>
          <div className="bar"><div className="fill" style={{ width: `${pct}%` }} /></div>
        </div>
      )}
    </div>
  );
}
