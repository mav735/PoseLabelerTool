import { useState } from "react";
import "./app.css";
import { Login } from "./Login";
import { Picker } from "./Picker";
import { ReviewView } from "./ReviewView";
import { Tools } from "./Tools";
import { lease, isLeased } from "./api";
import type { LabelPayload, Task } from "./types";

type User = { user_id: number; username: string };

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [active, setActive] = useState<(LabelPayload & { lease_id: number }) | null>(null);
  const [message, setMessage] = useState<string>("");
  const [model, setModel] = useState("");
  const [showTools, setShowTools] = useState(false);

  async function onLease(t: Task) {
    if (!user) return;
    try {
      const r = await lease(t, user.user_id);
      if (isLeased(r)) { setTask(t); setActive(r); setMessage(""); }
      else setMessage("Pool is empty for this task.");
    } catch {
      setMessage("Network error — please try again.");
    }
  }

  if (!user) return <Login onLogin={setUser} />;
  if (!active || !task) {
    if (showTools) return <div className="panel"><button onClick={() => setShowTools(false)}>← back</button><Tools model={model} /></div>;
    return <Picker user={user} model={model} onModel={setModel} onLease={onLease} onTools={() => setShowTools(true)} message={message} />;
  }
  return (
    <ReviewView
      user={user} task={task} first={active} model={model}
      onExhausted={() => { setActive(null); setMessage("Pool is empty for this task."); }}
    />
  );
}
