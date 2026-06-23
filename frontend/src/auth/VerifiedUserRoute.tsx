import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "./authHooks";

export function VerifiedUserRoute() {
  const { data: user, status } = useCurrentUser();

  if (status === "pending") {
    return null;
  }

  if (user && !user.emailVerified) {
    return <Navigate to="/auth/verify-email" replace />;
  }

  return <Outlet />;
}
