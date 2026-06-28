import { useEffect, useState } from "react";
import { listModels } from "./api";
import type { Task } from "./types";

const TASKS: { key: Task; label: string }[] = [
  { key: "bad", label: "Review bad" },
  { key: "model", label: "Review model" },
  { key: "all", label: "Review all" },
];

export function Picker({ user, model, onModel, onLease, message }: {
  user: { user_id: number; username: string };
  model: string;
  onModel: (m: string) => void;
  onLease: (task: Task) => void;
  message?: string;
}) {
  const [models, setModels] = useState<{ name: string; path: string }[]>([]);
  useEffect(() => { listModels().then(setModels); }, []);
  return (
    <div className="panel">
      <h2>Hi {user.username} — pick a task</h2>
      <label className="muted">Model
        <select value={model} onChange={(e) => onModel(e.target.value)}>
          <option value="">(none)</option>
          {models.map((m) => <option key={m.path} value={m.path}>{m.path}</option>)}
        </select>
      </label>
      {TASKS.map((t) => <button key={t.key} onClick={() => onLease(t.key)}>{t.label}</button>)}
      {message && <p className="msg">{message}</p>}
    </div>
  );
}
