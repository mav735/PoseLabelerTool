import { KPT_NAMES } from "./constants";
import type { Instance } from "./types";

export function InstanceList({
  instances,
  selected,
  onSelect,
}: {
  instances: Instance[];
  selected: number | null;
  onSelect: (i: number | null) => void;
}) {
  return (
    <div className="instance-list">
      {instances.map((inst, i) => {
        const visibleCount = inst.kpts.filter((kpt) => kpt[2] > 0).length;
        const isSelected = selected === i;
        return (
          <button
            key={i}
            className={`instance-card${isSelected ? " selected" : ""}`}
            onClick={() => onSelect(isSelected ? null : i)}
          >
            <div className="card-header">
              <span className="player-name">Player {i + 1}</span>
              <span className="tag">GT</span>
            </div>
            <span className="vis-sub">{visibleCount}/15 vis</span>
            <div className="vis-strip">
              {inst.kpts.map((kpt, k) => (
                <span
                  key={k}
                  className="vis-dot"
                  style={{ backgroundColor: `var(--vis${kpt[2]})` }}
                  title={`${KPT_NAMES[k]}:${kpt[2]}`}
                />
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}
