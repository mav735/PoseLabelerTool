import { useEffect, useState } from "react";
import { stats as apiStats } from "./api";
import type { Task } from "./types";

const TASKS: { key: Task; label: string }[] = [
  { key: "bad", label: "Review bad" },
  { key: "model", label: "Review model" },
  { key: "all", label: "Review all" },
];

export function TaskStep({ dataset, task, onTask }: {
  dataset: string; task: Task | null; onTask: (t: Task) => void;
}) {
  const [todo, setTodo] = useState<Record<string, number>>({});
  useEffect(() => {
    if (!dataset) return;
    let cancelled = false;
    void Promise.all(TASKS.map((t) =>
      apiStats(dataset, t.key).then((s) => [t.key, s.todo] as const).catch(() => [t.key, 0] as const)
    )).then((pairs) => { if (!cancelled) setTodo(Object.fromEntries(pairs)); });
    return () => { cancelled = true; };
  }, [dataset]);

  return (
    <div className="step-body">
      {TASKS.map((t) => (
        <button key={t.key} className={task === t.key ? "sel" : ""}
                disabled={todo[t.key] === 0} onClick={() => onTask(t.key)}>
          {t.label} <span className="muted">{todo[t.key] ?? "…"} left</span>
        </button>
      ))}
    </div>
  );
}
