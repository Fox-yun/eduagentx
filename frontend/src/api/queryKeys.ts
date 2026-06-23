export interface KnowledgeFilters {
  search?: string;
  tag?: string;
  status?: string;
}

export const queryKeys = {
  auth: {
    me: () => ["auth", "me"] as const,
    sessions: () => ["auth", "sessions"] as const,
  },

  resume: () => ["learning", "resume"] as const,

  goal: (goalId: string) => ["learning-goal", goalId] as const,

  diagnostic: (goalId: string) => ["diagnostic", goalId] as const,

  path: (pathId: string, version?: number) =>
    ["learning-path", pathId, version ?? "active"] as const,

  pathVersions: (pathId: string) => ["learning-path", pathId, "versions"] as const,

  node: (pathId: string, nodeId: string) => ["learning-node", pathId, nodeId] as const,

  unit: (pathId: string, nodeId: string) => ["learning-unit", pathId, nodeId] as const,

  assessment: (pathId: string, nodeId: string) => ["assessment", pathId, nodeId] as const,

  recommendations: (pathId: string) => ["recommendations", pathId] as const,

  tasks: () => ["tasks"] as const,

  knowledgeDocuments: (filters: KnowledgeFilters) =>
    ["knowledge-documents", filters] as const,
};
