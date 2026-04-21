import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Status palette aligned with backend status vocabulary.
        status: {
          pending: "#a1a1aa", // zinc-400
          running: "#3b82f6", // blue-500
          success: "#22c55e", // green-500
          warn: "#f59e0b", // amber-500
          error: "#ef4444", // red-500
        },
      },
    },
  },
  plugins: [],
};

export default config;
