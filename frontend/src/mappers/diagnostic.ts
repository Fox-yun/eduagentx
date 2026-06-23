import type {
  DiagnosticQuizDto,
  DiagnosticQuizModel,
  DiagnosticQuestionModel,
} from "../schemas/diagnostic";

export function mapDiagnosticDto(dto: DiagnosticQuizDto): DiagnosticQuizModel {
  return {
    diagnosticId: dto.diagnostic_id,
    goalId: dto.goal_id,
    status: dto.status,
    questions: dto.questions.map(mapDiagnosticQuestion),
    savedAnswers: dto.saved_answers,
    result: dto.result
      ? {
          level: dto.result.level,
          score: dto.result.score,
          strengths: dto.result.strengths,
          weaknesses: dto.result.weaknesses,
          recommendation: dto.result.recommendation,
        }
      : null,
    nextStep: dto.next_step,
  };
}

function mapDiagnosticQuestion(q: DiagnosticQuizDto["questions"][number]): DiagnosticQuestionModel {
  const base: DiagnosticQuestionModel = {
    questionId: q.question_id,
    type: q.type,
    prompt: q.prompt,
    required: q.required ?? true,
    answer: q.answer,
  };

  if (q.type === "single_choice" || q.type === "multiple_choice") {
    base.options = q.options;
  }

  if (q.type === "code_text") {
    base.language = q.language;
    base.codeSnippet = q.code_snippet;
  }

  return base;
}
