import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getGoalClarification, submitGoalClarification } from "../../api/goals";
import { ClarificationQuestionModel } from "../../schemas/goals";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { HelpCircle, AlertCircle, RefreshCw, Loader2, ArrowRight, CornerUpLeft } from "lucide-react";

export function GoalClarifyPage() {
  const { goalId } = useParams<{ goalId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [answers, setAnswers] = useState<Record<string, any>>({});

  const {
    data: clarifyData,
    status,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: queryKeys.goal(goalId || ""),
    queryFn: ({ signal }) => getGoalClarification(goalId || "", signal),
    enabled: !!goalId,
    staleTime: 0, // clarification needs real-time fetching on round changes
  });

  // Pre-fill answers from history on load
  useEffect(() => {
    if (clarifyData?.answersHistory) {
      setAnswers((prev) => ({ ...clarifyData.answersHistory, ...prev }));
    }
  }, [clarifyData]);

  const { mutate: submitClarification, isPending: isSubmitting } = useMutation({
    mutationFn: (answersToSubmit: Record<string, any>) => submitGoalClarification(goalId || "", answersToSubmit),
    onSuccess: (result) => {
      toast("澄清问题提交成功！", "success");
      if (result.nextStep === "clarify") {
        // Multi-round: refetch questions for next round
        refetch();
      } else if (result.nextStep === "diagnostic") {
        navigate(appRoutes.goalDiagnostic(goalId || ""));
      } else {
        navigate(`${appRoutes.goalGenerating(goalId || "")}?task=${result.activeTaskId || ""}`);
      }
    },
    onError: (err: any) => {
      toast(err.message || "提交澄清回答失败，请重试", "error");
    },
  });

  const handleAnswerChange = (questionId: string, value: any) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  const handleCheckboxChange = (questionId: string, option: string, checked: boolean) => {
    const current = (answers[questionId] as string[]) || [];
    if (checked) {
      setAnswers((prev) => ({ ...prev, [questionId]: [...current, option] }));
    } else {
      setAnswers((prev) => ({ ...prev, [questionId]: current.filter((o) => o !== option) }));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!clarifyData?.questions) return;

    // Basic validation: ensure all questions have some response
    const unanswered = clarifyData.questions.filter((q) => {
      const ans = answers[q.id];
      if (q.type === "multiple_choice") {
        return !ans || ans.length === 0;
      }
      if (q.type === "boolean") {
        return ans === undefined || ans === null;
      }
      if (q.type === "number") {
        return ans === undefined || ans === null || isNaN(ans);
      }
      return !ans || String(ans).trim() === "";
    });

    if (unanswered.length > 0) {
      toast(`请回答所有问题以继续：还有 ${unanswered.length} 个未答题`, "error");
      return;
    }

    submitClarification(answers);
  };

  // 1. Loading State
  if (status === "pending") {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">正在获取澄清问题...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  // 2. Error State
  if (status === "error") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">获取问题失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {(error as any)?.message || "连接服务器失败，请重试。"}
          </p>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow transition-colors cursor-pointer"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            重试加载
          </button>
        </div>
      </AppShell>
    );
  }

  const questions = clarifyData?.questions || [];

  return (
    <AppShell>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans p-6 sm:p-8 md:p-12 items-center justify-start">
        <div className="w-full max-w-2xl bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6">
          
          {/* Header */}
          <div className="flex flex-col gap-1 border-b border-border/60 pb-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
              <HelpCircle className="h-3.5 w-3.5" />
              目标澄清
            </span>
            <h1 className="text-2xl font-serif-cn font-bold text-ink flex items-center gap-2">
              智能体提问：完善学习方向
            </h1>
            <p className="text-xs text-muted">
              为了提供更精准的图谱，学习智能体需要向您澄清以下几个细节。
            </p>
          </div>

          {/* Form questions list */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-6">
            {questions.map((q: ClarificationQuestionModel, index: number) => {
              const currentAns = answers[q.id];

              return (
                <div key={q.id} className="p-5 bg-page/35 border border-border rounded-xl flex flex-col gap-3">
                  <div className="text-xs font-bold text-ink flex items-start gap-1.5 leading-relaxed">
                    <span className="text-primary font-mono">{index + 1}.</span>
                    <span>{q.text}</span>
                  </div>

                  {/* 1. Single Choice */}
                  {q.type === "single_choice" && (
                    <div className="flex flex-col gap-2 pl-4">
                      {(q.options || []).map((option) => (
                        <label key={option} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium">
                          <input
                            type="radio"
                            name={q.id}
                            value={option}
                            checked={currentAns === option}
                            onChange={() => handleAnswerChange(q.id, option)}
                            disabled={isSubmitting}
                            className="w-4 h-4 text-primary focus:ring-primary border-border bg-panel"
                          />
                          {option}
                        </label>
                      ))}
                    </div>
                  )}

                  {/* 2. Multiple Choice */}
                  {q.type === "multiple_choice" && (
                    <div className="flex flex-col gap-2 pl-4">
                      {(q.options || []).map((option) => {
                        const isChecked = Array.isArray(currentAns) && currentAns.includes(option);
                        return (
                          <label key={option} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={(e) => handleCheckboxChange(q.id, option, e.target.checked)}
                              disabled={isSubmitting}
                              className="w-4 h-4 rounded text-primary focus:ring-primary border-border bg-panel"
                            />
                            {option}
                          </label>
                        );
                      })}
                    </div>
                  )}

                  {/* 3. Text Input */}
                  {q.type === "text" && (
                    <div className="pl-4">
                      <input
                        type="text"
                        placeholder="请输入您的回答"
                        value={currentAns || ""}
                        onChange={(e) => handleAnswerChange(q.id, e.target.value)}
                        disabled={isSubmitting}
                        className="w-full px-3.5 py-2 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
                      />
                    </div>
                  )}

                  {/* 4. Number Input */}
                  {q.type === "number" && (
                    <div className="pl-4">
                      <input
                        type="number"
                        placeholder="请输入数字"
                        value={currentAns === undefined ? "" : currentAns}
                        onChange={(e) => handleAnswerChange(q.id, parseInt(e.target.value, 10))}
                        disabled={isSubmitting}
                        className="w-full sm:max-w-xs px-3.5 py-2 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 font-mono"
                      />
                    </div>
                  )}

                  {/* 5. Boolean Choice */}
                  {q.type === "boolean" && (
                    <div className="flex gap-3 pl-4">
                      {[
                        { val: true, label: "是 (Yes)" },
                        { val: false, label: "否 (No)" },
                      ].map((item) => {
                        const isSelected = currentAns === item.val;
                        return (
                          <button
                            key={item.label}
                            type="button"
                            onClick={() => handleAnswerChange(q.id, item.val)}
                            disabled={isSubmitting}
                            className={`px-4 py-2 border rounded-xl text-xs font-semibold cursor-pointer transition-all ${
                              isSelected
                                ? "border-primary bg-primary-soft/30 text-primary ring-1 ring-primary"
                                : "border-border bg-panel hover:bg-page text-ink"
                            }`}
                          >
                            {item.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Bottom Actions */}
            <div className="flex justify-between items-center border-t border-border/60 pt-4 mt-2">
              <button
                type="button"
                onClick={() => navigate(appRoutes.goalCreate())}
                disabled={isSubmitting}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer"
              >
                <CornerUpLeft className="h-3.5 w-3.5 text-muted" />
                修改目标
              </button>
              <button
                type="submit"
                disabled={isSubmitting || questions.length === 0}
                className="inline-flex items-center gap-1.5 px-6 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在提交回答...
                  </>
                ) : (
                  <>
                    提交回答并继续
                    <ArrowRight className="h-4 w-4" />
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
