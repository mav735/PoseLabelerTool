import { useCallback, useEffect, useState } from "react";
import { dedupNext, dedupResolve, imageUrl } from "./api";

type Pair = { id: number | null; keeper?: string; dup?: string; diff?: number };

export function DedupReview({ user }: { user: { user_id: number; username: string } }) {
  const [pair, setPair] = useState<Pair | null>(null);

  const load = useCallback(async () => { setPair(await dedupNext(user.user_id)); }, [user.user_id]);
  useEffect(() => { void load(); }, [load]);

  const resolve = useCallback(async (action: "delete" | "keep") => {
    if (!pair || pair.id == null) return;
    await dedupResolve(pair.id, action);
    void load();
  }, [pair, load]);

  if (!pair) return <div className="panel">Loading…</div>;
  if (pair.id == null) return <div className="panel">No duplicates to review.</div>;

  return (
    <div className="dedup" tabIndex={0} onKeyDown={(e) => { if (e.key === "d") void resolve("delete"); if (e.key === "k") void resolve("keep"); }}>
      <div className="dedup-head mono">diff {pair.diff?.toFixed(2)} — keep {pair.keeper}</div>
      <div className="dedup-imgs">
        <figure><img src={imageUrl(pair.keeper!)} alt="keeper" /><figcaption>keeper {pair.keeper}</figcaption></figure>
        <figure><img src={imageUrl(pair.dup!)} alt="duplicate" /><figcaption>duplicate {pair.dup}</figcaption></figure>
      </div>
      <div className="actionbar">
        <button onClick={() => void resolve("delete")}>Delete dup <kbd>d</kbd></button>
        <button onClick={() => void resolve("keep")}>Keep both <kbd>k</kbd></button>
      </div>
    </div>
  );
}
