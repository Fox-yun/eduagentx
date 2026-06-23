import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],

  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },

  build: {
    sourcemap: false,
    manifest: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("elkjs")) {
              return "elk";
            }
            if (id.includes("react-markdown") || id.includes("remark-gfm") || id.includes("micromark")) {
              return "markdown";
            }
          }
        },
      },
    },
  },

  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: [
      "./src/test/setup.ts",
    ],
    css: true,
    pool: "forks",
    poolOptions: {
      forks: {
        singleFork: true,
      },
    },
    isolate: true,
    exclude: [
      "**/node_modules/**",
      "**/dist/**",
      "e2e/**",
      "**/.{idea,git,cache,output,temp}/**",
    ],
    coverage: {
      provider: "v8",
      include: [
        "src/**/*.{ts,tsx}",
      ],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
      exclude: [
        "src/test/**",
        "src/mocks/**",
        "e2e/**",
        "**/*.d.ts",
        "**/*.config.*",
        "src/main.tsx",
        "src/**/types.ts",
        "src/pages/TermsPage/**",
        "src/pages/PrivacyPage/**",
        "src/app/App.tsx",
        "src/app/queryClient.ts",
      ],
    },
  },
});
