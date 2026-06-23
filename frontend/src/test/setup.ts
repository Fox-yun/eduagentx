import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Mock ResizeObserver
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as any).ResizeObserver = ResizeObserverMock;

// Mock matchMedia
window.matchMedia = window.matchMedia || (() => ({
  matches: false,
  media: "",
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
}));

// Mock getBoundingClientRect
HTMLElement.prototype.getBoundingClientRect = function () {
  return {
    width: 1000,
    height: 700,
    top: 0,
    left: 0,
    right: 1000,
    bottom: 700,
    x: 0,
    y: 0,
    toJSON: () => {},
  };
};

// Mock scrollIntoView
HTMLElement.prototype.scrollIntoView = vi.fn();

vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1));
vi.stubGlobal("cancelAnimationFrame", vi.fn());





// MSW mock server lifecycles
import { beforeAll, afterEach, afterAll } from "vitest";
import { server } from "./server";
import { disposeTaskConnectionRegistry } from "../features/tasks/useTaskStream";
import { MockTaskStreamTransport } from "../api/taskStreamTransport";

const originalWarn = console.warn;
const originalError = console.error;

beforeAll(() => {
  server.listen({ onUnhandledRequest: "bypass" });

  vi.spyOn(console, "warn").mockImplementation((msg, ...args) => {
    if (
      typeof msg === "string" &&
      (msg.includes("React Router Future Flag Warning") ||
        msg.includes("NaN") ||
        msg.includes("ResizeObserver"))
    ) {
      return;
    }
    originalWarn(msg, ...args);
  });

  vi.spyOn(console, "error").mockImplementation((msg, ...args) => {
    if (
      typeof msg === "string" &&
      (msg.includes("React Router Future Flag Warning") ||
        msg.includes("act(...)"))
    ) {
      return;
    }
    originalError(msg, ...args);
  });
});

afterEach(() => {
  cleanup();
  disposeTaskConnectionRegistry();
  MockTaskStreamTransport.reset();
  server.resetHandlers();
  vi.clearAllMocks();
});

afterAll(() => {
  server.close();
  vi.restoreAllMocks();
});
