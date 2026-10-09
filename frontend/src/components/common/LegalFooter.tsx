import { useState } from 'react'
import { createPortal } from 'react-dom'
import BrandLogo from './BrandLogo'
import Icon from './Icon'

interface LegalFooterProps {
  compact?: boolean
}

export default function LegalFooter({ compact = false }: LegalFooterProps) {
  return <footer className={`legal-footer ${compact ? 'legal-footer-compact' : ''}`}>
    <div className="legal-footer-brand">
      <BrandLogo size={18} decorative />
      <span>PatWiki</span>
    </div>
    <span className="legal-footer-copy">© {new Date().getFullYear()} designed by ALFRED SHI TEAM</span>
  </footer>
}

export function UserAgreementLink() {
  const [agreementOpen, setAgreementOpen] = useState(false)

  return (
    <>
      <button type="button" className="nav-item sidebar-agreement" title="用户使用协议" aria-label="用户使用协议" onClick={() => setAgreementOpen(true)}>
        <Icon name="file" size={17} />
        <span className="nav-label">用户使用协议</span>
      </button>

      {agreementOpen && createPortal(
        <div className="modal-overlay legal-modal-overlay" role="presentation" onMouseDown={event => {
          if (event.target === event.currentTarget) setAgreementOpen(false)
        }}>
          <section className="modal legal-modal" role="dialog" aria-modal="true" aria-labelledby="user-agreement-title">
            <div className="modal-header">
              <div>
                <h2 id="user-agreement-title">PatWiki 用户使用协议</h2>
                <p className="legal-modal-kicker">ALFRED SHI TEAM · 版权与使用规则</p>
              </div>
              <button type="button" className="modal-close" onClick={() => setAgreementOpen(false)} aria-label="关闭用户使用协议">×</button>
            </div>
            <div className="modal-body legal-modal-body">
              <p>欢迎使用 PatWiki 专利知识工作台。使用本产品即表示你已阅读并同意本协议。若你不同意任何条款，请停止使用相关功能。</p>
              <h3>一、内容与知识产权</h3>
              <p>PatWiki 的软件、界面、Logo、图形、文字、数据库结构、文档及相关视觉设计均由 <strong>ALFRED SHI TEAM</strong> 创作或依法取得授权，受著作权、商标及其他知识产权法律保护。未经书面许可，不得复制、修改、反向工程、出售、转授权、移除版权标识，或以相同、近似方式使用 PatWiki 品牌资产。</p>
              <h3>二、用户数据与授权</h3>
              <p>你或相关权利人保留用户数据本身的所有权及知识产权，本产品不会因存储或处理而取得这些权利。你对导入、创建、上传和分享的专利资料、项目资料及附件承担合法来源和使用责任，并应确保拥有必要的版权、商业秘密、个人信息及其他授权。为提供存储、检索、协作和导出功能，你授予本产品在服务范围内处理这些数据的必要权限；该授权不转移数据所有权。</p>
              <h3>三、分享与第三方服务</h3>
              <p>公开分享链接、表单和外部同步可能让指定范围外的人员访问内容，请在发布前确认信息范围。AI、外部数据源和其他第三方服务的结果仅供工作参考，你应自行复核其准确性、完整性和适用性。</p>
              <h3>四、版权投诉与联系</h3>
              <p>如你认为产品内的内容侵犯了你的合法权利，请保留相关页面、权属证明和联系方式，并向 ALFRED SHI TEAM 提交书面通知。我们会在核实后采取必要的下架、限制访问或纠正措施。</p>
              <h3>五、协议更新</h3>
              <p>我们可能根据产品功能或法律要求更新本协议。更新后的协议会在产品内展示；继续使用即视为接受更新后的条款。</p>
              <p className="legal-modal-note">最后更新：2026 年 10 月 7 日</p>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-primary" onClick={() => setAgreementOpen(false)}>关闭</button>
            </div>
          </section>
        </div>, document.body
      )}
    </>
  )
}
