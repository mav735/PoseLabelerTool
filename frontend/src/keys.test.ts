import { describe, it, expect } from "vitest";
import { keyToAction, keyToView } from "./keys";

describe("keys", () => {
  it("maps action keys", () => {
    expect(keyToAction("k")).toBe("keep");
    expect(keyToAction("d")).toBe("drop");
    expect(keyToAction("c")).toBe("clear");
    expect(keyToAction("r")).toBeNull();
    expect(keyToAction("e")).toBe("edit");
    expect(keyToAction("z")).toBeNull();
  });
  it("maps view keys", () => {
    expect(keyToView("v")).toBe("next");
    expect(keyToView("ArrowRight")).toBe("next");
    expect(keyToView("ArrowLeft")).toBe("prev");
    expect(keyToView("k")).toBeNull();
  });
});
