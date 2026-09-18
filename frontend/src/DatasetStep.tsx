import { useState } from "react";
import { addDataset } from "./api";
import type { DatasetInfo } from "./types";

function human(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0, n = bytes;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

export function DatasetStep({ dataset, rows, onDataset, onAdded }: {
  dataset: string; rows: DatasetInfo[]; onDataset: (name: string) => void; onAdded: () => void;
}) {
  const [name, setName] = useState("");
  const [repo, setRepo] = useState("");
  const [err, setErr] = useState("");

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
            <span className="ds-meta">{r.ready ? human(r.size_bytes) : r.local ? "missing images/" : "not downloaded"}</span>
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
