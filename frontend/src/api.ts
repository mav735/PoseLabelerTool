import type { Action, DatasetInfo, Instance, Kpt, LabelPayload, Task } from "./types";

export type LeaseResp = (LabelPayload & { lease_id: number }) | { stem: null };

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export function login(username: string) {
  return post<{ user_id: number; username: string }>("/api/login", { username });
}

export function lease(dataset: string, task: Task, user_id: number) {
  return post<LeaseResp>("/api/lease", { dataset, task, user_id });
}

export function heartbeat(lease_id: number) {
  return post<{ ok: boolean }>("/api/heartbeat", { lease_id });
}

export function submit(body: {
  dataset: string; stem: string; task: Task; user_id: number; action: Action;
  instances?: { kpts: Kpt[] }[]; width?: number; height?: number;
}) {
  return post<{ next: (LabelPayload & { lease_id: number }) | null }>("/api/submit", body);
}

export function release(lease_id: number) {
  return post<{ ok: boolean }>("/api/release", { lease_id });
}

export function imageUrl(dataset: string, stem: string): string {
  return `/api/image/${stem}?dataset=${encodeURIComponent(dataset)}`;
}

export async function stats(dataset: string, task: Task): Promise<{ total: number; done: number; leased: number; todo: number }> {
  const res = await fetch(`/api/stats?dataset=${encodeURIComponent(dataset)}&task=${task}`);
  if (!res.ok) throw new Error(`/api/stats -> ${res.status}`);
  return res.json();
}

export function isLeased(r: LeaseResp): r is LabelPayload & { lease_id: number } {
  return (r as { stem: string | null }).stem !== null;
}

export function listModels(): Promise<{ name: string; path: string }[]> {
  return fetch("/api/models").then((r) => (r.ok ? r.json() : [])).catch(() => []);
}

export async function getPred(dataset: string, stem: string, model: string): Promise<{ kpts: [number, number, number][] }[]> {
  if (!model) return [];
  try {
    const res = await fetch(`/api/pred/${stem}?dataset=${encodeURIComponent(dataset)}&model=${encodeURIComponent(model)}`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export function startJob(dataset: string, type: "oracle" | "dedup", params: Record<string, unknown>): Promise<{ id: number; status: string }> {
  return fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dataset, type, params }) }).then((r) => r.json());
}
export function jobStatus(id: number): Promise<{
  id: number; status: string; processed: number; total: number;
  result?: unknown; message?: string;
  meta?: { rate_bps?: number; eta_seconds?: number | null;
           files_done?: number; files_total?: number };
}> {
  return fetch(`/api/jobs/${id}`).then((r) => r.json());
}
export function listJobs(): Promise<{
  id: number; dataset: string; type: string; status: string;
  processed: number; total: number;
  meta?: { rate_bps?: number; eta_seconds?: number | null;
           files_done?: number; files_total?: number };
}[]> {
  return fetch("/api/jobs").then((r) => (r.ok ? r.json() : [])).catch(() => []);
}

export function dedupNext(dataset: string, user_id: number): Promise<{ id: number | null; keeper?: string; dup?: string; diff?: number }> {
  return fetch("/api/dedup/next", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dataset, user_id }) }).then((r) => r.json());
}
export function dedupResolve(pair_id: number, action: "delete" | "keep"): Promise<{ ok: boolean }> {
  return fetch("/api/dedup/resolve", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pair_id, action }) }).then((r) => r.json());
}

export function listDatasets(): Promise<DatasetInfo[]> {
  return fetch("/api/datasets").then((r) => (r.ok ? r.json() : [])).catch(() => []);
}

export function addDataset(body: { name: string; repo?: string; revision?: string }) {
  return post<{ ok: boolean }>("/api/datasets", body);
}

export function startDatasetDownload(name: string): Promise<{ job_id: number }> {
  return post<{ job_id: number }>(`/api/datasets/${encodeURIComponent(name)}/download`, {});
}

export function startSync(name: string): Promise<{ job_id: number }> {
  return post<{ job_id: number }>(`/api/datasets/${encodeURIComponent(name)}/sync`, {});
}

// No UI component calls this yet; the row only shows the pending count from
// DatasetInfo. Kept ahead of a future pending-changes preview rather than
// forgotten, the same way startModelDownload is kept ahead of its UI.
export function listPending(name: string): Promise<{
  count: number; changes: { path: string; op: string; age_seconds: number }[];
}> {
  return fetch(`/api/datasets/${encodeURIComponent(name)}/pending`).then((r) => r.json());
}

// No UI component calls this yet; POST /api/models/{name}/download is specced
// and tested backend-side, and this is its natural client pair, kept
// deliberately ahead of the model-download UI rather than forgotten.
export function startModelDownload(name: string): Promise<{ job_id: number }> {
  return post<{ job_id: number }>(`/api/models/${encodeURIComponent(name)}/download`, {});
}

export type { Instance };
