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
  generateLecture,
  createPractice,
  getMindMap,
  type MindMapResult,
} from "../../api/units";
import type { PracticeQuestionModel } from "../../schemas/units";
import { sendTutorQuestion, type ChatMessage, type TutorResponseMode } from "../../api/chat";
import { trackLearningEvent, type LearningEventType } from "../../api/learning";
import { queryKeys } from "../../api/queryKeys";
import { appRoutes } from "../../app/routes";
import { useTaskStream } from "../../api/taskStream";
import { isTerminalTaskStatus } from "../../features/tasks/taskEventPolicy";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { ProgressBar } from "../../components/common/ProgressBar";
import { MindMapGraph } from "../../features/node-details/MindMapGraph";
import { ResourcePanel } from "../../features/node-details/ResourcePanel";
import { TutorRichResponse } from "../../features/node-details/TutorRichResponse";
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
  PenTool,
  RefreshCw,
  MessageCircle,
  Send,
  Code2,
  Download,
} from "lucide-react";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function LearningMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ node: _node, ...props }) => (
          <h1 className="text-lg font-serif-cn font-bold border-b border-border/60 pb-1.5 mt-5 text-ink" {...props} />
        ),
        h2: ({ node: _node, ...props }) => (
          <h2 className="text-sm font-bold mt-4 text-ink" {...props} />
        ),
        h3: ({ node: _node, ...props }) => (
          <h3 className="text-xs font-bold mt-3 text-ink" {...props} />
        ),
        p: ({ node: _node, ...props }) => (
          <p className="text-xs text-muted leading-6 mt-1" {...props} />
        ),
        ul: ({ node: _node, ...props }) => (
          <ul className="list-disc pl-5 flex flex-col gap-1.5 mt-1" {...props} />
        ),
        ol: ({ node: _node, ...props }) => (
          <ol className="list-decimal pl-5 flex flex-col gap-1.5 mt-1" {...props} />
        ),
        li: ({ node: _node, ...props }) => <li className="text-xs text-muted leading-5" {...props} />,
        pre: ({ node: _node, ...props }) => (
          <pre className="bg-page/70 border border-border p-4 rounded-xl font-mono text-[11px] text-ink overflow-x-auto whitespace-pre my-3 select-text" {...props} />
        ),
        code: ({ node: _node, className, children: code, ...props }) => (
          <code
            className={className
              ? `${className} font-mono text-[11px] text-ink`
              : "bg-page border border-border px-1 py-0.5 rounded font-mono text-[10px] text-primary"}
            {...props}
          >
            {code}
          </code>
        ),
        table: ({ node: _node, ...props }) => (
          <table className="w-full text-xs text-left border-collapse border border-border rounded-xl my-3" {...props} />
        ),
        th: ({ node: _node, ...props }) => <th className="bg-page p-2 font-bold border border-border text-ink" {...props} />,
        td: ({ node: _node, ...props }) => <td className="p-2 border border-border text-muted" {...props} />,
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

