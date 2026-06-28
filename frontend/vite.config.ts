import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Windows case-insensitive fs: ./Editor would resolve to editor.ts before Editor.tsx.
    // Force the component to its .tsx file explicitly; ./editor (lowercase) is unaffected.
    alias: [
      { find: /^(.+\/)Editor$/, replacement: "$1Editor.tsx" },
    ],
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8080" },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/vitest.setup.ts"],
  },
});
