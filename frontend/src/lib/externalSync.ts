export const HIMMPAT_UPDATE_FIELDS = [
  'publication_number', 'application_number', 'title', 'abstract', 'applicant', 'assignee', 'inventor',
  'filing_date', 'publication_date', 'country', 'ipc_all', 'legal_status', 'grant_date',
  'agent', 'priority_number', 'priority_date', 'claims', 'description_full',
  'technical_problem', 'technical_solution', 'technical_effect',
]

export const HIMMPAT_OPTIONAL_FIELDS = new Set([
  'agent', 'priority_number', 'priority_date', 'claims', 'description_full',
  'technical_problem', 'technical_solution', 'technical_effect',
])
