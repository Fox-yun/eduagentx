import React from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Scale } from "lucide-react";

export function TermsPage() {
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
            <Scale className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold font-serif-cn text-ink">服务条款 (Terms of Service)</h1>
          <p className="text-[10px] text-muted font-semibold">生效日期：2026年6月23日</p>
        </div>

        <div className="text-xs leading-relaxed space-y-5 text-muted">
          <section>
            <h2 className="text-sm font-bold text-ink mb-2">1. 服务范围</h2>
            <p>
              EduAgentX 是一款提供多用户智能学习、引导式路径规划与单元内容实时生成的 AI 辅助学习系统。本服务仅供您的个人非商业学习目的使用。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">2. 账号责任</h2>
            <p>
              您需要妥善保管账号密码及会话信息。因您自身泄露或保管不当导致的任何损失，由您自行承担。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">3. 智能生成内容说明</h2>
            <p>
              本系统中的学习大纲、节点讲解、代码演示及评估题目均由 AI 智能体（Agent）实时生成。生成的内容仅供学术参考与模拟学习之用，系统不担保其绝对准确性、时效性及适用性。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">4. 禁止行为</h2>
            <p>
              用户不得利用本服务传输违法、侵权、虚假、垃圾信息，或尝试进行反编译、接口爬取、滥用 API 额度以及破坏系统安全保护机制的行为。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">5. 知识资料授权</h2>
            <p>
              您上传至智能知识库的个人参考资料，其著作权归您或原作者所有。您授予 EduAgentX 系统及关联智能体在为您提供个性化 RAG 辅导范围内对该等资料的非排他、临时性使用授权。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">6. 服务变更</h2>
            <p>
              我们保留根据技术迭代、运营需求随时调整、优化或终止部分服务功能的权利，修改将通过公告或更新生效日期的方式予以告知。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">7. 责任限制</h2>
            <p>
              在法律允许的最大范围内，EduAgentX 不对因使用或无法使用本服务导致的任何间接、偶然、特殊或惩罚性赔偿承担责任。
            </p>
          </section>

          <section>
            <h2 className="text-sm font-bold text-ink mb-2">8. 联系方式</h2>
            <p>
              如有关于本条款的任何疑问，请发送邮件至：<span className="text-primary select-all">support@eduagentx.test</span>
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
export default TermsPage;
