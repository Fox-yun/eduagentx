import React, { forwardRef } from "react";
import clsx from "clsx";
import * as Tooltip from "@radix-ui/react-tooltip";

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: React.ReactNode;
  tooltip?: string;
  variant?: "primary" | "secondary" | "ghost" | "accent";
  size?: "sm" | "md" | "lg";
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ icon, tooltip, variant = "secondary", size = "md", className, ...props }, ref) => {
    const button = (
      <button
        ref={ref}
        type="button"
        className={clsx(
          "inline-flex items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
          // Variants
          {
            "bg-primary text-white hover:bg-primary-hover": variant === "primary",
            "bg-panel border border-border text-ink hover:bg-panel-soft": variant === "secondary",
            "text-muted hover:text-ink hover:bg-panel-soft": variant === "ghost",
            "bg-accent text-white hover:bg-accent/90": variant === "accent",
          },
          // Sizes
          {
            "p-1.5 h-8 w-8 text-sm": size === "sm",
            "p-2 h-10 w-10 text-base": size === "md",
            "p-2.5 h-12 w-12 text-lg": size === "lg",
          },
          className
        )}
        {...props}
      >
        {icon}
      </button>
    );

    if (tooltip) {
      return (
        <Tooltip.Root>
          <Tooltip.Trigger asChild>{button}</Tooltip.Trigger>
          <Tooltip.Portal>
            <Tooltip.Content
              side="top"
              align="center"
              sideOffset={4}
              className="z-50 select-none rounded bg-ink px-2.5 py-1.5 text-xs text-panel shadow-md tooltip-enter"
            >
              {tooltip}
              <Tooltip.Arrow className="fill-ink" />
            </Tooltip.Content>
          </Tooltip.Portal>
        </Tooltip.Root>
      );
    }

    return button;
  }
);

IconButton.displayName = "IconButton";
