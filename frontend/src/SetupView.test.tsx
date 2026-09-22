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
  vi.spyOn(api, "listJobs").mockResolvedValue([]);
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
    await screen.findByText("people-v3 · 4 B");
    expect(screen.getByTestId("step-task")).toHaveAttribute("aria-disabled", "false");
  });

  it("shows the dataset name and size in the collapsed step and the footer", async () => {
    setup({ dataset: "people-v3" });
    expect(await screen.findByText("people-v3 · 4 B")).toBeInTheDocument();  // collapsed step 1
    expect(screen.getByText(/^Dataset: people-v3 · 4 B$/)).toBeInTheDocument();  // footer
  });

  it("omits the size for a catalogued-but-absent dataset", async () => {
    setup({ dataset: "hands-v1" });
    expect(await screen.findAllByText("hands-v1")).not.toHaveLength(0);
    expect(screen.queryByText(/hands-v1 ·/)).not.toBeInTheDocument();
  });

  it("does not let an unready dataset be chosen", async () => {
    const onDataset = vi.fn();
    setup({ onDataset });
    await userEvent.click(await screen.findByText("hands-v1"));
    expect(onDataset).not.toHaveBeenCalled();
  });

  it("disables Start until a dataset and task are chosen", async () => {
    setup({ dataset: "people-v3" });
    await screen.findByText("people-v3 · 4 B");
    expect(screen.getByRole("button", { name: /start reviewing/i })).toBeDisabled();
  });

  it("enables Start when both are chosen", async () => {
    setup({ dataset: "people-v3", task: "all" });
    await screen.findByText("people-v3 · 4 B");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /start reviewing/i })).toBeEnabled());
  });

  const downloadable = { name: "hands-v1", repo: "a/b", revision: "main",
                         local: false, ready: false, size_bytes: 0 };
  const needsAuth = { ...downloadable, name: "locked", auth_required: true };

  it("offers a download for a catalogued dataset that is not local", async () => {
    vi.spyOn(api, "listDatasets").mockResolvedValue([downloadable]);
    setup();
    expect(await screen.findByRole("button", { name: "Download" })).toBeInTheDocument();
  });

  it("offers no download for a local-only dataset", async () => {
    vi.spyOn(api, "listDatasets").mockResolvedValue([
      { name: "localonly", repo: null, revision: "main", local: true, ready: true, size_bytes: 10 },
    ]);
    setup();
    await screen.findByText("localonly");
    expect(screen.queryByRole("button", { name: "Download" })).toBeNull();
  });

  it("says the token is missing instead of offering a button", async () => {
    vi.spyOn(api, "listDatasets").mockResolvedValue([needsAuth]);
    setup();
    expect(await screen.findByText(/token/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download" })).toBeNull();
  });

  it("shows progress once a download starts", async () => {
    vi.spyOn(api, "listDatasets").mockResolvedValue([downloadable]);
    vi.spyOn(api, "startDatasetDownload").mockResolvedValue({ job_id: 5 });
    vi.spyOn(api, "jobStatus").mockResolvedValue({
      id: 5, status: "running", processed: 500, total: 1000,
      meta: { rate_bps: 100, eta_seconds: 5 },
    });
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Download" }));
    expect(await screen.findByText(/50%/)).toBeInTheDocument();
  });

  const interrupted = { name: "half-v1", repo: "a/b", revision: "main",
                        local: true, ready: false, size_bytes: 1234,
                        sync_complete: false };

  it("offers a retry for an interrupted download", async () => {
    vi.spyOn(api, "listDatasets").mockResolvedValue([interrupted]);
    setup();
    // local is true here; gating on !local would hide this button forever.
    expect(await screen.findByRole("button", { name: "Download" })).toBeInTheDocument();
  });

  it("says a part-downloaded dataset is incomplete, not missing images", async () => {
    vi.spyOn(api, "listDatasets").mockResolvedValue([interrupted]);
    setup();
    expect(await screen.findByText("download incomplete")).toBeInTheDocument();
    expect(screen.queryByText("missing images/")).toBeNull();
  });

  it("re-attaches to a download already running on the server", async () => {
    vi.spyOn(api, "listDatasets").mockResolvedValue([downloadable]);
    vi.spyOn(api, "listJobs").mockResolvedValue([
      { id: 12, dataset: "hands-v1", type: "download", status: "running",
        processed: 250, total: 1000, meta: { rate_bps: 50, eta_seconds: 15 } },
    ]);
    vi.spyOn(api, "jobStatus").mockResolvedValue({
      id: 12, status: "running", processed: 250, total: 1000,
      meta: { rate_bps: 50, eta_seconds: 15 },
    });
    setup();
    // No click: the page was reloaded while the download continued server-side.
    expect(await screen.findByText(/25%/)).toBeInTheDocument();
  });
});

describe("SetupView keyboard access", () => {
  it("selects a ready dataset with Enter", async () => {
    const onDataset = vi.fn();
    setup({ onDataset });
    await screen.findByText("people-v3");
    const row = screen.getByRole("button", { name: /people-v3/ });
    expect(row).toHaveAttribute("tabindex", "0");
    row.focus();
    await userEvent.keyboard("{Enter}");
    expect(onDataset).toHaveBeenCalledWith("people-v3");
  });

  it("selects a ready dataset with Space", async () => {
    const onDataset = vi.fn();
    setup({ onDataset });
    await screen.findByText("people-v3");
    screen.getByRole("button", { name: /people-v3/ }).focus();
    await userEvent.keyboard(" ");
    expect(onDataset).toHaveBeenCalledWith("people-v3");
  });

  it("will not select an unready dataset from the keyboard", async () => {
    const onDataset = vi.fn();
    setup({ onDataset });
    await screen.findByText("hands-v1");
    const row = screen.getByRole("button", { name: /hands-v1/ });
    expect(row).toHaveAttribute("tabindex", "-1");
    expect(row).toHaveAttribute("aria-disabled", "true");
    row.focus();
    await userEvent.keyboard("{Enter}");
    expect(onDataset).not.toHaveBeenCalled();
  });

  it("opens an unlocked step with Enter", async () => {
    setup({ dataset: "people-v3" });
    await screen.findByText("people-v3 · 4 B");
    const head = screen.getByTestId("step-dataset");
    expect(head).toHaveAttribute("tabindex", "0");
    expect(screen.queryByText("hands-v1")).not.toBeInTheDocument();
    head.focus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByText("hands-v1")).toBeInTheDocument();
  });

  it("keeps a locked step out of the tab order and unopenable", async () => {
    setup();
    await screen.findByText("people-v3");
    const head = screen.getByTestId("step-model");
    expect(head).toHaveAttribute("aria-disabled", "true");
    expect(head).toHaveAttribute("tabindex", "-1");
    head.focus();
    await userEvent.keyboard("{Enter}");
    await userEvent.keyboard(" ");
    expect(screen.queryByText("y.pt")).not.toBeInTheDocument();
    // step 1 stayed open rather than being replaced by the model step
    expect(screen.getByText("people-v3")).toBeInTheDocument();
  });
});
