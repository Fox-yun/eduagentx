import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { apiRequest } from "../api/client";
import { registerAuthFailureHandler } from "../api/authFailure";
import { ApiError, ApiSchemaError, AuthExpiredError } from "../api/errors";
import { http, HttpResponse } from "msw";
import { server } from "./server";
import { z } from "zod";

describe("API Client apiRequest", () => {
  const failureCallback = vi.fn();
  let unregisterFailure: () => void;

  beforeEach(() => {
    failureCallback.mockClear();
    unregisterFailure = registerAuthFailureHandler(failureCallback);
    // Reset any temporary handlers
    server.resetHandlers();
  });

  afterEach(() => {
    unregisterFailure();
  });

  it("should process successful JSON responses", async () => {
    server.use(
      http.get("/api/test-ok", () => {
        return HttpResponse.json({ success: true });
      })
    );

    const res = await apiRequest<{ success: boolean }>("/test-ok");
    expect(res.success).toBe(true);
  });

  it("should support Zod schema validation", async () => {
    server.use(
      http.get("/api/test-schema", () => {
        return HttpResponse.json({ name: "Alice", age: 30 });
      })
    );

    const schema = z.object({
      name: z.string(),
      age: z.number(),
    });

    const res = await apiRequest("/test-schema", { schema });
    expect(res.name).toBe("Alice");
    expect(res.age).toBe(30);
  });

  it("should throw ApiSchemaError on schema validation failure", async () => {
    server.use(
      http.get("/api/test-schema-fail", () => {
        return HttpResponse.json({ name: "Alice", age: "thirty" });
      })
    );

    const schema = z.object({
      name: z.string(),
      age: z.number(),
    });

    await expect(apiRequest("/test-schema-fail", { schema })).rejects.toThrow(ApiSchemaError);
  });

  it("should handle 204 No Content correctly", async () => {
    server.use(
      http.get("/api/test-nocontent", () => {
        return new HttpResponse(null, { status: 204 });
      })
    );

    const res = await apiRequest("/test-nocontent");
    expect(res).toBeUndefined();
  });

  it("should automatically append CSRF header for unsafe methods", async () => {
    let capturedHeader: string | null = null;
    server.use(
      http.post("/api/test-csrf", ({ request }) => {
        capturedHeader = request.headers.get("X-CSRF-Token");
        return HttpResponse.json({ ok: true });
      })
    );

    // Mock document cookie
    if (typeof document !== "undefined") {
      Object.defineProperty(document, "cookie", {
        writable: true,
        value: "csrftoken=mock-csrf-token",
      });
    }

    await apiRequest("/test-csrf", { method: "POST", body: {} });
    expect(capturedHeader).toBe("mock-csrf-token");
  });

  it("should throw ApiError and skip refresh if skipAuthRefresh is set", async () => {
    server.use(
      http.get("/api/test-401-skip", () => {
        return new HttpResponse(null, { status: 401 });
      })
    );

    await expect(
      apiRequest("/test-401-skip", { skipAuthRefresh: true })
    ).rejects.toThrow(ApiError);

    expect(failureCallback).not.toHaveBeenCalled();
  });

  it("should trigger refresh token single-flight on business request 401, retrying once", async () => {
    let refreshCount = 0;
    let requestCount = 0;

    server.use(
      http.post("/api/auth/refresh", () => {
        refreshCount++;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("/api/test-business-401", () => {
        requestCount++;
        if (requestCount === 1) {
          return new HttpResponse(null, { status: 401 });
        }
        return HttpResponse.json({ data: "success-data" });
      })
    );

    const res = await apiRequest<{ data: string }>("/test-business-401");
    expect(res.data).toBe("success-data");
    expect(refreshCount).toBe(1);
    expect(requestCount).toBe(2);
    expect(failureCallback).not.toHaveBeenCalled();
  });

  it("should execute only one refresh call for concurrent 401 requests", async () => {
    let refreshCount = 0;
    let req1Count = 0;
    let req2Count = 0;

    server.use(
      http.post("/api/auth/refresh", async () => {
        refreshCount++;
        // Delay slightly to keep the refreshPromise active
        await new Promise((resolve) => setTimeout(resolve, 50));
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("/api/req1", () => {
        req1Count++;
        if (req1Count === 1) return new HttpResponse(null, { status: 401 });
        return HttpResponse.json({ ok: 1 });
      }),
      http.get("/api/req2", () => {
        req2Count++;
        if (req2Count === 1) return new HttpResponse(null, { status: 401 });
        return HttpResponse.json({ ok: 2 });
      })
    );

    const [res1, res2] = await Promise.all([
      apiRequest<{ ok: number }>("/req1"),
      apiRequest<{ ok: number }>("/req2"),
    ]);

    expect(res1.ok).toBe(1);
    expect(res2.ok).toBe(2);
    expect(refreshCount).toBe(1); // Single-flight success!
    expect(failureCallback).not.toHaveBeenCalled();
  });

  it("should fail original requests and trigger logout if refresh fails", async () => {
    server.use(
      http.post("/api/auth/refresh", () => {
        return new HttpResponse(null, { status: 401 }); // Refresh fails!
      }),
      http.get("/api/test-business-fail", () => {
        return new HttpResponse(null, { status: 401 });
      })
    );

    await expect(apiRequest("/test-business-fail")).rejects.toThrow(AuthExpiredError);
    expect(failureCallback).toHaveBeenCalledTimes(1);
  });

  it("should trigger logout if retried request fails with 401 again", async () => {
    server.use(
      http.post("/api/auth/refresh", () => {
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("/api/test-double-401", () => {
        return new HttpResponse(null, { status: 401 }); // original and retry both fail 401
      })
    );

    await expect(apiRequest("/test-double-401")).rejects.toThrow(AuthExpiredError);
    expect(failureCallback).toHaveBeenCalledTimes(1);
  });
});
