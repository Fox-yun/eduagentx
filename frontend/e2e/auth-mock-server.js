import http from "http";

const PORT = 8000;

// Simple cookie parser helper
function parseCookies(cookieHeader) {
  const cookies = {};
  if (!cookieHeader) return cookies;
  cookieHeader.split(";").forEach(cookie => {
    const parts = cookie.split("=");
    const name = parts[0].trim();
    const value = parts[1] ? parts[1].trim() : "";
    cookies[name] = value;
  });
  return cookies;
}

// In-memory token rotation tracker
// refresh_token -> rotation count
const refreshTokens = new Map();
let refreshCount = 0;

// Helper to set cookie string
function serializeCookie(name, val, options = {}) {
  let str = `${name}=${val}`;
  if (options.path) str += `; Path=${options.path}`;
  if (options.httpOnly) str += "; HttpOnly";
  if (options.secure) str += "; Secure";
  if (options.maxAge !== undefined) str += `; Max-Age=${options.maxAge}`;
  if (options.sameSite) str += `; SameSite=${options.sameSite}`;
  return str;
}

// Unified nested error response helper
function sendError(res, status, code, message, details, requestId) {
  const errorBody = {
    error: {
      code,
      message,
      request_id: requestId || null,
    },
  };
  if (details !== undefined) {
    errorBody.error.details = details;
  }
  res.statusCode = status;
  res.end(JSON.stringify(errorBody));
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const cookies = parseCookies(req.headers.cookie);

  // Set standard response headers
  res.setHeader("Content-Type", "application/json");

  // Read request body helper
  let body = "";
  req.on("data", chunk => {
    body += chunk;
  });

  req.on("end", () => {
    let parsedBody = {};
    if (body) {
      try {
        parsedBody = JSON.parse(body);
      } catch (e) {
        // Not JSON or invalid
      }
    }

    const path = url.pathname;
    const method = req.method.toUpperCase();

    // CSRF protection check
    const isUnsafeMethod = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
    const isAuthLoginOrRegister = path === "/api/auth/login" || path === "/api/auth/register";

    if (isUnsafeMethod && !isAuthLoginOrRegister && !path.startsWith("/__test__/")) {
      const csrfHeader = req.headers["x-csrf-token"];
      const csrfCookie = cookies["csrftoken"];

      if (!csrfHeader || !csrfCookie || csrfHeader !== csrfCookie) {
        sendError(res, 403, "CSRF_ERROR", "CSRF token mismatch");
        return;
      }
    }

    // Health check endpoint
    if (path === "/health" && method === "GET") {
      res.statusCode = 200;
      res.end(JSON.stringify({ status: "ok" }));
      return;
    }

    // 1. GET /api/auth/csrf
    if (path === "/api/auth/csrf" && method === "GET") {
      const csrfToken = "csrf-token-123456";
      res.setHeader("Set-Cookie", serializeCookie("csrftoken", csrfToken, { path: "/", sameSite: "Lax" }));
      res.statusCode = 200;
      res.end(JSON.stringify({ csrf_token: csrfToken }));
      return;
    }

    // 2. GET /api/auth/me
    if (path === "/api/auth/me" && method === "GET") {
      const accessToken = cookies["access_token"];
      if (!accessToken || accessToken === "expired") {
        sendError(res, 401, "UNAUTHORIZED", "未登录或Token已过期");
        return;
      }

      res.statusCode = 200;
      res.end(JSON.stringify({
        user_id: "user-cookie-e2e",
        display_name: "Cookie Tester",
        email: "cookie-test@example.test",
        email_verified: true,
        onboarding_completed: true,
        status: "active",
      }));
      return;
    }

    // 3. POST /api/auth/login
    if (path === "/api/auth/login" && method === "POST") {
      if (!parsedBody.email || !parsedBody.password) {
        sendError(res, 400, "BAD_REQUEST", "邮箱和密码必填");
        return;
      }

      const initialRefreshToken = `ref-${Math.random().toString(36).substring(2)}`;
      refreshTokens.set(initialRefreshToken, 0);

      // Access token maxAge set to 2 seconds for E2E testing expiration flows
      const cookiesToSet = [
        serializeCookie("access_token", "valid-access-token", { path: "/", httpOnly: true, maxAge: 2, sameSite: "Lax" }),
        serializeCookie("refresh_token", initialRefreshToken, { path: "/", httpOnly: true, maxAge: 3600, sameSite: "Lax" }),
        serializeCookie("csrftoken", "csrf-cookie-val-999", { path: "/", maxAge: 3600, sameSite: "Lax" }),
      ];

      res.setHeader("Set-Cookie", cookiesToSet);
      res.statusCode = 200;
      res.end(JSON.stringify({
        user_id: "user-cookie-e2e",
        display_name: "Cookie Tester",
        email: parsedBody.email,
        email_verified: true,
        onboarding_completed: true,
        status: "active",
      }));
      return;
    }

    // 4. POST /api/auth/refresh
    if (path === "/api/auth/refresh" && method === "POST") {
      const refreshToken = cookies["refresh_token"];
      if (!refreshToken || !refreshTokens.has(refreshToken)) {
        sendError(res, 401, "UNAUTHORIZED", "Refresh token invalid");
        return;
      }

      refreshCount += 1;

      const rotationCount = refreshTokens.get(refreshToken);
      if (rotationCount >= 1) {
        // Reuse detection!
        refreshTokens.delete(refreshToken);
        res.setHeader("Set-Cookie", [
          serializeCookie("access_token", "", { path: "/", httpOnly: true, maxAge: 0, sameSite: "Lax" }),
          serializeCookie("refresh_token", "", { path: "/", httpOnly: true, maxAge: 0, sameSite: "Lax" }),
          serializeCookie("csrftoken", "", { path: "/", maxAge: 0, sameSite: "Lax" }),
        ]);
        sendError(res, 401, "REUSE_DETECTED", "Refresh token reused, session revoked");
        return;
      }

      // Mark this token as rotated
      refreshTokens.set(refreshToken, rotationCount + 1);

      // Create new refresh token
      const newRefreshToken = `ref-${Math.random().toString(36).substring(2)}`;
      refreshTokens.set(newRefreshToken, 0);

      res.setHeader("Set-Cookie", [
        serializeCookie("access_token", "valid-access-token-rotated", { path: "/", httpOnly: true, maxAge: 2, sameSite: "Lax" }),
        serializeCookie("refresh_token", newRefreshToken, { path: "/", httpOnly: true, maxAge: 3600, sameSite: "Lax" }),
      ]);
      res.statusCode = 204;
      res.end();
      return;
    }

    // 5. POST /api/auth/logout
    if (path === "/api/auth/logout" && method === "POST") {
      if (req.headers["x-test-fail-logout"] === "true") {
        sendError(res, 500, "SERVER_ERROR", "Internal server error during logout");
        return;
      }

      res.setHeader("Set-Cookie", [
        serializeCookie("access_token", "", { path: "/", httpOnly: true, maxAge: 0, sameSite: "Lax" }),
        serializeCookie("refresh_token", "", { path: "/", httpOnly: true, maxAge: 0, sameSite: "Lax" }),
        serializeCookie("csrftoken", "", { path: "/", maxAge: 0, sameSite: "Lax" }),
      ]);
      res.statusCode = 204;
      res.end();
      return;
    }

    // 6. POST /api/auth/change-password
    if (path === "/api/auth/change-password" && method === "POST") {
      res.statusCode = 204;
      res.end();
      return;
    }

    // E2E test helper routes
    if (path === "/__test__/reset" && method === "POST") {
      refreshCount = 0;
      refreshTokens.clear();
      res.setHeader("Set-Cookie", [
        serializeCookie("access_token", "", { path: "/", httpOnly: true, maxAge: 0, sameSite: "Lax" }),
        serializeCookie("refresh_token", "", { path: "/", httpOnly: true, maxAge: 0, sameSite: "Lax" }),
        serializeCookie("csrftoken", "", { path: "/", maxAge: 0, sameSite: "Lax" }),
      ]);
      res.statusCode = 200;
      res.end(JSON.stringify({ status: "reset" }));
      return;
    }

    if (path === "/__test__/expire-access" && method === "POST") {
      refreshCount = 0;
      res.setHeader("Set-Cookie", serializeCookie("access_token", "expired", { path: "/", httpOnly: true, maxAge: 0, sameSite: "Lax" }));
      res.statusCode = 200;
      res.end(JSON.stringify({ status: "expired" }));
      return;
    }

    if (path === "/__test__/refresh-count" && method === "GET") {
      res.statusCode = 200;
      res.end(JSON.stringify({ count: refreshCount }));
      return;
    }

    // Catch-all for other APIs
    if (path.startsWith("/api/")) {
      const isAuthRoute = path.startsWith("/api/auth/");
      if (!isAuthRoute) {
        const accessToken = cookies["access_token"];
        if (!accessToken || accessToken === "expired") {
          sendError(res, 401, "UNAUTHORIZED", "未登录或Token已过期");
          return;
        }
      }
      res.statusCode = 200;
      res.end(JSON.stringify({ success: true }));
      return;
    }

    sendError(res, 404, "NOT_FOUND", "Not Found");
  });
});

server.listen(PORT, () => {
  console.log(`E2E Auth Mock Server listening on http://localhost:${PORT}`);
});
