import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  createProfileConversation,
  getProfileConversation,
  sendProfileMessage,
  finalizeProfileConversation,
} from "../../api/profile";
import { ConversationStateModel } from "../../schemas/profile";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { Bot, User, Send, CheckCircle, AlertCircle, Loader2, Sparkles, CornerUpLeft } from "lucide-react";
import { DIMENSION_LABELS, PROFILE_DIMENSIONS } from "../../schemas/profile";

export function ProfileConversationPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [messageInput, setMessageInput] = useState("");
  const [learningGoalInput, setLearningGoalInput] = useState(searchParams.get("goal") || "");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Query: load existing conversation if sessionId is provided
  const {
    data: conversation,
    status: conversationStatus,
    error: conversationError,
    refetch: refetchConversation,
  } = useQuery({
    queryKey: queryKeys.profileConversation(sessionId || ""),
    queryFn: ({ signal }) => getProfileConversation(sessionId || "", signal),
    enabled: !!sessionId,
    staleTime: 0,
  });

  // Mutation: create new conversation
  const { mutate: createConversation, isPending: isCreating } = useMutation({
    mutationFn: (goal: string) => createProfileConversation(goal),
    onSuccess: (result) => {
      navigate(appRoutes.profileConversationSession(result.sessionId), { replace: true });
    },
    onError: (err: any) => {
      toast(err.message || "创建对话失败，请重试", "error");
    },
  });

  // Mutation: send message
  const { mutate: sendMessage, isPending: isSending } = useMutation({
    mutationFn: ({ sessionId, message }: { sessionId: string; message: string }) =>
      sendProfileMessage(sessionId, message),
    onSuccess: () => {
      setMessageInput("");
      refetchConversation();
    },
    onError: (err: any) => {
      toast(err.message || "发送消息失败，请重试", "error");
    },
  });

  // Mutation: finalize profile
  const { mutate: finalizeProfile, isPending: isFinalizing } = useMutation({
    mutationFn: (sid: string) => finalizeProfileConversation(sid),
    onSuccess: () => {
      toast("学习画像生成成功！", "success");
      navigate(appRoutes.profileSummary());
    },
    onError: (err: any) => {
      toast(err.message || "完成画像失败，请重试", "error");
    },
  });

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation?.messages]);

  // Calculate covered dimensions count
  const coveredCount = Object.keys(conversation?.extractedDimensions || {}).length;
  const totalCount = PROFILE_DIMENSIONS.length;
  const progressPercent = totalCount > 0 ? (coveredCount / totalCount) * 100 : 0;

  // Handle starting a new conversation
  const handleStartConversation = (e: React.FormEvent) => {
    e.preventDefault();
    if (!learningGoalInput.trim()) {
      toast("请输入您的学习目标", "error");
      return;
    }
    if (learningGoalInput.length < 10) {
      toast("请详细描述您的学习目标，至少 10 个字符", "error");
      return;
    }
    createConversation(learningGoalInput);
  };

  // Handle sending a message
  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionId || !messageInput.trim()) return;
    sendMessage({ sessionId, message: messageInput.trim() });
  };

  // Handle finalizing the profile
  const handleFinalize = () => {
    if (!sessionId) return;
    if (!conversation?.readyToFinalize) {
      toast("请先回答更多问题，系统需要更多信息才能生成准确的画像", "error");
      return;
    }
    finalizeProfile(sessionId);
  };

  // ──────────────────────────────────────────────
  // Render: No session ID - Show goal input form
  // ──────────────────────────────────────────────
  if (!sessionId) {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans p-6 sm:p-8 md:p-12 items-center justify-start">
          <div className="w-full max-w-2xl bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6">
            {/* Header */}
            <div className="flex flex-col gap-1 border-b border-border/60 pb-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5" />
                学习画像
              </span>
              <h1 className="text-2xl font-serif-cn font-bold text-ink flex items-center gap-2">
                创建个性化学习画像
              </h1>
              <p className="text-xs text-muted">
                通过对话，系统将了解您的八维学习特征，为您生成专属的学习画像。
              </p>
            </div>

            {/* Goal Input Form */}
            <form onSubmit={handleStartConversation} className="flex flex-col gap-6">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink">您的学习目标是什么？</label>
                <textarea
                  rows={4}
                  value={learningGoalInput}
                  onChange={(e) => setLearningGoalInput(e.target.value)}
                  disabled={isCreating}
                  placeholder="我想在两个月内掌握 Python 数据分析，最终可以独立完成一个真实的项目..."
                  className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                />
              </div>

              {/* Bottom Actions */}
              <div className="flex justify-between items-center border-t border-border/60 pt-4">
                <button
                  type="button"
                  onClick={() => navigate(appRoutes.home())}
                  disabled={isCreating}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer"
                >
                  <CornerUpLeft className="h-3.5 w-3.5 text-muted" />
                  返回首页
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !learningGoalInput.trim()}
                  className="inline-flex items-center gap-1.5 px-6 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                >
                  {isCreating ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      正在创建对话...
                    </>
                  ) : (
                    <>
                      开始对话
                      <Sparkles className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      </AppShell>
    );
  }

  // ──────────────────────────────────────────────
  // Render: Loading conversation
  // ──────────────────────────────────────────────
  if (conversationStatus === "pending") {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">正在加载对话...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  // ──────────────────────────────────────────────
  // Render: Error
  // ──────────────────────────────────────────────
  if (conversationStatus === "error") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">加载对话失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {(conversationError as any)?.message || "无法加载对话数据，请重试或返回首页"}
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => refetchConversation()}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer"
            >
              重试
            </button>
            <button
              onClick={() => navigate(appRoutes.home())}
              className="inline-flex items-center gap-1.5 px-4 py-2 border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer"
            >
              返回首页
            </button>
          </div>
        </div>
      </AppShell>
    );
  }

  // ──────────────────────────────────────────────
  // Render: Conversation UI
  // ──────────────────────────────────────────────
  const messages = conversation?.messages || [];
  const readyToFinalize = conversation?.readyToFinalize || false;
  const turnCount = conversation?.turnCount || 0;
  const missingDimensions = conversation?.extractedDimensions
    ? PROFILE_DIMENSIONS.filter((d) => !(d in conversation.extracted_dimensions))
    : PROFILE_DIMENSIONS;

  return (
    <AppShell>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-hidden font-sans">
        {/* Header */}
        <div className="border-b border-border bg-panel px-6 py-4 shrink-0">
          <div className="max-w-4xl mx-auto">
            <h1 className="text-lg font-serif-cn font-bold text-ink flex items-center gap-2">
              <Bot className="h-5 w-5 text-primary" />
              学习画像对话
            </h1>
            {/* Progress bar */}
            <div className="mt-3 flex flex-col gap-1">
              <div className="flex justify-between items-center text-[10px] text-muted">
                <span>画像维度覆盖度</span>
                <span>{coveredCount}/{totalCount}</span>
              </div>
              <div className="h-2 bg-page rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all duration-500 ease-out"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              {missingDimensions.length > 0 && missingDimensions.length < 4 && (
                <p className="text-[10px] text-muted mt-1">
                  还需了解：{missingDimensions.slice(0, 3).map((d) => DIMENSION_LABELS[d] || d).join("、")}
                  {missingDimensions.length > 3 && "等"}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="max-w-4xl mx-auto p-4 sm:p-6">
            <div className="flex flex-col gap-4">
              {messages.length === 0 && (
                <div className="text-center py-12">
                  <Bot className="h-12 w-12 text-primary/40 mx-auto mb-3" />
                  <p className="text-xs text-muted">对话内容为空</p>
                </div>
              )}

              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
                >
                  {/* Avatar */}
                  <div
                    className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                      msg.role === "user"
                        ? "bg-accent/20 border border-accent/40 text-accent"
                        : "bg-primary-soft text-primary"
                    }`}
                  >
                    {msg.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                  </div>

                  {/* Message Bubble */}
                  <div
                    className={`max-w-[70%] px-4 py-2.5 rounded-2xl ${
                      msg.role === "user"
                        ? "bg-primary text-white rounded-tr-sm"
                        : "bg-panel border border-border rounded-tl-sm"
                    }`}
                  >
                    <p className="text-xs leading-relaxed whitespace-pre-wrap break-words">{msg.content}</p>
                  </div>
                </div>
              ))}

              {/* Invisible element for auto-scroll */}
              <div ref={messagesEndRef} />

              {/* Loading indicator */}
              {(isCreating || isSending) && (
                <div className="flex gap-3">
                  <div className="shrink-0 w-8 h-8 rounded-full bg-primary-soft flex items-center justify-center">
                    <Bot className="h-4 w-4 text-primary" />
                  </div>
                  <div className="bg-panel border border-border px-4 py-2.5 rounded-2xl rounded-tl-sm">
                    <div className="flex gap-1.5">
                      <div className="w-2 h-2 bg-muted rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-2 h-2 bg-muted rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-2 h-2 bg-muted rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Input Area */}
        <div className="border-t border-border bg-panel px-6 py-4 shrink-0">
          <div className="max-w-4xl mx-auto">
            {/* Finalize Button */}
            {readyToFinalize && (
              <div className="mb-4">
                <button
                  onClick={handleFinalize}
                  disabled={isFinalizing}
                  className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-success hover:bg-success-hover text-white text-xs font-bold shadow-md transition-all cursor-pointer disabled:opacity-50"
                >
                  {isFinalizing ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      正在生成画像...
                    </>
                  ) : (
                    <>
                      <CheckCircle className="h-4.5 w-4.5" />
                      完成画像生成
                    </>
                  )}
                </button>
              </div>
            )}

            {/* Message Input */}
            {conversation?.status === "active" && !readyToFinalize && (
              <form onSubmit={handleSendMessage} className="flex gap-3">
                <input
                  type="text"
                  value={messageInput}
                  onChange={(e) => setMessageInput(e.target.value)}
                  disabled={isSending}
                  placeholder="输入您的回答..."
                  className="flex-1 px-4 py-2.5 bg-page border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
                <button
                  type="submit"
                  disabled={isSending || !messageInput.trim()}
                  className="px-4 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                >
                  <Send className="h-4 w-4" />
                </button>
              </form>
            )}

            {conversation?.status !== "active" && (
              <div className="text-center">
                <button
                  onClick={() => navigate(appRoutes.profileSummary())}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border hover:bg-page text-xs font-medium text-ink transition-colors cursor-pointer"
                >
                  查看我的画像
                  <Sparkles className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}