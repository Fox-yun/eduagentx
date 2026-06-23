import React from "react";
import { Link } from "react-router-dom";
import { HelpCircle, ArrowLeft } from "lucide-react";
import { AppShell } from "../../components/layout/AppShell";

export function NotFoundPage() {
  return (
    <AppShell>
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center select-none bg-page">
        <div className="h-24 w-24 rounded-full bg-danger/10 border border-danger/30 flex items-center justify-center mb-6 animate-bounce">
          <HelpCircle className="h-12 w-12 text-danger" />
        </div>
        <h1 className="text-3xl font-bold font-serif-cn text-ink mb-2">
          404 - 页面未找到
        </h1>
        <p className="text-muted max-w-md mb-8">
          您所寻找的学习路线或页面似乎迷失在了知识网格中。请返回控制台重新开始您的探险。
        </p>
        <Link
          to="/"
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-white font-medium hover:bg-primary-hover shadow-md hover:shadow-lg transition-all duration-200"
        >
          <ArrowLeft className="h-4 w-4" />
          返回学习控制台
        </Link>
      </div>
    </AppShell>
  );
}
