import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useCurrentUser } from "./authHooks";

export function AccountStatusRoute() {
  const { data: user, status } = useCurrentUser();

  if (status === "pending") {
    return null;
  }

  if (user) {
    if (user.status === "locked") {
      return <Navigate to="/account-locked" replace />;
    }
    if (user.status === "disabled") {
      return <Navigate to="/account-disabled" replace />;
    }
  }

  return <Outlet />;
}
export default AccountStatusRoute;
