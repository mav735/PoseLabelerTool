import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tools } from "./Tools";
import * as api from "./api";

describe("Tools", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("launches an oracle job and shows progress to done", async () => {
    vi.spyOn(api, "startJob").mockResolvedValue({ id: 7, status: "queued" });
    const statuses = [
      { id: 7, status: "running", processed: 5, total: 10 },
      { id: 7, status: "done", processed: 10, total: 10, result: { flagged: 3 } },
    ];
    vi.spyOn(api, "jobStatus").mockImplementation(async () => statuses.shift() ?? { id: 7, status: "done", processed: 10, total: 10 });
    const user = userEvent.setup();
    render(<Tools dataset="ds" model="best.pt" />);
    await user.click(screen.getByRole("button", { name: /run oracle/i }));
    expect(api.startJob).toHaveBeenCalledWith("ds", "oracle", expect.objectContaining({ model: "best.pt" }));
    expect(await screen.findByText(/done/i, undefined, { timeout: 3000 })).toBeInTheDocument();
  });
});
