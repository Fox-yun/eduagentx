import React from "react";
import { TopBar } from "./TopBar";

interface AppShellProps {
  children: React.ReactNode;
  title?: string;
  courseName?: string;
}

export function AppShell({ children, title, courseName }: AppShellProps) {
  return (
    <div className="h-screen w-screen flex flex-col bg-page text-ink overflow-hidden relative">
      {/* 1. Global Paper Noise Overlay */}
      <div
        className="fixed inset-0 pointer-events-none opacity-[0.025] z-50 bg-repeat bg-[size:120px_120px]"
        style={{ backgroundImage: "url(/textures/paper-noise.png)" }}
        aria-hidden="true"
      />

      {/* 2. Top Navigation Bar */}
      <TopBar title={title} courseName={courseName} />

      {/* 3. Main Workspace Area */}
      <main className="flex-1 min-h-0 flex flex-col relative">
        {children}
      </main>
    </div>
  );
}
