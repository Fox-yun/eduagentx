import React, { useState, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Search, UploadCloud, FileText, Trash2, Loader2, Sparkles, RefreshCw, X, AlertCircle } from "lucide-react";
import { getKnowledgeFiles, uploadKnowledgeFile, deleteKnowledgeFile, searchKnowledge } from "../../api/knowledge";
import { queryKeys } from "../../api/queryKeys";
import { useToast } from "../../components/feedback/Toast";

export function KnowledgePanel() {
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [searchVal, setSearchVal] = useState("");
  const [activeSearchQuery, setActiveSearchQuery] = useState<string | null>(null);

  // 1. Fetch files list
  const {
    data: filesData,
    isLoading: isFilesLoading,
    refetch: refetchFiles,
    isRefetching,
  } = useQuery({
    queryKey: queryKeys.knowledgeDocuments({}),
    queryFn: () => getKnowledgeFiles(),
    refetchInterval: (query) => {
      // Poll every 5s if there is any file indexing
      const hasIndexing = query.state.data?.items?.some((f) => f.status === "indexing");
      return hasIndexing ? 5000 : false;
    },
  });

  const files = filesData?.items ?? [];

  // 2. Search mutation/query
  const searchMutation = useMutation({
    mutationFn: (q: string) => searchKnowledge(q),
    onSuccess: (data) => {
      if (data.length === 0) {
        toast("没有找到相关参考内容", "info");
      }
    },
    onError: (err: any) => {
      toast(err.message || "搜索失败，请重试", "error");
    },
  });

  // 3. Upload mutation
  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadKnowledgeFile(file),
    onSuccess: () => {
      toast("文件上传成功，开始解析索引", "success");
      refetchFiles();
    },
    onError: (err: any) => {
      console.error("UPLOAD MUTATION ERROR:", err);
      toast(err.message || "文件上传失败，请重试", "error");
    },
  });

  // 4. Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteKnowledgeFile(id),
    onSuccess: () => {
      toast("文件已成功移除", "success");
      refetchFiles();
    },
    onError: (err: any) => {
      toast(err.message || "删除失败", "error");
    },
  });

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchVal.trim()) {
      handleClearSearch();
      return;
    }
    setActiveSearchQuery(searchVal.trim());
    searchMutation.mutate(searchVal.trim());
  };

  const handleClearSearch = () => {
    setSearchVal("");
    setActiveSearchQuery(null);
    searchMutation.reset();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  };

  const triggerSelectFile = () => {
    fileInputRef.current?.click();
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="h-full flex flex-col bg-panel text-ink border-l border-border animate-in fade-in duration-300">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold flex items-center gap-1.5 font-serif-cn text-primary">
            <Sparkles className="h-4 w-4 animate-pulse" />
            智能知识库
          </h2>
          <p className="text-[10px] text-muted leading-tight mt-0.5">
            上传个人资料进行 RAG 增强式个性化辅导
          </p>
        </div>
        <button
          onClick={() => refetchFiles()}
          disabled={isFilesLoading || isRefetching}
          className="p-1.5 rounded-lg hover:bg-page transition-colors cursor-pointer text-muted hover:text-ink disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRefetching ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Search Input */}
      <form onSubmit={handleSearchSubmit} className="p-4 border-b border-border bg-page/30 flex gap-2">
        <div className="relative flex-grow">
          <input
            type="text"
            placeholder="搜索知识库文档内容..."
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            className="w-full bg-page border border-border rounded-lg pl-8 pr-8 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary text-ink"
          />
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted pointer-events-none" />
          {searchVal && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="absolute right-2.5 top-2.5 p-0.5 rounded hover:bg-border text-muted hover:text-ink cursor-pointer"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
        <button
          type="submit"
          className="px-3 py-1.5 bg-primary hover:bg-primary-hover text-white text-xs font-semibold rounded-lg shadow-sm transition-colors cursor-pointer"
        >
          检索
        </button>
      </form>

      {/* Content Area */}
      <div className="flex-grow overflow-y-auto p-4 space-y-4">
        {activeSearchQuery ? (
          /* Search Results View */
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-muted uppercase tracking-wider">
                检索结果: "{activeSearchQuery}"
              </span>
              <button
                onClick={handleClearSearch}
                className="text-[10px] text-primary hover:underline cursor-pointer"
              >
                返回文档列表
              </button>
            </div>

            {searchMutation.isPending ? (
              <div className="py-8 flex flex-col items-center justify-center text-muted gap-2">
                <Loader2 className="h-5 w-5 animate-spin text-primary" />
                <span className="text-[10px]">正在深度检索向量索引...</span>
              </div>
            ) : searchMutation.data && searchMutation.data.length > 0 ? (
              <div className="space-y-2.5">
                {searchMutation.data.map((result) => (
                  <div
                    key={result.id}
                    className="p-3 bg-page/50 border border-border rounded-xl space-y-1.5 relative overflow-hidden"
                  >
                    <div className="flex justify-between items-center">
                      <span className="text-[10px] font-bold text-primary flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {result.fileName}
                      </span>
                      <span className="text-[9px] bg-primary-soft/10 text-primary px-1.5 py-0.5 rounded-full font-mono font-bold">
                        相似度 {(result.score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-[11px] text-ink leading-relaxed italic bg-panel p-2 rounded-lg border border-border/40">
                      "...{result.text}..."
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-muted">
                <AlertCircle className="h-5 w-5 mx-auto mb-2 text-muted" />
                <p className="text-[10px]">未匹配到相关文档切片，换个词试试？</p>
              </div>
            )}
          </div>
        ) : (
          /* Document Upload & Files List View */
          <>
            {/* Upload Area */}
            <div
              onClick={triggerSelectFile}
              className={`border border-dashed rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${
                uploadMutation.isPending
                  ? "bg-page/50 border-border cursor-not-allowed"
                  : "border-border hover:border-primary hover:bg-primary-soft/5"
              }`}
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                disabled={uploadMutation.isPending}
                className="hidden"
                accept=".pdf,.txt,.docx,.md,.json"
              />
              {uploadMutation.isPending ? (
                <div className="flex flex-col items-center gap-2 py-1.5">
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                  <p className="text-[11px] text-muted">正在上传并提取文本...</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-1.5 py-1.5 text-center">
                  <UploadCloud className="h-7 w-7 text-primary/80" />
                  <p className="text-[11px] font-semibold text-ink">
                    点击选择或拖拽文件上传
                  </p>
                  <p className="text-[9px] text-muted">
                    支持 PDF, TXT, DOCX, MD, JSON (最大 10MB)
                  </p>
                </div>
              )}
            </div>

            {/* Files List */}
            <div className="space-y-2">
              <span className="text-[10px] font-bold text-muted uppercase tracking-wider block mb-1">
                已上传的参考资料 ({files.length})
              </span>

              {isFilesLoading ? (
                <div className="py-6 flex flex-col items-center justify-center text-muted gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-[10px]">加载文档列表中...</span>
                </div>
              ) : files.length === 0 ? (
                <div className="p-6 text-center text-muted border border-border/40 rounded-xl bg-page/10">
                  <p className="text-[10px]">暂无参考资料，上传后将融入智能辅导</p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {files.map((file) => {
                    const isDeleting = deleteMutation.isPending && deleteMutation.variables === file.id;
                    const isIndexing = file.status === "indexing";
                    
                    return (
                      <div
                        key={file.id}
                        className="flex items-center justify-between p-2.5 border border-border/60 bg-panel rounded-lg hover:bg-page/20 transition-all"
                      >
                        <div className="flex items-center gap-2.5 min-w-0 flex-grow">
                          <FileText className={`h-4 w-4 shrink-0 ${isIndexing ? "text-primary animate-pulse" : "text-muted"}`} />
                          <div className="min-w-0">
                            <p className="text-[11px] font-medium text-ink truncate leading-normal">
                              {file.name}
                            </p>
                            <p className="text-[9px] text-muted font-mono mt-0.5">
                              {formatSize(file.size)}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 ml-3">
                          {/* Status Badge */}
                          {file.status === "indexing" && (
                            <span className="inline-flex items-center gap-1 text-[9px] font-bold text-warning bg-warning-soft/20 px-2 py-0.5 rounded-full">
                              <span className="w-1.5 h-1.5 bg-warning rounded-full animate-ping" />
                              解析中
                            </span>
                          )}
                          {file.status === "completed" && (
                            <span className="text-[9px] font-bold text-success bg-success-soft/20 px-2 py-0.5 rounded-full">
                              已就绪
                            </span>
                          )}
                          {file.status === "failed" && (
                            <span className="text-[9px] font-bold text-danger bg-danger-soft/20 px-2 py-0.5 rounded-full">
                              解析失败
                            </span>
                          )}

                          {/* Delete Button */}
                          <button
                            onClick={() => deleteMutation.mutate(file.id)}
                            disabled={isDeleting || isIndexing}
                            title="删除文件"
                            className="p-1 rounded text-muted hover:text-danger hover:bg-danger-soft/10 disabled:opacity-30 transition-colors cursor-pointer"
                          >
                            {isDeleting ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
