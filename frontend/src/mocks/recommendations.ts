import { MockRecommendation } from "../features/recommendations/types";

export const mockRecommendations: MockRecommendation[] = [
  {
    id: "rec-1",
    type: "review",
    title: "复习二叉树递归与非递归遍历",
    reason: "这是下一阶段图算法深度优先搜索 (DFS) 的核心基石，打牢非递归遍历功底能极大降低后续算法理解难度。",
    nodeIds: ["tree-traversal"],
    status: "new"
  },
  {
    id: "rec-2",
    type: "practice",
    title: "完成 BFS 入门练习",
    reason: "通过最基本的层序松弛或队列出入队，加深对广度优先搜寻 (BFS) 层级扩散机制的直观理解。",
    nodeIds: ["bfs"],
    status: "new"
  },
  {
    id: "rec-3",
    type: "resource",
    title: "阅读时间复杂度补充资料",
    reason: "提供堆的构建和排序复杂度在非均衡边界条件下的性能曲线图与数学归纳推导过程。",
    nodeIds: ["complexity"],
    status: "new"
  }
];
