import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "./api";
import { TaskStep } from "./TaskStep";

function setup(props = {}) {
  return render(<TaskStep dataset="people-v3" task={null} onTask={vi.fn()} {...props} />);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("TaskStep", () => {
  it("shows each task's remaining count", async () => {
    vi.spyOn(api, "stats").mockResolvedValue({ total: 10, done: 2, leased: 0, todo: 8 });
    setup();
    await waitFor(() => expect(screen.getAllByText("8 left")).toHaveLength(3));
    expect(screen.getByRole("button", { name: /review all/i })).toBeEnabled();
  });

  it("disables a task whose pool is genuinely empty", async () => {
    vi.spyOn(api, "stats").mockResolvedValue({ total: 10, done: 10, leased: 0, todo: 0 });
    setup();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /review all/i })).toBeDisabled());
    expect(screen.getAllByText("0 left")).toHaveLength(3);
  });

  it("does not claim zero, or disable, when the count could not be fetched", async () => {
    vi.spyOn(api, "stats").mockRejectedValue(new Error("500"));
    setup();
    await waitFor(() => expect(screen.getAllByText("count unavailable")).toHaveLength(3));
    expect(screen.queryByText("0 left")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /review all/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /review bad/i })).toBeEnabled();
  });
});
