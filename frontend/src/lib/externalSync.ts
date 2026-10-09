export interface ExternalUpdateField {
  key: string
  label: string
}

export interface ExternalUpdateFieldGroup {
  label: string
  fields: ExternalUpdateField[]
}

export const HIMMPAT_UPDATE_FIELD_GROUPS: ExternalUpdateFieldGroup[] = [
  {
    label: '基础著录项',
    fields: [
      { key: 'publication_date', label: '公开日' }, { key: 'grant_date', label: '授权日' }, { key: 'legal_status', label: '法律状态' },
      { key: 'application_number', label: '申请号' }, { key: 'publication_number', label: '公开号' }, { key: 'title', label: '标题' },
      { key: 'abstract', label: '摘要' }, { key: 'applicant', label: '申请人' }, { key: 'assignee', label: '受让人' },
      { key: 'inventor', label: '发明人' }, { key: 'filing_date', label: '申请日' }, { key: 'country', label: '国家/地区' },
      { key: 'ipc_all', label: 'IPC 分类' }, { key: 'agent', label: '代理人' }, { key: 'priority_date', label: '优先权日' },
      { key: 'priority_number', label: '优先权号' },
    ],
  },
  {
    label: '说明书与权利要求',
    fields: [
      { key: 'claims', label: '权利要求全文' }, { key: 'description_full', label: '说明书全文' },
      { key: 'technical_problem', label: '技术问题' }, { key: 'technical_solution', label: '技术方案' },
      { key: 'technical_effect', label: '技术效果' }, { key: 'legal_status_details', label: '法律事件详情' },
      { key: 'mcp_claim_metadata', label: '权利要求原始数据' }, { key: 'mcp_description_metadata', label: '说明书原始数据' },
    ],
  },
  {
    label: '原文与附图',
    fields: [
      { key: 'mcp_pdf_original', label: 'PDF 原文（保存到附件）' },
      { key: 'mcp_abstract_figure', label: '摘要附图（保存到附件）' },
      { key: 'mcp_description_figures', label: '说明书附图（保存到附件）' },
    ],
  },
  {
    label: '同族与引用',
    fields: [
      { key: 'family_members', label: '同族成员' }, { key: 'mcp_citation_data', label: '引用完整数据' },
      { key: 'cited_patents', label: '引用专利' }, { key: 'citing_patents', label: '被引用专利' },
    ],
  },
  {
    label: '法律与权属运营',
    fields: [
      { key: 'mcp_legal_event_details', label: '法律事件原始数据' }, { key: 'mcp_reexamination', label: '复审记录' },
      { key: 'mcp_invalidation', label: '无效记录' }, { key: 'mcp_transfer_events', label: '转让记录' },
      { key: 'mcp_license_events', label: '许可记录' }, { key: 'mcp_pledge_events', label: '质押记录' },
      { key: 'mcp_preservation_events', label: '保全记录' },
    ],
  },
  {
    label: '价值评估',
    fields: [
      { key: 'mcp_value_evaluation', label: '综合价值评估' }, { key: 'mcp_technology_value', label: '技术价值评估' },
      { key: 'mcp_legal_value', label: '法律价值评估' }, { key: 'mcp_market_value', label: '市场价值评估' },
      { key: 'mcp_strategic_value', label: '战略价值评估' },
    ],
  },
  {
    label: '完整著录数据',
    fields: [
      { key: 'mcp_record_fields', label: '完整著录项目' }, { key: 'mcp_priority_claims', label: '优先权主张' },
      { key: 'mcp_classification_details', label: '分类详情' }, { key: 'mcp_party_details', label: '申请人/发明人/代理人详情' },
    ],
  },
]

export const HIMMPAT_UPDATE_FIELD_OPTIONS = HIMMPAT_UPDATE_FIELD_GROUPS.flatMap(group => group.fields)
export const HIMMPAT_UPDATE_FIELDS = HIMMPAT_UPDATE_FIELD_OPTIONS.map(field => field.key)

export const HIMMPAT_OPTIONAL_FIELDS = new Set([
  'agent', 'priority_number', 'priority_date', 'claims', 'description_full',
  'technical_problem', 'technical_solution', 'technical_effect', 'legal_status_details',
  'family_members', 'cited_patents', 'citing_patents',
  ...HIMMPAT_UPDATE_FIELDS.filter(key => key.startsWith('mcp_')),
])

export const GENERIC_UPDATE_FIELD_OPTIONS: ExternalUpdateField[] = [
  { key: 'publication_number', label: '公开号' }, { key: 'application_number', label: '申请号' },
  { key: 'grant_number', label: '授权号' }, { key: 'title', label: '标题' }, { key: 'abstract', label: '摘要' },
  { key: 'applicant', label: '申请人' }, { key: 'assignee', label: '受让人' }, { key: 'inventor', label: '发明人' },
  { key: 'agent', label: '代理人' }, { key: 'filing_date', label: '申请日' }, { key: 'publication_date', label: '公开日' },
  { key: 'grant_date', label: '授权日' }, { key: 'country', label: '国家/地区' }, { key: 'ipc_main', label: '主 IPC' },
  { key: 'ipc_all', label: 'IPC 分类' }, { key: 'cpc_main', label: '主 CPC' }, { key: 'priority_number', label: '优先权号' },
  { key: 'priority_date', label: '优先权日' }, { key: 'legal_status', label: '法律状态' }, { key: 'claims', label: '权利要求全文' },
  { key: 'description_full', label: '说明书全文' }, { key: 'technical_problem', label: '技术问题' },
  { key: 'technical_solution', label: '技术方案' }, { key: 'technical_effect', label: '技术效果' },
]

export const EXTERNAL_UPDATE_PRESETS_STORAGE_KEY = 'patwiki_external_update_field_presets_v1'
