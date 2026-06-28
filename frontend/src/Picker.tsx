import type { Task } from "./types";

const TASKS: { key: Task; label: string }[] = [
  { key: "bad", label: "Review bad" },
  { key: "model", label: "Review model" },
  { key: "all", label: "Review all" },
];

export function Picker({ user, onLease, message }: {
  user: { user_id: number; username: string };
  onLease: (task: Task) => void;
  message?: string;
}) {
  return (
    <div className="panel-wrap">
      <div className="panel">
        <h2>Hi {user.username} — pick a task</h2>
        {TASKS.map((t) => (
          <button key={t.key} onClick={() => onLease(t.key)}>{t.label}</button>
        ))}
        {message && <p className="msg">{message}</p>}
      </div>
    </div>
  );
}
