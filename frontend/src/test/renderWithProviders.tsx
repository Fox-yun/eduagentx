import React from "react";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { ToastProvider } from "../components/feedback/Toast";
import { AuthBootstrap } from "../auth/AuthBootstrap";
import { UserModel } from "../schemas/users";
import { queryKeys } from "../api/queryKeys";
import { http, HttpResponse, RequestHandler } from "msw";
import { server } from "./server";

export interface RenderOptions {
  route?: string;
  authenticatedUser?: UserModel | null;
  queryClient?: QueryClient;
  handlers?: RequestHandler[];
}

export function renderWithProviders(
  ui: React.ReactElement,
  options: RenderOptions = {}
) {
  const {
    route = "/",
    authenticatedUser,
    queryClient,
    handlers = [],
  } = options;

  // Set up mock handlers in MSW
  const mswHandlers: RequestHandler[] = [...handlers];

  if (authenticatedUser === null) {
    mswHandlers.push(
      http.get("/api/auth/me", () => {
        return new HttpResponse(null, { status: 401 });
      }),
      http.get("http://localhost/api/auth/me", () => {
        return new HttpResponse(null, { status: 401 });
      }),
      http.get("http://localhost:3000/api/auth/me", () => {
        return new HttpResponse(null, { status: 401 });
      }),
      http.post("/api/auth/refresh", () => {
        return new HttpResponse(null, { status: 401 });
      }),
      http.post("http://localhost/api/auth/refresh", () => {
        return new HttpResponse(null, { status: 401 });
      }),
      http.post("http://localhost:3000/api/auth/refresh", () => {
        return new HttpResponse(null, { status: 401 });
      })
    );
  } else {
    const userToMock = authenticatedUser || {
      id: "user-123",
      displayName: "李明",
      email: "liming@example.com",
      emailVerified: true,
      onboardingCompleted: true,
      status: "active",
    };
    const mockResponseFn = () => {
      return HttpResponse.json({
        user_id: userToMock.id,
        display_name: userToMock.displayName,
        email: userToMock.email,
        email_verified: userToMock.emailVerified,
        onboarding_completed: userToMock.onboardingCompleted,
        status: userToMock.status || "active",
      });
    };
    mswHandlers.push(
      http.get("/api/auth/me", mockResponseFn),
      http.get("http://localhost/api/auth/me", mockResponseFn),
      http.get("http://localhost:3000/api/auth/me", mockResponseFn)
    );
  }

  // Register the MSW handlers for this specific test
  server.use(...mswHandlers);

  // Construct a fresh QueryClient if not provided
  const testQueryClient =
    queryClient ||
    new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
          staleTime: 0,
        },
        mutations: {
          retry: false,
        },
      },
    });

  // Pre-populate the auth.me query cache to avoid flash of loading screen for authenticated users
  if (authenticatedUser !== null) {
    const userToMock = authenticatedUser || {
      id: "user-123",
      displayName: "李明",
      email: "liming@example.com",
      emailVerified: true,
      onboardingCompleted: true,
      status: "active",
    };
    testQueryClient.setQueryData(queryKeys.auth.me(), userToMock);
  }

  const result = render(
    <QueryClientProvider client={testQueryClient}>
      <MemoryRouter initialEntries={[route]}>
        <TooltipProvider delayDuration={300}>
          <ToastProvider>
            <AuthBootstrap>{ui}</AuthBootstrap>
          </ToastProvider>
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );

  return {
    ...result,
    queryClient: testQueryClient,
  };
}
