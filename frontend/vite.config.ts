import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const enableMsw = process.env.VITE_ENABLE_MSW === "true";
const proxyTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

// Use Vite's native defineConfig to avoid loading vitest/config
// in non-test contexts (e.g. Playwright E2E). Vitest config is merged
// below only when needed.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],

  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    // When MSW is enabled, the service worker handles all /api/* requests.
    // The Vite proxy must be disabled so requests don't leak to a real backend
    // that doesn't recognise the MSW-managed session.
    ...(enableMsw
      ? {}
      : {
          proxy: {
            "/api/tasks": {
              target: proxyTarget,
              changeOrigin: true,
              configure: (proxy) => {
                proxy.on("proxyRes", (proxyRes, _req, res) => {
                  delete proxyRes.headers["content-length"];
                  proxyRes.headers["cache-control"] = "no-cache";
                  proxyRes.headers["x-accel-buffering"] = "no";
                });
              },
            },
            "/api": {
              target: proxyTarget,
              changeOrigin: true,
            },
          },
        }),
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
