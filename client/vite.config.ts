import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      // satori imports "harfbuzzjs", whose loader fetches a bare hb.wasm that the
      // build never ships. Swap in a module that bundles the wasm as a hashed
      // asset and points the loader at it (see src/lib/harfbuzz.ts).
      {
        find: /^harfbuzzjs$/,
        replacement: path.resolve(import.meta.dirname, "./src/lib/harfbuzz.ts"),
      },
      { find: "@", replacement: path.resolve(import.meta.dirname, "./src") },
    ],
  },
  server: {
    proxy: {
      // Forward API + SSE calls to the FastAPI dev server.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    css: false,
    restoreMocks: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
