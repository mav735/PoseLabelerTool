import { useState } from "react";
import { login } from "./api";

export function Login({ onLogin }: { onLogin: (u: { user_id: number; username: string }) => void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function go() {
    if (!name.trim() || busy) return;
    setBusy(true);
    setErr("");
    try { onLogin(await login(name.trim())); }
    catch { setErr("Login failed — please try again."); }
    finally { setBusy(false); }
  }
  return (
    <div className="panel">
      <h1>Pose Labeler</h1>
      <input placeholder="username" value={name} onChange={(e) => setName(e.target.value)}
             onKeyDown={(e) => e.key === "Enter" && go()} />
      <button onClick={go} disabled={busy}>Log in</button>
      {err && <p className="msg">{err}</p>}
    </div>
  );
}
