import React from "react";
import { describe, it, expect } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./renderWithProviders";
import { KnowledgePanel } from "../features/knowledge/KnowledgePanel";
import { TasksPanel } from "../features/tasks/TasksPanel";

describe("Knowledge & Tasks Panels", () => {
  it("should render KnowledgePanel with list and perform search", async () => {
    renderWithProviders(<KnowledgePanel />);

    // Check loading index documents
    expect(await screen.findByText("React-Design-Patterns.pdf")).toBeInTheDocument();
    expect(screen.getByText("Zustand-State-Management.md")).toBeInTheDocument();

    // Trigger search
    const searchInput = screen.getByPlaceholderText("搜索知识库文档内容...");
    fireEvent.change(searchInput, { target: { value: "react patterns" } });

    const searchBtn = screen.getByRole("button", { name: "检索" });
    fireEvent.click(searchBtn);

    // Verify search results display
    expect(await screen.findByText(/React 中的高阶组件与 Render Props/)).toBeInTheDocument();
    expect(screen.getByText("相似度 92%")).toBeInTheDocument();

    // Clear search
    const backBtn = screen.getByText("返回文档列表");
    fireEvent.click(backBtn);

    // Verify it returned to standard document lists
    expect(await screen.findByText("React-Design-Patterns.pdf")).toBeInTheDocument();
  });

  it("should trigger upload and delete in KnowledgePanel", async () => {
    renderWithProviders(<KnowledgePanel />);

    // Verify document list exists
    expect(await screen.findByText("React-Design-Patterns.pdf")).toBeInTheDocument();

    // Trigger upload (using mock input file selection)
    const file = new File(["dummy content"], "Uploaded-Document.pdf", { type: "application/pdf" });
    screen.getByText("点击选择或拖拽文件上传");
    // We select the hidden input to trigger the change
    // Wait, the input has type file and is hidden:
    const fileInputs = document.querySelectorAll("input[type='file']");
    expect(fileInputs.length).toBe(1);
    
    fireEvent.change(fileInputs[0], { target: { files: [file] } });

    // Expect upload success toast
    expect(await screen.findByText("文件上传成功，开始解析索引")).toBeInTheDocument();

    // Trigger delete document
    const trashButtons = screen.getAllByTitle("删除文件");
    expect(trashButtons.length).toBeGreaterThan(0);
    
    fireEvent.click(trashButtons[0]);
    expect(await screen.findByText("文件已成功移除")).toBeInTheDocument();
  });

  it("should render TasksPanel and monitor active tasks progress", async () => {
    renderWithProviders(<TasksPanel />);

    // Verify mock tasks are rendered
    expect(await screen.findByText("生成学习路径：React 高级模式")).toBeInTheDocument();
    expect(screen.getByText("知识库切片提取")).toBeInTheDocument();

    // Verify progress bar representation
    expect(screen.getByText("45%")).toBeInTheDocument();
    expect(screen.getByText("正在根据大纲生成节点与连线...")).toBeInTheDocument();
    expect(screen.getByText("智能体协作轨迹")).toBeInTheDocument();
    expect(screen.getByText("路径规划智能体")).toBeInTheDocument();
    expect(screen.getByText("正在生成节点与依赖关系。")).toBeInTheDocument();

    // Cancel task
    const cancelBtn = screen.getByRole("button", { name: "取消任务" });
    fireEvent.click(cancelBtn);

    // Verify cancellation toast feedback
    expect(await screen.findByText("任务已请求取消")).toBeInTheDocument();
  });
});
