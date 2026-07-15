import { renderHook, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTaskStream, subscribeToTask, disposeTaskConnectionRegistry } from "../features/tasks/useTaskStream";
import { MockTaskStreamTransport, TaskEventDto, setTaskStreamTransport } from "../api/taskStreamTransport";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";

vi.mock("../api/tasks", () => ({
  getTask: vi.fn().mockResolvedValue({
    task_id: "test-task-123",
    type: "learning_path_generation",
    title: "Test Task",
    status: "completed",
    progress: 100,
    currentStage: "done",
    message: "done",
    result: { path_id: "path-123" },
    error: null,
    requestId: null,
    createdAt: "",
    updatedAt: "",
  }),
}));

function makeEvent(overrides: Partial<TaskEventDto> & { task_id: string }): TaskEventDto {
  return {
    event_id: overrides.event_id || `evt-${Math.random().toString(36).slice(2)}`,
    task_id: overrides.task_id,
    type: overrides.type || "progress",
    status: overrides.status || "running",
    progress: overrides.progress ?? 50,
    stage: overrides.stage ?? null,
    message: overrides.message ?? "",
    result: overrides.result ?? null,
    timestamp: overrides.timestamp || new Date().toISOString(),
  };
}

describe("useTaskStream & Registry", () => {
  let queryClient: QueryClient;
  const fakeTransport = new MockTaskStreamTransport();

  beforeEach(() => {
    setTaskStreamTransport(fakeTransport);
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    disposeTaskConnectionRegistry();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("streams events and updates hook state", async () => {
    const taskId = "task-stream-ok";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "e1", status: "running", progress: 30, message: "step1" }),
      makeEvent({ task_id: taskId, event_id: "e2", status: "running", progress: 70, message: "step2" }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.progress).toBe(70);
    expect(result.current.message).toBe("step2");
  });

  it("deduplicates events by event_id", async () => {
    const taskId = "task-dedup";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "dup", progress: 20, message: "first" }),
      makeEvent({ task_id: taskId, event_id: "dup", progress: 90, message: "second" }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.progress).toBe(20);
  });

  it("handles completed terminal state and sets pathId", async () => {
    const taskId = "task-completed";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "c1", type: "completed", status: "completed", progress: 100, result: { path_id: "p-1" } }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.status).toBe("completed");
    expect(result.current.pathId).toBe("p-1");
  });

  it("exposes the path-generation task created by diagnostic grading", async () => {
    const taskId = "task-diagnostic-grading";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({
        task_id: taskId,
        event_id: "grading-completed",
        type: "completed",
        status: "completed",
        progress: 100,
        result: { path_task_id: "task-path-generation" },
      }),
    ]);

    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });

    expect(result.current.nextTaskId).toBe("task-path-generation");
  });

  it("handles failed terminal state and sets error", async () => {
    const taskId = "task-failed";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "f1", type: "failed", status: "failed", progress: 40, message: "crashed" }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.status).toBe("failed");
    expect(result.current.error).toBeTruthy();
  });

  it("handles cancelled terminal state", async () => {
    const taskId = "task-cancelled";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "x1", type: "cancelled", status: "cancelled", progress: 10 }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.status).toBe("cancelled");
  });

  it("handles partial_completed terminal state", async () => {
    const taskId = "task-partial";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "p1", type: "partial_completed", status: "partial_completed", progress: 70 }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.status).toBe("partial_completed");
  });

  it("handles expired terminal state", async () => {
    const taskId = "task-expired";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "ex1", type: "snapshot", status: "expired", progress: 0 }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.status).toBe("expired");
  });

  it("handles unit generation result", async () => {
    const taskId = "task-unit-gen";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "u1", type: "completed", status: "completed", progress: 100, result: { path_id: "p1", node_id: "n1" } }),
    ]);
    const { result } = renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 200)); });
    expect(result.current.status).toBe("completed");
  });

  it("supports dual subscribers sharing one connection", () => {
    const taskId = "dual-sub";
    const sub1 = { onMessage: vi.fn(), onError: vi.fn() };
    const sub2 = { onMessage: vi.fn(), onError: vi.fn() };
    const unsub1 = subscribeToTask(taskId, sub1);
    const unsub2 = subscribeToTask(taskId, sub2);
    const evt = makeEvent({ task_id: taskId, event_id: "d1", progress: 55 });
    MockTaskStreamTransport.triggerEvent(taskId, evt);
    expect(sub1.onMessage).toHaveBeenCalledWith(evt);
    expect(sub2.onMessage).toHaveBeenCalledWith(evt);
    unsub1();
    unsub2();
  });

  it("delivers cached terminal event to late subscriber", async () => {
    const taskId = "late-sub";
    MockTaskStreamTransport.setMockEvents(taskId, [
      makeEvent({ task_id: taskId, event_id: "ls1", type: "completed", status: "completed", progress: 100 }),
    ]);
    renderHook(() => useTaskStream(taskId), { wrapper });
    await act(async () => { await new Promise(r => setTimeout(r, 300)); });
    const lateSub = { onMessage: vi.fn(), onError: vi.fn() };
    const unsub = subscribeToTask(taskId, lateSub);
    expect(lateSub.onMessage).toHaveBeenCalled();
    unsub();
  });

  it("unsubscribes cleanly without affecting other subscribers", () => {
    const taskId = "unsub-clean";
    const sub1 = { onMessage: vi.fn(), onError: vi.fn() };
    const sub2 = { onMessage: vi.fn(), onError: vi.fn() };
    const unsub1 = subscribeToTask(taskId, sub1);
    subscribeToTask(taskId, sub2);
    unsub1();
    const evt = makeEvent({ task_id: taskId, event_id: "uc1" });
    MockTaskStreamTransport.triggerEvent(taskId, evt);
    expect(sub1.onMessage).not.toHaveBeenCalled();
    expect(sub2.onMessage).toHaveBeenCalledWith(evt);
    unsub1();
  });

  it("handles null taskId gracefully", () => {
    const { result } = renderHook(() => useTaskStream(null), { wrapper });
    expect(result.current.progress).toBe(0);
    expect(result.current.status).toBe("pending");
  });

  it("handles undefined taskId gracefully", () => {
    const { result } = renderHook(() => useTaskStream(undefined), { wrapper });
    expect(result.current.progress).toBe(0);
    expect(result.current.status).toBe("pending");
  });

  it("dispose registry is idempotent", () => {
    expect(() => disposeTaskConnectionRegistry()).not.toThrow();
    expect(() => disposeTaskConnectionRegistry()).not.toThrow();
  });

  it("connection state reports polling for transport-managed", () => {
    const taskId = "polling-state";
    const sub = { onMessage: vi.fn(), onError: vi.fn(), onConnectionState: vi.fn() };
    const unsub = subscribeToTask(taskId, sub);
    expect(sub.onConnectionState).toHaveBeenCalled();
    unsub();
  });

  it("trims event deduplication cache past 500 events", () => {
    const taskId = "trim-dedup";
    const sub = { onMessage: vi.fn(), onError: vi.fn() };
    const unsub = subscribeToTask(taskId, sub);

    for (let i = 0; i <= 500; i++) {
      MockTaskStreamTransport.triggerEvent(taskId, makeEvent({ task_id: taskId, event_id: `evt-${i}` }));
    }

    const initialCallCount = sub.onMessage.mock.calls.length;
    MockTaskStreamTransport.triggerEvent(taskId, makeEvent({ task_id: taskId, event_id: "evt-0" }));
    expect(sub.onMessage.mock.calls.length).toBe(initialCallCount + 1);

    unsub();
  });

  it("checks connection epochs to ignore outdated asynchronous callbacks", async () => {
    const taskId = "epoch-check";
    const sub = { onMessage: vi.fn(), onError: vi.fn() };
    const unsub = subscribeToTask(taskId, sub);

    disposeTaskConnectionRegistry();

    MockTaskStreamTransport.triggerEvent(taskId, makeEvent({ task_id: taskId, event_id: "evt-stale" }));
    expect(sub.onMessage).not.toHaveBeenCalled();

    unsub();
  });

  it("triggers automatic fallback polling after 5 consecutive failures", () => {
    vi.useFakeTimers();
    const taskId = "fallback-trigger";
    
    const failingTransport = {
      recoveryMode: "hook-managed" as const,
      connect: vi.fn().mockImplementation((id: string, handlers: any) => {
        setTimeout(() => {
          handlers.onError(new Error("Connection failed"));
        }, 0);
        return { close: vi.fn() };
      }),
    };
    setTaskStreamTransport(failingTransport);

    const sub = { onMessage: vi.fn(), onError: vi.fn(), onConnectionState: vi.fn() };
    const unsub = subscribeToTask(taskId, sub);

    act(() => {
      vi.advanceTimersByTime(0);
    });

    for (let i = 0; i < 5; i++) {
      act(() => {
        vi.advanceTimersByTime(16000);
      });
    }

    expect(sub.onConnectionState).toHaveBeenCalled();
    const lastCallState = sub.onConnectionState.mock.calls[sub.onConnectionState.mock.calls.length - 1][0].state;
    expect(lastCallState).toBe("polling");

    unsub();
    vi.useRealTimers();
  });
});

import { isTerminalTaskStatus, mapTaskEventType, TERMINAL_TASK_STATUSES } from "../features/tasks/taskEventPolicy";

describe("taskEventPolicy", () => {
  it("correctly identifies terminal statuses", () => {
    const terminals = Array.from(TERMINAL_TASK_STATUSES);
    for (const status of terminals) {
      expect(isTerminalTaskStatus(status)).toBe(true);
    }
    expect(isTerminalTaskStatus("pending")).toBe(false);
    expect(isTerminalTaskStatus("running")).toBe(false);
  });

  it("correctly maps task status to event type", () => {
    expect(mapTaskEventType("completed")).toBe("completed");
    expect(mapTaskEventType("partial_completed")).toBe("partial_completed");
    expect(mapTaskEventType("failed")).toBe("failed");
    expect(mapTaskEventType("cancelled")).toBe("cancelled");
    expect(mapTaskEventType("expired")).toBe("snapshot");
    expect(mapTaskEventType("interrupted")).toBe("snapshot");
    expect(mapTaskEventType("pending")).toBe("progress");
    expect(mapTaskEventType("running")).toBe("progress");
  });
});
