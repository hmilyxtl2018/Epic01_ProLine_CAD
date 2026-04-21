/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import path from "node:path";

// jsdom + esbuild's automatic JSX transform is enough for the pure-
// component / lib unit tests we run today. (Tried happy-dom v15 first;
// its strict localStorage policy on opaque origins blocked our api.ts
// tests.) Add @vitejs/plugin-react when we need full React Fast Refresh.
export default defineConfig({
  test: {
    environment: "jsdom",
    environmentOptions: {
      jsdom: {
        url: "http://localhost:3000",
      },
    },
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  esbuild: {
    jsx: "automatic",
  },
});
