import type React from "react";
import { KPT_NAMES, VIS_COLORS } from "./constants";
import { EyeButton } from "./EyeButton";

export function InstanceCard({ label, source, vs, selected, onSelect, draggable, onDragStart, hidden, onToggleHide }: {
  label: string;
  source: "gt" | "pred";
  vs: number[];
  selected?: boolean;
  onSelect?: () => void;
  draggable?: boolean;
  onDragStart?: (e: React.DragEvent) => void;
  hidden?: boolean;
  onToggleHide?: () => void;
}) {
  const visCount = vs.filter((v) => v > 0).length;
  return (
    <div className={`inst ${source}${selected ? " sel" : ""}${hidden ? " hidden" : ""}`} onClick={onSelect}
         draggable={draggable} onDragStart={onDragStart}>
      <div className="inst-row">
        <span className={`tag ${source}`}>{source === "gt" ? "GT" : "PRED"}</span>
        <span className="inst-label">{label}</span>
        <span className="mono inst-vis">{visCount}/15</span>
        {onToggleHide && <EyeButton on={!hidden} onToggle={onToggleHide} />}
      </div>
      <div className="strip">
        {vs.map((v, k) => <span key={k} className="dot" style={{ background: VIS_COLORS[v] }} title={`${KPT_NAMES[k]}:${v}`} />)}
      </div>
    </div>
  );
}
