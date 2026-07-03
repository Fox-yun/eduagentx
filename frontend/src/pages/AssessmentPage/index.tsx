import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getLearningPath } from "../../api/paths";
import {
  createAssessment,
  submitAssessment,
  generateQuizBank,
  getQuizBank,
  getAttemptResult,
} from "../../api/units";
import type { AssessmentSubmitResultModel, QuizBankResult } from "../../api/units";
import { useTaskStream } from "../../api/taskStream";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import type { QuizBankQuestion } from "../../api/units";
import {
  ArrowRight,
  ArrowLeft,
  Sparkles,
  Loader2,
  AlertCircle,
  CheckCircle,
  Lightbulb,
  Clock,
  RefreshCw,
  BookOpen,
} from "lucide-react";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

type PagePhase =
  | "quiz_bank_missing"
  | "quiz_bank_generating"
  | "quiz_bank_ready"
  | "formal_assessment_creating"
  | "answering"
  | "grading"
  | "result";

export function AssessmentPage() {
  const { pathId, nodeId } = useParams<{ pathId: string; nodeId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // State
  const [phase, setPhase] = useState<PagePhase>("quiz_bank_missing");
  const [quizBank, setQuizBank] = useState<QuizBankResult | null>(null);
  const [formalAssessmentId, setFormalAssessmentId] = useState<string | null>(null);
  const [formalQuestions, setFormalQuestions] = useState<QuizBankQuestion[]>([]);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, string | string[] | null>>({});
  const [assessmentResult, setAssessmentResult] = useState<AssessmentSubmitResultModel | null>(null);
  const [localActiveTaskId, setLocalActiveTaskId] = useState<string | null>(null);

  // Path data
  const { data: pathData } = useQuery({
    queryKey: queryKeys.path(pathId || ""),
    queryFn: ({ signal }) => getLearningPath(pathId || "", signal),
    enabled: !!pathId,
  });
  const nodeObj = pathData?.nodes?.find((n) => n.id === nodeId);

  // ----- Derived state & callbacks -----
  const _invalidateQueries = useCallback(() => {
    if (!pathId) return;
    queryClient.invalidateQueries({ queryKey: queryKeys.path(pathId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.resume() });
    queryClient.invalidateQueries({ queryKey: ["learning-unit", pathId, nodeId] });
    queryClient.invalidateQueries({ queryKey: ["quiz-bank", pathId, nodeId] });
    queryClient.invalidateQueries({ queryKey: ["student-profile-summary"] });
  }, [queryClient, pathId, nodeId]);

  // ----- Quiz-bank query -----
  const {
    data: qbData,
    refetch: refetchQuizBank,
  } = useQuery({
    queryKey: ["quiz-bank", pathId, nodeId],
    queryFn: ({ signal }) => getQuizBank(pathId!, nodeId!, signal),
    enabled: !!pathId && !!nodeId,
  });

  // Derive quiz-bank task ID for SSE
  const qbTaskId = qbData?.activeTaskId || localActiveTaskId;
  const { status: qbTaskStatus } = useTaskStream(qbTaskId ?? null);

  // Auto-refresh quiz bank on task completion
  useEffect(() => {
    if (qbTaskStatus === "completed") {
      setLocalActiveTaskId(null);
      refetchQuizBank();
    }
  }, [qbTaskStatus, refetchQuizBank]);

  // ----- Formal assessment polling (for short-answer grading) -----
  const gradingAttemptId = searchParams.get("attempt_id");
  const [pollAttemptId, setPollAttemptId] = useState<string | null>(
    gradingAttemptId || null
  );

  const { data: polledResult } = useQuery({
    queryKey: ["attempt-result", pathId, nodeId, pollAttemptId],
    queryFn: ({ signal }) =>
      getAttemptResult(pathId!, nodeId!, pollAttemptId!, signal),
    enabled: !!pathId && !!nodeId && !!pollAttemptId && phase === "grading",
    refetchInterval: phase === "grading" ? 2000 : false,
  });

  useEffect(() => {
    if (polledResult && polledResult.status === "completed") {
      const res: AssessmentSubmitResultModel = {
        attemptId: polledResult.attempt_id,
        status: "completed",
        score: polledResult.score,
        passed: polledResult.assessment_passed,
        gradingQuality: polledResult.grading_quality as any,
        activeTaskId: null,
        feedback: null,
        masteryBefore: polledResult.mastery_before,
        masteryAfter: polledResult.mastery_after,
        nodeCompleted: polledResult.node_completed,
        unlockedNodeIds: [],
      };
      setAssessmentResult(res);
      setPhase("result");
      _invalidateQueries();
    }
  }, [polledResult, phase, _invalidateQueries, pathId]);

  // ----- Init: derive phase from quiz-bank data -----
  useEffect(() => {
    if (!qbData) return;
    if (qbData.status === "not_generated" || !qbData.assessmentId) {
      setPhase("quiz_bank_missing");
    } else if (qbData.status === "generating" || qbData.status === "pending") {
      setPhase("quiz_bank_generating");
      setQuizBank(qbData);
    } else if (qbData.status === "ready") {
      setPhase("quiz_bank_ready");
      setQuizBank(qbData);
    }
  }, [qbData]);

  // ----- Generate quiz bank -----
  const { mutate: doGenerateQuizBank, isPending: isGenQb } = useMutation({
    mutationFn: () => generateQuizBank(pathId!, nodeId!),
    onSuccess: (res) => {
      setLocalActiveTaskId(res.activeTaskId);
      setPhase("quiz_bank_generating");
    },
    onError: (err) => toast(getErrorMessage(err, "生成题库失败"), "error"),
  });

  // ----- Create formal assessment -----
  const { mutate: doCreateFormal, isPending: isCreatingFormal } = useMutation({
    mutationFn: () => createAssessment(pathId!, nodeId!, "formal"),
    onSuccess: (res: any) => {
      setFormalAssessmentId(res.assessment_id);
      const questions: QuizBankQuestion[] = (res.questions || []).map(
        (q: any) => ({
          questionId: q.question_id,
          type: q.type,
          text: q.prompt,
          options: q.options || undefined,
          difficulty: q.difficulty || null,
          knowledgePoint: q.knowledge_point || null,
          maxScore: q.max_score || null,
        })
      );
      setFormalQuestions(questions);
      setQuizAnswers({});
      setAssessmentResult(null);
      setPhase("answering");
    },
    onError: (err) => toast(getErrorMessage(err, "创建正式评估失败"), "error"),
  });

  // ----- Submit assessment -----
  const { mutate: doSubmit, isPending: isSubmitting } = useMutation({
    mutationFn: (answers: Record<string, string | string[] | null>) =>
      submitAssessment(formalAssessmentId!, answers),
    onSuccess: (res) => {
      if (res.status === "grading") {
        setPollAttemptId(res.attemptId);
        setPhase("grading");
        toast("客观题已完成评分，简答题正在评阅中...", "info");
      } else {
        setAssessmentResult(res);
        setPhase("result");
        _invalidateQueries();
        toast(
          res.passed ? "评估已通过！" : "评估未通过，建议重新学习",
          res.passed ? "success" : "error"
        );
      }
    },
    onError: (err) => toast(getErrorMessage(err, "提交评估失败"), "error"),
  });

  // ----- Answer change handlers -----
  const handleAnswerChange = (questionId: string, value: string) => {
    setQuizAnswers((prev) => ({ ...prev, [questionId]: value }));
  };
  const handleCheckboxChange = (
    questionId: string,
    option: string,
    checked: boolean
  ) => {
    const current = Array.isArray(quizAnswers[questionId])
      ? (quizAnswers[questionId] as string[])
      : [];
    setQuizAnswers((prev) => ({
      ...prev,
      [questionId]: checked
        ? [...current, option]
        : current.filter((o) => o !== option),
    }));
  };
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formalAssessmentId) return;
    doSubmit(quizAnswers);
  };

  // Clear attempt_id from URL after recovery
  useEffect(() => {
    if (phase === "result" && gradingAttemptId) {
      navigate(appRoutes.assessment(pathId!, nodeId!), { replace: true });
    }
  }, [phase, gradingAttemptId, navigate, pathId, nodeId]);

  return (
    <AppShell title={`评估 — ${nodeObj?.title || ""}`} courseName={pathData?.title}>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans items-center">
        <div className="w-full max-w-3xl p-6 sm:p-8 md:p-12 flex flex-col gap-6">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border/60 pb-4">
            <button
              onClick={() =>
                navigate(appRoutes.learningUnit(pathId || "", nodeId || ""))
              }
              className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink transition-colors cursor-pointer"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              返回学习单元
            </button>
            <span className="text-[10px] font-bold text-primary bg-primary-soft/45 px-2.5 py-0.5 rounded-lg">
              评估中心
            </span>
          </div>

          {/* ======== QUIZ BANK MISSING ======== */}
          {phase === "quiz_bank_missing" && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-12 text-center flex flex-col items-center gap-5">
              <div className="p-4 bg-primary-soft/30 text-primary rounded-full animate-pulse">
                <BookOpen className="h-10 w-10" />
              </div>
              <div className="max-w-md flex flex-col gap-1.5">
                <h2 className="text-lg font-serif-cn font-bold text-ink">题库尚未生成</h2>
                <p className="text-xs text-muted leading-relaxed">
                  先生成题库用于练习，再开始正式评估以更新掌握度。
                </p>
              </div>
              <button
                onClick={() => doGenerateQuizBank()}
                disabled={isGenQb}
                className="inline-flex items-center gap-1.5 px-8 py-3.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-sm font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
              >
                {isGenQb ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在生成...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    生成题库
                  </>
                )}
              </button>
            </div>
          )}

          {/* ======== QUIZ BANK GENERATING ======== */}
          {phase === "quiz_bank_generating" && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col items-center gap-4">
              <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
              <p className="text-xs text-muted font-semibold animate-pulse">
                智能体正在生成题库...
              </p>
              <p className="text-[10px] text-muted-soft">
                基于节点内容生成题目，请稍候
              </p>
              {(qbTaskStatus === "running" || qbTaskStatus === "pending") && (
                <button
                  onClick={() => refetchQuizBank()}
                  className="inline-flex items-center gap-1 text-xs text-primary cursor-pointer hover:underline mt-2"
                >
                  <RefreshCw className="h-3 w-3" />
                  刷新状态
                </button>
              )}
            </div>
          )}

          {/* ======== QUIZ BANK READY ======== */}
          {phase === "quiz_bank_ready" && quizBank && (
            <div className="flex flex-col gap-5">
              {/* Quiz bank status */}
              <div className="bg-panel border border-border rounded-2xl shadow-card p-6 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-serif-cn font-bold text-ink">
                    题库已就绪
                  </h3>
                  <span className="text-[10px] bg-success/15 text-success px-2 py-0.5 rounded-full font-bold">
                    {quizBank.questions.length} 题
                  </span>
                </div>
                <p className="text-xs text-muted">
                  题库已包含 {quizBank.questions.length} 道题目。您可以先浏览练习，再开始正式评估。
                </p>
                <div className="flex gap-3 mt-2">
                  <button
                    onClick={() => doCreateFormal()}
                    disabled={isCreatingFormal}
                    className="inline-flex items-center gap-1.5 px-6 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                  >
                    {isCreatingFormal ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        创建中...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3.5 w-3.5" />
                        开始正式评估
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => doGenerateQuizBank()}
                    disabled={isGenQb}
                    className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-border text-xs text-muted hover:text-ink transition-all cursor-pointer disabled:opacity-50"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    重新生成
                  </button>
                </div>
              </div>

              {/* Browse questions */}
              <div className="flex flex-col gap-3">
                {quizBank.questions.map((q, idx) => (
                  <div
                    key={q.questionId}
                    className="bg-panel border border-border rounded-xl p-4 flex flex-col gap-2"
                  >
                    <div className="flex items-start gap-2">
                      <span className="text-[10px] font-mono text-primary font-bold shrink-0 mt-0.5">
                        #{idx + 1}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-ink leading-relaxed">
                          {q.text}
                        </p>
                        {q.options && (
                          <div className="flex flex-col gap-1 mt-2 pl-2">
                            {q.options.map((o) => (
                              <span
                                key={o.value}
                                className="text-[11px] text-muted"
                              >
                                {o.label}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-soft bg-page px-2 py-0.5 rounded shrink-0">
                        {q.type === "single_choice"
                          ? "单选"
                          : q.type === "multiple_choice"
                          ? "多选"
                          : "简答"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ======== FORMAL ASSESSMENT CREATING ======== */}
          {phase === "formal_assessment_creating" && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col items-center gap-4">
              <div className="w-10 h-10 rounded-full border-4 border-primary-soft border-t-primary animate-spin" />
              <p className="text-xs text-muted font-semibold animate-pulse">
                正在创建正式评估...
              </p>
            </div>
          )}

          {/* ======== ANSWERING ======== */}
          {phase === "answering" && (
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              <div className="bg-panel border border-border rounded-2xl shadow-card p-6 flex flex-col gap-1">
                <h3 className="text-base font-serif-cn font-bold text-ink">
                  正式评估：{nodeObj?.title}
                </h3>
                <p className="text-xs text-muted">
                  共 {formalQuestions.length} 题，60 分以上通过，Mastery ≥ 70 完成节点
                </p>
              </div>

              {formalQuestions.map((q, idx) => {
                const currentAns = quizAnswers[q.questionId];
                return (
                  <div
                    key={q.questionId}
                    className="bg-panel border border-border rounded-xl p-5 flex flex-col gap-3"
                  >
                    <div className="text-xs font-bold text-ink flex items-start gap-1.5 leading-relaxed">
                      <span className="text-primary font-mono">{idx + 1}.</span>
                      <span>{q.text}</span>
                      {q.maxScore && (
                        <span className="text-[10px] text-muted-soft ml-auto shrink-0">
                          {q.maxScore}分
                        </span>
                      )}
                    </div>

                    {q.type === "single_choice" && q.options && (
                      <div className="flex flex-col gap-2 pl-4">
                        {q.options.map((opt) => (
                          <label
                            key={opt.value}
                            className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium"
                          >
                            <input
                              type="radio"
                              name={q.questionId}
                              value={opt.value}
                              checked={currentAns === opt.value}
                              onChange={() =>
                                handleAnswerChange(q.questionId, opt.value)
                              }
                              disabled={isSubmitting}
                              className="w-4 h-4 text-primary focus:ring-primary border-border bg-panel"
                            />
                            {opt.label}
                          </label>
                        ))}
                      </div>
                    )}

                    {q.type === "multiple_choice" && q.options && (
                      <div className="flex flex-col gap-2 pl-4">
                        {q.options.map((opt) => {
                          const checked =
                            Array.isArray(currentAns) &&
                            currentAns.includes(opt.value);
                          return (
                            <label
                              key={opt.value}
                              className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium"
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(e) =>
                                  handleCheckboxChange(
                                    q.questionId,
                                    opt.value,
                                    e.target.checked
                                  )
                                }
                                disabled={isSubmitting}
                                className="w-4 h-4 rounded text-primary focus:ring-primary border-border bg-panel"
                              />
                              {opt.label}
                            </label>
                          );
                        })}
                      </div>
                    )}

                    {q.type === "short_answer" && (
                      <div className="pl-4">
                        <textarea
                          rows={3}
                          placeholder="请在此输入您的解答..."
                          value={typeof currentAns === "string" ? currentAns : ""}
                          onChange={(e) =>
                            handleAnswerChange(q.questionId, e.target.value)
                          }
                          disabled={isSubmitting}
                          className="w-full px-3 py-2 bg-page border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                        />
                      </div>
                    )}
                  </div>
                );
              })}

              <div className="flex justify-center pt-2 pb-4">
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="inline-flex items-center gap-1.5 px-8 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-sm font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      提交评分中...
                    </>
                  ) : (
                    <>
                      提交评估
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* ======== GRADING (short answers) ======== */}
          {phase === "grading" && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col items-center gap-4">
              <Clock className="h-10 w-10 text-primary animate-pulse" />
              <p className="text-sm font-bold text-ink">评估正在评阅中</p>
              <p className="text-xs text-muted text-center">
                客观题已完成评分。<br />
                简答题正在由 AI 智能体评阅，请稍候...
              </p>
              <div className="w-48 h-1.5 bg-primary-soft rounded-full overflow-hidden">
                <div className="h-full bg-primary rounded-full animate-pulse w-2/3" />
              </div>
              {pollAttemptId && (
                <button
                  onClick={() => navigate(appRoutes.assessment(pathId!, nodeId!) + `?attempt_id=${pollAttemptId}`, { replace: true })}
                  className="text-[10px] text-muted underline cursor-pointer"
                >
                  复制结果链接（刷新后可恢复）
                </button>
              )}
            </div>
          )}

          {/* ======== RESULT ======== */}
          {phase === "result" && assessmentResult && (
            <div className="flex flex-col gap-6">
              {/* === PROVISIONAL WARNING === */}
              {assessmentResult.gradingQuality === "provisional" && (
                <div className="p-4 bg-warning/10 border border-warning/30 rounded-2xl flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-warning shrink-0 mt-0.5" />
                  <div className="flex flex-col gap-0.5">
                    <span className="text-xs font-bold text-warning">临时评分</span>
                    <p className="text-[11px] text-muted leading-relaxed">
                      简答题当前使用备用评分结果。本次结果暂不更新正式掌握度，也不会解锁后续节点。
                    </p>
                  </div>
                </div>
              )}

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
                      {assessmentResult.passed
                        ? "评估已通过！"
                        : "未能通过本次评估"}
                    </h3>
                    <span className="text-xl font-mono font-bold text-ink">
                      {assessmentResult.score ?? "—"} / 100
                    </span>
                  </div>

                  {/* Threshold explanation */}
                  {assessmentResult.gradingQuality === "final" && (
                    <div className="flex flex-col gap-0.5 mt-1">
                      <p className="text-xs text-muted">
                        评估通过阈值：60 分
                        {assessmentResult.passed
                          ? " ✓"
                          : " — 未达标"}
                      </p>
                      {assessmentResult.masteryAfter !== null && (
                        <p className="text-xs text-muted">
                          当前掌握度：{Math.round(assessmentResult.masteryAfter)} 分
                          {assessmentResult.nodeCompleted
                            ? " ✓ 节点已完成（≥70）"
                            : " — 未达到节点完成标准（需 70 分）"}
                        </p>
                      )}
                    </div>
                  )}

                  {assessmentResult.masteryAfter !== null &&
                    assessmentResult.masteryBefore !== null &&
                    assessmentResult.gradingQuality === "final" && (
                      <span className="text-xs font-semibold font-mono text-primary flex items-center gap-1 mt-2">
                        <Lightbulb className="h-4 w-4" />
                        掌握度：{Math.round(assessmentResult.masteryBefore)} →{" "}
                        {Math.round(assessmentResult.masteryAfter)}
                        {assessmentResult.nodeCompleted &&
                          " 🎉 节点完成！"}
                      </span>
                    )}
                </div>
              </div>

              {/* Unlocked nodes */}
              {assessmentResult.unlockedNodeIds.length > 0 && (
                <div className="p-4 bg-success/5 border border-success/20 rounded-2xl">
                  <span className="text-[10px] font-bold text-success uppercase tracking-wider">
                    新解锁节点
                  </span>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {assessmentResult.unlockedNodeIds.map((nid: string) => {
                      const n = pathData?.nodes?.find((nd) => nd.id === nid);
                      return (
                        <span
                          key={nid}
                          className="text-xs bg-panel border border-success/30 px-2.5 py-1 rounded-lg text-ink"
                        >
                          {n?.title || nid.slice(0, 8)}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Grading quality badge */}
              {assessmentResult.gradingQuality === "provisional" && (
                <div className="flex items-center gap-2 text-[11px] text-muted-soft justify-center">
                  <AlertCircle className="h-3 w-3" />
                  评分方式：临时（备用评分）
                </div>
              )}

              {/* Back button */}
              <div className="flex justify-center pt-2 pb-4 gap-3">
                {assessmentResult.gradingQuality === "final" &&
                  !assessmentResult.nodeCompleted && (
                    <button
                      onClick={() => {
                        setPhase("quiz_bank_ready");
                        setAssessmentResult(null);
                      }}
                      className="px-6 py-3 border border-border text-muted hover:text-ink text-sm font-bold rounded-xl cursor-pointer transition-all"
                    >
                      重新评估
                    </button>
                  )}
                <button
                  onClick={() =>
                    navigate(appRoutes.learningPath(pathId || ""))
                  }
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
