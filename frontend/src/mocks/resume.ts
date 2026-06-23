export interface StudentStats {
  totalStudyMinutes: number;
  completedNodesCount: number;
  averageMastery: number;
  overallStability: "stable" | "weak" | "unknown";
}

export interface ActivePathSummary {
  id: string;
  title: string;
  courseName: string;
  progressPercent: number;
  lastActiveAt: string;
  currentNodeId: string;
  currentNodeTitle: string;
  completedNodes: number;
  totalNodes: number;
}

export interface ResumeData {
  studentName: string;
  activePath: ActivePathSummary;
  stats: StudentStats;
  recentActivities: Array<{
    id: string;
    nodeId: string;
    nodeTitle: string;
    action: string;
    timestamp: string;
  }>;
}

export const mockResumeData: ResumeData = {
  studentName: "李明",
  activePath: {
    id: "mock-path",
    title: "数据结构与图算法通关路径",
    courseName: "数据结构与算法",
    progressPercent: 25, // 3 completed nodes / 12 total = 25%
    lastActiveAt: "2026-06-23T03:00:00+08:00",
    currentNodeId: "tree-traversal",
    currentNodeTitle: "二叉树的非递归遍历",
    completedNodes: 3,
    totalNodes: 12,
  },
  stats: {
    totalStudyMinutes: 75, // 20 + 25 + 30
    completedNodesCount: 3,
    averageMastery: 95, // (100 + 95 + 90) / 3 = 95
    overallStability: "stable",
  },
  recentActivities: [
    {
      id: "act-1",
      nodeId: "complexity",
      nodeTitle: "时间与空间复杂度分析",
      action: "完成节点学习并达到 90% 掌握度",
      timestamp: "2026-06-22T21:30:00+08:00",
    },
    {
      id: "act-2",
      nodeId: "tree-basic",
      nodeTitle: "树与二叉树基本概念",
      action: "完成节点学习并达到 95% 掌握度",
      timestamp: "2026-06-21T18:15:00+08:00",
    },
    {
      id: "act-3",
      nodeId: "ds-intro",
      nodeTitle: "数据结构基础知识",
      action: "完成节点学习并达到 100% 掌握度",
      timestamp: "2026-06-20T10:00:00+08:00",
    },
  ],
};
