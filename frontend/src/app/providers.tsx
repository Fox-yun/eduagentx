import { ReactNode, useState } from "react";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "./queryClient";
import { ToastProvider } from "../components/feedback/Toast";
import { AuthBootstrap } from "../auth/AuthBootstrap";
import { DesktopBootstrap } from "../desktop/DesktopBootstrap";
import { NetworkStatusBanner } from "../desktop/NetworkStatusBanner";

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  // Instantiate QueryClient inside state so each mount gets a clean cache instance
  const [queryClient] = useState(() => createQueryClient());

  return (
    <DesktopBootstrap>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={300}>
          <ToastProvider>
            <NetworkStatusBanner />
            <AuthBootstrap>{children}</AuthBootstrap>
          </ToastProvider>
        </TooltipProvider>
      </QueryClientProvider>
    </DesktopBootstrap>
  );
}
