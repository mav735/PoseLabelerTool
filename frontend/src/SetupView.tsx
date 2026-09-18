import { useEffect, useState } from "react";
import { listDatasets } from "./api";
import { DatasetStep } from "./DatasetStep";
import { ModelStep } from "./ModelStep";
import { TaskStep } from "./TaskStep";
import type { DatasetInfo, Task } from "./types";

type Step = 1 | 2 | 3;

export function SetupView({ user, dataset, model, task, onDataset, onModel,
                            onTask, onStart, onTools, onDedup, message }: {
  user: { user_id: number; username: string };
  dataset: string; model: string; task: Task | null;
  onDataset: (d: string) => void; onModel: (m: string) => void;
  onTask: (t: Task) => void; onStart: () => void;
  onTools: () => void; onDedup: () => void; message?: string;
}) {
  const [open, setOpen] = useState<Step>(dataset ? 3 : 1);
  const [rows, setRows] = useState<DatasetInfo[]>([]);
  const refresh = () => listDatasets().then(setRows);
  useEffect(() => { void refresh(); }, []);

  const current = rows.find((r) => r.name === dataset);
  const ready = Boolean(dataset) && Boolean(current?.ready);
  const canStart = ready && task !== null;

  function header(n: Step, label: string, summary: string, locked: boolean) {
    return (
      <div className="step-head" data-testid={`step-${["", "dataset", "model", "task"][n]}`}
           aria-disabled={locked ? "true" : "false"}
           onClick={() => !locked && setOpen(n)}>
        <span className="step-mark">{summary ? "✓" : open === n ? "▼" : "▸"}</span>
        <b>{n} · {label}</b>
        <span className="step-summary">{locked ? "locked" : summary}</span>
      </div>
    );
  }

  return (
    <div className="panel-wrap">
      <div className="panel setup">
        <h2>Hi {user.username}</h2>

        {header(1, "Dataset", open === 1 ? "" : dataset, false)}
        {open === 1 && <DatasetStep dataset={dataset} rows={rows} onAdded={refresh}
          onDataset={(d) => { onDataset(d); setOpen(2); }} />}

        {header(2, "Model", open === 2 ? "" : (model || "(none)"), !ready)}
        {open === 2 && ready && <ModelStep model={model}
          onModel={(m) => { onModel(m); setOpen(3); }} />}

        {header(3, "Task", open === 3 ? "" : (task ?? ""), !ready)}
        {open === 3 && ready && <TaskStep dataset={dataset} task={task} onTask={onTask} />}

        <button className="primary" disabled={!canStart} onClick={onStart}>
          Start reviewing
        </button>
        <div className="setup-foot">
          <span className="muted">{dataset ? `Dataset: ${dataset}` : "no dataset"}</span>
          <button onClick={onTools}>Tools</button>
          <button onClick={onDedup}>Dedup</button>
        </div>
        {message && <p className="msg">{message}</p>}
      </div>
    </div>
  );
}
