import React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ShieldCheck } from "lucide-react";

export function PrivacyPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-page py-12 px-6 font-sans select-text text-ink">
      <div className="max-w-3xl mx-auto bg-panel border border-border rounded-2xl shadow-card p-8 sm:p-12 flex flex-col gap-6 relative">
        <button
          onClick={() => navigate(-1)}
          className="absolute left-8 top-8 inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink transition-colors cursor-pointer select-none"
        >
          <ArrowLeft className="h-4 w-4" />
          返回
        </button>

        <div className="flex flex-col items-center gap-3 mt-4 select-none">
          <div className="p-3 bg-primary-soft/30 text-primary rounded-xl">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">隐私政策 (Privacy Policy)</h1>
          <p className="text-[10px] text-muted font-semibold">生效日期：2026年6月23日</p>
        </div>

        <div className="text-xs leading-relaxed space-y-5 text-muted">
          <section>
            <h2 className="text-sm font-bold text-ink mb-2">1. 收集的数据</h2>
            <p>
              我们可能收集的个人及业务数据包括：您的注册信息（昵称、电子邮箱）、账户状态、Onboarding 学习偏好、设定的学习目标、能力诊断评估回答、单元测试答题记录以及您主动上传至智能知识库的文件资料。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">2. 学习数据用途</h2>
            <p>
              收集到的学习偏好、目标和诊断答卷，将严格用于调优大语言模型（LLM）与智能规划体，以为您生成最匹配的拓扑树级大纲和单元文章讲解。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">3. 智能体处理说明</h2>
            <p>
              为了生成学习材料和进行答题评测，您的学习目标及诊断问卷内容将以提示词（Prompt）和 RAG 上下文形式输入大语言模型 API。我们不对任何外部第三方模型服务商披露您的账户真实姓名及敏感注册凭据。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">4. 知识资料处理</h2>
            <p>
              您上传到个人知识库的资料仅在您当前的会话和关联的学习目标生成中进行私有向量检索（RAG）。我们承诺不会将您上传的任何文件公开，亦不会用于共享模型的大规模通用训练。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">5. Cookie 与会话</h2>
            <p>
              我们使用安全、带有 HttpOnly 属性的 Cookie 验证您的登录状态。这可以保证您的身份凭证不被恶意脚本（XSS）拦截，从而提高账号访问的安全性。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">6. 数据保存时间</h2>
            <p>
              您的学习轨迹、掌握度和知识库文档将被安全保存，直到您主动注销账号、删除对应文档或我们终止该阶段服务的运营。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">7. 数据删除</h2>
            <p>
              您可以在“个人设置”或“安全设置”中，或者在“智能知识库”面板中随时点击删除您已上传的文件，删除操作将同步清理其在向量索引数据库中的副本。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">8. 用户权利</h2>
            <p>
              您可以随时访问系统查看您的个人学习数据，申请导出或限制部分非必要的个人数据收集行为。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">9. 联系方式</h2>
            <p>
              如有任何关于隐私数据保护的建议或要求，请联系我们：<span className="text-primary select-all">privacy@eduagentx.test</span>
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
export default PrivacyPage;
