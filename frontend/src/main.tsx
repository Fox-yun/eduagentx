import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/index.css";
import "./styles/animations.css";
import { App } from "./app/App";
import { apiRequest } from "./api/client";

if (
  import.meta.env.DEV &&
  import.meta.env.VITE_EXPOSE_TEST_API === "true"
) {
  (window as any).apiRequest = apiRequest;
}

declare global {
  interface Window {
    apiRequest?: typeof apiRequest;
    __EDUAGENTX_MSW_READY__?: boolean;
  }
}

async function enableMocking() {
  if (
    !import.meta.env.DEV ||
    import.meta.env.VITE_ENABLE_MSW !== "true" ||
    (typeof window !== "undefined" && (
      window.location.search.includes("disable-msw=true") ||
      localStorage.getItem("disable-msw") === "true"
    ))
  ) {
    return;
  }

  const { worker } = await import("./mocks/browser");

  await worker.start({
    onUnhandledRequest(request, print) {
      const url = new URL(request.url);
      if (url.pathname.startsWith("/api/")) {
        print.error();
        throw new Error(
          `Unhandled API request: ${request.method} ${url.pathname}`
        );
      }
      (print as any).bypass?.();
    },
  });

  window.__EDUAGENTX_MSW_READY__ = true;
}

enableMocking().then(() => {
  const container = document.getElementById("root");
  if (!container) {
    throw new Error("Missing #root element");
  }
  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>
  );
});
