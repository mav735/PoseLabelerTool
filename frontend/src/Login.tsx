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
    <div className="panel-wrap">
      <div className="panel">
        <h1>Pose Labeler</h1>
        {/* A visible label, not a placeholder: the placeholder disappears as
            soon as the field has content, and it was the only thing naming
            this input for a screen reader. */}
        <label htmlFor="login-username">
          username
          <input id="login-username" value={name} onChange={(e) => setName(e.target.value)}
                 autoFocus autoComplete="username"
                 onKeyDown={(e) => e.key === "Enter" && go()} />
        </label>
        <button onClick={go} disabled={busy}>{busy ? "Signing in…" : "Log in"}</button>
        {err && <p className="msg">{err}</p>}
      </div>
    </div>
  );
}
