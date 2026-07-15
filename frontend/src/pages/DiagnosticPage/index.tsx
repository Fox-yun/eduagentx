import React, { useState, useRef, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getDiagnostic, submitDiagnostic } from "../../api/goals";
import { DiagnosticQuestionModel } from "../../schemas/diagnostic";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { HelpCircle, AlertCircle, RefreshCw, Loader2, ArrowRight, ArrowLeft, CheckCircle, SkipForward, Code } from "lucide-react";

type DiagnosticState = "loading" | "answering" | "submitting" | "completed" | "skipped" | "error";

export function DiagnosticPage() {
  const { goalId } = useParams<{ goalId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

 const [activeQuestionIndex, setActiveQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string | string[] | boolean | null>>({});
  const [pageState, setPageState] = useState<DiagnosticState>("answering");
  const navigationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (navigationTimerRef.current !== null) {
        clearTimeout(navigationTimerRef.current);
      }
    };
  }, []);

  const {
    data: quizData,
    status,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: queryKeys.diagnostic(goalId || ""),
    queryFn: ({ signal }) => getDiagnostic(goalId || "", signal),
    enabled: !!goalId,
    staleTime: 60_000,
  });

  const { mutate: submitAnswers } = useMutation({
    mutationFn: ({
      answers: answersToSubmit,
      skip,
    }: {
      answers: Record<string, string | string[] | boolean | null>;
      skip: boolean;
    }) => {
      const attemptId = quizData?.attemptId;
      if (!attemptId) throw new Error("Missing attempt ID");
      const answerList = Object.entries(answersToSubmit).map(([question_id, answer]) => ({
        question_id,
        answer,
      }));
      return submitDiagnostic(goalId || "", attemptId, answerList, skip);
    },
    onMutate: () => {
      setPageState("submitting");
    },
    onSuccess: (result) => {
      setPageState("completed");
      toast("诊断结果提交成功，即将开始生成学习路径...", "success");
      navigationTimerRef.current = setTimeout(() => {
        navigate(`${appRoutes.goalGenerating(goalId || "")}?task=${result.taskId}`);
      }, 1500);
    },
    onError: (err: any) => {
      setPageState("answering");
      toast(err.message || "提交回答失败，请重试", "error");
    },
  });

  const handleAnswerChange = (questionId: string, value: string | string[] | boolean | null) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  const getTextAnswer = (questionId: string) => {
    const answer = answers[questionId];
    return typeof answer === "string" ? answer : "";
  };

  const handleCheckboxChange = (questionId: string, option: string, checked: boolean) => {
    const existingAnswer = answers[questionId];
    const current = Array.isArray(existingAnswer) ? existingAnswer : [];
    if (checked) {
      setAnswers((prev) => ({ ...prev, [questionId]: [...current, option] }));
    } else {
      setAnswers((prev) => ({ ...prev, [questionId]: current.filter((o) => o !== option) }));
    }
  };

  const handleNext = () => {
    if (!quizData?.questions) return;
    if (activeQuestionIndex < quizData.questions.length - 1) {
      setActiveQuestionIndex((prev) => prev + 1);
    }
  };

  const handlePrev = () => {
    if (activeQuestionIndex > 0) {
      setActiveQuestionIndex((prev) => prev - 1);
    }
  };

  const handleSubmit = () => {
    submitAnswers({ answers, skip: false });
  };

  const handleSkip = () => {
    setPageState("skipped");
    toast("已跳过评估诊断", "success");
    submitAnswers({ answers: {}, skip: true });
  };

  // 1. Loading State
  if (status === "pending" || pageState === "loading") {
    return (
      <AppShell>
        <div className="flex-grow flex items-center justify-center bg-page">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
            <p className="text-xs text-muted">智能体正在为您生成个性化诊断题目，请稍候...</p>
          </div>
        </div>
      </AppShell>
    );
  }

  // 2. Error State
  if (status === "error" || pageState === "error") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center p-6 text-center bg-page select-none">
          <div className="p-4 bg-danger/10 text-danger rounded-full mb-4">
            <AlertCircle className="h-8 w-8" />
          </div>
          <h2 className="text-base font-bold text-ink mb-1.5 font-serif-cn">载入诊断失败</h2>
          <p className="text-xs text-muted max-w-[280px] leading-relaxed mb-6">
            {(error as any)?.message || "获取问题详情失败，请检查网络连接后重试。"}
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

  const questions = quizData?.questions || [];
  const currentQuestion: DiagnosticQuestionModel | undefined = questions[activeQuestionIndex];
  const isLastQuestion = activeQuestionIndex === questions.length - 1;

  if (pageState === "submitting") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center gap-4 bg-page">
          <Loader2 className="h-10 w-10 animate-spin text-primary" />
          <h2 className="text-sm font-bold text-ink">正在提交评估数据...</h2>
        </div>
      </AppShell>
    );
  }

  if (pageState === "completed" || pageState === "skipped") {
    return (
      <AppShell>
        <div className="flex-grow flex flex-col items-center justify-center gap-3 bg-page text-center p-6">
          <div className="p-4 bg-success/10 text-success rounded-full">
            <CheckCircle className="h-10 w-10 animate-bounce" />
          </div>
          <h2 className="text-base font-bold text-ink font-serif-cn">诊断提交成功！</h2>
          <p className="text-xs text-muted max-w-[260px] leading-relaxed">
            智能学习体已接收到您的基础水平，正在进入学习路径生成引擎。
          </p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans p-6 sm:p-8 md:p-12 items-center justify-start">
        <div className="w-full max-w-2xl bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6">
          
          {/* Top Info & Progress Bar */}
          <div className="flex flex-col gap-4 border-b border-border/60 pb-4">
            <div className="flex justify-between items-center">
              <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
                <HelpCircle className="h-3.5 w-3.5" />
                能力诊断评估
              </span>
              <button
                onClick={handleSkip}
                className="inline-flex items-center gap-1 text-[11px] font-bold text-muted hover:text-ink cursor-pointer hover:underline"
              >
                跳过评估
                <SkipForward className="h-3 w-3" />
              </button>
            </div>
            
            <div className="flex items-center justify-between text-xs text-ink font-semibold">
              <span>评估题目 ({activeQuestionIndex + 1} / {questions.length})</span>
              <span className="font-mono">{Math.round(((activeQuestionIndex + 1) / questions.length) * 100)}%</span>
            </div>
            <div className="w-full h-1.5 bg-page border border-border/60 rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${((activeQuestionIndex + 1) / questions.length) * 100}%` }}
              />
            </div>
          </div>

          {/* Question Render Area */}
          {currentQuestion && (
            <div className="flex flex-col gap-5 min-h-[180px]">
              <div className="text-sm font-bold text-ink leading-relaxed">
                {currentQuestion.prompt}
              </div>

              {/* 1. Single Choice */}
              {currentQuestion.type === "single_choice" && currentQuestion.options && (
                <div className="flex flex-col gap-2.5 pl-2">
                  {currentQuestion.options.map((option) => (
                    <label
                      key={option.value}
                      className={`flex items-center gap-3 p-3.5 border rounded-xl cursor-pointer text-xs transition-all font-semibold ${
                        answers[currentQuestion.questionId] === option.value
                          ? "border-primary bg-primary-soft/30 text-ink ring-1 ring-primary"
                          : "border-border bg-panel hover:bg-page text-ink"
                      }`}
                    >
                      <input
                        type="radio"
                        name={currentQuestion.questionId}
                        value={option.value}
                        checked={answers[currentQuestion.questionId] === option.value}
                        onChange={() => handleAnswerChange(currentQuestion.questionId, option.value)}
                        className="w-4 h-4 text-primary focus:ring-primary border-border bg-panel"
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              )}

              {/* 2. Multiple Choice */}
              {currentQuestion.type === "multiple_choice" && currentQuestion.options && (
                <div className="flex flex-col gap-2.5 pl-2">
                  {currentQuestion.options.map((option) => {
                    const currentAnswer = answers[currentQuestion.questionId];
                    const isChecked =
                      Array.isArray(currentAnswer) &&
                      currentAnswer.includes(option.value);
                    return (
                      <label
                        key={option.value}
                        className={`flex items-center gap-3 p-3.5 border rounded-xl cursor-pointer text-xs transition-all font-semibold ${
                          isChecked
                            ? "border-primary bg-primary-soft/30 text-ink ring-1 ring-primary"
                            : "border-border bg-panel hover:bg-page text-ink"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={(e) => handleCheckboxChange(currentQuestion.questionId, option.value, e.target.checked)}
                          className="w-4 h-4 rounded text-primary focus:ring-primary border-border bg-panel"
                        />
                        {option.label}
                      </label>
                    );
                  })}
                </div>
              )}

              {/* 3. True / False */}
              {currentQuestion.type === "true_false" && (
                <div className="flex flex-col gap-2.5 pl-2">
                  {[
                    { value: true, label: "正确" },
                    { value: false, label: "错误" },
                  ].map((option) => (
                    <label
                      key={String(option.value)}
                      className={`flex items-center gap-3 p-3.5 border rounded-xl cursor-pointer text-xs transition-all font-semibold ${
                        answers[currentQuestion.questionId] === option.value
                          ? "border-primary bg-primary-soft/30 text-ink ring-1 ring-primary"
                          : "border-border bg-panel hover:bg-page text-ink"
                      }`}
                    >
                      <input
                        type="radio"
                        name={currentQuestion.questionId}
                        checked={answers[currentQuestion.questionId] === option.value}
                        onChange={() => handleAnswerChange(currentQuestion.questionId, option.value)}
                        className="w-4 h-4 text-primary focus:ring-primary border-border bg-panel"
                      />
                      {option.label}
                    </label>
                  ))}
                </div>
              )}

              {/* 4. Short Answer */}
              {currentQuestion.type === "short_answer" && (
                <div className="pl-2">
                  <input
                    type="text"
                    placeholder="请输入您的简答"
                    value={getTextAnswer(currentQuestion.questionId)}
                    onChange={(e) => handleAnswerChange(currentQuestion.questionId, e.target.value)}
                    className="w-full px-4 py-3 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              )}

              {/* 5. Code Text Block */}
              {currentQuestion.type === "code_text" && (
                <div className="flex flex-col gap-1.5 pl-2">
                  <div className="flex items-center gap-1.5 text-[10px] text-muted font-bold font-mono">
                    <Code className="h-3.5 w-3.5" />
                    编程输入区域
                  </div>
                  <textarea
                    rows={8}
                    placeholder="// 在此输入代码回答（只作文本保存，不执行）..."
                    value={getTextAnswer(currentQuestion.questionId)}
                    onChange={(e) => handleAnswerChange(currentQuestion.questionId, e.target.value)}
                    className="w-full px-4 py-3 bg-page border border-border focus:border-primary rounded-xl text-xs font-mono text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                  />
                </div>
              )}
            </div>
          )}

          {/* Controls Footer */}
          <div className="flex items-center justify-between border-t border-border/60 pt-4 mt-2">
            <button
              onClick={handlePrev}
              disabled={activeQuestionIndex === 0}
              className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer disabled:opacity-30 disabled:pointer-events-none"
            >
              <ArrowLeft className="h-3.5 w-3.5 text-muted" />
              上一题
            </button>

            {!isLastQuestion ? (
              <button
                onClick={handleNext}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-semibold shadow-sm transition-all cursor-pointer"
              >
                下一题
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                className="inline-flex items-center gap-1.5 px-6 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
              >
                提交诊断并继续
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

        </div>
      </div>
    </AppShell>
  );
}
