import { InstanceCard } from "./InstanceCard";
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
      {instances.map((inst, i) => (
        <InstanceCard
          key={i}
          label={`Player ${i + 1}`}
          source="gt"
          vs={inst.kpts.map((k) => k[2])}
          selected={selected === i}
          onSelect={() => onSelect(selected === i ? null : i)}
        />
      ))}
    </div>
  );
}
