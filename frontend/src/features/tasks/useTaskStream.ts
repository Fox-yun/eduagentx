import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../api/queryKeys";
import { getTask } from "../../api/tasks";
import { TaskStatus } from "../../schemas/tasks";
import {
  taskStreamTransport,
  TaskEventDto,
  TaskStreamConnection,
} from "../../api/taskStreamTransport";
import { z } from "zod";
import { isTerminalTaskStatus, mapTaskEventType } from "./taskEventPolicy";

// DTO result validators
const PathGenerationResultSchema = z.object({
  path_id: z.string(),
  version: z.number().int().positive().optional(),
});

const UnitGenerationResultSchema = z.object({
  path_id: z.string(),
  node_id: z.string(),
  unit_id: z.string().optional(),
});

export interface TaskSubscriber {
  onMessage: (event: TaskEventDto) => void;
  onError: (err: Error) => void;
  onConnectionState?: (snapshot: TaskConnectionSnapshot) => void;
}

export interface TaskConnectionSnapshot {
  state: "connecting" | "connected" | "reconnecting" | "polling" | "terminal";
  error: Error | null;
}

interface SharedTaskConnection {
  taskId: string;
  subscribers: Set<TaskSubscriber>;
  transportConnection: TaskStreamConnection | null;
  state: "connecting" | "connected" | "reconnecting" | "polling" | "terminal";
  latestEvent: TaskEventDto | null;
  seenEventIds: Set<string>;
  reconnectAttempts: number;
  connectionEpoch: number;
  reconnectTimerId: ReturnType<typeof setTimeout> | null;
  pollTimerId: ReturnType<typeof setTimeout> | null;
  pollAbortController: AbortController | null;
  lastError: Error | null;
  terminalCleanupTimerId: ReturnType<typeof setTimeout> | null;
  terminalAt: number | null;
}

const taskConnections = new Map<string, SharedTaskConnection>();
const CLEANUP_DELAY_MS = 5_000;
const STALE_SWEEP_INTERVAL_MS = 30_000;
const TERMINAL_CACHE_DURATION_MS = 30_000;
const MAX_SEEN_EVENTS = 500;

let sweepIntervalId: ReturnType<typeof setInterval> | null = null;

function ensureRegistrySweep() {
  if (sweepIntervalId !== null) return;
  sweepIntervalId = setInterval(sweepExpiredConnections, STALE_SWEEP_INTERVAL_MS);
}

function sweepExpiredConnections() {
  const now = Date.now();
  for (const [taskId, shared] of taskConnections.entries()) {
    if (shared.subscribers.size === 0) {
      const isTerminalCacheExpired =
        shared.state === "terminal" &&
        shared.terminalAt !== null &&
        now - shared.terminalAt >= TERMINAL_CACHE_DURATION_MS;

      const isNonTerminalStale = shared.state !== "terminal";

      if (isTerminalCacheExpired || isNonTerminalStale) {
        closeSharedConnection(shared);
        taskConnections.delete(taskId);
      }
    }
  }
  if (taskConnections.size === 0 && sweepIntervalId !== null) {
    clearInterval(sweepIntervalId);
    sweepIntervalId = null;
  }
}

function closeSharedConnection(shared: SharedTaskConnection) {
  if (shared.pollAbortController) {
    shared.pollAbortController.abort();
    shared.pollAbortController = null;
  }
  if (shared.transportConnection) {
    shared.transportConnection.close();
    shared.transportConnection = null;
  }
  if (shared.reconnectTimerId !== null) {
    clearTimeout(shared.reconnectTimerId);
    shared.reconnectTimerId = null;
  }
  if (shared.pollTimerId !== null) {
    clearTimeout(shared.pollTimerId);
    shared.pollTimerId = null;
  }
  if (shared.terminalCleanupTimerId !== null) {
    clearTimeout(shared.terminalCleanupTimerId);
    shared.terminalCleanupTimerId = null;
  }
}

export function disposeTaskConnectionRegistry() {
  for (const shared of taskConnections.values()) {
    shared.connectionEpoch += 1;
    shared.subscribers.clear();
    closeSharedConnection(shared);
  }
  taskConnections.clear();
  if (sweepIntervalId !== null) {
    clearInterval(sweepIntervalId);
    sweepIntervalId = null;
  }
}

function notifyConnectionState(shared: SharedTaskConnection) {
  const snapshot: TaskConnectionSnapshot = {
    state: shared.state,
    error: shared.lastError,
  };
  shared.subscribers.forEach((sub) => sub.onConnectionState?.(snapshot));
}

