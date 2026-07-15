import { CheckCircle2, ShieldCheck, TriangleAlert } from "lucide-react";
import type { ResourceQuality } from "../../api/resources";

const GRADE_LABELS: Record<ResourceQuality["grade"], string> = {
  excellent: "优秀",
  good: "良好",
  acceptable: "达标",
  needs_review: "需要复核",
};

export function ResourceQualityReport({ quality }: { quality: ResourceQuality }) {
  const Icon = quality.passed ? ShieldCheck : TriangleAlert;

  return (
    <section
      className={`rounded-xl border p-4 ${
        quality.passed
          ? "border-success/25 bg-success/5"
          : "border-warning/30 bg-warning/5"
      }`}
      aria-label="资源质量报告"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className={`h-5 w-5 ${quality.passed ? "text-success" : "text-warning"}`} />
          <div>
            <h4 className="text-xs font-bold text-ink">资源质量审查</h4>
            <p className="mt-0.5 text-[9px] text-muted">
              规则版本 {quality.rubric_version} · 交付门槛 {quality.threshold} 分
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xl font-black text-ink">{quality.score}</span>
          <span className="text-[10px] text-muted">/ {quality.max_score}</span>
          <span
            className={`rounded-full px-2 py-1 text-[10px] font-bold ${
              quality.passed ? "bg-success/10 text-success" : "bg-warning/10 text-warning"
            }`}
          >
            {GRADE_LABELS[quality.grade]}
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {quality.dimensions.map((dimension) => {
          const percent = Math.round((dimension.score / dimension.max_score) * 100);
          return (
            <div key={dimension.key} className="rounded-lg border border-border/70 bg-panel/70 p-3">
              <div className="flex items-center justify-between text-[10px]">
                <span className="font-bold text-ink">{dimension.label}</span>
                <span className="font-mono text-muted">
                  {dimension.score}/{dimension.max_score}
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-page">
                <div
                  className={quality.passed ? "h-full rounded-full bg-success" : "h-full rounded-full bg-warning"}
                  style={{ width: `${Math.min(percent, 100)}%` }}
                />
              </div>
              <p className="mt-2 text-[9px] leading-4 text-muted">{dimension.summary}</p>
            </div>
          );
        })}
      </div>

      {quality.warnings.length > 0 && (
        <div className="mt-3 rounded-lg border border-warning/20 bg-panel/60 p-3">
          <p className="text-[10px] font-bold text-warning">改进建议</p>
          <ul className="mt-2 space-y-1 text-[9px] leading-4 text-muted">
            {quality.warnings.map((warning) => (
              <li key={warning} className="flex gap-1.5">
                <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0" />
                {warning}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
