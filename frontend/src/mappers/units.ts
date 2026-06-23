import {
  UnitContentDto,
  UnitContentModel,
  AssessmentDto,
  AssessmentModel,
  AssessmentSubmitResponseDto,
  AssessmentSubmitResultModel,
} from "../schemas/units";

export function mapUnitContent(dto: UnitContentDto): UnitContentModel {
  // If status is not ready or failed, some fields might be null/missing in raw responses
  const introduction = dto.introduction || null;
  const objectives = dto.objectives || [];
  const sections = dto.sections || [];
  const practiceTasks = dto.practice_tasks || [];
  const summary = dto.summary || null;
  const references = dto.references || [];

  // Generate markdown content
  let content = "";
  if (introduction) {
    content += `${introduction}\n\n`;
  }
  if (objectives.length > 0) {
    content += `## 学习目标\n\n`;
    objectives.forEach((obj: string) => {
      content += `* ${obj}\n`;
    });
    content += `\n`;
  }
  if (sections.length > 0) {
    const sortedSections = [...sections].sort((a, b) => a.order - b.order);
    sortedSections.forEach((sec) => {
      content += `# ${sec.title}\n\n${sec.content}\n\n`;
    });
  }
  if (practiceTasks.length > 0) {
    content += `## 实践任务\n\n`;
    practiceTasks.forEach((pt) => {
      content += `### ${pt.title} (${pt.difficulty})\n${pt.description}\n\n`;
    });
  }
  if (summary) {
    content += `## 总结\n\n${summary}\n\n`;
  }
  if (references.length > 0) {
    content += `## 参考资料\n\n`;
    references.forEach((ref) => {
      if (ref.url) {
        content += `* [${ref.title}](${ref.url}) (${ref.type})\n`;
      } else {
        content += `* ${ref.title} (${ref.type})\n`;
      }
    });
  }

  return {
    unitId: dto.unit_id,
    pathId: dto.path_id,
    pathVersion: dto.path_version,
    nodeId: dto.node_id,
    contentVersion: dto.content_version,
    status: dto.status,
    activeTaskId: dto.active_task_id || null,
    introduction,
    objectives,
    sections: sections.map((s: any) => ({
      sectionId: s.section_id,
      title: s.title,
      content: s.content,
      order: s.order,
    })),
    practiceTasks: practiceTasks.map((t: any) => ({
      taskId: t.task_id,
      title: t.title,
      description: t.description,
      difficulty: t.difficulty,
    })),
    summary,
    references: references.map((r: any) => ({
      title: r.title,
      url: r.url || null,
      type: r.type,
    })),
    content: content.trim() || null,
    error: dto.error || null,
  };
}

export function mapAssessment(dto: AssessmentDto): AssessmentModel {
  return {
    assessmentId: dto.assessment_id,
    pathId: dto.path_id,
    pathVersion: dto.path_version,
    nodeId: dto.node_id,
    status: dto.status,
    questions: dto.questions.map((q) => {
      const base: { id: string; type: typeof q.type; text: string; options?: string[]; language?: string; codeSnippet?: string } = {
        id: q.question_id,
        type: q.type,
        text: q.prompt,
      };

      if (q.type === "single_choice" || q.type === "multiple_choice") {
        base.options = q.options.map((o) => typeof o === "string" ? o : o.value);
      }

      if (q.type === "code_text") {
        base.language = q.language;
        base.codeSnippet = q.code_snippet;
      }

      return base;
    }),
    savedAnswers: dto.saved_answers || {},
    score: dto.score,
    mastery: dto.mastery,
    passed: dto.passed,
    weakConcepts: dto.weak_concepts || [],
    explanations: dto.explanations || {},
    recommendedActions: dto.recommended_actions || [],
  };
}

export function mapAssessmentSubmitResponse(
  dto: AssessmentSubmitResponseDto
): AssessmentSubmitResultModel {
  return {
    score: dto.score,
    passed: dto.passed,
    feedback: dto.feedback || null,
    masteryDelta: dto.mastery_delta || null,
  };
}