function dispatchTaskEvent(
  shared: SharedTaskConnection,
  event: TaskEventDto,
  epoch: number,
) {
  if (epoch !== shared.connectionEpoch) return;

  if (shared.seenEventIds.has(event.event_id)) return;

  shared.seenEventIds.add(event.event_id);
  while (shared.seenEventIds.size > MAX_SEEN_EVENTS) {
    const oldest = shared.seenEventIds.values().next().value;
    if (oldest) {
      shared.seenEventIds.delete(oldest);
    }
  }

  shared.latestEvent = event;
  shared.reconnectAttempts = 0;
  shared.lastError = null;
  notifyConnectionState(shared);

  shared.subscribers.forEach((sub) => sub.onMessage(event));

  if (isTerminalTaskStatus(event.status)) {
    handleTerminalStateTransition(shared, event);
  }
}

function startPhysicalConnection(shared: SharedTaskConnection) {
  if (shared.state === "terminal") return;
  shared.connectionEpoch += 1;
  const currentEpoch = shared.connectionEpoch;
  shared.lastError = null;
  const isHookManaged = taskStreamTransport.recoveryMode === "hook-managed";
  shared.state = isHookManaged ? "connecting" : "polling";
  notifyConnectionState(shared);
  if (shared.transportConnection) {
    shared.transportConnection.close();
    shared.transportConnection = null;
  }

  try {
    shared.transportConnection = taskStreamTransport.connect(shared.taskId, {
      onMessage: (event) => {
        dispatchTaskEvent(shared, event, currentEpoch);
      },
      onError: (err) => {
        if (shared.connectionEpoch !== currentEpoch) return;
        if (shared.state === "terminal") return;
        shared.lastError = err;
        notifyConnectionState(shared);
        if (isHookManaged) {
          restartPhysicalConnection(shared);
        } else {
          const errorObj = err instanceof Error ? err : new Error(String(err));
    shared.subscribers.forEach((sub) => sub.onError(errorObj));
        }
      },
    });
  } catch (err: unknown) {
    shared.lastError = err instanceof Error ? err : new Error(String(err));
    notifyConnectionState(shared);
    if (isHookManaged) {
      restartPhysicalConnection(shared);
    } else {
      const errorObj = err instanceof Error ? err : new Error(String(err));
    shared.subscribers.forEach((sub) => sub.onError(errorObj));
    }
  }
}

function restartPhysicalConnection(shared: SharedTaskConnection) {
  if (shared.state === "terminal") return;
  shared.connectionEpoch += 1;
  if (shared.reconnectTimerId !== null) {
    clearTimeout(shared.reconnectTimerId);
    shared.reconnectTimerId = null;
  }
  if (shared.transportConnection) {
    shared.transportConnection.close();
    shared.transportConnection = null;
  }
  shared.state = "reconnecting";
  notifyConnectionState(shared);

  const delays = [1000, 2000, 4000, 8000, 15000];
  const attempt = shared.reconnectAttempts;

  if (attempt >= 5) {
    startFallbackPolling(shared);
  } else {
    shared.reconnectAttempts++;
    shared.reconnectTimerId = setTimeout(() => {
      startPhysicalConnection(shared);
    }, delays[attempt]);
  }
}

function startFallbackPolling(shared: SharedTaskConnection) {
  shared.state = "polling";
  notifyConnectionState(shared);

  const abortController = new AbortController();
  shared.pollAbortController = abortController;

  const poll = async () => {
    if (shared.state !== "polling" || abortController.signal.aborted) return;
    try {
      const isVisible = typeof document !== "undefined" ? document.visibilityState === "visible" : true;
      if (!isVisible) {
        shared.pollTimerId = setTimeout(poll, 10000);
        return;
      }

      const epoch = shared.connectionEpoch;
      const task = await getTask(shared.taskId, abortController.signal);

      if (shared.connectionEpoch !== epoch || shared.state !== "polling" || abortController.signal.aborted) {
        return;
      }

      const event: TaskEventDto = {
        event_id: `poll-${task.taskId}-${task.status}-${task.progress}-${task.updatedAt}`,
        task_id: task.taskId,
        type: mapTaskEventType(task.status),
        status: task.status,
        progress: task.progress,
        stage: task.currentStage,
        message: task.message,
        result: task.result,
        timestamp: new Date().toISOString(),
      };

      dispatchTaskEvent(shared, event, epoch);

      if (shared.state === "polling") {
        shared.pollTimerId = setTimeout(poll, 3000);
      }
    } catch (err: unknown) {
      if (abortController.signal.aborted) return;
      if (shared.state === "polling") {
        shared.lastError = err instanceof Error ? err : new Error(String(err));
        notifyConnectionState(shared);
        const errorObj = err instanceof Error ? err : new Error(String(err));
    shared.subscribers.forEach((sub) => sub.onError(errorObj));
        shared.pollTimerId = setTimeout(poll, 3000);
      }
    }
  };

  poll();
}

