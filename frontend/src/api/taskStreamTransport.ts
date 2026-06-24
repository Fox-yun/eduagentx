import { getTask } from "./tasks";
import { TaskEventDtoSchema, TaskEventDto } from "../schemas/taskEvents";
import { TaskStatus } from "../schemas/tasks";
import { isTerminalTaskStatus, mapTaskEventType } from "../features/tasks/taskEventPolicy";

export type { TaskEventDto } from "../schemas/taskEvents";

export interface TaskStreamHandlers {
  onMessage: (event: TaskEventDto) => void;
  onError: (error: Error) => void;
}

export interface TaskStreamConnection {
  close: () => void;
}

export interface TaskStreamTransport {
  readonly recoveryMode: "hook-managed" | "transport-managed";
  connect(taskId: string, handlers: TaskStreamHandlers): TaskStreamConnection;
}

export interface TaskModel {
  taskId: string;
  type: string;
  title: string;
  status: TaskStatus;
  progress: number;
  currentStage: string | null;
  message: string | null;
  result: unknown;
  error: string | null;
  requestId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TaskSnapshotProvider {
  getTask(taskId: string, signal?: AbortSignal): Promise<TaskModel>;
}

export class HttpTaskSnapshotProvider implements TaskSnapshotProvider {
  getTask(taskId: string, signal?: AbortSignal): Promise<TaskModel> {
    return getTask(taskId, signal);
  }
}

export class EventSourceTaskStreamTransport implements TaskStreamTransport {
  readonly recoveryMode = "hook-managed";

  connect(taskId: string, handlers: TaskStreamHandlers): TaskStreamConnection {
    const url = `/api/tasks/${taskId}/stream`;
    const eventSource = new EventSource(url, { withCredentials: true });

    eventSource.onmessage = (event) => {
      try {
        const rawData = JSON.parse(event.data);
        const parsed = TaskEventDtoSchema.parse({
          event_id: event.lastEventId || rawData.event_id || String(Date.now() + Math.random()),
          ...rawData,
        });
        handlers.onMessage(parsed);
      } catch (error: unknown) {
        const normalized = error instanceof Error ? error : new Error(String(error));
        handlers.onError(normalized);
      }
    };

    eventSource.onerror = () => {
      handlers.onError(new Error("EventSource connection error"));
    };

    return {
      close: () => {
        eventSource.close();
      },
    };
  }
}

export class PollingTaskStreamTransport implements TaskStreamTransport {
  readonly recoveryMode = "transport-managed";

  constructor(private readonly provider: TaskSnapshotProvider) {}

  connect(taskId: string, handlers: TaskStreamHandlers): TaskStreamConnection {
    let closed = false;
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const poll = async () => {
      if (closed) return;
      controller = new AbortController();

      try {
        const task = await this.provider.getTask(taskId, controller.signal);
        if (closed) return;

        const eventId = [
          task.taskId,
          task.status,
          task.progress,
          task.updatedAt,
        ].join(":");

        const event: TaskEventDto = {
          event_id: eventId,
          task_id: task.taskId,
          type: mapTaskEventType(task.status),
          status: task.status,
          progress: task.progress,
          stage: task.currentStage,
          message: task.message,
          result: task.result,
          timestamp: new Date().toISOString(),
        };

        handlers.onMessage(event);

        if (isTerminalTaskStatus(task.status)) {
          return;
        }
      } catch (err: unknown) {
        if (!closed) {
          handlers.onError(err instanceof Error ? err : new Error(String(err)));
        }
      }

      if (!closed) {
        const isHidden = typeof document !== "undefined" && document.hidden;
        timerId = setTimeout(poll, isHidden ? 10000 : 1500);
      }
    };

    poll();

    const handleVisibilityChange = () => {
      if (closed || !timerId) return;
      clearTimeout(timerId);
      const isHidden = typeof document !== "undefined" && document.hidden;
      timerId = setTimeout(poll, isHidden ? 10000 : 1500);
    };

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
    }

    return {
      close: () => {
        closed = true;
        if (timerId) {
          clearTimeout(timerId);
          timerId = null;
        }
        if (controller) {
          controller.abort();
          controller = null;
        }
        if (typeof document !== "undefined") {
          document.removeEventListener("visibilitychange", handleVisibilityChange);
        }
      },
    };
  }
}

export class MockTaskStreamTransport implements TaskStreamTransport {
  readonly recoveryMode = "hook-managed";
  private static mockData: Record<string, TaskEventDto[]> = {};
  private static listeners: Record<string, TaskStreamHandlers[]> = {};
  private static pendingTimers: Set<ReturnType<typeof setTimeout>> = new Set();

  static setMockEvents(taskId: string, events: TaskEventDto[]) {
    this.mockData[taskId] = events;
  }

  static triggerEvent(taskId: string, event: TaskEventDto) {
    if (this.listeners[taskId]) {
      this.listeners[taskId].forEach((l) => l.onMessage(event));
    }
  }

  static reset() {
    this.mockData = {};
    this.listeners = {};
    this.pendingTimers.forEach((t) => clearTimeout(t));
    this.pendingTimers.clear();
  }

  connect(taskId: string, handlers: TaskStreamHandlers): TaskStreamConnection {
    if (!MockTaskStreamTransport.listeners[taskId]) {
      MockTaskStreamTransport.listeners[taskId] = [];
    }
    MockTaskStreamTransport.listeners[taskId].push(handlers);

    const mockEvents = MockTaskStreamTransport.mockData[taskId] || [];
    let timerId: ReturnType<typeof setTimeout> | null = null;
    let index = 0;

    const playNext = () => {
      if (timerId) {
        MockTaskStreamTransport.pendingTimers.delete(timerId);
      }
      if (index < mockEvents.length) {
        handlers.onMessage(mockEvents[index]);
        index++;
        timerId = setTimeout(playNext, 80);
        MockTaskStreamTransport.pendingTimers.add(timerId);
      }
    };

    timerId = setTimeout(playNext, 30);
    MockTaskStreamTransport.pendingTimers.add(timerId);

    return {
      close: () => {
        if (timerId) {
          clearTimeout(timerId);
          MockTaskStreamTransport.pendingTimers.delete(timerId);
          timerId = null;
        }
        if (MockTaskStreamTransport.listeners[taskId]) {
          MockTaskStreamTransport.listeners[taskId] = MockTaskStreamTransport.listeners[taskId].filter(
            (l) => l !== handlers
          );
        }
      },
    };
  }
}

const enableMsw = import.meta.env.DEV && import.meta.env.VITE_ENABLE_MSW === "true";

let activeTransport: TaskStreamTransport = enableMsw
  ? new PollingTaskStreamTransport(new HttpTaskSnapshotProvider())
  : new EventSourceTaskStreamTransport();

export function setTaskStreamTransport(t: TaskStreamTransport) {
  activeTransport = t;
}

export function getTaskStreamTransport(): TaskStreamTransport {
  return activeTransport;
}

export const taskStreamTransport = {
  get recoveryMode(): "hook-managed" | "transport-managed" {
    return activeTransport.recoveryMode;
  },
  connect: (taskId: string, handlers: TaskStreamHandlers): TaskStreamConnection => {
    return activeTransport.connect(taskId, handlers);
  }
};
