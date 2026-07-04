import {
  UnitContentDto,
  UnitContentModel,
  AssessmentDto,
  AssessmentModel,
  AssessmentSubmitResponseDto,
  AssessmentSubmitResultModel,
  PracticeSetDto,
  PracticeQuestionModel,
  LectureModel,
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
    activeVersionId: dto.active_version_id || null,
    pendingVersionId: dto.pending_version_id || null,
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
    lecture: mapLecture((dto as any).lecture),
    activeLectureTaskId: (dto as any).active_lecture_task_id || null,
  };
}

function mapLecture(lectureData: any): LectureModel | null {
  if (!lectureData) return null;

  // Build combined lecture markdown
  let lectureContent = "";
  if (lectureData.introduction) {
    lectureContent += `${lectureData.introduction}\n\n`;
  }
  if (lectureData.sections?.length > 0) {
    const sortedSections = [...lectureData.sections].sort((a: any, b: any) => a.order - b.order);
    sortedSections.forEach((sec: any) => {
      lectureContent += `# ${sec.title}\n\n${sec.content}\n\n`;
    });
  }
  if (lectureData.key_takeaways?.length > 0) {
    lectureContent += `## 核心要点\n\n`;
    lectureData.key_takeaways.forEach((t: string) => {
      lectureContent += `* ${t}\n`;
    });
    lectureContent += `\n`;
  }
  if (lectureData.common_mistakes?.length > 0) {
    lectureContent += `## 常见误区\n\n`;
    lectureData.common_mistakes.forEach((m: any) => {
      lectureContent += `### ❌ ${m.mistake}\n${m.explanation}\n\n`;
    });
  }
  if (lectureData.summary) {
    lectureContent += `## 总结\n\n${lectureData.summary}\n\n`;
  }

  return {
    introduction: lectureData.introduction || null,
    sections: (lectureData.sections || []).map((s: any) => ({
      sectionId: s.section_id,
      title: s.title,
      content: s.content,
      order: s.order,
    })),
    keyTakeaways: lectureData.key_takeaways || [],
    commonMistakes: (lectureData.common_mistakes || []).map((m: any) => ({
      mistake: m.mistake,
      explanation: m.explanation,
    })),
    summary: lectureData.summary || null,
    content: lectureContent.trim() || null,
  };
}

export function mapAssessment(dto: AssessmentDto): AssessmentModel {
  return {
    assessmentId: dto.assessment_id,
    status: dto.status,
    questions: dto.questions.map((q) => {
      const base: { id: string; type: typeof q.type; text: string; options?: {value: string; label: string}[] } = {
        id: q.question_id,
        type: q.type,
        text: q.prompt,
      };

      if (q.type === "single_choice" || q.type === "multiple_choice") {
        base.options = q.options.map((o) => typeof o === "string" ? {value: o, label: o} : {value: o.value, label: o.label});
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
    activeTaskId: dto.active_task_id || null,
  };
}

export function mapAssessmentGenerationResult(dto: any): AssessmentModel {
  return {
    assessmentId: dto.assessment_id,
    status: dto.status,
    questions: (dto.questions || []).map((q: any) => ({
      id: q.question_id,
      type: q.type,
      text: q.prompt,
      options: q.options
        ? q.options.map((o: any) =>
            typeof o === "string" ? { value: o, label: o } : { value: o.value, label: o.label }
          )
        : undefined,
    })),
    savedAnswers: {},
    score: null,
    mastery: null,
    passed: null,
    weakConcepts: [],
    explanations: {},
    recommendedActions: [],
    activeTaskId: dto.active_task_id || null,
  };
}

export function mapAssessmentSubmitResponse(
  dto: AssessmentSubmitResponseDto
): AssessmentSubmitResultModel {
  return {
    attemptId: dto.attempt_id,
    status: dto.status,
    score: dto.score,
    passed: dto.assessment_passed,
    gradingQuality: dto.grading_quality,
    activeTaskId: dto.active_task_id || null,
    feedback: dto.feedback || null,
    masteryBefore: dto.mastery_before ?? null,
    masteryAfter: dto.mastery_after ?? null,
    nodeCompleted: dto.node_completed ?? null,
    unlockedNodeIds: dto.unlocked_node_ids || [],
  };
}

export function mapPracticeQuestions(dto: PracticeSetDto): PracticeQuestionModel[] {
  return dto.questions.map((q) => ({
    id: q.question_id,
    type: q.type as PracticeQuestionModel["type"],
    text: q.prompt,
    options: q.options
      ? q.options.map((o) => (typeof o === "string" ? {value: o, label: o} : {value: o.value, label: o.label}))
      : undefined,
    correctAnswer: q.correct_answer || null,
  }));
}