function handleTerminalStateTransition(shared: SharedTaskConnection, event: TaskEventDto) {
  closeSharedConnection(shared);
  shared.state = "terminal";
  shared.latestEvent = event;
  shared.terminalAt = Date.now();
  shared.lastError = null;
  notifyConnectionState(shared);

  shared.terminalCleanupTimerId = setTimeout(() => {
    if (shared.subscribers.size === 0) {
      taskConnections.delete(shared.taskId);
    }
  }, TERMINAL_CACHE_DURATION_MS);
}

export function subscribeToTask(taskId: string, subscriber: TaskSubscriber): () => void {
  ensureRegistrySweep();
  let shared = taskConnections.get(taskId);

  if (shared) {
    if (shared.terminalCleanupTimerId !== null) {
      clearTimeout(shared.terminalCleanupTimerId);
      shared.terminalCleanupTimerId = null;
    }
  } else {
    shared = {
      taskId,
      subscribers: new Set(),
      transportConnection: null,
      state: "connecting",
      latestEvent: null,
      seenEventIds: new Set(),
      reconnectAttempts: 0,
      connectionEpoch: 0,
      reconnectTimerId: null,
      pollTimerId: null,
      pollAbortController: null,
      lastError: null,
      terminalCleanupTimerId: null,
      terminalAt: null,
    };
    taskConnections.set(taskId, shared);
  }

  shared.subscribers.add(subscriber);

  if (!shared.transportConnection && shared.state === "connecting" && shared.connectionEpoch === 0) {
    startPhysicalConnection(shared);
  }

  if (shared.latestEvent) {
    subscriber.onMessage(shared.latestEvent);
  }

  return () => {
    const active = taskConnections.get(taskId);
    if (!active) return;
    active.subscribers.delete(subscriber);

    if (active.subscribers.size === 0) {
      if (active.state === "terminal") {
        if (active.terminalCleanupTimerId === null) {
          const timeSinceTerminal = active.terminalAt ? Date.now() - active.terminalAt : 0;
          const remainingTime = Math.max(0, TERMINAL_CACHE_DURATION_MS - timeSinceTerminal);
          active.terminalCleanupTimerId = setTimeout(() => {
            if (active.subscribers.size === 0) {
              taskConnections.delete(taskId);
            }
          }, remainingTime);
        }
      } else {
        active.terminalCleanupTimerId = setTimeout(() => {
          if (active.subscribers.size === 0) {
            closeSharedConnection(active);
            taskConnections.delete(taskId);
          }
        }, CLEANUP_DELAY_MS);
      }
    }
  };
}

export function useTaskStream(taskId: string | null | undefined) {
  const queryClient = useQueryClient();
  const [progress, setProgress] = useState<number>(0);
  const [message, setMessage] = useState<string>("正在连接任务�?..");
  const [stage, setStage] = useState<string | null>(null);
  const [status, setStatus] = useState<TaskStatus>("pending");
  const [error, setError] = useState<string | null>(null);
  const [pathId, setPathId] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<TaskConnectionSnapshot["state"]>("connecting");

  useEffect(() => {
    if (!taskId) return;

    setProgress(0);
    setMessage("正在初始化任�?..");
    setStage(null);
    setStatus("pending");
    setError(null);
    setPathId(null);

    const handleMessage = (event: TaskEventDto) => {
      setProgress(event.progress);
      setMessage(event.message || "");
      setStage(event.stage);
      setStatus(event.status);

      if (event.status === "failed") {
        const resultObj = event.result as Record<string, unknown> | null | undefined;
        setError((resultObj?.error as string) || event.message || "任务执行失败");
      }

      if (isTerminalTaskStatus(event.status)) {
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks() });
        if (event.status === "completed" && event.result) {
          const pathParse = PathGenerationResultSchema.safeParse(event.result);
          if (pathParse.success) {
            setPathId(pathParse.data.path_id);
            queryClient.invalidateQueries({ queryKey: queryKeys.path(pathParse.data.path_id) });
          }
          const unitParse = UnitGenerationResultSchema.safeParse(event.result);
          if (unitParse.success) {
            queryClient.invalidateQueries({
              queryKey: queryKeys.unit(unitParse.data.path_id, unitParse.data.node_id),
            });
          }
        }
      }
    };

    const handleError = (err: Error) => {
      setError(err.message);
    };

    const handleConnectionState = (snapshot: TaskConnectionSnapshot) => {
      setConnectionState(snapshot.state);
    };

    const unsubscribe = subscribeToTask(taskId, {
      onMessage: handleMessage,
      onError: handleError,
      onConnectionState: handleConnectionState,
    });

    return () => {
      unsubscribe();
    };
  }, [taskId, queryClient]);

  return {
    progress,
    message,
    stage,
    status,
    error,
    pathId,
    isPolling: connectionState === "polling",
  };
}

