import { ReactNode, useState } from "react";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "./queryClient";
import { ToastProvider } from "../components/feedback/Toast";
import { AuthBootstrap } from "../auth/AuthBootstrap";

interface AppProvidersProps {
  children: ReactNode;
}

export function AppProviders({ children }: AppProvidersProps) {
  // Instantiate QueryClient inside state so each mount gets a clean cache instance
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <ToastProvider>
          <AuthBootstrap>{children}</AuthBootstrap>
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
