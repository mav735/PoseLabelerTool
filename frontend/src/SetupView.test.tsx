import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "./api";
import { SetupView } from "./SetupView";

const user = { user_id: 1, username: "alexander" };
const ready = { name: "people-v3", repo: null, revision: "main", local: true, ready: true, size_bytes: 4 };
const notReady = { name: "hands-v1", repo: "a/b", revision: "main", local: false, ready: false, size_bytes: 0 };

function setup(props = {}) {
  return render(
    <SetupView user={user} dataset="" model="" task={null}
      onDataset={vi.fn()} onModel={vi.fn()} onTask={vi.fn()}
      onStart={vi.fn()} onTools={vi.fn()} onDedup={vi.fn()} {...props} />);
}

beforeEach(() => {
  vi.spyOn(api, "listDatasets").mockResolvedValue([ready, notReady]);
  vi.spyOn(api, "listModels").mockResolvedValue([{ name: "y.pt", path: "y.pt" }]);
  vi.spyOn(api, "stats").mockResolvedValue({ total: 10, done: 2, leased: 0, todo: 8 });
});

describe("SetupView", () => {
  it("lists datasets with their readiness", async () => {
    setup();
    expect(await screen.findByText("people-v3")).toBeInTheDocument();
    expect(screen.getByText("hands-v1")).toBeInTheDocument();
  });

  it("locks the model and task steps until a dataset is ready", async () => {
    setup();
    await screen.findByText("people-v3");
    expect(screen.getByTestId("step-model")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("step-task")).toHaveAttribute("aria-disabled", "true");
  });

  it("unlocks the later steps once a ready dataset is chosen", async () => {
    setup({ dataset: "people-v3" });
    await screen.findByText("people-v3");
    expect(screen.getByTestId("step-task")).toHaveAttribute("aria-disabled", "false");
  });

  it("does not let an unready dataset be chosen", async () => {
    const onDataset = vi.fn();
    setup({ onDataset });
    await userEvent.click(await screen.findByText("hands-v1"));
    expect(onDataset).not.toHaveBeenCalled();
  });

  it("disables Start until a dataset and task are chosen", async () => {
    setup({ dataset: "people-v3" });
    await screen.findByText("people-v3");
    expect(screen.getByRole("button", { name: /start reviewing/i })).toBeDisabled();
  });

  it("enables Start when both are chosen", async () => {
    setup({ dataset: "people-v3", task: "all" });
    await screen.findByText("people-v3");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /start reviewing/i })).toBeEnabled());
  });
});
