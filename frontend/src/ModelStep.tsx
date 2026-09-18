import { useEffect, useState } from "react";
import { listModels } from "./api";

export function ModelStep({ model, onModel }: {
  model: string; onModel: (m: string) => void;
}) {
  const [models, setModels] = useState<{ name: string; path: string }[]>([]);
  useEffect(() => { void listModels().then(setModels); }, []);
  return (
    <div className="step-body">
      <select value={model} onChange={(e) => onModel(e.target.value)}>
        <option value="">(none)</option>
        {models.map((m) => <option key={m.path} value={m.path}>{m.path}</option>)}
      </select>
      {!model && <p className="muted">Without a model the PRED overlay and the oracle are unavailable.</p>}
    </div>
  );
}
