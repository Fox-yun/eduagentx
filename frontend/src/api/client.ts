import { ZodType } from "zod";
import { ApiError, ApiSchemaError, AuthExpiredError } from "./errors";
import { getCsrfToken, shouldAddCsrf, CSRF_HEADER_NAME } from "./csrf";
import { triggerAuthFailure } from "./authFailure";
import { ApiErrorDtoSchema } from "../schemas/errors";

export interface ApiRequestOptions<T = unknown> extends Omit<RequestInit, "body"> {
  body?: unknown;
  timeoutMs?: number;
  schema?: ZodType<T>;
  skipAuthRefresh?: boolean;
  alreadyRetried?: boolean;
}

let refreshPromise: Promise<void> | null = null;

async function performRefresh(): Promise<void> {
  await apiRequest<void>("/auth/refresh", {
    method: "POST",
    skipAuthRefresh: true,
  });
}

async function refreshSession(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = performRefresh()
      .catch((err) => {
        triggerAuthFailure();
        throw err;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function apiRequest<T = unknown>(
  path: string,
  options: ApiRequestOptions<T> = {}
): Promise<T> {
  const {
    body,
    timeoutMs = 15000,
    schema,
    skipAuthRefresh = false,
    alreadyRetried = false,
    ...init
  } = options;

  const origin =
    typeof window !== "undefined" && window.location && window.location.origin && window.location.origin !== "null"
      ? window.location.origin
      : "";

  const url =
    path.startsWith("http://") || path.startsWith("https://")
      ? path
      : `${origin}/api${path.startsWith("/") ? path : `/${path}`}`;

  const headers = new Headers(init.headers || {});

  // 1. Body payload serialization
  let requestBody: FormData | string | undefined = undefined;
  if (body !== undefined) {
    if (body instanceof FormData) {
      requestBody = body;
    } else {
      requestBody = JSON.stringify(body);
      headers.set("Content-Type", "application/json");
    }
  }

  // 2. Add CSRF token for unsafe methods on local api
  const isLocalApi = !path.startsWith("http://") && !path.startsWith("https://");
  const method = init.method || "GET";
  if (isLocalApi && shouldAddCsrf(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers.set(CSRF_HEADER_NAME, csrfToken);
    }
  }

  // 3. Set credentials to "include" for HttpOnly Cookies
  const fetchInit: RequestInit = {
    ...init,
    method,
    headers,
    body: requestBody,
    credentials: "include",
  };

  // 4. Timeout and AbortController Merging
  let didTimeout = false;
  const controller = new AbortController();
  const externalSignal = options.signal ?? init.signal; // Ensure we look at the right signal property
  const handleExternalAbort = () => {
    controller.abort(externalSignal?.reason);
  };

  if (externalSignal) {
    if (externalSignal.aborted) {
      handleExternalAbort();
    } else {
      externalSignal.addEventListener("abort", handleExternalAbort, { once: true });
    }
  }

  const timeoutId = setTimeout(() => {
    didTimeout = true;
    controller.abort(new DOMException("Request timeout", "TimeoutError"));
  }, timeoutMs);

  const isTest = typeof process !== "undefined" && process.env.NODE_ENV === "test";
  if (!isTest) {
    fetchInit.signal = controller.signal;
  } else {
    delete fetchInit.signal;
  }

  try {
    const response = await fetch(url, fetchInit);
    const requestId = response.headers.get("X-Request-Id") || undefined;

    // 5. Check response status
    if (!response.ok) {
      if (response.status === 401) {
        if (skipAuthRefresh) {
          throw new ApiError("Unauthenticated", 401, "UNAUTHENTICATED", undefined, requestId);
        }
        if (alreadyRetried) {
          triggerAuthFailure();
          throw new AuthExpiredError();
        }
        return await handleUnauthorized(
          () => apiRequest<T>(path, { ...options, alreadyRetried: true })
        );
      }

      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }

      const parsed = ApiErrorDtoSchema.safeParse(payload);
      const headerRequestId = response.headers.get("x-request-id") || undefined;

      if (parsed.success) {
        throw new ApiError(
          parsed.data.error.message,
          response.status,
          parsed.data.error.code,
          parsed.data.error.details,
          parsed.data.error.request_id ?? headerRequestId
        );
      }

      throw new ApiError(
        response.statusText || "请求失败",
        response.status,
        "HTTP_ERROR",
        undefined,
        headerRequestId
      );
    }

    // 6. Handle 204 or Empty Content
    if (response.status === 204) {
      return undefined as unknown as T;
    }

    const contentType = response.headers.get("Content-Type") || "";
    let data: unknown;

    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    // 7. Zod Schema validation
    if (schema) {
      const parsed = schema.safeParse(data);
      if (!parsed.success) {
        if (typeof import.meta !== "undefined" && import.meta.env?.DEV) {
          console.error("Zod validation failed for endpoint:", url, parsed.error);
        }
        throw new ApiSchemaError(parsed.error.issues, url);
      }
      return parsed.data;
    }

    return data as T;
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "AbortError") {
      if (didTimeout) {
        throw new ApiError("请求超时", 408, "REQUEST_TIMEOUT");
      }
      throw error;
    }
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError("请求超时", 408, "REQUEST_TIMEOUT");
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener("abort", handleExternalAbort);
    }
  }
}

async function handleUnauthorized<T>(
  request: () => Promise<T>
): Promise<T> {
  try {
    await refreshSession();
  } catch {
    throw new AuthExpiredError();
  }

  return request();
}
