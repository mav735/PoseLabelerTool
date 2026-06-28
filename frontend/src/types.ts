export type Kpt = [number, number, number];
export interface Instance { cx: number; cy: number; w: number; h: number; kpts: Kpt[]; }
export interface LabelPayload { stem: string; width: number; height: number; instances: Instance[]; lease_id?: number; }
export type Task = "bad" | "model" | "all";
export type Action = "keep" | "drop" | "clear" | "replace" | "edit";
export type View = 0 | 1 | 2;
