import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import * as api from "./api";

const dataset = { name: "people-v3", repo: null, revision: "main", local: true, ready: true, size_bytes: 1 };

describe("App shell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("login then pick then empty-pool message", async () => {
    vi.spyOn(api, "login").mockResolvedValue({ user_id: 1, username: "bob" });
    vi.spyOn(api, "lease").mockResolvedValue({ stem: null });
    vi.spyOn(api, "listDatasets").mockResolvedValue([dataset]);
    vi.spyOn(api, "listModels").mockResolvedValue([]);
    vi.spyOn(api, "stats").mockResolvedValue({ total: 10, done: 0, leased: 0, todo: 10 });
    const user = userEvent.setup();

    render(<App />);
    await user.type(screen.getByPlaceholderText(/username/i), "bob");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await user.click(await screen.findByText("people-v3"));
    await user.click(screen.getByTestId("step-task"));
    await user.click(await screen.findByRole("button", { name: /review all/i }));
    await user.click(screen.getByRole("button", { name: /start reviewing/i }));

    expect(await screen.findByText(/pool is empty/i)).toBeInTheDocument();
    expect(api.lease).toHaveBeenCalledWith("people-v3", "all", 1);
  });

  it("shows a network-error message when lease rejects", async () => {
    vi.spyOn(api, "login").mockResolvedValue({ user_id: 1, username: "bob" });
    vi.spyOn(api, "lease").mockRejectedValue(new Error("boom"));
    vi.spyOn(api, "listDatasets").mockResolvedValue([dataset]);
    vi.spyOn(api, "listModels").mockResolvedValue([]);
    vi.spyOn(api, "stats").mockResolvedValue({ total: 10, done: 0, leased: 0, todo: 10 });
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByPlaceholderText(/username/i), "bob");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await user.click(await screen.findByText("people-v3"));
    await user.click(screen.getByTestId("step-task"));
    await user.click(await screen.findByRole("button", { name: /review all/i }));
    await user.click(screen.getByRole("button", { name: /start reviewing/i }));

    expect(await screen.findByText(/network error/i)).toBeInTheDocument();
  });

  it("restores the last session from localStorage", async () => {
    localStorage.setItem("plt.session",
      JSON.stringify({ dataset: "people-v3", model: "y.pt", task: "all" }));
    vi.spyOn(api, "login").mockResolvedValue({ user_id: 1, username: "alexander" });
    vi.spyOn(api, "listDatasets").mockResolvedValue([dataset]);
    vi.spyOn(api, "listModels").mockResolvedValue([]);
    render(<App />);
    await userEvent.type(screen.getByPlaceholderText("username"), "alexander");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    expect(await screen.findByText("people-v3 · 1 B")).toBeInTheDocument();
  });

  it("passes the dataset when leasing", async () => {
    vi.spyOn(api, "login").mockResolvedValue({ user_id: 1, username: "alexander" });
    vi.spyOn(api, "lease").mockResolvedValue({ stem: null });
    vi.spyOn(api, "listDatasets").mockResolvedValue([dataset]);
    vi.spyOn(api, "listModels").mockResolvedValue([]);
    vi.spyOn(api, "stats").mockResolvedValue({ total: 1, done: 0, leased: 0, todo: 1 });
    render(<App />);
    await userEvent.type(screen.getByPlaceholderText("username"), "alexander");
    await userEvent.click(screen.getByRole("button", { name: /log in/i }));
    await userEvent.click(await screen.findByText("people-v3"));
    await userEvent.click(screen.getByTestId("step-task"));
    await userEvent.click(await screen.findByText(/review all/i));
    await userEvent.click(screen.getByRole("button", { name: /start reviewing/i }));
    await waitFor(() => expect(api.lease).toHaveBeenCalledWith("people-v3", "all", 1));
  });
});
