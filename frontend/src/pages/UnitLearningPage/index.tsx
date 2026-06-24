import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getLearningPath } from "../../api/paths";
import {
  getUnitContent,
  generateUnitContent,
  regenerateUnitContent,
  createAssessment,
  submitAssessment,
} from "../../api/units";
import type { AssessmentModel, AssessmentSubmitResultModel } from "../../schemas/units";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useTaskStream } from "../../api/taskStream";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { ProgressBar } from "../../components/common/ProgressBar";
import {
  ArrowRight,
  Settings2,
  Sparkles,
  Loader2,
  AlertCircle,
  FileText,
  CheckCircle,
  RotateCcw,
  ArrowLeft,
  Lightbulb,
  X,
} from "lucide-react";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function UnitLearningPage() {
  const { pathId, nodeId } = useParams<{ pathId: string; nodeId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [localActiveTaskId, setLocalActiveTaskId] = useState<string | null>(null);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [preferenceText, setPreferenceText] = useState("");
  
  // Assessment state
  const [quizOpen, setQuizOpen] = useState(false);
  const [activeAssessment, setActiveAssessment] = useState<AssessmentModel | null>(null);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string | string[] | null>>({});
  const [assessmentResult, setAssessmentResult] = useState<AssessmentSubmitResultModel | null>(null);

  // Queries
  const { data: pathData } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });

  const {
    data: unitData,
    status: unitStatus,
    error: unitError,
    refetch: refetchUnit,
  } = useQuery({
    queryKey: queryKeys.unit(pathId || "", nodeId || ""),
    queryFn: ({ signal }) => getUnitContent(pathId || "", nodeId || "", signal),
    enabled: !!pathId && !!nodeId,
  });

  const nodeObj = pathData?.nodes?.find((n) => n.id === nodeId);

  // Task Stream Hook
  const activeTaskId = localActiveTaskId || unitData?.activeTaskId;
  const {
    progress,
    message: taskMessage,
    stage: taskStage,
    status: taskStatus,
  } = useTaskStream(activeTaskId);

  // Auto-refresh unit when content generation completes
  useEffect(() => {
    if (taskStatus === "completed") {
      toast("单元内容生成成功！", "success");
      setLocalActiveTaskId(null);
      refetchUnit();
      queryClient.invalidateQueries({ queryKey: queryKeys.path(pathId || "") });
      queryClient.invalidateQueries({ queryKey: queryKeys.resume() });
    }
  }, [taskStatus, pathId, refetchUnit, queryClient, toast]);

  // Generate mutation
  const { mutate: performGenerate, isPending: isGenerating } = useMutation({
    mutationFn: () => generateUnitContent(pathId || "", nodeId || ""),
    onSuccess: (res) => {
      toast("已提交内容生成请求，正在排队...", "success");
      setLocalActiveTaskId(res.activeTaskId);
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "生成内容失败，请重试"), "error");
    },
  });

  // Regenerate mutation
  const { mutate: performRegenerate, isPending: isRegenerating } = useMutation({
    mutationFn: (pref: string) => regenerateUnitContent(pathId || "", nodeId || "", pref),
    onSuccess: (res) => {
      toast("已提交重新生成请求，正在重新编写...", "success");
      setPreferenceText("");
      setPreferencesOpen(false);
      setLocalActiveTaskId(res.activeTaskId);
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "重新生成内容失败，请重试"), "error");
    },
  });

  // Create Assessment mutation
  const { mutate: performCreateAssessment, isPending: isCreatingAssessment } = useMutation({
    mutationFn: () => createAssessment(pathId || "", nodeId || ""),
    onSuccess: (res) => {
      setActiveAssessment(res);
      setQuizAnswers({});
      setAssessmentResult(null);
      setQuizOpen(true);
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "创建通关评估失败，请重试"), "error");
    },
  });

  // Submit Assessment mutation
  const { mutate: performSubmitAssessment, isPending: isSubmittingAssessment } = useMutation({
    mutationFn: (answers: Record<string, string | string[] | null>) =>
      submitAssessment(activeAssessment?.assessmentId || "", answers),
    onSuccess: (res) => {
      setAssessmentResult(res);
      toast(res.passed ? "恭喜，您已成功通关此节点！" : "评估未通过，建议重新学习本单元", res.passed ? "success" : "error");
      queryClient.invalidateQueries({ queryKey: queryKeys.path(pathId || "") });
      queryClient.invalidateQueries({ queryKey: queryKeys.resume() });
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "提交评估失败，请重试"), "error");
    },
  });

  const handlePreferencesSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performRegenerate(preferenceText);
  };

  const handleQuizAnswerChange = (questionId: string, value: string | string[] | null) => {
    setQuizAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  const handleQuizCheckboxChange = (questionId: string, option: string, checked: boolean) => {
    const current = Array.isArray(quizAnswers[questionId]) ? (quizAnswers[questionId] as string[]) : [];
    if (checked) {
      setQuizAnswers((prev) => ({ ...prev, [questionId]: [...current, option] }));
    } else {
      setQuizAnswers((prev) => ({ ...prev, [questionId]: current.filter((o) => o !== option) }));
    }
  };

  const handleQuizSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeAssessment) return;
    performSubmitAssessment(quizAnswers);
  };

  if (unitStatus === "pending") {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">正在加载学习单元...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  if (unitStatus === "error") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">获取单元数据失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {getErrorMessage(unitError, "连接服务器失败，请重试。")}
          </p>
          <button
            onClick={() => refetchUnit()}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer"
          >
            重载单元
          </button>
        </div>
      </AppShell>
    );
  }

  const isRegeneratedOrGenerating = !!activeTaskId || isGenerating || isRegenerating;

  return (
    <AppShell title={nodeObj?.title} courseName={pathData?.title}>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans items-center justify-start relative">
        <div className="w-full max-w-4xl p-6 sm:p-8 md:p-12 flex flex-col gap-6">
          
          {/* Breadcrumb Navigation Header */}
          <div className="flex items-center justify-between border-b border-border/60 pb-4">
            <button
              onClick={() => navigate(appRoutes.learningPath(pathId || ""))}
              className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink transition-colors cursor-pointer"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              返回学习图谱
            </button>

            <span className="text-[10px] font-bold text-primary bg-primary-soft/45 px-2.5 py-0.5 rounded-lg">
              {nodeObj?.difficulty ? (nodeObj.difficulty.charAt(0).toUpperCase() + nodeObj.difficulty.slice(1)) : "知识单元"} • Node Level {nodeObj?.level || 1}
            </span>
          </div>

          {/* Not Generated State */}
          {unitData?.status === "not_generated" && !isRegeneratedOrGenerating && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-12 text-center flex flex-col items-center gap-5 my-6">
              <div className="p-4 bg-primary-soft/30 text-primary rounded-full animate-pulse">
                <FileText className="h-10 w-10" />
              </div>
              <div className="max-w-md flex flex-col gap-1.5">
                <h2 className="text-lg font-serif-cn font-bold text-ink">本知识节点内容尚未生成</h2>
                <p className="text-xs text-muted leading-relaxed">
                  EduAgentX 智能体将根据当前图谱的拓扑层级、您的 onboarding 角色偏好以及上下文要求，为您实时生成导学、章节讲解和代码示例。
                </p>
              </div>
              <button
                onClick={() => performGenerate()}
                className="inline-flex items-center gap-1.5 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
              >
                <Sparkles className="h-4 w-4 fill-white" />
                生成本单元学习材料
              </button>
            </div>
          )}

          {/* Failed State */}
          {unitData?.status === "failed" && !isRegeneratedOrGenerating && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-5 my-4">
              <div className="p-5 bg-danger/10 border border-danger/20 rounded-xl flex items-start gap-3.5">
                <div className="p-2 bg-danger/20 text-danger rounded-lg shrink-0">
                  <AlertCircle className="h-6 w-6" />
                </div>
                <div className="flex-1 flex flex-col gap-1">
                  <h3 className="text-sm font-bold text-ink">学习单元生成失败</h3>
                  <p className="text-xs text-muted leading-relaxed">
                    智能体在生成该节点的导学大纲时遇到了网络异常：
                  </p>
                  <p className="text-xs text-danger font-mono font-semibold bg-panel p-2.5 rounded-lg border border-border mt-1.5">
                    {unitData.error || "服务器响应超时，处理大纲失败。"}
                  </p>
                </div>
              </div>
              
              <div className="flex justify-end gap-3 pt-3 border-t border-border/60">
                <button
                  onClick={() => setPreferencesOpen(true)}
                  className="px-4 py-2 border border-border hover:bg-page text-xs font-semibold text-ink rounded-lg cursor-pointer transition-colors"
                >
                  设定生成偏好并重试
                </button>
                <button
                  onClick={() => performGenerate()}
                  className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow cursor-pointer"
                >
                  重新生成
                </button>
              </div>
            </div>
          )}

          {/* Active Generating state (Task Stream Overlay inline) */}
          {isRegeneratedOrGenerating && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-5 my-4">
              <div className="flex flex-col gap-1">
                <h3 className="text-base font-serif-cn font-bold text-ink flex items-center gap-2">
                  <Loader2 className="h-4.5 w-4.5 text-primary animate-spin" />
                  {taskStage ? `AI 智能体正在编写：${taskStage}` : "正在启动单元编写智能体..."}
                </h3>
                <p className="text-xs text-muted">结合全图拓扑、前置节点掌握情况和您的偏好语言进行针对性讲解。</p>
              </div>

              <div className="flex justify-between items-center text-xs text-muted font-semibold">
                <span>生成进度</span>
                <span className="font-mono text-ink text-sm font-bold">{progress}%</span>
              </div>
              <ProgressBar progress={progress} height="h-2.5" />

              <div className="p-4 bg-page/40 border border-border rounded-xl">
                <span className="text-[10px] font-bold text-primary uppercase tracking-wider block mb-1">执行状态日志</span>
                <p className="text-xs text-ink leading-relaxed font-mono whitespace-pre-wrap max-h-36 overflow-y-auto">
                  {taskMessage || "正在连接编写流..."}
                </p>
              </div>
            </div>
          )}

          {/* Ready State: Main Learning Content */}
          {unitData?.status === "ready" && !isRegeneratedOrGenerating && (
            <div className="flex flex-col gap-8">
              {/* Main Markdown explanation */}
              <article className="bg-panel border border-border rounded-2xl shadow-card p-6 sm:p-8 select-text">
                <div className="text-xs text-ink leading-relaxed flex flex-col gap-4 font-sans select-text">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      h1: ({ node: _node, ...props }) => (
                        <h1 className="text-lg font-serif-cn font-bold border-b border-border/60 pb-1.5 mt-5 text-ink" {...props} />
                      ),
                      h2: ({ node: _node, ...props }) => (
                        <h2 className="text-sm font-bold mt-4 text-ink flex items-center gap-1.5" {...props} />
                      ),
                      p: ({ node: _node, ...props }) => (
                        <p className="text-xs text-muted leading-relaxed mt-1" {...props} />
                      ),
                      ul: ({ node: _node, ...props }) => (
                        <ul className="list-disc pl-5 flex flex-col gap-1.5 mt-1" {...props} />
                      ),
                      ol: ({ node: _node, ...props }) => (
                        <ol className="list-decimal pl-5 flex flex-col gap-1.5 mt-1" {...props} />
                      ),
                      li: ({ node: _node, ...props }) => (
                        <li className="text-xs text-muted" {...props} />
                      ),
                      code: ({ node: _node, inline, className: _className, children, ...props }: any) => {
                        return inline ? (
                          <code className="bg-page border border-border px-1 py-0.5 rounded font-mono text-[10px] text-primary" {...props}>
                            {children}
                          </code>
                        ) : (
                          <pre className="bg-page/70 border border-border p-3.5 rounded-xl font-mono text-[10px] text-ink overflow-x-auto whitespace-pre my-2 select-text">
                            <code {...props}>{children}</code>
                          </pre>
                        );
                      },
                      table: ({ node: _node, ...props }) => (
                        <table className="w-full text-xs text-left border-collapse border border-border rounded-xl my-3" {...props} />
                      ),
                      th: ({ node: _node, ...props }) => (
                        <th className="bg-page p-2 font-bold border border-border text-ink" {...props} />
                      ),
                      td: ({ node: _node, ...props }) => (
                        <td className="p-2 border border-border text-muted" {...props} />
                      ),
                    }}
                  >
                    {unitData.content || ""}
                  </ReactMarkdown>
                </div>
              </article>

              {/* Action buttons at bottom */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border/60 pt-4">
                <button
                  onClick={() => setPreferencesOpen(true)}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-border hover:bg-panel-soft text-xs font-semibold text-ink transition-colors cursor-pointer"
                >
                  <RotateCcw className="h-3.5 w-3.5 text-muted" />
                  提交偏好重新生成
                </button>

                <button
                  onClick={() => performCreateAssessment()}
                  disabled={isCreatingAssessment}
                  className="inline-flex items-center gap-1.5 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
                >
                  {isCreatingAssessment ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      正在创建评估...
                    </>
                  ) : (
                    <>
                      开始通关评估
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

        </div>
      </div>

      {/* Preferences Dialog */}
      {preferencesOpen && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-6 transition-opacity">
          <div className="w-full max-w-md bg-panel border border-border rounded-2xl shadow-card p-6 flex flex-col gap-4 select-none animate-fade-in">
            <div className="flex flex-col gap-0.5 border-b border-border/50 pb-3">
              <h3 className="text-sm font-bold text-ink font-serif-cn flex items-center gap-1.5">
                <Settings2 className="h-4.5 w-4.5 text-primary" />
                个性化生成偏好
              </h3>
              <p className="text-xs text-muted font-medium">您可以为智能体提供本次编写的格式、难度或重点偏好。</p>
            </div>

            <form onSubmit={handlePreferencesSubmit} className="flex flex-col gap-4">
              <textarea
                rows={3}
                value={preferenceText}
                onChange={(e) => setPreferenceText(e.target.value)}
                placeholder="例如：多给出一点 Python 的代码示例，或者以工程项目架构的眼光来讲解..."
                className="w-full px-3 py-2 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                required
              />

              <div className="flex justify-end gap-2.5 pt-2 border-t border-border/50">
                <button
                  type="button"
                  onClick={() => {
                    setPreferencesOpen(false);
                    setPreferenceText("");
                  }}
                  className="px-4 py-2.5 border border-border rounded-xl text-xs font-semibold text-ink hover:bg-page cursor-pointer transition-colors"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={!preferenceText.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                >
                  重新编写
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Quiz Modal / Assessment Overlay */}
      {quizOpen && activeAssessment && (
        <div className="fixed inset-0 bg-black/60 z-40 flex items-center justify-center p-6 overflow-y-auto select-none">
          <div className="w-full max-w-2xl bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6 my-8 animate-scale-up">
            
            {/* Header */}
            <div className="flex flex-col gap-1 border-b border-border/60 pb-4 relative">
              <span className="text-[10px] font-bold text-primary flex items-center gap-1">
                <Sparkles className="h-3.5 w-3.5" />
                通关评测 (Node Assessment)
              </span>
              <h3 className="text-lg font-serif-cn font-bold text-ink">
                测试挑战：{nodeObj?.title}
              </h3>
              {!assessmentResult && (
                <button
                  onClick={() => setQuizOpen(false)}
                  className="absolute right-0 top-0 p-1.5 rounded-lg hover:bg-panel-soft text-muted hover:text-ink cursor-pointer"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Quiz Body form */}
            {!assessmentResult ? (
              <form onSubmit={handleQuizSubmit} className="flex flex-col gap-6">
                {activeAssessment.questions.map((q, index: number) => {
                  const currentAns = quizAnswers[q.id];

                  return (
                    <div key={q.id} className="p-4 bg-page/35 border border-border rounded-xl flex flex-col gap-3">
                      <div className="text-xs font-bold text-ink flex items-start gap-1.5 leading-relaxed">
                        <span className="text-primary font-mono">{index + 1}.</span>
                        <span>{q.text}</span>
                      </div>

                      {/* 1. Single Choice */}
                      {q.type === "single_choice" && q.options && (
                        <div className="flex flex-col gap-2 pl-4">
                          {q.options.map((option: string) => (
                            <label key={option} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium">
                              <input
                                type="radio"
                                name={q.id}
                                value={option}
                                checked={currentAns === option}
                                onChange={() => handleQuizAnswerChange(q.id, option)}
                                disabled={isSubmittingAssessment}
                                className="w-4 h-4 text-primary focus:ring-primary border-border bg-panel"
                              />
                              {option}
                            </label>
                          ))}
                        </div>
                      )}

                      {/* 2. Multiple Choice */}
                      {q.type === "multiple_choice" && q.options && (
                        <div className="flex flex-col gap-2 pl-4">
                          {q.options.map((option: string) => {
                            const isChecked = Array.isArray(currentAns) && currentAns.includes(option);
                            return (
                              <label key={option} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium">
                                <input
                                  type="checkbox"
                                  checked={isChecked}
                                  onChange={(e) => handleQuizCheckboxChange(q.id, option, e.target.checked)}
                                  disabled={isSubmittingAssessment}
                                  className="w-4 h-4 rounded text-primary focus:ring-primary border-border bg-panel"
                                />
                                {option}
                              </label>
                            );
                          })}
                        </div>
                      )}

                      {/* 3. Short Answer */}
                      {q.type === "short_answer" && (
                        <div className="pl-4">
                          <textarea
                            rows={3}
                            placeholder="请在此输入您的解答说明..."
                            value={currentAns || ""}
                            onChange={(e) => handleQuizAnswerChange(q.id, e.target.value)}
                            disabled={isSubmittingAssessment}
                            className="w-full px-3 py-2 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                          />
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Submit button */}
                <div className="flex justify-end pt-3 border-t border-border/60">
                  <button
                    type="submit"
                    disabled={isSubmittingAssessment || activeAssessment.questions.length === 0}
                    className="inline-flex items-center gap-1.5 px-6 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                  >
                    {isSubmittingAssessment ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        正在提交评估...
                      </>
                    ) : (
                      <>
                        提交评估答案
                        <ArrowRight className="h-4 w-4" />
                      </>
                    )}
                  </button>
                </div>
              </form>
            ) : (
              // Quiz Results State
              <div className="flex flex-col gap-6">
                <div
                  className={`p-5 rounded-2xl border flex items-start gap-4 ${
                    assessmentResult.passed
                      ? "bg-success/5 border-success/20 text-success"
                      : "bg-danger/5 border-danger/20 text-danger"
                  }`}
                >
                  <div className="p-2 rounded-lg bg-panel shrink-0 shadow-sm">
                    {assessmentResult.passed ? (
                      <CheckCircle className="h-7 w-7 text-success" />
                    ) : (
                      <AlertCircle className="h-7 w-7 text-danger" />
                    )}
                  </div>

                  <div className="flex-1 flex flex-col gap-1">
                    <div className="flex items-baseline justify-between">
                      <h4 className="text-sm font-bold text-ink">
                        {assessmentResult.passed ? "通关评估已通过！" : "未能完成本次通关"}
                      </h4>
                      <span className="text-lg font-mono font-bold">
                        得分为 {assessmentResult.score} / 100
                      </span>
                    </div>

                    <p className="text-xs text-muted leading-relaxed mt-1">
                      {assessmentResult.passed
                        ? "您已掌握该节点的关键概念，节点已解锁，继续探索后面的更高 Level 吧！"
                        : "评估未能达标（需 60 分以上）。请重新阅读单元讲解或在图谱上复习相关前置内容。"}
                    </p>

                    {assessmentResult.masteryDelta !== null && assessmentResult.masteryDelta !== 0 && (
                      <span className="text-xs font-semibold font-mono text-primary flex items-center gap-1 mt-2">
                        <Lightbulb className="h-4.5 w-4.5" />
                        掌握度已更新：{assessmentResult.masteryDelta > 0 ? `+${assessmentResult.masteryDelta}` : assessmentResult.masteryDelta}%
                      </span>
                    )}
                  </div>
                </div>

                {/* AI Review feedback text */}
                <div className="p-5 bg-page/35 border border-border rounded-2xl flex flex-col gap-2">
                  <span className="text-[10px] font-bold text-primary uppercase tracking-wider">智能体学习反馈</span>
                  <p className="text-xs text-ink leading-relaxed select-text font-serif-cn whitespace-pre-wrap">
                    {assessmentResult.feedback || "AI 智能体未给出具体评价，请继续前行！"}
                  </p>
                </div>

                {/* Close results / navigation back to path */}
                <div className="flex justify-end pt-3 border-t border-border/60">
                  <button
                    onClick={() => {
                      setQuizOpen(false);
                      setAssessmentResult(null);
                      navigate(appRoutes.learningPath(pathId || ""));
                    }}
                    className="px-6 py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl shadow cursor-pointer transition-all"
                  >
                    完成并返回图谱
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </AppShell>
  );
}
