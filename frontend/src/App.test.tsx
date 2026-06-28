import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import * as api from "./api";

describe("App shell", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("login then pick then empty-pool message", async () => {
    vi.spyOn(api, "login").mockResolvedValue({ user_id: 1, username: "bob" });
    vi.spyOn(api, "lease").mockResolvedValue({ stem: null });
    const user = userEvent.setup();

    render(<App />);
    await user.type(screen.getByPlaceholderText(/username/i), "bob");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByRole("button", { name: /review all/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /review all/i }));

    expect(await screen.findByText(/pool is empty/i)).toBeInTheDocument();
    expect(api.lease).toHaveBeenCalledWith("all", 1);
  });

  it("shows a network-error message when lease rejects", async () => {
    vi.spyOn(api, "login").mockResolvedValue({ user_id: 1, username: "bob" });
    vi.spyOn(api, "lease").mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByPlaceholderText(/username/i), "bob");
    await user.click(screen.getByRole("button", { name: /log in/i }));
    await user.click(await screen.findByRole("button", { name: /review all/i }));
    expect(await screen.findByText(/network error/i)).toBeInTheDocument();
  });
});
