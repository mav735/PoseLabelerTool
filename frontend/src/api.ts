import type { Action, Instance, Kpt, LabelPayload, Task } from "./types";

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

export function lease(task: Task, user_id: number) {
  return post<LeaseResp>("/api/lease", { task, user_id });
}

export function heartbeat(lease_id: number) {
  return post<{ ok: boolean }>("/api/heartbeat", { lease_id });
}

export function submit(body: {
  stem: string; task: Task; user_id: number; action: Action;
  instances?: { kpts: Kpt[] }[]; width?: number; height?: number;
}) {
  return post<{ next: (LabelPayload & { lease_id: number }) | null }>("/api/submit", body);
}

export function release(lease_id: number) {
  return post<{ ok: boolean }>("/api/release", { lease_id });
}

export async function getLabel(stem: string): Promise<LabelPayload> {
  const res = await fetch(`/api/label/${stem}`);
  if (!res.ok) throw new Error(`label ${stem} -> ${res.status}`);
  return res.json();
}

export function imageUrl(stem: string): string {
  return `/api/image/${stem}`;
}

export function isLeased(r: LeaseResp): r is LabelPayload & { lease_id: number } {
  return (r as { stem: string | null }).stem !== null;
}

export type { Instance };
