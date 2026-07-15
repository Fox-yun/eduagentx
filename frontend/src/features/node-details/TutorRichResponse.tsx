import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clipboard,
  Code2,
  Lightbulb,
  Network,
  Pause,
  Play,
  RotateCcw,
  Terminal,
  ThumbsDown,
  ThumbsUp,
  Timer,
  Video,
} from "lucide-react";
import type { ChatMessage, TutorResponseMode } from "../../api/chat";

type TutorView = "text" | TutorResponseMode;

export function TutorRichResponse({
  message,
  onFeedback,
}: {
  message: ChatMessage;
  onFeedback: (message: ChatMessage, helpful: boolean) => void;
}) {
  const availableViews: TutorView[] = ["text"];
  if (message.diagram) availableViews.push("diagram");
  if (message.codeExample) availableViews.push("code");
  if (message.storyboard) availableViews.push("storyboard");
  const [activeView, setActiveView] = React.useState<TutorView>("text");
  const [feedback, setFeedback] = React.useState<"up" | "down" | null>(null);

  const labels: Record<TutorView, { label: string; icon: React.ReactNode }> = {
    text: { label: "讲解", icon: <BookOpen className="h-3 w-3" /> },
    diagram: { label: "图解", icon: <Network className="h-3 w-3" /> },
    code: { label: "代码", icon: <Code2 className="h-3 w-3" /> },
    storyboard: { label: "动画", icon: <Video className="h-3 w-3" /> },
  };

  const handleFeedback = (helpful: boolean) => {
    if (feedback) return;
    setFeedback(helpful ? "up" : "down");
    onFeedback(message, helpful);
  };

  return (
    <div className="max-w-[96%] overflow-hidden rounded-2xl rounded-bl-md border border-border bg-page text-ink">
      {availableViews.length > 1 && (
        <div className="flex gap-1 border-b border-border/60 bg-panel/70 p-1.5">
          {availableViews.map((view) => (
            <button
              key={view}
              type="button"
              onClick={() => setActiveView(view)}
              className={`flex items-center gap-1 rounded-lg px-2 py-1 text-[9px] font-semibold transition-colors ${activeView === view ? "bg-primary text-white" : "text-muted hover:bg-page"}`}
            >
              {labels[view].icon} {labels[view].label}
            </button>
          ))}
        </div>
      )}

      <div className="p-3.5">
        {activeView === "text" && (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-2 text-xs leading-relaxed last:mb-0">{children}</p>,
              ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-4 text-xs">{children}</ul>,
              ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-4 text-xs">{children}</ol>,
              code: ({ children }) => <code className="rounded bg-panel px-1 py-0.5 font-mono text-[10px] text-primary">{children}</code>,
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
        {activeView === "diagram" && message.diagram && <TutorDiagramView diagram={message.diagram} />}
        {activeView === "code" && message.codeExample && <TutorCodeView example={message.codeExample} />}
        {activeView === "storyboard" && message.storyboard && <TutorStoryboardView storyboard={message.storyboard} />}
      </div>

      {message.citations && message.citations.length > 0 && (
        <div className="mx-3.5 flex flex-wrap gap-1.5 border-t border-border/50 py-2.5">
          {message.citations.map((citation) => (
            <span
              key={citation.chunk_id}
              className="inline-flex items-center gap-1 rounded-md bg-primary/8 px-1.5 py-0.5 text-[9px] font-medium text-primary"
              title={citation.section_title || undefined}
            >
              <BookOpen className="h-2.5 w-2.5 shrink-0" />
              <span className="max-w-[110px] truncate">{citation.file_name}</span>
              {citation.page_number != null && <span className="opacity-70">p.{citation.page_number}</span>}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 border-t border-border/50 bg-panel/40 px-3.5 py-2">
        <div className="flex flex-wrap gap-1 text-[8px] text-subtle">
          {message.personalization?.applied && <span className="rounded bg-primary/8 px-1.5 py-0.5">画像 v{message.personalization.profileVersion}</span>}
          {message.quality?.grounded && <span className="rounded bg-success/10 px-1.5 py-0.5 text-success">内容有据</span>}
          {message.quality?.safetyChecked && <span className="rounded bg-panel-soft px-1.5 py-0.5">已审查</span>}
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => handleFeedback(true)} className={`rounded p-1 ${feedback === "up" ? "bg-success/15 text-success" : "text-subtle hover:text-success"}`} title="回答有帮助">
            <ThumbsUp className="h-3 w-3" />
          </button>
          <button type="button" onClick={() => handleFeedback(false)} className={`rounded p-1 ${feedback === "down" ? "bg-danger/10 text-danger" : "text-subtle hover:text-danger"}`} title="回答需改进">
            <ThumbsDown className="h-3 w-3" />
          </button>
        </div>
      </div>

      {message.agentTrace && message.agentTrace.length > 0 && (
        <details className="border-t border-border/50 px-3.5 py-2 text-[9px]">
          <summary className="flex cursor-pointer list-none items-center gap-1 font-semibold text-muted">
            <ChevronDown className="h-3 w-3" /> {message.agentTrace.length} 个辅导智能体协作完成
          </summary>
          <div className="mt-2 flex flex-col gap-1.5">
            {message.agentTrace.map((step) => (
              <div key={`${step.agent}-${step.role}`} className="flex items-start gap-2 rounded-lg bg-panel/60 p-2">
                {step.status === "completed" ? <Check className="mt-0.5 h-3 w-3 shrink-0 text-success" /> : <span className="text-danger">!</span>}
                <div>
                  <p className="font-semibold text-ink">{step.role}</p>
                  <p className="mt-0.5 leading-relaxed text-subtle">{step.summary}</p>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function TutorDiagramView({ diagram }: { diagram: NonNullable<ChatMessage["diagram"]> }) {
  const diagramType = diagram.diagram_type ?? "concept_map";
  const typeLabels = {
    concept_map: "概念关系",
    flow: "执行流程",
    hierarchy: "层级结构",
    comparison: "双栏对比",
    cycle: "循环闭环",
  } as const;

  return (
    <div>
      <div className="mb-3">
        <div className="flex items-start justify-between gap-2">
          <h4 className="text-xs font-bold leading-relaxed text-ink">{diagram.title}</h4>
          <span className="shrink-0 rounded-full bg-primary/8 px-2 py-1 text-[8px] font-semibold text-primary">
            {typeLabels[diagramType]}
          </span>
        </div>
        {diagram.summary && <p className="mt-1 text-[9px] leading-relaxed text-muted">{diagram.summary}</p>}
      </div>
      {diagramType === "flow" && <FlowDiagram diagram={diagram} />}
      {diagramType === "concept_map" && <ConceptMapDiagram diagram={diagram} />}
      {diagramType === "hierarchy" && <HierarchyDiagram diagram={diagram} />}
      {diagramType === "comparison" && <ComparisonDiagram diagram={diagram} />}
      {diagramType === "cycle" && <CycleDiagram diagram={diagram} />}
    </div>
  );
}

type Diagram = NonNullable<ChatMessage["diagram"]>;
type DiagramNode = Diagram["nodes"][number];

function DiagramNodeCard({ node, marker, compact = false }: { node: DiagramNode; marker: React.ReactNode; compact?: boolean }) {
  return (
    <div
      className={`relative w-full rounded-xl border ${compact ? "p-2" : "p-3"} ${
        node.kind === "question"
          ? "border-primary/30 bg-primary/8"
          : node.kind === "practice"
            ? "border-success/30 bg-success/8"
            : "border-border bg-panel"
      }`}
    >
      <div className={`flex items-start ${compact ? "gap-1.5" : "gap-2.5"}`}>
        <span
          className={`flex shrink-0 items-center justify-center rounded-lg font-bold ${compact ? "h-5 w-5 text-[8px]" : "h-6 w-6 text-[9px]"} ${
            node.kind === "question"
              ? "bg-primary text-white"
              : node.kind === "practice"
                ? "bg-success text-white"
                : "bg-primary/10 text-primary"
          }`}
        >
          {marker}
        </span>
        <div className="min-w-0">
          <p className={`${compact ? "text-[9px]" : "text-[10px]"} font-bold leading-relaxed text-ink`}>{node.label}</p>
          {node.detail && <p className={`mt-1 ${compact ? "text-[8px]" : "text-[9px]"} leading-relaxed text-muted`}>{node.detail}</p>}
        </div>
      </div>
    </div>
  );
}

function edgeLabel(diagram: Diagram, source: string, target: string) {
  return diagram.edges.find((edge) => edge.source === source && edge.target === target)?.label ?? "关联";
}

function FlowDiagram({ diagram }: { diagram: Diagram }) {
  return (
    <div aria-label="执行流程图" className="relative flex flex-col">
      {diagram.nodes.map((node, index) => (
        <React.Fragment key={node.id}>
          <DiagramNodeCard
            node={node}
            marker={node.kind === "question" ? "起" : node.kind === "practice" ? <Check className="h-3 w-3" /> : index + 1}
          />
          {index < diagram.nodes.length - 1 && (() => {
            const nextNode = diagram.nodes[index + 1];
            return (
              <div className="flex h-8 items-center justify-center gap-1.5 text-[8px] text-subtle">
                <span className="h-full w-px bg-border" />
                <span className="rounded-full border border-border bg-page px-2 py-0.5 font-medium text-muted">
                  {edgeLabel(diagram, node.id, nextNode.id)}
                </span>
                <span className="text-primary">↓</span>
              </div>
            );
          })()}
        </React.Fragment>
      ))}
    </div>
  );
}

function ConceptMapDiagram({ diagram }: { diagram: Diagram }) {
  const center = diagram.nodes.find((node) => node.kind === "question") ?? diagram.nodes[0];
  const practice = diagram.nodes.find((node) => node.kind === "practice");
  const concepts = diagram.nodes.filter((node) => node.id !== center.id && node.id !== practice?.id);
  return (
    <div aria-label="概念关系图" className="rounded-2xl border border-primary/15 bg-primary/[0.025] p-2.5">
      <div className="mx-auto max-w-[88%]">
        <DiagramNodeCard node={center} marker="核" />
      </div>
      <div className="flex h-7 items-center justify-center">
        <span className="h-full w-px bg-primary/25" />
        <span className="ml-2 rounded-full bg-primary/8 px-2 py-0.5 text-[8px] font-semibold text-primary">向外展开</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {concepts.map((node, index) => (
          <div key={node.id} className="relative">
            <span className="mb-1 block text-center text-[7px] font-medium text-primary">{edgeLabel(diagram, center.id, node.id)}</span>
            <DiagramNodeCard node={node} marker={index + 1} compact />
          </div>
        ))}
      </div>
      {practice && (
        <div className="mt-2">
          <div className="mb-1 text-center text-[8px] text-success">各概念汇合到实践验证 ↓</div>
          <DiagramNodeCard node={practice} marker={<Check className="h-3 w-3" />} compact />
        </div>
      )}
    </div>
  );
}

function hierarchyLevels(diagram: Diagram): DiagramNode[][] {
  const root = diagram.nodes.find((node) => node.kind === "question") ?? diagram.nodes[0];
  const byId = new Map(diagram.nodes.map((node) => [node.id, node]));
  const visited = new Set([root.id]);
  const levels: DiagramNode[][] = [[root]];
  let current = [root.id];
  while (current.length > 0) {
    const nextIds = diagram.edges
      .filter((edge) => current.includes(edge.source) && !visited.has(edge.target))
      .map((edge) => edge.target);
    const uniqueIds = [...new Set(nextIds)];
    uniqueIds.forEach((id) => visited.add(id));
    const level = uniqueIds.map((id) => byId.get(id)).filter((node): node is DiagramNode => Boolean(node));
    if (level.length === 0) break;
    levels.push(level);
    current = uniqueIds;
  }
  const remaining = diagram.nodes.filter((node) => !visited.has(node.id));
  if (remaining.length > 0) levels.push(remaining);
  return levels;
}

function HierarchyDiagram({ diagram }: { diagram: Diagram }) {
  const levels = hierarchyLevels(diagram);
  return (
    <div aria-label="层级结构图" className="rounded-2xl border border-border bg-panel/40 p-2.5">
      {levels.map((level, levelIndex) => (
        <React.Fragment key={`level-${levelIndex}`}>
          {levelIndex > 0 && (
            <div className="flex h-7 items-center justify-center gap-2 text-[8px] text-primary">
              <span className="h-full w-px bg-primary/25" />
              <span className="rounded-full bg-page px-2 py-0.5">第 {levelIndex + 1} 层</span>
            </div>
          )}
          <div className={`grid gap-2 ${level.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
            {level.map((node, index) => <DiagramNodeCard key={node.id} node={node} marker={levelIndex === 0 ? "根" : index + 1} compact={level.length > 1} />)}
          </div>
        </React.Fragment>
      ))}
    </div>
  );
}

function ComparisonDiagram({ diagram }: { diagram: Diagram }) {
  const root = diagram.nodes.find((node) => node.kind === "question");
  const practice = diagram.nodes.find((node) => node.kind === "practice");
  const groups = diagram.groups?.slice(0, 2) ?? [{ id: "left", label: "对象 A" }, { id: "right", label: "对象 B" }];
  const concepts = diagram.nodes.filter((node) => node.kind === "concept");
  const nodesForGroup = (groupId: string, groupIndex: number) => concepts.filter((node, index) => (node.group ? node.group === groupId : index % 2 === groupIndex));
  return (
    <div aria-label="双栏对比图">
      {root && <div className="mb-2"><DiagramNodeCard node={root} marker="比" compact /></div>}
      <div className="grid grid-cols-2 gap-2 rounded-2xl border border-border bg-panel/40 p-2">
        {groups.map((group, groupIndex) => (
          <section key={group.id} className="min-w-0 rounded-xl bg-page p-1.5">
            <h5 className={`mb-2 rounded-lg px-2 py-1.5 text-center text-[9px] font-bold ${groupIndex === 0 ? "bg-primary/10 text-primary" : "bg-accent/10 text-accent"}`}>{group.label}</h5>
            <div className="space-y-2">
              {nodesForGroup(group.id, groupIndex).map((node, index) => <DiagramNodeCard key={node.id} node={node} marker={index + 1} compact />)}
            </div>
          </section>
        ))}
      </div>
      {practice && <div className="mt-2"><DiagramNodeCard node={practice} marker={<Check className="h-3 w-3" />} compact /></div>}
    </div>
  );
}

function CycleDiagram({ diagram }: { diagram: Diagram }) {
  return (
    <div aria-label="循环闭环图" className="rounded-2xl border border-primary/15 bg-primary/[0.025] p-2.5">
      <div className="grid grid-cols-2 gap-2">
        {diagram.nodes.map((node, index) => (
          <div key={node.id} className="relative pb-3">
            <DiagramNodeCard node={node} marker={index + 1} compact />
            {index < diagram.nodes.length - 1 && <span className="absolute bottom-0 right-1 text-sm font-bold text-primary">↘</span>}
          </div>
        ))}
      </div>
      <div className="mt-1 flex items-center justify-center gap-2 rounded-xl border border-dashed border-primary/30 bg-page px-3 py-2 text-[8px] font-semibold text-primary">
        <RotateCcw className="h-3.5 w-3.5" /> {diagram.edges.find((edge) => edge.target === diagram.nodes[0]?.id)?.label || "结果反馈到起点，进入下一轮"}
      </div>
    </div>
  );
}

function TutorCodeView({ example }: { example: NonNullable<ChatMessage["codeExample"]> }) {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    await navigator.clipboard?.writeText(example.code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h4 className="text-xs font-bold text-ink">{example.title}</h4>
          <span className="mt-1 inline-flex items-center gap-1 rounded bg-panel px-1.5 py-0.5 font-mono text-[8px] text-primary">
            <Terminal className="h-2.5 w-2.5" /> {example.language}
          </span>
        </div>
        <button type="button" onClick={copy} className="flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-[9px] text-muted">
          {copied ? <Check className="h-3 w-3 text-success" /> : <Clipboard className="h-3 w-3" />} {copied ? "已复制" : "复制"}
        </button>
      </div>
      <pre className="max-h-64 overflow-auto rounded-xl bg-[#172033] p-3 font-mono text-[10px] leading-relaxed text-slate-100"><code>{example.code}</code></pre>
      {example.expected_output && (
        <div className="mt-2 overflow-hidden rounded-xl border border-success/20 bg-success/5">
          <div className="flex items-center gap-1 border-b border-success/15 px-3 py-1.5 text-[8px] font-bold text-success">
            <CheckCircle2 className="h-3 w-3" /> 预期输出
          </div>
          <pre className="whitespace-pre-wrap px-3 py-2 font-mono text-[9px] leading-relaxed text-ink">{example.expected_output}</pre>
        </div>
      )}
      <p className="mt-2 text-[9px] leading-relaxed text-muted">{example.explanation}</p>
      {example.walkthrough && example.walkthrough.length > 0 && (
        <ol className="mt-2 space-y-1.5">
          {example.walkthrough.map((step, index) => (
            <li key={`${index}-${step}`} className="flex items-start gap-2 rounded-lg bg-panel/70 px-2.5 py-2 text-[9px] leading-relaxed text-ink">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[8px] font-bold text-primary">{index + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      )}
      {example.challenge && (
        <div className="mt-2 flex items-start gap-2 rounded-xl border border-accent/25 bg-accent/8 p-2.5 text-[9px] leading-relaxed text-ink">
          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
          <div><strong>动手改一改：</strong>{example.challenge}</div>
        </div>
      )}
    </div>
  );
}

function TutorStoryboardView({ storyboard }: { storyboard: NonNullable<ChatMessage["storyboard"]> }) {
  const [sceneIndex, setSceneIndex] = React.useState(0);
  const [playing, setPlaying] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const scene = storyboard.scenes[sceneIndex];
  const sceneKeywords = scene.keywords ?? [];
  const visualKeywords = sceneKeywords.length > 0 ? sceneKeywords : [scene.title];
  const activeKeywordIndex = Math.min(Math.floor(progress / (100 / visualKeywords.length)), visualKeywords.length - 1);
  const defaultDuration = Math.max(4, Math.round(storyboard.estimated_seconds / Math.max(storyboard.scenes.length, 1)));
  const sceneDuration = scene.duration_seconds || defaultDuration;

  React.useEffect(() => {
    if (!playing || storyboard.scenes.length === 0) return;
    const timer = window.setInterval(() => {
      setProgress((current) => {
        const next = current + 100 / (sceneDuration * 10);
        if (next < 100) return next;
        if (sceneIndex >= storyboard.scenes.length - 1) {
          setPlaying(false);
          return 100;
        }
        setSceneIndex((index) => index + 1);
        return 0;
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [playing, sceneDuration, sceneIndex, storyboard.scenes.length]);

  const goToScene = (index: number) => {
    setSceneIndex(Math.max(0, Math.min(index, storyboard.scenes.length - 1)));
    setProgress(0);
    setPlaying(false);
  };
  const togglePlayback = () => {
    if (sceneIndex === storyboard.scenes.length - 1 && progress >= 100) {
      setSceneIndex(0);
      setProgress(0);
      setPlaying(true);
      return;
    }
    setPlaying((value) => !value);
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h4 className="text-xs font-bold text-ink">{storyboard.title}</h4>
          <p className="mt-0.5 flex items-center gap-1 text-[8px] text-subtle">
            <Timer className="h-2.5 w-2.5" /> 约 {storyboard.estimated_seconds} 秒 · {storyboard.scenes.length} 个动态场景
          </p>
        </div>
        <button type="button" onClick={togglePlayback} className="rounded-full bg-primary p-2 text-white" aria-label={playing ? "暂停动画" : progress >= 100 ? "重新播放动画" : "播放动画"}>
          {playing ? <Pause className="h-3 w-3" /> : progress >= 100 ? <RotateCcw className="h-3 w-3" /> : <Play className="h-3 w-3" />}
        </button>
      </div>
      <div className="relative min-h-52 overflow-hidden rounded-xl border border-primary/10 bg-gradient-to-br from-primary/15 via-accent/10 to-success/10 p-4">
        <div className={`absolute -right-8 -top-8 h-28 w-28 rounded-full bg-primary/10 blur-xl transition-transform duration-700 ${playing ? "scale-125" : "scale-100"}`} />
        <div key={sceneIndex} className="relative animate-fade-in">
          <div className="flex items-center justify-between gap-2">
            <span className="rounded-full bg-panel/90 px-2 py-1 text-[8px] font-bold text-primary">场景 {sceneIndex + 1}/{storyboard.scenes.length}</span>
            <span className="text-[8px] font-medium text-subtle">{sceneDuration} 秒</span>
          </div>
          <h5 className="mt-3 text-sm font-bold text-ink">{scene.title}</h5>
          <div className="relative mt-3 overflow-hidden rounded-xl border border-white/70 bg-white/55 p-3 shadow-inner">
            <div className="absolute left-5 right-5 top-1/2 h-1 -translate-y-1/2 rounded-full bg-border/80" />
            <div
              className="absolute left-5 top-1/2 h-1 -translate-y-1/2 rounded-full bg-primary transition-[width] duration-100"
              style={{ width: `calc((100% - 2.5rem) * ${progress / 100})` }}
            />
            <div className="relative flex items-center justify-between gap-1.5">
              {visualKeywords.map((keyword, index) => (
                <div
                  key={`${keyword}-${index}`}
                  className={`flex min-h-12 min-w-0 flex-1 items-center justify-center rounded-xl border px-1.5 py-2 text-center text-[8px] font-bold leading-tight transition-all duration-300 ${
                    index < activeKeywordIndex
                      ? "border-success/30 bg-success text-white"
                      : index === activeKeywordIndex
                        ? "scale-105 border-primary bg-primary text-white shadow-md"
                        : "border-border bg-panel text-muted"
                  }`}
                >
                  {keyword}
                </div>
              ))}
            </div>
          </div>
          <div className="mt-3 rounded-xl border border-white/60 bg-panel/70 p-3 shadow-sm">
            <p className="text-[8px] font-bold uppercase tracking-wide text-subtle">画面变化</p>
            <p className="mt-1 text-[10px] leading-relaxed text-muted">{scene.visual}</p>
          </div>
          <div className="mt-2 rounded-xl bg-ink/90 p-3 text-slate-100 shadow-sm">
            <p className="text-[8px] font-bold text-primary-soft">同步讲解</p>
            <p className="mt-1 text-[10px] leading-relaxed">{scene.narration}</p>
          </div>
        </div>
      </div>
      <div className="mt-2 flex gap-1.5">
        {storyboard.scenes.map((_, index) => (
          <button key={index} type="button" onClick={() => goToScene(index)} className="h-1.5 flex-1 overflow-hidden rounded-full bg-border" aria-label={`切换到场景 ${index + 1}`}>
            <span
              className="block h-full rounded-full bg-primary transition-[width] duration-100"
              style={{ width: index < sceneIndex ? "100%" : index === sceneIndex ? `${progress}%` : "0%" }}
            />
          </button>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between">
        <button type="button" onClick={() => goToScene(sceneIndex - 1)} disabled={sceneIndex === 0} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[8px] font-medium text-muted disabled:opacity-30">
          <ChevronLeft className="h-3 w-3" /> 上一幕
        </button>
        <span className="text-[8px] text-subtle">{playing ? "正在播放" : "可逐幕查看或自动播放"}</span>
        <button type="button" onClick={() => goToScene(sceneIndex + 1)} disabled={sceneIndex === storyboard.scenes.length - 1} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[8px] font-medium text-muted disabled:opacity-30">
          下一幕 <ChevronRight className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}
