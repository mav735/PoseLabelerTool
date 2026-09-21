import "@testing-library/jest-dom";
Object.defineProperty(HTMLCanvasElement.prototype, "getContext", { value: () => null });

// jsdom does not always expose localStorage — under jsdom 25 on Node 26 neither
// `globalThis.localStorage` nor `window.localStorage` is defined, while on other
// combinations both are. The app tolerates its absence (every access is wrapped
// in try/catch), but the tests need it present to exercise session persistence
// at all, so supply an in-memory Storage when the environment lacks one.
if (typeof globalThis.localStorage === "undefined") {
  const store = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return store.size;
    },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => {
      store.set(k, String(v));
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => {
      store.clear();
    },
  };
  Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });
  if (typeof window !== "undefined") {
    Object.defineProperty(window, "localStorage", { value: storage, configurable: true });
  }
}
