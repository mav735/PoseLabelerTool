import type { Action } from "./types";

export function keyToAction(key: string): Action | null {
  const m: Record<string, Action> = { k: "keep", d: "drop", c: "clear", e: "edit" };
  return m[key] ?? null;
}

export function keyToView(key: string): "next" | "prev" | null {
  if (key === "v" || key === "ArrowRight") return "next";
  if (key === "ArrowLeft") return "prev";
  return null;
}
