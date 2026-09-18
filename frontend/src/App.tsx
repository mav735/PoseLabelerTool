import { useEffect, useState } from "react";
import "./app.css";
import { Login } from "./Login";
import { SetupView } from "./SetupView";
import { ReviewView } from "./ReviewView";
import { Tools } from "./Tools";
import { DedupReview } from "./DedupReview";
import { lease, isLeased } from "./api";
import type { LabelPayload, Task } from "./types";

type User = { user_id: number; username: string };

const KEY = "plt.session";

function restore(): { dataset: string; model: string; task: Task | null } {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { dataset: "", model: "", task: null, ...JSON.parse(raw) };
  } catch { /* storage unavailable or corrupt — fall through */ }
  return { dataset: "", model: "", task: null };
}

export function App() {
  const initial = restore();
  const [user, setUser] = useState<User | null>(null);
  const [dataset, setDataset] = useState(initial.dataset);
  const [model, setModel] = useState(initial.model);
  const [task, setTask] = useState<Task | null>(initial.task);
  const [active, setActive] = useState<(LabelPayload & { lease_id: number }) | null>(null);
  const [message, setMessage] = useState("");
  const [showTools, setShowTools] = useState(false);
  const [showDedup, setShowDedup] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify({ dataset, model, task })); }
    catch { /* ignore — storage unavailable */ }
  }, [dataset, model, task]);

  async function onStart() {
    if (!user || !dataset || !task) return;
    try {
      const r = await lease(dataset, task, user.user_id);
      if (isLeased(r)) { setActive(r); setMessage(""); }
      else setMessage("Pool is empty for this task.");
    } catch {
      setMessage("Network error — please try again.");
    }
  }

  if (!user) return <Login onLogin={setUser} />;
  if (!active || !task) {
    if (showTools) return <div className="panel-wrap"><div className="panel">
      <button onClick={() => setShowTools(false)}>← back</button>
      <Tools dataset={dataset} model={model} /></div></div>;
    if (showDedup) return <div className="panel-wrap"><div className="panel">
      <button onClick={() => setShowDedup(false)}>← back</button>
      <DedupReview dataset={dataset} user={user} /></div></div>;
    return <SetupView user={user} dataset={dataset} model={model} task={task}
      onDataset={setDataset} onModel={setModel} onTask={setTask}
      onStart={onStart} onTools={() => setShowTools(true)}
      onDedup={() => setShowDedup(true)} message={message} />;
  }
  return (
    <ReviewView
      user={user} dataset={dataset} task={task} first={active} model={model}
      onExhausted={() => { setActive(null); setMessage("Pool is empty for this task."); }}
    />
  );
}