export function UnitLearningPage() {
  const { pathId, nodeId } = useParams<{ pathId: string; nodeId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [localActiveTaskId, setLocalActiveTaskId] = useState<string | null>(null);
  const [localLectureTaskId, setLocalLectureTaskId] = useState<string | null>(null);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [preferenceText, setPreferenceText] = useState("");
  const requestedLectureKeyRef = React.useRef<string | null>(null);
  const trackedEventsRef = React.useRef(new Set<string>());

  const trackOnce = React.useCallback((
    key: string,
    eventType: LearningEventType,
    resourceType?: string,
    metadata?: Record<string, unknown>
  ) => {
    if (!pathId || !nodeId || trackedEventsRef.current.has(key)) return;
    trackedEventsRef.current.add(key);
    void trackLearningEvent({
      pathId,
      nodeId,
      eventType,
      resourceType,
      clientEventId: `${key}:${crypto.randomUUID()}`,
      metadata,
    })
      .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.effectiveness(pathId) }))
      .catch(() => {
        trackedEventsRef.current.delete(key);
      });
  }, [pathId, nodeId, queryClient]);

  // Practice state
  const [practiceQuestions, setPracticeQuestions] = useState<PracticeQuestionModel[]>([]);
  const [practiceAnswers, setPracticeAnswers] = useState<Record<string, string | string[] | null>>({});
  const [practiceRevealed, setPracticeRevealed] = useState<Record<string, boolean>>({});
  const [practiceOpen, setPracticeOpen] = useState(false);

  // Tutor Q&A state
  const [tutorOpen] = useState(true);
  const [tutorInput, setTutorInput] = useState("");
  const [tutorMessages, setTutorMessages] = useState<ChatMessage[]>([]);
  const [tutorResponseModes, setTutorResponseModes] = useState<TutorResponseMode[]>([
    "diagram",
    "code",
    "storyboard",
  ]);
  const tutorEndRef = React.useRef<HTMLDivElement>(null);

  // Resource tabs state
  const [activeTab, setActiveTab] = useState<"lecture" | "mindmap" | "resources">("lecture");
  const [mindMapData, setMindMapData] = useState<MindMapResult | null>(null);
  const [mindMapSourceOpen, setMindMapSourceOpen] = useState(false);

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

  useEffect(() => {
    trackOnce("node-opened", "node_opened");
  }, [trackOnce]);

  useEffect(() => {
    if (activeTab === "lecture" && unitData?.lecture?.content) {
      trackOnce("lecture-opened", "resource_opened", "lecture");
    }
    if (activeTab === "mindmap" && mindMapData) {
      trackOnce("mindmap-opened", "resource_opened", "mindmap");
    }
    if (activeTab === "resources") {
      trackOnce("resource-center-opened", "resource_opened", "resource_center");
    }
  }, [activeTab, unitData?.lecture?.content, mindMapData, trackOnce]);

  useEffect(() => {
    const resourceType =
      activeTab === "lecture" ? "lecture" : activeTab === "mindmap" ? "mindmap" : "resource_center";
    const resourceReady =
      activeTab === "lecture" ? !!unitData?.lecture?.content : activeTab === "mindmap" ? !!mindMapData : true;
    if (!pathId || !nodeId || !resourceReady) return;

    const startedAt = Date.now();
    return () => {
      const durationSeconds = Math.floor((Date.now() - startedAt) / 1000);
      if (durationSeconds < 1) return;
      void trackLearningEvent({
        pathId,
        nodeId,
        eventType: "resource_completed",
        resourceType,
        durationSeconds,
        clientEventId: `${resourceType}-session:${crypto.randomUUID()}`,
      })
        .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.effectiveness(pathId) }))
        .catch(() => undefined);
    };
  }, [activeTab, unitData?.lecture?.content, mindMapData, pathId, nodeId, queryClient]);

  // Task Stream Hook
  const activeTaskId = localActiveTaskId || unitData?.activeTaskId;
  const {
    progress,
    message: taskMessage,
    stage: taskStage,
    status: taskStatus,
  } = useTaskStream(activeTaskId);

  const activeLectureTaskId = localLectureTaskId || unitData?.activeLectureTaskId;
  const {
    progress: lectureProgress,
    message: lectureTaskMessage,
    stage: lectureTaskStage,
    status: lectureTaskStatus,
    error: lectureTaskError,
  } = useTaskStream(activeLectureTaskId);

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

  const {
    mutate: performGenerateLecture,
    isPending: isRequestingLecture,
    error: lectureRequestError,
  } = useMutation({
    mutationFn: () => generateLecture(pathId || "", nodeId || ""),
    onSuccess: (res) => {
      setLocalLectureTaskId(res.activeTaskId);
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "课程讲义生成失败，请重试"), "error");
    },
  });

  // The lecture is the learner-facing course body. Generate it as soon as the
  // structured unit source is ready, while guarding against duplicate posts.
  useEffect(() => {
    if (
      unitData?.status !== "ready" ||
      !unitData.content ||
      unitData.lecture?.content ||
      activeLectureTaskId ||
      isRequestingLecture
    ) {
      return;
    }

    const sourceKey = `${unitData.unitId}:${unitData.contentVersion}`;
    if (requestedLectureKeyRef.current === sourceKey) return;
    requestedLectureKeyRef.current = sourceKey;
    performGenerateLecture();
  }, [
    unitData,
    activeLectureTaskId,
    isRequestingLecture,
    performGenerateLecture,
  ]);

  useEffect(() => {
    if (lectureTaskStatus !== "completed" || !activeLectureTaskId) return;
    toast("课程讲义生成成功", "success");
    setLocalLectureTaskId(null);
    refetchUnit();
  }, [lectureTaskStatus, activeLectureTaskId, refetchUnit, toast]);

  // Practice mutation
  const { mutate: performLoadPractice, isPending: isLoadingPractice } = useMutation({
    mutationFn: () => createPractice(pathId || "", nodeId || ""),
    onSuccess: (questions) => {
      trackOnce("practice-started", "practice_started", undefined, { question_count: questions.length });
      setPracticeQuestions(questions);
      setPracticeAnswers({});
      setPracticeRevealed({});
      setPracticeOpen(true);
    },
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "加载练习题失败，请重试"), "error");
    },
  });

  const {
    mutate: performLoadMindMap,
    isPending: isLoadingMindMap,
    error: mindMapError,
  } = useMutation({
    mutationFn: () => getMindMap(pathId || "", nodeId || ""),
    onSuccess: setMindMapData,
    onError: (err: unknown) => {
      toast(getErrorMessage(err, "思维导图加载失败，请重试"), "error");
    },
  });

  // Tutor Q&A mutation
  const { mutate: performAskTutor, isPending: isTutorLoading } = useMutation({
    mutationFn: ({ question, modes }: { question: string; modes: TutorResponseMode[] }) =>
      sendTutorQuestion(pathId || "", nodeId || "", question, modes),
    onSuccess: (reply) => {
      setTutorMessages((prev) => [...prev, reply]);
      setTutorInput("");
    },
    onError: (err: unknown) => {
      setTutorMessages((prev) => [
        ...prev,
        { role: "assistant", content: `抱歉，答疑出现错误：${getErrorMessage(err, "请重试")}` },
      ]);
    },
  });

  // Auto-scroll tutor messages
  useEffect(() => {
    tutorEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [tutorMessages, isTutorLoading]);

  const handleTutorSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = tutorInput.trim();
    if (!q) return;
    trackOnce(`tutor-question-${Date.now()}`, "tutor_question", undefined, { response_modes: tutorResponseModes });
    setTutorMessages((prev) => [...prev, { role: "user", content: q }]);
    performAskTutor({ question: q, modes: tutorResponseModes });
  };

  const handleTutorFeedback = (message: ChatMessage, helpful: boolean) => {
    if (!pathId || !nodeId || !message.responseId) return;
    void trackLearningEvent({
      pathId,
      nodeId,
      eventType: "tutor_feedback",
      clientEventId: `tutor-feedback:${message.responseId}`,
      metadata: {
        response_id: message.responseId,
        helpful,
        response_modes: (message.modalities || []).filter((mode) => mode !== "text"),
      },
    })
      .then(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.profile() });
        queryClient.invalidateQueries({ queryKey: queryKeys.effectiveness(pathId) });
      })
      .catch(() => undefined);
  };

  const toggleTutorMode = (mode: TutorResponseMode) => {
    setTutorResponseModes((current) =>
      current.includes(mode) ? current.filter((item) => item !== mode) : [...current, mode]
    );
  };

  const handlePracticeAnswer = (questionId: string, value: string) => {
    setPracticeAnswers((prev) => ({ ...prev, [questionId]: value }));
    setPracticeRevealed((prev) => ({ ...prev, [questionId]: true }));
  };

  const handlePracticeCheckbox = (questionId: string, option: string, checked: boolean) => {
    const current = Array.isArray(practiceAnswers[questionId]) ? (practiceAnswers[questionId] as string[]) : [];
    const next = checked ? [...current, option] : current.filter((o) => o !== option);
    setPracticeAnswers((prev) => ({ ...prev, [questionId]: next }));
  };

  const handlePracticeMultiReveal = (questionId: string) => {
    setPracticeRevealed((prev) => ({ ...prev, [questionId]: true }));
  };

  const handlePreferencesSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    performRegenerate(preferenceText);
  };

  const navigateToLectureSection = (sectionId: string) => {
    setActiveTab("lecture");
    window.setTimeout(() => {
      document
        .getElementById(`lecture-section-${sectionId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
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
  const isLectureTaskRunning =
    !!activeLectureTaskId && !isTerminalTaskStatus(lectureTaskStatus);

  return (
    <AppShell title={nodeObj?.title} courseName={pathData?.title}>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans items-center justify-start relative">
        <div className={`w-full p-6 sm:p-8 md:p-12 flex gap-6 ${tutorOpen ? "max-w-7xl" : "max-w-4xl flex-col"}`}>

          {/* Left column: main content */}
          <div className={`flex flex-col gap-6 ${tutorOpen ? "flex-1 min-w-0" : ""}`}>
          
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

          {/* Not Generated State — blank state, no active task */}
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

          {/* Active Generating Banner — shown as top bar when generating or regenerating */}
          {isRegeneratedOrGenerating && (
            <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-5 my-4">
              <div className="flex flex-col gap-1">
                <h3 className="text-base font-serif-cn font-bold text-ink flex items-center gap-2">
                  <Loader2 className="h-4.5 w-4.5 text-primary animate-spin" />
                  {taskStage ? `AI 智能体正在编写：${taskStage}` : "正在启动单元编写智能体..."}
                </h3>
                <p className="text-xs text-muted">
                  {unitData?.activeVersionId
                    ? "当前仍展示上一版本内容，新版本生成完成后将自动切换。"
                    : "结合全图拓扑、前置节点掌握情况和您的偏好语言进行针对性讲解。"}
                </p>
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

          {/* Ready State: Main Learning Content — also shown during regeneration (old version remains visible) */}
          {(unitData?.status === "ready" || unitData?.status === "regenerating") && unitData.content && (
            <div className="flex flex-col gap-8">
              {/* Resource Tabs */}
              <div className="flex gap-1 bg-panel border border-border rounded-2xl shadow-card p-1.5 overflow-x-auto">
                {(["lecture", "mindmap", "resources"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => {
                      setActiveTab(tab);
                      if (tab === "mindmap" && !mindMapData && !isLoadingMindMap) {
                        performLoadMindMap();
                      }
                    }}
                    className={`px-4 py-2 text-xs font-semibold rounded-xl transition-colors cursor-pointer whitespace-nowrap ${
                      activeTab === tab
                        ? "bg-primary text-white shadow-md"
                        : "text-muted hover:text-ink hover:bg-page/50"
                    }`}
                  >
                    {tab === "lecture" && "📖 课程讲义"}
                    {tab === "mindmap" && "🧠 思维导图"}
                    {tab === "resources" && "✨ 多模态资源"}
                  </button>
                ))}
              </div>

              {/* Lecture is the single learner-facing course body. */}
              {activeTab === "lecture" && (
              <div className="flex flex-col gap-8">
              {/* Main lecture */}
              {unitData.lecture?.content ? (
              <article className="bg-panel border border-border rounded-2xl shadow-card p-5 sm:p-8 select-text">
                <div className="mb-7 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-xl border border-border bg-page/45 p-4">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted">预计学习</p>
                    <p className="mt-1 text-sm font-bold text-ink">{unitData.estimatedMinutes || Math.max(15, unitData.lecture.sections.length * 10)} 分钟</p>
                  </div>
                  <div className="rounded-xl border border-border bg-page/45 p-4">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted">内容深度</p>
                    <p className="mt-1 text-sm font-bold text-ink">{unitData.lecture.sections.length} 个章节 · 示例与易错点</p>
                  </div>
                  <div className="rounded-xl border border-border bg-page/45 p-4">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted">完成标准</p>
                    <p className="mt-1 text-sm font-bold text-ink">讲义 + 练习 + 通关评估</p>
                  </div>
                </div>

                {(unitData.prerequisites.length > 0 || unitData.completionCriteria.length > 0) && (
                  <div className="mb-7 grid gap-4 md:grid-cols-2">
                    {unitData.prerequisites.length > 0 && (
                      <div className="rounded-xl border border-border p-4">
                        <h3 className="text-xs font-bold text-ink">学习前准备</h3>
                        <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] leading-5 text-muted">
                          {unitData.prerequisites.map((item) => <li key={item}>{item}</li>)}
                        </ul>
                      </div>
                    )}
                    {unitData.completionCriteria.length > 0 && (
                      <div className="rounded-xl border border-primary/20 bg-primary-soft/15 p-4">
                        <h3 className="text-xs font-bold text-ink">学完后你应该能</h3>
                        <ul className="mt-2 space-y-1 text-[11px] leading-5 text-muted">
                          {unitData.completionCriteria.map((item) => <li key={item}>✓ {item}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                <div className="grid gap-8 lg:grid-cols-[190px_minmax(0,1fr)]">
                  <aside className="h-fit rounded-xl border border-border bg-page/35 p-3 lg:sticky lg:top-4">
                    <p className="px-2 pb-2 text-[10px] font-bold uppercase tracking-wider text-muted">讲义目录</p>
                    <nav className="flex flex-col gap-1" aria-label="讲义目录">
                      {[...unitData.lecture.sections].sort((a, b) => a.order - b.order).map((section, index) => (
                        <button
                          key={section.sectionId}
                          onClick={() => navigateToLectureSection(section.sourceSectionId || section.sectionId)}
                          className="rounded-lg px-2.5 py-2 text-left text-[11px] leading-4 text-muted transition-colors hover:bg-panel hover:text-primary cursor-pointer"
                        >
                          <span className="mr-1.5 font-mono text-[9px] text-primary">{String(index + 1).padStart(2, "0")}</span>
                          {section.title}
                        </button>
                      ))}
                    </nav>
                  </aside>

                  <div className="min-w-0 text-xs text-ink font-sans select-text">
                    {unitData.lecture.introduction && (
                      <div className="mb-8 rounded-xl border-l-4 border-primary bg-primary-soft/10 px-5 py-3">
                        <LearningMarkdown>{unitData.lecture.introduction}</LearningMarkdown>
                      </div>
                    )}
                    {[...unitData.lecture.sections].sort((a, b) => a.order - b.order).map((section, index) => (
                      <section
                        key={section.sectionId}
                        id={`lecture-section-${section.sourceSectionId || section.sectionId}`}
                        className="scroll-mt-6 border-b border-border/60 py-7 first:pt-0"
                      >
                        <div className="mb-3 flex items-center gap-3">
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-[10px] font-bold text-white">{index + 1}</span>
                          <h2 className="text-base font-bold font-serif-cn text-ink">{section.title}</h2>
                        </div>
                        <LearningMarkdown>{section.content}</LearningMarkdown>
                      </section>
                    ))}

                    {unitData.lecture.keyTakeaways.length > 0 && (
                      <section className="mt-7 rounded-xl border border-primary/25 bg-primary-soft/15 p-5">
                        <h2 className="text-sm font-bold text-ink">核心要点</h2>
                        <ul className="mt-3 space-y-2 text-xs leading-5 text-muted">
                          {unitData.lecture.keyTakeaways.map((item) => <li key={item}>✓ {item}</li>)}
                        </ul>
                      </section>
                    )}
                    {unitData.lecture.commonMistakes.length > 0 && (
                      <section className="mt-5 rounded-xl border border-danger/20 bg-danger/5 p-5">
                        <h2 className="text-sm font-bold text-ink">常见误区与纠正</h2>
                        <div className="mt-3 space-y-3">
                          {unitData.lecture.commonMistakes.map((item) => (
                            <div key={item.mistake}>
                              <p className="text-xs font-bold text-danger">× {item.mistake}</p>
                              <p className="mt-1 text-xs leading-5 text-muted">{item.explanation}</p>
                            </div>
                          ))}
                        </div>
                      </section>
                    )}
                    {unitData.lecture.summary && (
                      <section className="mt-7">
                        <h2 className="text-sm font-bold text-ink">本单元小结</h2>
                        <LearningMarkdown>{unitData.lecture.summary}</LearningMarkdown>
                      </section>
                    )}
                  </div>
                </div>
              </article>
              ) : (
                <div className="bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-5">
                  {isLectureTaskRunning ? (
                    <>
                      <div className="flex flex-col gap-1">
                        <h3 className="text-base font-serif-cn font-bold text-ink flex items-center gap-2">
                          <Loader2 className="h-4.5 w-4.5 text-primary animate-spin" />
                          {lectureTaskStage ? `正在生成课程讲义：${lectureTaskStage}` : "正在准备课程讲义..."}
                        </h3>
                        <p className="text-xs text-muted">
                          系统正在把课程结构整理为一份连续、可直接学习的讲义。
                        </p>
                      </div>
                      <div className="flex justify-between items-center text-xs text-muted font-semibold">
                        <span>讲义进度</span>
                        <span className="font-mono text-ink text-sm font-bold">{lectureProgress}%</span>
                      </div>
                      <ProgressBar progress={lectureProgress} height="h-2.5" />
                      <p className="text-xs text-ink leading-relaxed font-mono whitespace-pre-wrap">
                        {lectureTaskMessage || "正在连接讲义生成任务..."}
                      </p>
                    </>
                  ) : isRequestingLecture ? (
                    <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted">
                      <Loader2 className="h-4 w-4 text-primary animate-spin" />
                      正在创建讲义生成任务...
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-4 py-6 text-center">
                      <AlertCircle className="h-8 w-8 text-danger" />
                      <div>
                        <h3 className="text-sm font-bold text-ink">课程讲义暂未生成</h3>
                        <p className="mt-1 text-xs text-muted">
                          {lectureTaskError || getErrorMessage(lectureRequestError, "可以重新发起生成任务。")}
                        </p>
                      </div>
                      <button
                        onClick={() => performGenerateLecture()}
                        className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow cursor-pointer"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        重新生成课程讲义
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Practice Section */}
              {practiceOpen && (practiceQuestions.length > 0 || isLoadingPractice) && (
                <div className="bg-panel border border-border rounded-2xl shadow-card p-6 flex flex-col gap-5">
                  <div className="flex items-center justify-between border-b border-border/60 pb-3">
                    <div className="flex items-center gap-2">
                      <PenTool className="h-4 w-4 text-primary" />
                      <h3 className="text-sm font-bold text-ink font-serif-cn">练习题</h3>
                      <span className="text-[10px] text-muted">（即时反馈，可重复练习）</span>
                    </div>
                    <button
                      onClick={() => performLoadPractice()}
                      disabled={isLoadingPractice}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border hover:bg-page text-[10px] font-semibold text-muted cursor-pointer transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3 w-3 ${isLoadingPractice ? "animate-spin" : ""}`} />
                      换一批题目
                    </button>
                  </div>

                  {/* Loading state for new questions */}
                  {isLoadingPractice && (
                    <div className="flex flex-col items-center justify-center gap-3 py-10">
                      <div className="w-8 h-8 rounded-full border-3 border-primary-soft border-t-primary animate-spin" />
                      <p className="text-xs text-muted font-semibold animate-pulse">新题目生成中...</p>
                      <p className="text-[10px] text-muted-soft">智能体正在根据节点内容编写练习题</p>
                    </div>
                  )}

                  {/* Question list — hidden during loading */}
                  {!isLoadingPractice && practiceQuestions.map((q, idx) => {
                    const revealed = practiceRevealed[q.id];
                    const ans = practiceAnswers[q.id];

                    return (
                      <div key={q.id} className="p-4 bg-page/35 border border-border rounded-xl flex flex-col gap-3">
                        <div className="text-xs font-bold text-ink flex items-start gap-1.5 leading-relaxed">
                          <span className="text-primary font-mono">{idx + 1}.</span>
                          <span>{q.text}</span>
                        </div>

                        {q.type === "single_choice" && q.options && (
                          <div className="flex flex-col gap-2 pl-4">
                            {q.options.map((option) => {
                              const selected = ans === option.value;
                              const optionCorrect = revealed && q.correctAnswer === option.value;
                              const optionWrong = revealed && selected && !optionCorrect;
                              return (
                                <label
                                  key={option.value}
                                  className={`flex items-center gap-2.5 text-xs cursor-pointer font-medium rounded-lg px-2 py-1 transition-colors ${
                                    optionCorrect ? "bg-success/10 text-success" :
                                    optionWrong ? "bg-danger/10 text-danger" :
                                    selected ? "bg-primary-soft/20" : "text-ink"
                                  }`}
                                >
                                  <input
                                    type="radio"
                                    name={`practice-${q.id}`}
                                    value={option.value}
                                    checked={selected}
                                    onChange={() => handlePracticeAnswer(q.id, option.value)}
                                    disabled={revealed}
                                    className="w-4 h-4 text-primary focus:ring-primary border-border bg-panel"
                                  />
                                  {option.label}
                                  {optionCorrect && <CheckCircle className="h-3.5 w-3.5 text-success ml-auto" />}
                                  {optionWrong && <AlertCircle className="h-3.5 w-3.5 text-danger ml-auto" />}
                                </label>
                              );
                            })}
                          </div>
                        )}

                        {q.type === "multiple_choice" && q.options && (
                          <div className="flex flex-col gap-2 pl-4">
                            {q.options.map((option) => {
                              const isChecked = Array.isArray(ans) && ans.includes(option.value);
                              return (
                                <label key={option.value} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer font-medium">
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={(e) => handlePracticeCheckbox(q.id, option.value, e.target.checked)}
                                    disabled={revealed}
                                    className="w-4 h-4 rounded text-primary focus:ring-primary border-border bg-panel"
                                  />
                                  {option.label}
                                </label>
                              );
                            })}
                            {!revealed && (
                              <button
                                onClick={() => handlePracticeMultiReveal(q.id)}
                                className="self-start mt-1 px-3 py-1 text-[10px] font-semibold text-primary border border-primary/30 rounded-lg hover:bg-primary-soft/10 cursor-pointer"
                              >
                                查看答案
                              </button>
                            )}
                            {revealed && q.correctAnswer && (
                              <p className="text-[10px] text-success mt-1">
                                ✅ 正确答案：{JSON.parse(q.correctAnswer).join(", ")}
                              </p>
                            )}
                          </div>
                        )}

                        {q.type === "short_answer" && (
                          <div className="pl-4 flex flex-col gap-2">
                            <textarea
                              rows={3}
                              placeholder="请在此输入您的解答..."
                              value={typeof ans === "string" ? ans : ""}
                              onChange={(e) => setPracticeAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                              className="w-full px-3 py-2 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                            />
                            {!revealed && (
                              <button
                                onClick={() => handlePracticeMultiReveal(q.id)}
                                className="self-start px-3 py-1 text-[10px] font-semibold text-primary border border-primary/30 rounded-lg hover:bg-primary-soft/10 cursor-pointer"
                              >
                                查看参考思路
                              </button>
                            )}
                            {revealed && (
                              <p className="text-[10px] text-muted italic">💡 这是开放性题目，请结合自己的理解作答。</p>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Action buttons at bottom */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border/60 pt-4">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPreferencesOpen(true)}
                    disabled={isLectureTaskRunning || isRegeneratedOrGenerating}
                    className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-border hover:bg-panel-soft text-xs font-semibold text-ink transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <RotateCcw className="h-3.5 w-3.5 text-muted" />
                    提交偏好重新生成
                  </button>
                  <button
                    onClick={() => performLoadPractice()}
                    disabled={isLoadingPractice}
                    className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl border border-primary/40 hover:bg-primary-soft/10 text-xs font-semibold text-primary transition-colors cursor-pointer"
                  >
                    {isLoadingPractice ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <PenTool className="h-3.5 w-3.5" />
                    )}
                    练习题
                  </button>
                </div>

                <button
                  onClick={() => navigate(appRoutes.assessment(pathId || "", nodeId || ""))}
                  className="inline-flex items-center gap-1.5 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer"
                >
                  <Sparkles className="h-4 w-4" />
                  评估中心
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>

              </div>
              )}

              {/* Mind Map Tab */}
              {activeTab === "mindmap" && (
                <div className="bg-panel border border-border rounded-2xl shadow-card p-6">
                  {mindMapData ? (
                    <div className="flex flex-col gap-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-bold text-ink font-serif-cn">思维导图</h3>
                          <p className="mt-1 text-[10px] text-muted">支持拖动画布、缩放视图；点击章节或知识点可跳转到对应讲义</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setMindMapSourceOpen((open) => !open)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-border hover:bg-page text-[10px] font-semibold text-muted rounded-lg cursor-pointer"
                          >
                            <Code2 className="h-3 w-3" />
                            {mindMapSourceOpen ? "隐藏源码" : "查看源码"}
                          </button>
                          <button
                            onClick={() => {
                              const blob = new Blob([mindMapData.mermaid], { type: "text/plain" });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement("a");
                              a.href = url;
                              a.download = "mindmap.mermaid";
                              a.click();
                              URL.revokeObjectURL(url);
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-border hover:bg-page text-[10px] font-semibold text-muted rounded-lg cursor-pointer"
                          >
                            <Download className="h-3 w-3" />
                            下载源码
                          </button>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2 text-[9px] text-muted" aria-label="思维导图图例">
                        <span className="rounded-full border border-[#8ea7cd] bg-[#f0f5fd] px-2 py-1">目标节点</span>
                        <span className="rounded-full border border-border bg-page px-2 py-1">核心概念</span>
                        <span className="rounded-full border border-[#76a48b] bg-[#edf8f0] px-2 py-1">示例</span>
                        <span className="rounded-full border border-[#d7988f] bg-[#fff1ef] px-2 py-1">易错点</span>
                        <span className="rounded-full border border-[#ad91c5] bg-[#f8f1fc] px-2 py-1">实践任务</span>
                      </div>
                      <MindMapGraph tree={mindMapData.tree} onNavigateToSection={navigateToLectureSection} />
                      {mindMapSourceOpen && (
                        <div className="flex flex-col gap-2">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-muted">Mermaid 源码</span>
                          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-xl border border-border bg-page/50 p-4 font-mono text-[11px] text-ink">
                            {mindMapData.mermaid}
                          </pre>
                        </div>
                      )}
                    </div>
                  ) : isLoadingMindMap ? (
                    <div className="flex flex-col items-center justify-center gap-3 py-16">
                      <Loader2 className="h-6 w-6 animate-spin text-primary" />
                      <p className="text-xs font-semibold text-ink">正在构建思维导图...</p>
                      <p className="text-[10px] text-muted">正在从当前课程讲义提取学习目标和章节关系</p>
                    </div>
                  ) : (
                    <div className="text-center py-12">
                      <AlertCircle className="mx-auto mb-3 h-7 w-7 text-danger" />
                      <p className="text-xs text-muted mb-3">
                        {getErrorMessage(mindMapError, "思维导图尚未加载")}
                      </p>
                      <button
                        onClick={() => performLoadMindMap()}
                        className="px-4 py-2 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl cursor-pointer"
                      >
                        重新加载思维导图
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Personalized multimodal resources */}
              {activeTab === "resources" && nodeId && (
                <div className="bg-panel border border-border rounded-2xl shadow-card p-6">
                  <div className="mb-5">
                    <h3 className="text-sm font-bold text-ink font-serif-cn">个性化多模态资源中心</h3>
                    <p className="mt-1 text-[10px] leading-4 text-muted">
                      五类高价值资源由不同生成智能体协作完成，并在交付前经过统一质量评分。
                    </p>
                  </div>
                  <ResourcePanel nodeId={nodeId} />
                </div>
              )}

            </div>
          )}
          </div>
          {/* End left column */}

          {/* Right sidebar: Tutor Q&A */}
          {tutorOpen && (
            <div className="w-[360px] shrink-0 bg-panel border border-border rounded-2xl shadow-card flex flex-col sticky top-6 max-h-[calc(100vh-120px)]">
              <div className="flex items-center gap-2 px-5 py-4 border-b border-border/60 shrink-0">
                <MessageCircle className="h-4 w-4 text-primary" />
                <div>
                  <h3 className="text-sm font-bold text-ink font-serif-cn">多模态答疑辅导</h3>
                  <p className="mt-0.5 text-[9px] text-subtle">讲解 · 图解 · 代码 · 动画微课</p>
                </div>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto flex flex-col gap-3 p-5 min-h-0">
                {tutorMessages.length === 0 && (
                  <div className="text-center py-8 text-xs text-muted">
                    <MessageCircle className="h-8 w-8 mx-auto mb-2 opacity-30" />
                    <p>关于「{nodeObj?.title || "本知识点"}」有什么疑问？</p>
                    <p className="text-[10px] mt-1.5 leading-relaxed">例如：能举个具体例子吗？<br/>和前置节点有什么关联？</p>
                  </div>
                )}

                {tutorMessages.map((msg, idx) => (
                  <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    {msg.role === "user" ? (
                      <div className="max-w-[90%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-xs leading-relaxed text-white">
                        {msg.content}
                      </div>
                    ) : (
                      <TutorRichResponse message={msg} onFeedback={handleTutorFeedback} />
                    )}
                  </div>
                ))}

                {isTutorLoading && (
                  <div className="flex justify-start">
                    <div className="bg-page border border-border px-3.5 py-2.5 rounded-2xl rounded-bl-md flex items-center gap-2">
                      <Loader2 className="h-3 w-3 animate-spin text-primary" />
                      <span className="text-[11px] text-muted animate-pulse">思考中...</span>
                    </div>
                  </div>
                )}
                <div ref={tutorEndRef} />
              </div>

              {/* Input */}
              <form onSubmit={handleTutorSubmit} className="flex shrink-0 flex-col gap-2 border-t border-border/60 p-4">
                <div className="flex items-center gap-1.5" aria-label="选择回答形式">
                  {([
                    ["diagram", "🧩 图解"],
                    ["code", "💻 代码"],
                    ["storyboard", "🎬 动画"],
                  ] as const).map(([mode, label]) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => toggleTutorMode(mode)}
                      className={`rounded-full border px-2 py-1 text-[9px] font-semibold transition-colors ${tutorResponseModes.includes(mode) ? "border-primary/30 bg-primary/8 text-primary" : "border-border text-subtle"}`}
                      aria-pressed={tutorResponseModes.includes(mode)}
                    >
                      {label}
                    </button>
                  ))}
                  <span className="ml-auto text-[8px] text-subtle">可多选</span>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={tutorInput}
                    onChange={(e) => setTutorInput(e.target.value)}
                    placeholder="输入你的问题..."
                    disabled={isTutorLoading}
                    className="flex-1 px-3 py-2.5 bg-page border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={!tutorInput.trim() || isTutorLoading}
                    className="inline-flex items-center gap-1 px-3.5 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold shadow transition-colors cursor-pointer disabled:opacity-50"
                  >
                    <Send className="h-3.5 w-3.5" />
                  </button>
                </div>
              </form>
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

    </AppShell>
  );
}
