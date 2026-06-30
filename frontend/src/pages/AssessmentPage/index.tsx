import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getLearningPath } from "../../api/paths";
import { createAssessment, submitAssessment } from "../../api/units";
import type { AssessmentModel, AssessmentSubmitResultModel } from "../../schemas/units";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import {
  ArrowRight,
  ArrowLeft,
  Sparkles,
  Loader2,
  AlertCircle,
  CheckCircle,
  Lightbulb,
} from "lucide-react";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function AssessmentPage() {
  const { pathId, nodeId } = useParams<{ pathId: string; nodeId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [activeAssessment, setActiveAssessment] = useState<AssessmentModel | null>(null);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string | string[] | null>>({});
  const [assessmentResult, setAssessmentResult] = useState<AssessmentSubmitResultModel | null>(null);

  const { data: pathData } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });

  const nodeObj = pathData?.nodes?.find((n) => n.id === nodeId);

  // Create assessment mutation
  const { mutate: performCreateAssessment, isPending: isCreating } = useMutation({
    mutationFn: () => createAssessment(pathId || "", nodeId || ""),
    onSuccess: (res) => {
      setActiveAssessment(res);
      setQuizAnswers({});
      setAssessmentResult(null);
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "创建通关评估失败，请重试"), "error");
    },
  });

  // Submit assessment mutation
  const { mutate: performSubmit, isPending: isSubmitting } = useMutation({
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

  const handleAnswerChange = (questionId: string, value: string) => {
    setQuizAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  const handleCheckboxChange = (questionId: string, option: string, checked: boolean) => {
    const current = Array.isArray(quizAnswers[questionId]) ? (quizAnswers[questionId] as string[]) : [];
    if (checked) {
      setQuizAnswers((prev) => ({ ...prev, [questionId]: [...current, option] }));
    } else {
      setQuizAnswers((prev) => ({ ...prev, [questionId]: current.filter((o) => o !== option) }));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeAssessment) return;
    performSubmit(quizAnswers);
  };

  return (
    <AppShell title={`通关评估 — ${nodeObj?.title || ""}`} courseName={pathData?.title}>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans items-center">
        <div className="w-full max-w-3xl p-6 sm:p-8 md:p-12 flex flex-col gap-6">

          {/* Header */}
          <div className="flex items-center justify-between border-b border-border/60 pb-4">
            <button
              onClick={() => navigate(appRoutes.learningUnit(pathId || "", nodeId || ""))}
              className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink transition-colors cursor-pointer"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              返回学习单元
            </button>
            <span className="text-[10px] font-bold text-primary bg-primary-soft/45 px-2.5 py-0.5 rounded-lg">
              通关评测 (Assessment)
            </span>
          </div>

          {/* No assessment yet — show create button */}
          {!activeAssessment && !assessmentResult && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-12 text-center flex flex-col items-center gap-5">
              <div className="p-4 bg-primary-soft/30 text-primary rounded-full animate-pulse">
                <Sparkles className="h-10 w-10" />
              </div>
              <div className="max-w-md flex flex-col gap-1.5">
                <h2 className="text-lg font-serif-cn font-bold text-ink">准备好了吗？</h2>
                <p className="text-xs text-muted leading-relaxed">
                  通关评估将测试您对「{nodeObj?.title || "本节点"}」的掌握程度。评估包含 ≥10 道题目（单选、多选、简答），需 60 分以上通过。
                </p>
              </div>
              <button
                onClick={() => performCreateAssessment()}
                disabled={isCreating}
                className="inline-flex items-center gap-1.5 px-8 py-3.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-sm font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
              >
                {isCreating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在生成评估题目...
                  </>
                ) : (
                  <>
                    开始通关评估 (≥10题)
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </div>
          )}

          {/* Loading state */}
          {isCreating && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col items-center gap-4">
              <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
              <p className="text-xs text-muted font-semibold animate-pulse">智能体正在生成评估题目...</p>
              <p className="text-[10px] text-muted-soft">基于节点内容生成 10+ 道题目，请稍候</p>
            </div>
          )}

          {/* Quiz form */}
          {activeAssessment && !assessmentResult && (
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              <div className="bg-panel border border-border rounded-2xl shadow-card p-6 flex flex-col gap-1">
                <h3 className="text-base font-serif-cn font-bold text-ink">
                  测试挑战：{nodeObj?.title}
                </h3>
                <p className="text-xs text-muted">共 {activeAssessment.questions.length} 题，需 60 分以上通过</p>
              </div>

              {activeAssessment.questions.map((q, index: number) => {
                const currentAns = quizAnswers[q.id];

                return (
                  <div key={q.id} className="bg-panel border border-border rounded-xl p-5 flex flex-col gap-3">
                    <div className="text-xs font-bold text-ink flex items-start gap-1.5 leading-relaxed">
                      <span className="text-primary font-mono">{index + 1}.</span>
                      <span>{q.text}</span>
                    </div>

                    {/* Single Choice */}
                    {q.type === "single_choice" && q.options && (
                      <div className="flex flex-col gap-2 pl-4">
                        {q.options.map((option) => (
                          <label key={option.value} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium">
                            <input
                              type="radio"
                              name={q.id}
                              value={option.value}
                              checked={currentAns === option.value}
                              onChange={() => handleAnswerChange(q.id, option.value)}
                              disabled={isSubmitting}
                              className="w-4 h-4 text-primary focus:ring-primary border-border bg-panel"
                            />
                            {option.label}
                          </label>
                        ))}
                      </div>
                    )}

                    {/* Multiple Choice */}
                    {q.type === "multiple_choice" && q.options && (
                      <div className="flex flex-col gap-2 pl-4">
                        {q.options.map((option) => {
                          const isChecked = Array.isArray(currentAns) && currentAns.includes(option.value);
                          return (
                            <label key={option.value} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium">
                              <input
                                type="checkbox"
                                checked={isChecked}
                                onChange={(e) => handleCheckboxChange(q.id, option.value, e.target.checked)}
                                disabled={isSubmitting}
                                className="w-4 h-4 rounded text-primary focus:ring-primary border-border bg-panel"
                              />
                              {option.label}
                            </label>
                          );
                        })}
                      </div>
                    )}

                    {/* Short Answer */}
                    {q.type === "short_answer" && (
                      <div className="pl-4">
                        <textarea
                          rows={4}
                          placeholder="请在此输入您的解答说明..."
                          value={typeof currentAns === "string" ? currentAns : ""}
                          onChange={(e) => handleAnswerChange(q.id, e.target.value)}
                          disabled={isSubmitting}
                          className="w-full px-3 py-2 bg-page border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                        />
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Submit button */}
              <div className="flex justify-center pt-2 pb-4">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="inline-flex items-center gap-1.5 px-8 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-sm font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      正在提交并评分...
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
          )}

          {/* Results */}
          {assessmentResult && (
            <div className="flex flex-col gap-6">
              {/* Score card */}
              <div
                className={`p-6 rounded-2xl border flex items-start gap-4 ${
                  assessmentResult.passed
                    ? "bg-success/5 border-success/20"
                    : "bg-danger/5 border-danger/20"
                }`}
              >
                <div className="p-2 rounded-lg bg-panel shrink-0 shadow-sm">
                  {assessmentResult.passed ? (
                    <CheckCircle className="h-8 w-8 text-success" />
                  ) : (
                    <AlertCircle className="h-8 w-8 text-danger" />
                  )}
                </div>

                <div className="flex-1 flex flex-col gap-1">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-base font-bold text-ink">
                      {assessmentResult.passed ? "通关评估已通过！" : "未能完成本次通关"}
                    </h3>
                    <span className="text-xl font-mono font-bold text-ink">
                      {assessmentResult.score} / 100
                    </span>
                  </div>

                  <p className="text-xs text-muted leading-relaxed mt-1">
                    {assessmentResult.passed
                      ? "您已掌握该节点的关键概念，节点已解锁，继续探索后面的更高 Level 吧！"
                      : "评估未能达标（需 60 分以上）。请重新阅读单元讲解或在图谱上复习相关前置内容。"}
                  </p>

                  {assessmentResult.masteryDelta !== null && assessmentResult.masteryDelta !== 0 && (
                    <span className="text-xs font-semibold font-mono text-primary flex items-center gap-1 mt-2">
                      <Lightbulb className="h-4 w-4" />
                      掌握度已更新：{assessmentResult.masteryDelta > 0 ? `+${assessmentResult.masteryDelta}` : assessmentResult.masteryDelta}%
                    </span>
                  )}
                </div>
              </div>

              {/* Feedback */}
              <div className="p-5 bg-page/35 border border-border rounded-2xl flex flex-col gap-2">
                <span className="text-[10px] font-bold text-primary uppercase tracking-wider">智能体学习反馈</span>
                <p className="text-xs text-ink leading-relaxed select-text font-serif-cn whitespace-pre-wrap">
                  {assessmentResult.feedback || "AI 智能体未给出具体评价，请继续前行！"}
                </p>
              </div>

              {/* Back button */}
              <div className="flex justify-center pt-2 pb-4">
                <button
                  onClick={() => navigate(appRoutes.learningPath(pathId || ""))}
                  className="px-8 py-3 bg-primary hover:bg-primary-hover text-white text-sm font-bold rounded-xl shadow cursor-pointer transition-all"
                >
                  完成并返回图谱
                </button>
              </div>
            </div>
          )}

        </div>
      </div>
    </AppShell>
  );
}
