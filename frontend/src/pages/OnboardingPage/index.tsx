import React, { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { submitOnboarding } from "../../api/users";
import { queryKeys } from "../../api/queryKeys";
import { useToast } from "../../components/feedback/Toast";
import { appRoutes } from "../../app/routes";
import { ArrowLeft, ArrowRight, Check, Plus, X, Sparkles, BookOpen, Clock, Settings2 } from "lucide-react";

const onboardingSchema = z.object({
  role: z.enum(["student", "teacher", "professional", "self_learner", "other"]),
  learningInterests: z.array(z.string()).min(1, "请至少添加一个感兴趣的学习方向或技能标签"),
  preferredLanguage: z.string().min(1, "请输入首选语言"),
  weeklyHours: z.number().min(1, "学习时长必须至少 1 小时").max(168),
  learningPreferences: z.array(z.enum(["project_based", "theory_first", "practice_first", "case_based"])).min(1, "请至少选择一种学习方式"),
  useDiagnostic: z.boolean(),
  useKnowledgeBase: z.boolean(),
});

type OnboardingSchemaValues = z.infer<typeof onboardingSchema>;

export function OnboardingPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [currentStep, setCurrentStep] = useState(1);
  const [interestInput, setInterestInput] = useState("");

  const {
    control,
    handleSubmit,
    setValue,
    watch,
    trigger,
    formState: { errors },
  } = useForm<OnboardingSchemaValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: {
      role: "student",
      learningInterests: ["数据结构", "Python", "机器学习"],
      preferredLanguage: "中文",
      weeklyHours: 10,
      learningPreferences: ["practice_first"],
      useDiagnostic: true,
      useKnowledgeBase: false,
    },
  });

  const interests = watch("learningInterests");
  const selectedPreferences = watch("learningPreferences");

  const { mutate: performOnboarding, isPending } = useMutation({
    mutationFn: submitOnboarding,
    onSuccess: (updatedUser) => {
      queryClient.setQueryData(queryKeys.auth.me(), updatedUser);
      toast("个性化设置保存成功！", "success");
      navigate(appRoutes.goalCreate(), { replace: true });
    },
    onError: (err: any) => {
      toast(err.message || "保存设置失败，请稍后重试", "error");
    },
  });

  const handleNextStep = async () => {
    let isValid = false;
    if (currentStep === 1) {
      isValid = await trigger(["role", "preferredLanguage"]);
    } else if (currentStep === 2) {
      isValid = await trigger(["learningInterests", "weeklyHours"]);
    }
    
    if (isValid) {
      setCurrentStep((prev) => prev + 1);
    }
  };

  const handlePrevStep = () => {
    setCurrentStep((prev) => prev - 1);
  };

  const handleAddInterest = (e: React.KeyboardEvent | React.MouseEvent) => {
    if (e.type === "keydown" && (e as React.KeyboardEvent).key !== "Enter") {
      return;
    }
    e.preventDefault();
    const tag = interestInput.trim();
    if (tag && !interests.includes(tag)) {
      setValue("learningInterests", [...interests, tag], { shouldValidate: true });
      setInterestInput("");
    }
  };

  const handleRemoveInterest = (tag: string) => {
    setValue(
      "learningInterests",
      interests.filter((item) => item !== tag),
      { shouldValidate: true }
    );
  };

  const togglePreference = (pref: "project_based" | "theory_first" | "practice_first" | "case_based") => {
    if (selectedPreferences.includes(pref)) {
      setValue(
        "learningPreferences",
        selectedPreferences.filter((p) => p !== pref),
        { shouldValidate: true }
      );
    } else {
      setValue("learningPreferences", [...selectedPreferences, pref], { shouldValidate: true });
    }
  };

  const onSubmit = (values: OnboardingSchemaValues) => {
    performOnboarding(values);
  };

  return (
    <div className="min-h-screen bg-page flex items-center justify-center p-6 select-none font-sans">
      <div className="w-full max-w-xl bg-panel border border-border rounded-2xl shadow-card overflow-hidden flex flex-col gap-6 p-8">
        
        {/* Header Block */}
        <div className="flex flex-col items-center gap-2">
          <div className="p-3 bg-primary-soft text-primary rounded-xl">
            <Sparkles className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">量身定制您的学习智能体</h1>
          <p className="text-xs text-muted">只需三步，我们将为您配置最适合的学习路径与节奏</p>
        </div>

        {/* Multi-step indicator bar */}
        <div className="flex items-center justify-center gap-4 w-full max-w-sm mx-auto mb-2">
          {[1, 2, 3].map((step) => (
            <React.Fragment key={step}>
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 ${
                  currentStep === step
                    ? "bg-primary text-white scale-110 shadow-sm"
                    : currentStep > step
                    ? "bg-primary-soft text-primary"
                    : "bg-page border border-border text-muted"
                }`}
              >
                {currentStep > step ? <Check className="h-3.5 w-3.5" /> : step}
              </div>
              {step < 3 && (
                <div
                  className={`flex-grow h-0.5 max-w-[60px] rounded transition-colors duration-300 ${
                    currentStep > step ? "bg-primary" : "bg-border"
                  }`}
                />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Content Container */}
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-6 min-h-[220px]">
          
          {/* STEP 1: Basic details */}
          {currentStep === 1 && (
            <div className="flex flex-col gap-5 animate-fade-in">
              <div className="flex items-center gap-2 text-sm font-bold text-ink border-b border-border/60 pb-2">
                <BookOpen className="h-4.5 w-4.5 text-primary" />
                第一步：选择角色与偏好语言
              </div>

              {/* Role select */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink">您目前的主要身份是？</label>
                <Controller
                  name="role"
                  control={control}
                  render={({ field }) => (
                    <select
                      {...field}
                      disabled={isPending}
                      className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
                    >
                      <option value="student">在校学生 (Student)</option>
                      <option value="teacher">教师 / 学术研究者 (Teacher/Academic)</option>
                      <option value="professional">职场人士 (Professional)</option>
                      <option value="self_learner">自主学习爱好者 (Self Learner)</option>
                      <option value="other">其他身份 (Other)</option>
                    </select>
                  )}
                />
                {errors.role && <p className="text-[10px] text-danger font-semibold mt-0.5">{errors.role.message}</p>}
              </div>

              {/* Language select */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink">首选学习语言</label>
                <Controller
                  name="preferredLanguage"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="text"
                      placeholder="例如：中文, English"
                      {...field}
                      disabled={isPending}
                      className="w-full px-3.5 py-2.5 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
                    />
                  )}
                />
                {errors.preferredLanguage && (
                  <p className="text-[10px] text-danger font-semibold mt-0.5">{errors.preferredLanguage.message}</p>
                )}
              </div>
            </div>
          )}

          {/* STEP 2: Interests and Commitment */}
          {currentStep === 2 && (
            <div className="flex flex-col gap-5 animate-fade-in">
              <div className="flex items-center gap-2 text-sm font-bold text-ink border-b border-border/60 pb-2">
                <Clock className="h-4.5 w-4.5 text-primary" />
                第二步：设定方向与每周课时
              </div>

              {/* Interests tag input */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-ink">您感兴趣的专业方向或技能标签</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="输入标签并回车"
                    value={interestInput}
                    onChange={(e) => setInterestInput(e.target.value)}
                    onKeyDown={handleAddInterest}
                    disabled={isPending}
                    className="flex-grow px-3.5 py-2 bg-panel border border-border focus:border-primary rounded-xl text-xs text-ink transition-all focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  <button
                    type="button"
                    onClick={handleAddInterest}
                    disabled={isPending}
                    className="px-3 py-2 bg-primary-soft hover:bg-primary/20 text-primary rounded-xl cursor-pointer"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>
                
                {/* Active tags display */}
                <div className="flex flex-wrap gap-1.5 mt-2 p-2.5 bg-page/50 border border-border/60 rounded-xl min-h-[50px]">
                  {interests.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 px-2.5 py-1 bg-panel border border-border rounded-lg text-[10px] text-ink font-semibold"
                    >
                      {tag}
                      <button
                        type="button"
                        onClick={() => handleRemoveInterest(tag)}
                        disabled={isPending}
                        className="text-muted hover:text-danger cursor-pointer"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  {interests.length === 0 && (
                    <span className="text-[10px] text-muted self-center">请添加至少一个标签</span>
                  )}
                </div>
                {errors.learningInterests && (
                  <p className="text-[10px] text-danger font-semibold mt-0.5">{errors.learningInterests.message}</p>
                )}
              </div>

              {/* Weekly Hours Input */}
              <div className="flex flex-col gap-2">
                <div className="flex justify-between items-center text-xs font-semibold text-ink">
                  <span>每周可支配学习时长</span>
                  <span className="font-mono text-primary bg-primary-soft px-2 py-0.5 rounded">
                    {watch("weeklyHours")} 小时 / 周
                  </span>
                </div>
                <Controller
                  name="weeklyHours"
                  control={control}
                  render={({ field }) => (
                    <input
                      type="range"
                      min={1}
                      max={40}
                      step={1}
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10))}
                      disabled={isPending}
                      className="w-full accent-primary cursor-pointer h-1.5 bg-border rounded-lg appearance-none"
                    />
                  )}
                />
                <div className="flex justify-between text-[10px] text-muted font-medium">
                  <span>1 小时</span>
                  <span>10 小时</span>
                  <span>20 小时</span>
                  <span>30 小时</span>
                  <span>40 小时</span>
                </div>
              </div>
            </div>
          )}

          {/* STEP 3: Style Preferences & Toggle Configs */}
          {currentStep === 3 && (
            <div className="flex flex-col gap-5 animate-fade-in">
              <div className="flex items-center gap-2 text-sm font-bold text-ink border-b border-border/60 pb-2">
                <Settings2 className="h-4.5 w-4.5 text-primary" />
                第三步：设定学习偏好与高级功能
              </div>

              {/* Learning Style Preferences checkbox grid */}
              <div className="flex flex-col gap-2">
                <label className="text-xs font-semibold text-ink">偏好的学习方式 (可多选)</label>
                <div className="grid grid-cols-2 gap-2.5">
                  {[
                    { id: "practice_first", label: "实践第一", desc: "动手练项目, 遇到卡点补理论" },
                    { id: "project_based", label: "项目驱动", desc: "围绕具体项目目标逐步学习" },
                    { id: "theory_first", label: "理论先行", desc: "先理清概念框架再做应用" },
                    { id: "case_based", label: "案例分析", desc: "探究实际问题解法并分析" },
                  ].map((style) => {
                    const isSelected = selectedPreferences.includes(style.id as any);
                    return (
                      <button
                        key={style.id}
                        type="button"
                        onClick={() => togglePreference(style.id as any)}
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
                {errors.learningPreferences && (
                  <p className="text-[10px] text-danger font-semibold mt-0.5">{errors.learningPreferences.message}</p>
                )}
              </div>

              {/* Toggles */}
              <div className="flex flex-col gap-3.5 mt-2 bg-page/40 p-4 border border-border/60 rounded-xl">
                {/* Use Diagnostic Toggle */}
                <label className="flex items-center justify-between cursor-pointer">
                  <div className="flex flex-col gap-0.5 max-w-[80%]">
                    <span className="text-xs font-bold text-ink">开启能力诊断</span>
                    <span className="text-[10px] text-muted leading-tight">
                      激活图谱前先回答几个基础问题，智能体将根据答题结果对路径进行二次修剪
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

                {/* Use Knowledge Base Toggle */}
                <label className="flex items-center justify-between cursor-pointer border-t border-border/50 pt-3">
                  <div className="flex flex-col gap-0.5 max-w-[80%]">
                    <span className="text-xs font-bold text-ink">关联个人知识库</span>
                    <span className="text-[10px] text-muted leading-tight">
                      允许智能体在设计学习路径和生成单元时，参考您在知识库中上传的个人文档
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
              </div>
            </div>
          )}

          {/* Stepper Footer Controls */}
          <div className="flex items-center justify-between border-t border-border/60 pt-4 mt-2">
            {currentStep > 1 ? (
              <button
                type="button"
                onClick={handlePrevStep}
                disabled={isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-border hover:bg-page text-xs font-semibold text-ink transition-colors cursor-pointer disabled:opacity-50"
              >
                <ArrowLeft className="h-3.5 w-3.5 text-muted" />
                上一步
              </button>
            ) : (
              <div />
            )}

            {currentStep < 3 ? (
              <button
                key="btn-next"
                type="button"
                onClick={handleNextStep}
                disabled={isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-semibold shadow-sm transition-all cursor-pointer"
              >
                下一步
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            ) : (
              <button
                key="btn-submit"
                type="submit"
                disabled={isPending}
                className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-xs font-bold shadow-md hover:shadow-lg transition-all cursor-pointer disabled:opacity-50"
              >
                保存并开始学习
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

        </form>
      </div>
    </div>
  );
}
