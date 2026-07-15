import { Activity, AlertTriangle, BarChart3, BookOpen, Brain, CheckCircle2, Clock3, GitBranch } from "lucide-react";
import type { EffectivenessReport } from "../../api/effectiveness";

const ratingLabels = {
  excellent: { label: "效果优秀", className: "bg-success/15 text-success" },
  steady: { label: "稳步提升", className: "bg-primary/10 text-primary" },
  needs_attention: { label: "需要关注", className: "bg-warning/15 text-warning" },
  insufficient_data: { label: "数据积累中", className: "bg-panel-soft text-muted" },
};

const resourceLabels: Record<string, string> = {
  lecture: "课程讲义",
  mindmap: "思维导图",
  pptx: "演示文稿",
  video: "教学视频",
  code_zip: "代码案例",
  interactive_cards: "互动卡片",
  walkthrough: "实操指导",
  simulation: "交互模拟",
};

const dimensionLabels: Record<string, string> = {
  knowledge_depth: "知识深度",
  prerequisite_mastery: "先修掌握",
  concept_grasp: "概念理解",
  problem_solving: "问题解决",
  practice_ability: "实践能力",
  learning_pace: "学习节奏",
  resource_preference: "资源偏好",
  error_pattern: "易错模式",
};

export function EffectivenessPanel({ report }: { report: EffectivenessReport }) {
  const rating = ratingLabels[report.rating];
  const overviewCards = [
    { label: "路径完成率", value: `${report.overview.completion_rate}%`, icon: CheckCircle2 },
    { label: "平均掌握度", value: `${report.overview.average_mastery}%`, icon: Brain },
    { label: "评估通过率", value: `${report.overview.assessment_pass_rate}%`, icon: BarChart3 },
    { label: "有效学习时长", value: `${report.overview.learning_minutes} 分钟`, icon: Clock3 },
  ];

  return (
    <div className="flex flex-col gap-4 select-none">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted flex items-center gap-1.5">
          <Activity className="h-3.5 w-3.5 text-primary" /> 学习效果评估
        </span>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${rating.className}`}>{rating.label}</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {overviewCards.map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-xl border border-border bg-panel p-3">
            <Icon className="mb-2 h-3.5 w-3.5 text-primary" />
            <p className="text-sm font-bold text-ink">{value}</p>
            <p className="mt-0.5 text-[9px] text-subtle">{label}</p>
          </div>
        ))}
      </div>

      <section className="rounded-xl border border-border bg-panel p-3.5">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-xs font-bold text-ink">节点掌握情况</h4>
          <span className="text-[9px] text-subtle">已完成 {report.overview.completed_nodes}/{report.overview.total_nodes}</span>
        </div>
        <div className="flex flex-col gap-2.5">
          {report.node_performance.slice(0, 6).map((node) => (
            <div key={node.node_id}>
              <div className="mb-1 flex items-center justify-between gap-2 text-[10px]">
                <span className="truncate text-muted">{node.title}</span>
                <span className="shrink-0 font-mono text-ink">{node.mastery}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-page">
                <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.max(0, Math.min(node.mastery, 100))}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-border bg-panel p-3.5">
        <h4 className="mb-3 flex items-center gap-1.5 text-xs font-bold text-ink">
          <BookOpen className="h-3.5 w-3.5 text-accent" /> 资源利用
        </h4>
        {report.resource_usage.length === 0 ? (
          <p className="text-[10px] text-subtle">开始阅读讲义或查看思维导图后，这里会形成资源偏好统计。</p>
        ) : (
          <div className="flex flex-col gap-2">
            {report.resource_usage.map((resource) => (
              <div key={resource.resource_type} className="flex items-center justify-between text-[10px]">
                <span className="text-muted">{resourceLabels[resource.resource_type] ?? resource.resource_type}</span>
                <span className="font-mono text-ink">{resource.opens} 次 · {resource.duration_minutes} 分钟</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {report.weak_points.length > 0 && (
        <section className="rounded-xl border border-warning/25 bg-warning/5 p-3.5">
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-bold text-ink">
            <AlertTriangle className="h-3.5 w-3.5 text-warning" /> 当前薄弱点
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {report.weak_points.map((point) => (
              <span key={point.name} className="rounded-full border border-warning/20 bg-panel px-2 py-1 text-[9px] text-muted">
                {point.name} · {Math.round(point.weight * 100)}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-xl border border-border bg-panel p-3.5">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-xs font-bold text-ink">画像更新依据</h4>
          <span className="text-[9px] text-subtle">v{report.profile.version} · 置信度 {Math.round(report.profile.confidence * 100)}%</span>
        </div>
        {report.profile.recent_evidence.length === 0 ? (
          <p className="text-[10px] text-subtle">暂无画像证据</p>
        ) : (
          <div className="flex flex-col gap-2">
            {report.profile.recent_evidence.slice(0, 5).map((evidence, index) => (
              <div key={`${evidence.dimension}-${evidence.created_at}-${index}`} className="border-l-2 border-primary/30 pl-2.5">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="font-semibold text-ink">{dimensionLabels[evidence.dimension] ?? evidence.dimension}</span>
                  <span className="text-subtle">可信度 {Math.round(evidence.confidence * 100)}%</span>
                </div>
                <p className="mt-0.5 line-clamp-2 text-[9px] leading-relaxed text-muted">
                  {evidence.evidence_text || evidence.evidence_type}
                </p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-border bg-panel p-3.5">
        <h4 className="mb-2 flex items-center gap-1.5 text-xs font-bold text-ink">
          <GitBranch className="h-3.5 w-3.5 text-warning" /> 路径优化记录
        </h4>
        <p className="text-[10px] leading-relaxed text-muted">
          当前版本 v{report.path_versions.current_version}，共 {report.path_versions.total_versions} 个版本；
          已产生 {report.adaptation.proposal_count} 个适配提案，接受 {report.adaptation.accepted_count} 个。
        </p>
        {report.adaptation.latest_reason && <p className="mt-2 rounded-lg bg-page p-2 text-[9px] leading-relaxed text-subtle">最近依据：{report.adaptation.latest_reason}</p>}
      </section>

      <section className="rounded-xl border border-primary/20 bg-primary/5 p-3.5">
        <h4 className="mb-2 text-xs font-bold text-ink">下一步建议</h4>
        <ul className="flex flex-col gap-1.5">
          {report.suggestions.map((suggestion) => (
            <li key={suggestion} className="flex items-start gap-1.5 text-[10px] leading-relaxed text-muted">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" /> {suggestion}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
