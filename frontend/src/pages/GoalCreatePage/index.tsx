import React, { useEffect } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createLearningGoal } from "../../api/goals";
import { appRoutes } from "../../app/routes";
import { useToast } from "../../components/feedback/Toast";
import { AppShell } from "../../components/layout/AppShell";
import { Compass, BookOpen, Clock, Settings2, Sparkles, Loader2, ArrowRight } from "lucide-react";

const createGoalFormSchema = z.object({
  rawGoal: z.string().min(10, "请详细描述您的学习目标，至少 10 个字符"),
  currentLevel: z.enum(["beginner", "intermediate", "advanced"]),
  targetLevel: z.enum(["beginner", "intermediate", "advanced"]),
  durationWeeks: z.number().min(1, "周期至少 1 周").max(52),
  weeklyHours: z.number().min(1, "每周课时至少 1 小时").max(168),
  preferences: z.array(z.string()).min(1, "请至少选择一种学习偏好"),
  useDiagnostic: z.boolean(),
  useKnowledgeBase: z.boolean(),
  contentLanguage: z.string().min(1, "语言设置不能为空"),
});

type CreateGoalValues = z.infer<typeof createGoalFormSchema>;
const DRAFT_KEY = "eduagentx.goal-draft.v1";

export function GoalCreatePage() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const getInitialValues = (): CreateGoalValues => {
    try {
      const stored = sessionStorage.getItem(DRAFT_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Basic schema safety check
        if (parsed && typeof parsed.rawGoal === "string") {
          return parsed;
        }
      }
    } catch {
      // Ignore sessionStorage limits
    }
    return {
      rawGoal: "",
      currentLevel: "beginner",
      targetLevel: "intermediate",
      durationWeeks: 8,
      weeklyHours: 10,
      preferences: ["practice_first"],
      useDiagnostic: true,
      useKnowledgeBase: false,
      contentLanguage: "中文",
    };
  };

  const {
    control,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<CreateGoalValues>({
    resolver: zodResolver(createGoalFormSchema),
    defaultValues: getInitialValues(),
  });

  const formValues = watch();
  const selectedPreferences = watch("preferences");

  const isSuccessfullySubmittedRef = React.useRef(false);

  const { mutate: performCreate, isPending } = useMutation({
    mutationFn: createLearningGoal,
    onSuccess: (result) => {
      isSuccessfullySubmittedRef.current = true;
      try {
        sessionStorage.removeItem(DRAFT_KEY);
      } catch {
        // Ignore
      }
      toast("目标设定成功！", "success");

      if (result.nextStep === "clarify") {
        navigate(appRoutes.goalClarify(result.goalId));
      } else if (result.nextStep === "diagnostic") {
        navigate(appRoutes.goalDiagnostic(result.goalId));
      } else {
        navigate(`${appRoutes.goalGenerating(result.goalId)}?task=${result.activeTaskId || ""}`);
      }
    },
    onError: (err: any) => {
      toast(err.message || "设定学习目标失败，请重试", "error");
    },
  });

  // Save changes to draft
  useEffect(() => {
    if (isPending || isSuccessfullySubmittedRef.current) return;
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(formValues));
    } catch {
      // Ignore
    }
  }, [formValues, isPending]);

  const togglePreference = (pref: string) => {
    if (selectedPreferences.includes(pref)) {
      setValue(
        "preferences",
        selectedPreferences.filter((p) => p !== pref),
        { shouldValidate: true }
      );
    } else {
      setValue("preferences", [...selectedPreferences, pref], { shouldValidate: true });
    }
  };

  const onSubmit = (values: CreateGoalValues) => {
    performCreate(values);
  };

  return (
    <AppShell>
      <div className="flex-grow flex flex-col min-h-0 bg-page select-none overflow-y-auto font-sans p-6 sm:p-8 md:p-12 items-center justify-start">
        <div className="w-full max-w-2xl bg-panel border border-border rounded-2xl shadow-card p-8 flex flex-col gap-6">
          {/* Header Title */}
          <div className="flex flex-col gap-1 border-b border-border/60 pb-4">
            <span className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
              <Compass className="h-3.5 w-3.5" />
              智能体工坊
            </span>
            <h1 className="text-2xl font-serif-cn font-bold text-ink flex items-center gap-2">
              <Sparkles className="h-5.5 w-5.5 text-primary" />
              设定新学习目标
            </h1>
            <p className="text-xs text-muted">
              使用自然语言告诉智能体你想学什么，我们将生成最科学的技能路径。
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-6">
            
            {/* Raw goal target text */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-ink flex items-center gap-1">
                <BookOpen className="h-3.5 w-3.5 text-primary" />
                我想要学... (具体学习目标)
              </label>
              <Controller
                name="rawGoal"
                control={control}
                render={({ field }) => (
                  <textarea
                    rows={4}
                    placeholder="我想在两个月内掌握 Python 数据分析，最终可以独立完成一个真实的项目..."
                    {...field}
                    disabled={isPending}
                    className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
                  />
                )}
              />
              {errors.rawGoal && <p className="text-[10px] text-danger font-semibold">{errors.rawGoal.message}</p>}
            </div>

            {/* Level Settings */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink">当前能力起点</label>
                <Controller
                  name="currentLevel"
                  control={control}
                  render={({ field }) => (
                    <select
                      {...field}
                      disabled={isPending}
                      className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink focus:outline-none focus:ring-2 focus:ring-primary/20"
                    >
                      <option value="beginner">零基础 / 初学者 (Beginner)</option>
                      <option value="intermediate">有一定基础 / 进阶 (Intermediate)</option>
                      <option value="advanced">熟练使用 / 专家 (Advanced)</option>
                    </select>
                  )}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink">期望达成目标</label>
                <Controller
                  name="targetLevel"
                  control={control}
                  render={({ field }) => (
                    <select
                      {...field}
                      disabled={isPending}
                      className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink focus:outline-none focus:ring-2 focus:ring-primary/20"
                    >
                      <option value="beginner">基础入门级别 (Beginner)</option>
                      <option value="intermediate">独立解决一般问题 / 进阶 (Intermediate)</option>
                      <option value="advanced">掌握底层原理 / 专家级别 (Advanced)</option>
                    </select>
                  )}
                />
              </div>
            </div>

            {/* Duration & Weekly Hours */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5 text-primary" />
                  期望达标周期 (周)
                </label>
                <Controller
                  name="durationWeeks"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="number"
                      min={1}
                      max={52}
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 1)}
                      disabled={isPending}
                      className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  )}
                />
                {errors.durationWeeks && (
                  <p className="text-[10px] text-danger font-semibold">{errors.durationWeeks.message}</p>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5 text-primary" />
                  每周可学习时长 (小时)
                </label>
                <Controller
                  name="weeklyHours"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="number"
                      min={1}
                      max={168}
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 1)}
                      disabled={isPending}
                      className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  )}
                />
                {errors.weeklyHours && (
                  <p className="text-[10px] text-danger font-semibold">{errors.weeklyHours.message}</p>
                )}
              </div>
            </div>

            {/* Learning Style Preferences */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-semibold text-ink flex items-center gap-1">
                <Settings2 className="h-3.5 w-3.5 text-primary" />
                本目标的首选学习方式 (可多选)
              </label>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: "practice_first", label: "实践第一", desc: "从代码和练习开始补理论" },
                  { id: "project_based", label: "项目驱动", desc: "围绕具体项目目标迭代" },
                  { id: "theory_first", label: "理论先行", desc: "系统化建立知识点架构" },
                  { id: "case_based", label: "案例分析", desc: "研究行业具体实践与运用" },
                ].map((style) => {
                  const isSelected = selectedPreferences.includes(style.id);
                  return (
                    <button
                      key={style.id}
                      type="button"
                      onClick={() => togglePreference(style.id)}
                      disabled={isPending}
                      className={`flex flex-col items-start gap-1 p-3 rounded-xl border text-left cursor-pointer transition-all ${
                        isSelected
                          ? "border-primary bg-primary-soft/30 ring-1 ring-primary"
                          : "border-border bg-panel hover:bg-page"
                      }`}
                    >
                      <span className="text-xs font-bold text-ink">{style.label}</span>
                      <span className="text-[10px] text-muted leading-tight">{style.desc}</span>
                    </button>
                  );
                })}
              </div>
              {errors.preferences && (
                <p className="text-[10px] text-danger font-semibold">{errors.preferences.message}</p>
              )}
            </div>

            {/* Advanced configurations */}
            <div className="flex flex-col gap-3.5 bg-page/40 p-4 border border-border/60 rounded-xl">
              {/* Use Diagnostic */}
              <label className="flex items-center justify-between cursor-pointer">
                <div className="flex flex-col gap-0.5 max-w-[80%]">
                  <span className="text-xs font-bold text-ink">进行能力水平评估</span>
                  <span className="text-[10px] text-muted">
                    生成路径前进行 5-10 题诊断，自动识别已掌握的知识节点进行豁免
                  </span>
                </div>
                <Controller
                  name="useDiagnostic"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="checkbox"
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      disabled={isPending}
                      className="w-4 h-4 rounded text-primary focus:ring-primary bg-panel cursor-pointer"
                    />
                  )}
                />
              </label>

              {/* Use Knowledge Base */}
              <label className="flex items-center justify-between cursor-pointer border-t border-border/50 pt-3">
                <div className="flex flex-col gap-0.5 max-w-[80%]">
                  <span className="text-xs font-bold text-ink">关联个人专属知识库</span>
                  <span className="text-[10px] text-muted">
                    允许智能体在本次学习路径生成时检索和调用我上传的参考文档
                  </span>
                </div>
                <Controller
                  name="useKnowledgeBase"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="checkbox"
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      disabled={isPending}
                      className="w-4 h-4 rounded text-primary focus:ring-primary bg-panel cursor-pointer"
                    />
                  )}
                />
              </label>

              {/* Language Preference */}
              <div className="flex flex-col gap-1.5 border-t border-border/50 pt-3">
                <label className="text-xs font-semibold text-ink">内容生成语言</label>
                <Controller
                  name="contentLanguage"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="text"
                      placeholder="例如：中文"
                      {...field}
                      disabled={isPending}
                      className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  )}
                />
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex justify-end gap-3 border-t border-border/60 pt-4">
              <button
                type="submit"
                disabled={isPending}
                className="inline-flex items-center gap-1.5 px-6 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
              >
                {isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在分析学习目标...
                  </>
                ) : (
                  <>
                    生成学习路径
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
