import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useCurrentUser } from "./authHooks";

export function ProtectedRoute() {
  const { data: user, status } = useCurrentUser();
  const location = useLocation();

  if (status === "pending") {
    return null;
  }

  if (!user) {
    const redirectParam = `?redirect=${encodeURIComponent(location.pathname + location.search)}`;
    return <Navigate to={`/auth/login${redirectParam}`} replace />;
  }

  return <Outlet />;
}
