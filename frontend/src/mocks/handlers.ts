import { http, HttpResponse } from "msw";
import { db, MockGoal, MockPath, MockTask, MockDocument, mockNowIso, trackTimeout } from "./statefulDb";

import { z } from "zod";

export const handlers = [
  // E2E Mock DB Reset endpoint
  http.post("/api/__mock__/reset", ({ request }) => {
    const url = new URL(request.url);
    const MockScenarioSchema = z.enum([
      "guest",
      "active-user",
      "locked-user",
      "disabled-user",
    ]);

    const parsed = MockScenarioSchema.safeParse(
      url.searchParams.get("scenario") ?? "guest"
    );

    if (!parsed.success) {
      return HttpResponse.json(
        {
          error: {
            code: "INVALID_MOCK_SCENARIO",
            message: "Invalid mock scenario",
            request_id: null,
          },
        },
        {
          status: 400,
        }
      );
    }

    const scenario = parsed.data;

    if (scenario === "guest") {
      db.reset({ authenticated: false, seedDemoData: false, scenario: "guest" });
    } else if (scenario === "locked-user") {
      db.reset({ authenticated: false, seedDemoData: true, scenario: "locked-user" });
      db.sessionUserId = "user-locked";
    } else if (scenario === "disabled-user") {
      db.reset({ authenticated: false, seedDemoData: true, scenario: "disabled-user" });
      db.sessionUserId = "user-disabled";
    } else {
      db.reset({ authenticated: true, seedDemoData: true, scenario: "active-user" });
    }

    return HttpResponse.json({
      scenario: db.scenario,
      reset_at: mockNowIso(),
    });
  }),

  // 1. GET /api/auth/me
  http.get("/api/auth/me", () => {
    if (!db.sessionUserId) {
      return HttpResponse.json(
        {
          error: {
            code: "UNAUTHORIZED",
            message: "未登录",
            details: null,
            request_id: null,
          },
        },
        { status: 401 }
      );
    }
    const user = db.users.get(db.sessionUserId);
    if (!user) {
      return HttpResponse.json(
        {
          error: {
            code: "UNAUTHORIZED",
            message: "会话失效",
            details: null,
            request_id: null,
          },
        },
        { status: 401 }
      );
    }
    return HttpResponse.json(user);
  }),

  // 2. POST /api/auth/login
  http.post("/api/auth/login", async ({ request }) => {
    const body = (await request.json()) as any;
    if (!body.email || !body.password) {
      return HttpResponse.json(
        {
          error: {
            code: "BAD_REQUEST",
            message: "邮箱或密码不能为空",
            details: null,
            request_id: null,
          },
        },
        { status: 400 }
      );
    }
    if (body.password === "wrong-password") {
      return HttpResponse.json(
        {
          error: {
            code: "UNAUTHORIZED",
            message: "密码错误",
            details: null,
            request_id: null,
          },
        },
        { status: 401 }
      );
    }

    // Look for matching user or create new active one
    let targetUser: any = null;
    for (const u of db.users.values()) {
      if (u.email === body.email) {
        targetUser = u;
        break;
      }
    }

    if (!targetUser) {
      targetUser = {
        user_id: `user-${Math.random().toString(36).substr(2, 9)}`,
        display_name: body.email.split("@")[0],
        email: body.email,
        email_verified: true,
        onboarding_completed: true,
        status: "active",
        avatar_url: null,
        timezone: "Asia/Shanghai",
      };
      db.users.set(targetUser.user_id, targetUser);
    }

    db.sessionUserId = targetUser.user_id;
    return HttpResponse.json(targetUser);
  }),

  // 3. POST /api/auth/register
  http.post("/api/auth/register", async ({ request }) => {
    const body = (await request.json()) as any;
    const newUserId = `user-${Math.random().toString(36).substr(2, 9)}`;
    
    // Simulate user creation in pending_verification status
    const newUser = {
      user_id: newUserId,
      display_name: body.display_name || "新用户",
      email: body.email,
      email_verified: false,
      onboarding_completed: false,
      status: "pending_verification" as const,
    };
    db.users.set(newUserId, newUser);
    db.sessionUserId = newUserId;

    return HttpResponse.json({
      next_step: "verify_email",
      user: newUser,
    });
  }),

  // 4. POST /api/auth/verify-email
  http.post("/api/auth/verify-email", async ({ request }) => {
     const body = (await request.json()) as any;
     if (body.token === "invalid-token") {
       return HttpResponse.json(
         {
           error: {
             code: "INVALID_TOKEN",
             message: "验证链接无效或已过期",
             details: null,
             request_id: null,
           },
         },
         { status: 400 }
       );
     }

     if (!db.sessionUserId) {
       return HttpResponse.json(
         {
           error: {
             code: "UNAUTHORIZED",
             message: "未登录",
             details: null,
             request_id: null,
           },
         },
         { status: 401 }
       );
     }

     const user = db.users.get(db.sessionUserId);
     if (user) {
       user.email_verified = true;
       user.status = "active";
       db.users.set(user.user_id, user);
       return HttpResponse.json(user);
     }

     return HttpResponse.json(
       {
         error: {
           code: "NOT_FOUND",
           message: "用户未找到",
           details: null,
           request_id: null,
         },
       },
       { status: 404 }
     );
   }),

   // 5. POST /api/users/me/onboarding
   http.post("/api/users/me/onboarding", async ({ request }) => {
     const body = (await request.json()) as any;
     if (!db.sessionUserId) {
       return HttpResponse.json(
         {
           error: {
             code: "UNAUTHORIZED",
             message: "未登录",
             details: null,
             request_id: null,
           },
         },
         { status: 401 }
       );
     }

    const user = db.users.get(db.sessionUserId);
    if (user) {
      user.onboarding_completed = true;
      user.preferences = body.preferences || [];
      user.use_diagnostic = body.use_diagnostic ?? true;
      user.use_knowledge_base = body.use_knowledge_base ?? false;
      db.users.set(user.user_id, user);
      return HttpResponse.json(user);
    }

    return new HttpResponse(null, { status: 404 });
  }),

  // 6. POST /api/auth/logout
  http.post("/api/auth/logout", () => {
    db.sessionUserId = null;
    return new HttpResponse(null, { status: 204 });
  }),

  // 7. POST /api/auth/refresh
  http.post("/api/auth/refresh", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // 8. GET /api/learning/resume
  http.get("/api/learning/resume", () => {
    if (!db.sessionUserId) {
      return HttpResponse.json(
        {
          error: {
            code: "UNAUTHORIZED",
            message: "未登录",
            details: null,
            request_id: null,
          },
        },
        { status: 401 }
      );
    }

    const userGoals = Array.from(db.goals.values());
    if (userGoals.length === 0) {
      return HttpResponse.json({ type: "empty" });
    }

    const goal = userGoals[userGoals.length - 1];

    if (goal.status === "clarifying") {
      return HttpResponse.json({
        type: "generating",
        goal_id: goal.goal_id,
        task_id: goal.active_task_id || "task-clarify",
        goal_title: goal.raw_goal,
        progress: 10,
        stage: "目标澄清",
        message: "智能体正在澄清细节问题...",
      });
    }

    if (goal.status === "planning" || goal.status === "analyzing" || goal.status === "diagnosing") {
      return HttpResponse.json({
        type: "generating",
        goal_id: goal.goal_id,
        task_id: goal.active_task_id || "task-gen",
        goal_title: goal.raw_goal,
        progress: 45,
        stage: "正在规划图谱阶段",
        message: "正在梳理知识节点连线...",
      });
    }

    const userPaths = Array.from(db.paths.values());
    if (userPaths.length > 0) {
      const path = userPaths[userPaths.length - 1];
      if (path.status === "draft") {
        return HttpResponse.json({
          type: "review",
          goal_id: goal.goal_id,
          path_id: path.path_id,
          path_title: path.title,
          version: path.version,
          total_nodes: path.nodes.length,
          estimated_minutes: path.total_estimated_minutes,
        });
      } else if (path.status === "active") {
        const currentNode = path.nodes.find((n) => n.status === "current" || n.status === "available") || path.nodes[0];
        const completedCount = path.nodes.filter((n) => n.status === "completed").length;
        const progressVal = Math.round((completedCount / path.nodes.length) * 100);

        // Check if all nodes are completed → return completed resume
        if (completedCount === path.nodes.length) {
          const avgMastery = path.nodes.reduce((sum, n) => sum + n.mastery, 0) / path.nodes.length;
          return HttpResponse.json({
            type: "completed",
            path_id: path.path_id,
            path_title: path.title,
            completed_nodes: completedCount,
            total_nodes: path.nodes.length,
            completed_at: new Date().toISOString(),
            mastery: Math.round(avgMastery),
          });
        }

        return HttpResponse.json({
          type: "active",
          path_id: path.path_id,
          path_title: path.title,
          current_node_id: currentNode?.node_id || "node-1",
          current_node_title: currentNode?.title || "未开始",
          completed_nodes: completedCount,
          total_nodes: path.nodes.length,
          progress: progressVal,
          last_active_at: new Date().toISOString(),
        });
      } else if (path.status === "completed") {
        const completedCount = path.nodes.filter((n) => n.status === "completed").length;
        const avgMastery = path.nodes.length > 0
          ? path.nodes.reduce((sum, n) => sum + n.mastery, 0) / path.nodes.length
          : 0;
        return HttpResponse.json({
          type: "completed",
          path_id: path.path_id,
          path_title: path.title,
          completed_nodes: completedCount,
          total_nodes: path.nodes.length,
          completed_at: path.updated_at,
          mastery: Math.round(avgMastery),
        });
      }
    }

    return HttpResponse.json({ type: "empty" });
  }),

  // 9. POST /api/learning-goals
  http.post("/api/learning-goals", async ({ request }) => {
    const body = (await request.json()) as any;
    const goalId = `goal-${Math.random().toString(36).substr(2, 9)}`;

    const newGoal: MockGoal = {
      goal_id: goalId,
      raw_goal: body.raw_goal,
      normalized_goal: body.raw_goal,
      current_level: body.current_level || "beginner",
      target_level: body.target_level || "advanced",
      duration_weeks: body.duration_weeks || 4,
      weekly_hours: body.weekly_hours || 10,
      preferences: body.preferences || [],
      use_diagnostic: body.use_diagnostic ?? true,
      use_knowledge_base: body.use_knowledge_base ?? false,
      status: "clarifying",
      next_step: "clarify",
      active_task_id: `task-gen-${goalId}`,
      created_at: mockNowIso(),
      updated_at: mockNowIso(),
    };
    db.goals.set(goalId, newGoal);

    // Seed mock clarification
    db.clarifications.set(goalId, {
      questions: [
        {
          question_id: "q-clarify-1",
          type: "single_choice",
          prompt: "您首选的练习和代码演示语言是？",
          required: true,
          options: [{ value: "Python", label: "Python" }, { value: "Java", label: "Java" }],
          answer: null,
        },
      ],
      answers_history: {},
    });

    // Seed mock diagnostic
    db.diagnostics.set(goalId, {
      diagnostic_id: `diag-${goalId}`,
      goal_id: goalId,
      status: "pending",
      questions: [
        {
          question_id: "q-diag-1",
          type: "single_choice",
          prompt: "在完全二叉树中，若叶子节点数为 10，则树中度为 2 的节点数是？",
          options: [
            { value: "9", label: "9 个" },
            { value: "10", label: "10 个" },
            { value: "11", label: "11 个" },
          ],
          answer: null,
        },
      ],
      saved_answers: {},
      result: null,
      next_step: "generating",
    });

    // Create background path generator task
    const mockTask: MockTask = {
      task_id: `task-gen-${goalId}`,
      type: "learning_path_generation",
      title: "规划您的学习路径",
      status: "pending",
      progress: 0,
      current_stage: "分析学习目标",
      message: "启动规划引擎...",
      result: null,
      error: null,
      request_id: null,
      created_at: mockNowIso(),
      updated_at: mockNowIso(),
      target: { type: "path_generation", goalId: goalId },
    };
    db.tasks.set(mockTask.task_id, mockTask);

    return HttpResponse.json({
      goal_id: goalId,
      next_step: newGoal.next_step,
      active_task_id: newGoal.active_task_id,
    });
  }),

  // 10. GET /api/learning-goals/:goalId
  http.get("/api/learning-goals/:goalId", ({ params }) => {
    const goal = db.goals.get(params.goalId as string);
    if (!goal) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(goal);
  }),

  // 11. GET/POST clarifications
  http.get("/api/learning-goals/:goalId/clarifications", ({ params }) => {
    const clarify = db.clarifications.get(params.goalId as string);
    if (!clarify) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(clarify);
  }),

  http.post("/api/learning-goals/:goalId/clarifications", async ({ params, request }) => {
    const goalId = params.goalId as string;
    await request.json();
    
    const goal = db.goals.get(goalId);
    if (goal) {
      goal.status = goal.use_diagnostic ? "diagnosing" : "planning";
      goal.next_step = goal.use_diagnostic ? "diagnostic" : "generating";
      db.goals.set(goalId, goal);
      return HttpResponse.json({
        next_step: goal.next_step,
        active_task_id: goal.active_task_id,
      });
    }
    return new HttpResponse(null, { status: 404 });
  }),

  // 12. GET/POST diagnostics
  http.get("/api/learning-goals/:goalId/diagnostic", ({ params }) => {
    const diag = db.diagnostics.get(params.goalId as string);
    if (!diag) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(diag);
  }),

  http.post("/api/learning-goals/:goalId/diagnostic/submit", async ({ params }) => {
    const goalId = params.goalId as string;
    const goal = db.goals.get(goalId);
    if (goal) {
      goal.status = "planning";
      goal.next_step = "generating";
      db.goals.set(goalId, goal);

      // Trigger the mock task generation run
      const task = db.tasks.get(goal.active_task_id || "");
      if (task) {
        task.status = "running";
        task.progress = 15;
        db.tasks.set(task.task_id, task);
      }

      return HttpResponse.json({
        next_step: "generating",
        active_task_id: goal.active_task_id || `task-gen-${goalId}`,
      });
    }
    return new HttpResponse(null, { status: 404 });
  }),

  // 13. GET /api/tasks/:taskId (Real-time simulation)
  http.get("/api/tasks/:taskId", ({ params }) => {
    const taskId = params.taskId as string;
    const task = db.tasks.get(taskId);
    if (!task) return new HttpResponse(null, { status: 404 });

    // Auto-advance task progress for E2E flow
    if (task.status === "pending") {
      task.status = "running";
      task.progress = 10;
      task.current_stage = "分析知识体系";
      task.message = "已完成前置诊断分析，正在提取核心节点...";
      task.updated_at = mockNowIso();
    } else if (task.status === "running") {
      task.progress += 40;
      if (task.progress >= 100) {
        task.progress = 100;
        task.status = "completed";
        task.current_stage = "生成完成";
        task.message = "AI 规划学习路径设计完成！";
        task.updated_at = mockNowIso();

        if (task.target?.type === "unit_generation") {
          const { pathId, nodeId } = task.target;
          const path = db.paths.get(pathId);
          if (path) {
            const node = path.nodes.find(n => n.node_id === nodeId);
            if (node) {
              node.content_status = "ready";
            }
          }
          // Seed the unit content
          db.units.set(`${pathId}-${nodeId}`, {
            unit_id: `unit-${nodeId}`,
            path_id: pathId,
            path_version: 1,
            node_id: nodeId,
            content_version: 1,
            status: "ready",
            active_task_id: null,
            introduction: "本单元讲解 DFS 递归模型及栈结构性质。",
            objectives: ["学会手写递归", "理解树的前序中序后序关系"],
            sections: [
              {
                section_id: "sec-1",
                title: "1. 树深度遍历原理",
                content: "DFS 使用栈结构或者系统递归函数调用栈进行前序扩展。我们依次访问当前节点，然后再递归调用左右子树。",
                order: 1,
              }
            ],
            practice_tasks: [
              {
                task_id: "practice-1",
                title: "写出DFS中序递归伪代码",
                description: "在纸上手写左子树-根节点-右子树逻辑。",
                difficulty: "beginner",
              }
            ],
            summary: "树的DFS遍历是算法可视化的核心课程。",
            references: [
              { title: "算法导论", url: null, type: "book" }
            ],
            error: null,
          });
          task.result = {
            path_id: pathId,
            node_id: nodeId,
            unit_id: `unit-${nodeId}`,
          };
        } else if (task.target?.type === "path_generation") {
          const { goalId } = task.target;
          const goal = db.goals.get(goalId);
          if (goal) {
            goal.status = "ready";
            goal.next_step = "review";
            db.goals.set(goalId, goal);
          }

          const pathId = `path-${goalId}`;
          const newPath: MockPath = {
            path_id: pathId,
            goal_id: goalId,
            title: `量身定制的 ${goal?.raw_goal || "二叉树"} 规划路径`,
            description: "个性化定制大纲拓扑图",
            version: 1,
            active_version: 0,
            status: "draft",
            current_node_id: "node-e2e-1",
            total_estimated_minutes: 90,
            generation_summary: "提取出2个关键知识节点：1. 理论基础，2. 可视化组件。",
            stages: [
              {
                stage_id: "stage-e2e",
                title: "第一阶段：树结构及核心遍历",
                description: "算法与工程基础",
                stage_order: 1,
                outcome: "掌握 DFS 遍历原理",
                node_ids: ["node-e2e-1", "node-e2e-2"],
              }
            ],
            nodes: [
              {
                node_id: "node-e2e-1",
                stage_id: "stage-e2e",
                title: "二叉树 DFS 基础遍历",
                description: "理解前中后序遍历模板。",
                node_order: 1,
                level: 1,
                difficulty: "beginner",
                estimated_minutes: 40,
                status: "available",
                mastery: 0,
                content_status: "not_generated",
                learning_outcomes: ["DFS 模板书写"],
                assessment_strategy: "选择题测试",
                generation_reason: "先修内容点",
                prerequisite_ids: [],
                next_node_ids: ["node-e2e-2"],
              },
              {
                node_id: "node-e2e-2",
                stage_id: "stage-e2e",
                title: "React SVG 树图绘制",
                description: "绘制二叉树拓扑连线结构。",
                node_order: 2,
                level: 2,
                difficulty: "intermediate",
                estimated_minutes: 50,
                status: "locked",
                mastery: 0,
                content_status: "not_generated",
                learning_outcomes: ["完成树连线"],
                assessment_strategy: "实操设计评审",
                generation_reason: "第二阶段渲染",
                prerequisite_ids: ["node-e2e-1"],
                next_node_ids: [],
              }
            ],
            edges: [
              {
                edge_id: "edge-e2e-1",
                source_node_id: "node-e2e-1",
                target_node_id: "node-e2e-2",
              }
            ],
            created_at: mockNowIso(),
            updated_at: mockNowIso(),
          };
          db.paths.set(pathId, newPath);
          task.result = {
            path_id: pathId,
            version: 1,
          };
        }
      } else {
        task.current_stage = "生成树拓扑连线";
        task.message = "计算节点层级连线中...";
        task.updated_at = mockNowIso();
      }
    }
    
    db.tasks.set(taskId, task);
    return HttpResponse.json(task);
  }),

  // 14. GET learning-paths & activate
  http.get("/api/learning-paths/:pathId", ({ params }) => {
    const path = db.paths.get(params.pathId as string);
    if (!path) {
      return HttpResponse.json(
        {
          error: {
            code: "NOT_FOUND",
            message: "Path not found",
            details: null,
            request_id: null,
          },
        },
        { status: 404 }
      );
    }
    return HttpResponse.json(path);
  }),

  http.post("/api/learning-paths/:pathId/activate", ({ params }) => {
    const pathId = params.pathId as string;
    const path = db.paths.get(pathId);
    if (path) {
      path.status = "active";
      path.active_version = 1;
      db.paths.set(pathId, path);
      
      const goal = db.goals.get(path.goal_id);
      if (goal) {
        goal.status = "active";
        db.goals.set(path.goal_id, goal);
      }
      return HttpResponse.json(path);
    }
    return HttpResponse.json(
      {
        error: {
          code: "NOT_FOUND",
          message: "Path not found",
          details: null,
          request_id: null,
        },
      },
      { status: 404 }
    );
  }),

  // 15. Unit contents GET/POST
  http.get("/api/learning-paths/:pathId/nodes/:nodeId/content", ({ params }) => {
    const pathId = params.pathId as string;
    const nodeId = params.nodeId as string;
    const key = `${pathId}-${nodeId}`;

    const path = db.paths.get(pathId);
    const node = path?.nodes.find(n => n.node_id === nodeId);
    
    if (!path || !node) {
      return HttpResponse.json(
        {
          error: {
            code: "NOT_FOUND",
            message: "Path or node not found",
            details: null,
            request_id: null,
          },
        },
        { status: 404 }
      );
    }

    const unit = db.units.get(key);
    if (unit) {
      return HttpResponse.json(unit);
    }

    // Default response for not_generated/generating node
    if (node.content_status === "generating") {
      return HttpResponse.json({
        unit_id: `unit-${nodeId}`,
        path_id: pathId,
        path_version: 1,
        node_id: nodeId,
        content_version: 1,
        status: "generating",
        active_task_id: `task-unit-${pathId}-${nodeId}`,
        introduction: null,
        objectives: [],
        sections: [],
        practice_tasks: [],
        summary: null,
        references: [],
        error: null,
      });
    }

    return HttpResponse.json(
      {
        error: {
          code: "NOT_FOUND",
          message: "Content not generated yet",
          details: null,
          request_id: null,
        },
      },
      { status: 404 }
    );
  }),

  http.post("/api/learning-paths/:pathId/nodes/:nodeId/content", ({ params }) => {
    const pathId = params.pathId as string;
    const nodeId = params.nodeId as string;
    const path = db.paths.get(pathId);
    
    if (path) {
      const node = path.nodes.find(n => n.node_id === nodeId);
      if (node) {
        node.content_status = "generating";
      }
    }

    // Register active content task
    const taskId = `task-unit-${pathId}-${nodeId}`;
    const mockTask: MockTask = {
      task_id: taskId,
      type: "learning_unit_generation",
      title: "生成知识单元内容",
      status: "pending",
      progress: 0,
      current_stage: "准备章节大纲",
      message: "初始化单元生成引擎...",
      result: null,
      error: null,
      request_id: null,
      created_at: mockNowIso(),
      updated_at: mockNowIso(),
      target: { type: "unit_generation", pathId: pathId, nodeId: nodeId },
    };
    db.tasks.set(taskId, mockTask);

    return HttpResponse.json({
      next_step: "generating",
      active_task_id: taskId,
    });
  }),

  // 16. Assessment POST creation & submit
  http.post("/api/learning-paths/:pathId/nodes/:nodeId/assessments", ({ params }) => {
    const pathId = params.pathId as string;
    const nodeId = params.nodeId as string;
    const assId = `ass-${pathId}-${nodeId}`;

    const defaultAssessment = {
      assessment_id: assId,
      path_id: pathId,
      path_version: 1,
      node_id: nodeId,
      status: "pending" as const,
      questions: [
        {
          question_id: "ass-q-1",
          type: "single_choice" as const,
          prompt: "在前序二叉树遍历中，根节点是第几个被访问的？",
          options: [
            { value: "first", label: "第一个" },
            { value: "second", label: "第二个" },
            { value: "last", label: "最后一个" }
          ],
        }
      ],
      saved_answers: {},
      score: null,
      mastery: null,
      passed: null,
      weak_concepts: [],
      explanations: { "ass-q-1": "前序遍历中根节点优先访问" },
      recommended_actions: [],
    };
    db.assessments.set(assId, defaultAssessment);
    return HttpResponse.json(defaultAssessment);
  }),

  http.post("/api/assessments/:assessmentId/submit", async ({ params, request }) => {
    const assId = params.assessmentId as string;
    const body = (await request.json()) as any;
    const assessment = db.assessments.get(assId);

    if (assessment) {
      assessment.status = "submitted";
      assessment.saved_answers = body.answers;
      assessment.score = 100;
      assessment.passed = true;
      assessment.mastery = 95;
      assessment.weak_concepts = [];
      assessment.recommended_actions = ["继续学习下一章节"];
      db.assessments.set(assId, assessment);

      // Unlock next node in the path!
      const path = db.paths.get(assessment.path_id);
      if (path) {
        const currentNode = path.nodes.find((n) => n.node_id === assessment.node_id);
        if (currentNode) {
          currentNode.status = "completed";
          currentNode.mastery = 95;
        }

        // Find next locked node and set to available/current
        const nextNode = path.nodes.find((n) => n.status === "locked" || n.status === "available");
        if (nextNode) {
          nextNode.status = "current";
        }
        db.paths.set(assessment.path_id, path);
      }

      return HttpResponse.json({
        score: 100,
        passed: true,
        feedback: "非常好！您已完全掌握该节点的核心内容，后继学习章节已成功解锁。",
        mastery_delta: 25,
      });
    }
    return HttpResponse.json(
      {
        error: {
          code: "NOT_FOUND",
          message: "Assessment not found",
          details: null,
          request_id: null,
        },
      },
      { status: 404 }
    );
  }),

  // 17. Knowledge Documents API endpoints
  http.get("/api/knowledge/documents", () => {
    return HttpResponse.json({
      items: Array.from(db.documents.values()),
      next_cursor: null,
      total: db.documents.size,
    });
  }),

  http.post("/api/knowledge/documents", async ({ request }) => {
    // Parse file upload
    const formData = await request.formData();
    const file = formData.get("file") as File;
    const docId = `doc-${Math.random().toString(36).substr(2, 9)}`;

    const newDoc: MockDocument = {
      document_id: docId,
      display_name: file ? file.name : "未知文档.txt",
      scope: "course",
      course_id: null,
      mime_type: file ? file.type : "text/plain",
      size_bytes: file ? file.size : 1024,
      status: "pending",
      operation_status: "indexing",
      index_task_id: null,
      error: null,
      created_at: mockNowIso(),
      updated_at: mockNowIso(),
    };
    db.documents.set(docId, newDoc);

    // Simulate indexing completing immediately for testing ease
    trackTimeout(
      setTimeout(() => {
        const d = db.documents.get(docId);
        if (d) {
          d.status = "indexed";
          db.documents.set(docId, d);
        }
      }, 2000)
    );

    return HttpResponse.json(newDoc);
  }),

  http.delete("/api/knowledge/documents/:documentId", ({ params }) => {
    const docId = params.documentId as string;
    db.documents.delete(docId);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post("/api/knowledge/documents/:documentId/reindex", ({ params }) => {
    const docId = params.documentId as string;
    const doc = db.documents.get(docId);
    if (doc) {
      doc.status = "pending";
      db.documents.set(docId, doc);
      trackTimeout(
        setTimeout(() => {
          doc.status = "indexed";
          db.documents.set(docId, doc);
        }, 1500)
      );
      return HttpResponse.json(doc);
    }
    return HttpResponse.json(
      {
        error: {
          code: "NOT_FOUND",
          message: "Document not found",
          details: null,
          request_id: null,
        },
      },
      { status: 404 }
    );
  }),

  // RAG Search Endpoint
  http.get("/api/knowledge/search", ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get("q") || "";
    
    // Stub result
    const results = [
      {
        id: "search-chunk-1",
        file_name: "React 性能调优指南.md",
        text: `针对包含 '${query}' 的概念：深度优先搜索 (DFS) 和 Canvas 可视化在 React 中由于高频绘制容易引发渲染卡顿。我们可以配合 useMemo 和 useCallback 对渲染节点和计算坐标的过程进行缓存，并在 Canvas 绘制中采用双缓冲技术。`,
        score: 0.92,
      }
    ];
    return HttpResponse.json(results);
  }),
];
