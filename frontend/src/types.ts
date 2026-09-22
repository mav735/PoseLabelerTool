export type Kpt = [number, number, number];
export interface Instance { cx: number; cy: number; w: number; h: number; kpts: Kpt[]; }
export interface LabelPayload { stem: string; width: number; height: number; instances: Instance[]; lease_id?: number; }
export type Task = "bad" | "model" | "all";
export type Action = "keep" | "drop" | "clear" | "replace" | "edit";
export type View = 0 | 1 | 2;

export interface DatasetInfo {
  name: string;
  repo: string | null;
  revision: string;
  local: boolean;
  ready: boolean;
  sync_complete?: boolean;
  size_bytes: number;
  catalog_error?: string;
  auth_required?: boolean;
  pending_changes?: number;
  diverged?: boolean;
}
