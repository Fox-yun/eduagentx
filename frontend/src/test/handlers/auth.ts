import { http, HttpResponse } from "msw";

export const defaultMockUser = {
  user_id: "user-123",
  display_name: "李明",
  email: "liming@example.com",
  email_verified: true,
  onboarding_completed: true,
  status: "active",
};

export const authHandlers = [
  // 1. GET /api/auth/me
  http.get("/api/auth/me", () => {
    return HttpResponse.json(defaultMockUser);
  }),
  http.get("http://localhost/api/auth/me", () => {
    return HttpResponse.json(defaultMockUser);
  }),
  http.get("http://localhost:3000/api/auth/me", () => {
    return HttpResponse.json(defaultMockUser);
  }),

  // 2. POST /api/auth/login
  http.post("/api/auth/login", async ({ request }) => {
    try {
      const body = (await request.json()) as any;
      if (!body.email || !body.password) {
        return HttpResponse.json(
          {
            error: {
              code: "BAD_REQUEST",
              message: "邮箱或密码不能为空",
              details: null,
              request_id: null,
            },
          },
          { status: 400 }
        );
      }
      if (body.password === "wrong-password") {
        return HttpResponse.json(
          {
            error: {
              code: "UNAUTHORIZED",
              message: "密码错误",
              details: null,
              request_id: null,
            },
          },
          { status: 401 }
        );
      }
      return HttpResponse.json({
        user_id: "user-123",
        display_name: "李明",
        email: body.email,
        email_verified: true,
        onboarding_completed: true,
        status: "active",
      });
    } catch {
      return HttpResponse.json(
        {
          error: {
            code: "BAD_REQUEST",
            message: "请求解析失败",
            details: null,
            request_id: null,
          },
        },
        { status: 400 }
      );
    }
  }),

  // 3. POST /api/auth/register
  http.post("/api/auth/register", async ({ request }) => {
    try {
      const body = (await request.json()) as any;
      if (body.email === "exists@example.com") {
        return HttpResponse.json(
          {
            error: {
              code: "CONFLICT",
              message: "该邮箱已被注册",
              details: null,
              request_id: null,
            },
          },
          { status: 409 }
        );
      }
      // Return verify_email discriminated union response
      return HttpResponse.json({
        next_step: "verify_email",
        user: {
          user_id: "user-456",
          display_name: body.display_name || "新用户",
          email: body.email || "new@example.com",
          email_verified: false,
          onboarding_completed: false,
          status: "pending_verification",
        },
      });
    } catch {
      return HttpResponse.json(
        {
          error: {
            code: "BAD_REQUEST",
            message: "请求解析失败",
            details: null,
            request_id: null,
          },
        },
        { status: 400 }
      );
    }
  }),

  // 4. POST /api/auth/logout
  http.post("/api/auth/logout", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // 5. POST /api/auth/refresh
  http.post("/api/auth/refresh", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // 6. POST /api/auth/verify-email
  http.post("/api/auth/verify-email", async ({ request }) => {
    try {
      const body = (await request.json()) as any;
      if (body.token === "invalid-token") {
        return HttpResponse.json(
          {
            error: {
              code: "INVALID_TOKEN",
              message: "验证链接无效或已过期",
              details: null,
              request_id: null,
            },
          },
          { status: 400 }
        );
      }
      return HttpResponse.json({
        user_id: "user-123",
        display_name: "李明",
        email: "liming@example.com",
        email_verified: true,
        onboarding_completed: false,
        status: "active",
      });
    } catch {
      return HttpResponse.json(
        {
          error: {
            code: "BAD_REQUEST",
            message: "请求解析失败",
            details: null,
            request_id: null,
          },
        },
        { status: 400 }
      );
    }
  }),

  // 7. POST /api/auth/resend-verification
  http.post("/api/auth/resend-verification", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // 8. POST /api/auth/forgot-password
  http.post("/api/auth/forgot-password", async ({ request }) => {
    try {
      const body = (await request.json()) as any;
      if (body.email === "nonexistent@example.com") {
        return HttpResponse.json(
          {
            error: {
              code: "NOT_FOUND",
              message: "该邮箱账户不存在",
              details: null,
              request_id: null,
            },
          },
          { status: 404 }
        );
      }
      return new HttpResponse(null, { status: 204 });
    } catch {
      return HttpResponse.json(
        {
          error: {
            code: "BAD_REQUEST",
            message: "请求解析失败",
            details: null,
            request_id: null,
          },
        },
        { status: 400 }
      );
    }
  }),

  // 9. POST /api/auth/reset-password
  http.post("/api/auth/reset-password", async ({ request }) => {
    try {
      const body = (await request.json()) as any;
      if (body.token === "expired-token") {
        return HttpResponse.json(
          {
            error: {
              code: "INVALID_TOKEN",
              message: "重置链接已失效",
              details: null,
              request_id: null,
            },
          },
          { status: 400 }
        );
      }
      return new HttpResponse(null, { status: 204 });
    } catch {
      return HttpResponse.json(
        {
          error: {
            code: "BAD_REQUEST",
            message: "请求解析失败",
            details: null,
            request_id: null,
          },
        },
        { status: 400 }
      );
    }
  }),
];

export const handlers = [...authHandlers];
