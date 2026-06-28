import type { Task } from "./types";
import type { LabelPayload } from "./types";

export function ReviewView(_props: {
  user: { user_id: number; username: string };
  task: Task;
  first: LabelPayload & { lease_id: number };
  onExhausted: () => void;
}) {
  return <div className="review">review</div>;
}
