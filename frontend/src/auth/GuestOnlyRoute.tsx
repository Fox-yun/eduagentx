import React from "react";
import { Navigate, Outlet, useSearchParams } from "react-router-dom";
import { useCurrentUser } from "./authHooks";
import { sanitizeRedirect } from "./sanitizeRedirect";

export function GuestOnlyRoute() {
  const { data: user, status } = useCurrentUser();
  const [searchParams] = useSearchParams();

  if (status === "pending") {
    return null;
  }

  if (user) {
    const redirect = sanitizeRedirect(searchParams.get("redirect"));
    return <Navigate to={redirect} replace />;
  }

  return <Outlet />;
}
