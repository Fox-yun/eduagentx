import { RecommendationDto, mapRecommendation } from "../schemas/recommendations";
import { RecommendationModel } from "../features/recommendations/types";

/** Test-only mock recommendations in DTO format (snake_case) — used by MSW handlers. */
export const mockRecommendationDtos: RecommendationDto[] = [
  {
    id: "rec-1",
    type: "review",
    title: "复习二叉树递归与非递归遍历",
    reason:
      "这是下一阶段图算法深度优先搜索 (DFS) 的核心基石，打牢非递归遍历功底能极大降低后续算法理解难度。",
    node_ids: ["tree-traversal"],
    status: "new",
    resource: null,
    evidence: ["掌握度: 45%", "评估状态: failed"],
    priority: 3,
    confidence: 0.85,
    action: "review_node",
  },
  {
    id: "rec-2",
    type: "practice",
    title: "完成 BFS 入门练习",
    reason:
      "通过最基本的层序松弛或队列出入队，加深对广度优先搜寻 (BFS) 层级扩散机制的直观理解。",
    node_ids: ["bfs"],
    status: "new",
    resource: null,
    evidence: ["难度: beginner", "偏好: quiz"],
    priority: 1,
    confidence: 0.7,
    action: "start_practice",
  },
  {
    id: "rec-3",
    type: "resource",
    title: "阅读时间复杂度补充资料",
    reason:
      "提供堆的构建和排序复杂度在非均衡边界条件下的性能曲线图与数学归纳推导过程。",
    node_ids: ["complexity"],
    status: "new",
    resource: {
      document_id: "doc-1",
      file_name: "complexity.pdf",
      chunk_id: "chunk-1",
      page_number: 12,
      section_title: "时间复杂度分析",
    },
    evidence: ["知识库匹配: 时间复杂度", "文件: complexity.pdf"],
    priority: 1,
    confidence: 0.6,
    action: "read_document",
  },
];

/** Mapped mock recommendations in frontend model format (camelCase) — used by unit tests. */
export const mockRecommendations: RecommendationModel[] =
  mockRecommendationDtos.map(mapRecommendation);
