import { useEffect, useRef, useState } from "react";
import { addDataset, startDatasetDownload, startSync, jobStatus, listJobs } from "./api";
import type { DatasetInfo } from "./types";

export function human(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, n = bytes;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

type Progress = { pct: number; done: number; total: number; rate: number;
                  eta: number | null; status: string };

export function DatasetStep({ dataset, rows, onDataset, onAdded }: {
  dataset: string; rows: DatasetInfo[]; onDataset: (name: string) => void; onAdded: () => void;
}) {
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [err, setErr] = useState("");
  const [dl, setDl] = useState<Record<string, Progress>>({});
  const timers = useRef<Record<string, number>>({});

  useEffect(() => () => {
    Object.values(timers.current).forEach((t) => window.clearInterval(t));
  }, []);

  async function poll(name: string, id: number) {
    const s = await jobStatus(id);
    const pct = s.total ? Math.round((s.processed / s.total) * 100) : 0;
    setDl((d) => ({ ...d, [name]: {
      pct, done: s.processed, total: s.total, rate: s.meta?.rate_bps ?? 0,
      eta: s.meta?.eta_seconds ?? null, status: s.status } }));
    if (s.status === "done" || s.status === "error") {
      window.clearInterval(timers.current[name]);
      delete timers.current[name];
      if (s.status === "done") {
        setDl((d) => { const { [name]: _done, ...rest } = d; return rest; });
      }
      onAdded();                       // refresh rows: the dataset may now be ready
    }
  }

  function track(name: string, id: number) {
    if (timers.current[name]) return;          // already tracking this row
    void poll(name, id);
    timers.current[name] = window.setInterval(() => void poll(name, id), 1500);
  }

  useEffect(() => {
    let cancelled = false;
    void listJobs().then((jobs) => {
      if (cancelled) return;
      for (const j of jobs) {
        if (j.type === "download" && (j.status === "queued" || j.status === "running")) {
          track(j.dataset, j.id);
        }
      }
    });
    return () => { cancelled = true; };
  }, []);

  async function download(name: string) {
    try {
      const { job_id } = await startDatasetDownload(name);
      track(name, job_id);
    } catch {
      setErr("Could not start that download.");
    }
  }

  async function sync(name: string) {
    try {
      await startSync(name);
      onAdded();
    } catch {
      setErr("Could not start that sync.");
    }
  }

  async function add() {
    if (!name.trim()) return;
    try {
      await addDataset({ name: name.trim(), repo: repo.trim() || undefined });
      setName(""); setRepo(""); setErr("");
      onAdded();
    } catch (e) {
      const status = e instanceof Error ? e.message : "";
      if (status.includes("409")) setErr("A dataset with that name already exists.");
      else if (status.includes("400")) setErr("That name or repo isn't valid.");
      else setErr("Could not add that repo.");
    }
  }

  return (
    <div className="step-body">
      <ul className="ds-list">
        {rows.map((r) => (
          <li key={r.name}
              className={`ds-row${r.name === dataset ? " sel" : ""}${r.ready ? "" : " off"}`}
              role="button"
              aria-disabled={r.ready ? "false" : "true"}
              // an unready row is not activatable, so tab must not stop on it
              tabIndex={r.ready ? 0 : -1}
              onClick={() => r.ready && onDataset(r.name)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" && e.key !== " ") return;
                e.preventDefault();          // Space would scroll the panel
                if (r.ready) onDataset(r.name);
              }}>
            <span className="ds-dot">{r.ready ? "●" : "○"}</span>
            <span className="ds-name">{r.name}</span>
            <span className="ds-meta">{
              r.ready ? human(r.size_bytes)
              : r.sync_complete === false ? "download incomplete"
              : r.local ? "missing images/"
              : "not downloaded"
            }</span>
            {r.auth_required && <span className="ds-meta">no HF token configured</span>}
            {r.diverged && <span className="ds-meta">diverged — remote moved, sync paused</span>}
            {!r.diverged && (r.pending_changes ?? 0) > 0 && (
              <>
                <span className="ds-meta">{r.pending_changes} unsynced</span>
                <button onClick={(e) => { e.stopPropagation(); void sync(r.name); }}>Sync now</button>
              </>
            )}
            {!r.ready && r.repo && !r.auth_required && !dl[r.name] && (
              <button onClick={(e) => { e.stopPropagation(); void download(r.name); }}>
                Download
              </button>
            )}
            {dl[r.name] && (
              <span className="ds-meta">
                {dl[r.name].status === "error" ? "download failed" :
                 `${dl[r.name].pct}% · ${human(dl[r.name].done)} / ${human(dl[r.name].total)}` +
                 (dl[r.name].rate > 0 ? ` · ${human(dl[r.name].rate)}/s` : "") +
                 (dl[r.name].eta !== null ? ` · ${dl[r.name].eta}s left` : "")}
              </span>
            )}
          </li>
        ))}
      </ul>
      {rows.some((r) => r.catalog_error) && (
        <p className="msg">Catalog problem: {rows.find((r) => r.catalog_error)!.catalog_error}</p>
      )}
      <div className="ds-add">
        <input placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="owner/repo (optional)" value={repo} onChange={(e) => setRepo(e.target.value)} />
        <button onClick={() => void add()}>+ Add repo</button>
      </div>
      {err && <p className="msg">{err}</p>}
    </div>
  );
}
