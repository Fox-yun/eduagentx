import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "./authHooks";

export function OnboardingRoute() {
  const { data: user, status } = useCurrentUser();

  if (status === "pending") {
    return null;
  }

  if (user && !user.onboardingCompleted) {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}
