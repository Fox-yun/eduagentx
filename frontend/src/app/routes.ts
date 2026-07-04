export const appRoutes = {
  home: () => "/",
  login: () => "/auth/login",
  onboarding: () => "/onboarding",
  goalCreate: () => "/goals/new",
  goalClarify: (goalId: string) => `/goals/${goalId}/clarify`,
  goalDiagnostic: (goalId: string) => `/goals/${goalId}/diagnostic`,
  goalGenerating: (goalId: string) => `/goals/${goalId}/generating`,
  pathReview: (pathId: string) => `/learning-paths/${pathId}/review`,
  learningPath: (pathId: string) => `/learning-paths/${pathId}`,
  learningUnit: (pathId: string, nodeId: string) => `/learning-paths/${pathId}/nodes/${nodeId}`,
  assessment: (pathId: string, nodeId: string) => `/learning-paths/${pathId}/nodes/${nodeId}/assessment`,
  profileConversation: () => "/profile/conversation",
  profileConversationSession: (sessionId: string) => `/profile/conversation/${sessionId}`,
  profileSummary: () => "/profile",
};

export const routes = {
  learningPath: appRoutes.learningPath,
  learningNode: appRoutes.learningUnit,
};

