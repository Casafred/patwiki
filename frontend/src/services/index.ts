import {
  aiApi,
  analyticsApi,
  automationApi,
  customFieldApi,
  dashboardApi,
  fieldApi,
  linkApi,
  patentApi,
  productApi,
  projectApi,
  projectRiskApi,
  searchApi,
  tagApi,
  viewApi,
} from '../api'
import type { FieldMeta, JsonObject } from '../types'

let fieldCache: FieldMeta[] | null = null
let fieldRequest: Promise<FieldMeta[]> | null = null

const cloneFields = (fields: FieldMeta[]) => fields.map(field => ({ ...field }))

export const fieldService = {
  list(force = false): Promise<FieldMeta[]> {
    if (!force && fieldCache) return Promise.resolve(cloneFields(fieldCache))
    if (!force && fieldRequest) return fieldRequest.then(cloneFields)
    fieldRequest = fieldApi.list()
      .then(fields => {
        fieldCache = fields
        return fields
      })
      .finally(() => { fieldRequest = null })
    return fieldRequest.then(cloneFields)
  },
  invalidate() {
    fieldCache = null
  },
}

export const patentService = {
  list: (params: JsonObject = {}) => patentApi.list(params),
  get: (id: number) => patentApi.get(id),
  family: (id: number) => patentApi.family(id),
  update: (...args: Parameters<typeof patentApi.update>) => patentApi.update(...args),
  listProjects: (id: number) => patentApi.listProjects(id),
  replaceProjects: (...args: Parameters<typeof patentApi.replaceProjects>) => patentApi.replaceProjects(...args),
  delete: (id: number) => patentApi.delete(id),
  bulkUpdate: (...args: Parameters<typeof patentApi.bulkUpdate>) => patentApi.bulkUpdate(...args),
  bulkTag: (...args: Parameters<typeof patentApi.bulkTag>) => patentApi.bulkTag(...args),
  bulkDelete: (ids: number[]) => patentApi.bulkDelete(ids),
  cleanupInvalidPlaceholders: (dryRun = true) => patentApi.cleanupInvalidPlaceholders(dryRun),
  updateCell: (...args: Parameters<typeof patentApi.updateCell>) => patentApi.updateCell(...args),
  getHistory: (...args: Parameters<typeof patentApi.getHistory>) => patentApi.getHistory(...args),
  identifiers: (id: number) => patentApi.identifiers(id),
  fieldSources: (id: number) => patentApi.fieldSources(id),
  identityConflicts: (id: number) => patentApi.identityConflicts(id),
}

export const aiService = {
  process: (...args: Parameters<typeof aiApi.process>) => aiApi.process(...args),
  getTask: (id: number) => aiApi.getTask(id),
  listAIFields: () => aiApi.listAIFields(),
  listValues: (patentId: number) => aiApi.listValues(patentId),
  overrideValue: (...args: Parameters<typeof aiApi.overrideValue>) => aiApi.overrideValue(...args),
  clearOverride: (...args: Parameters<typeof aiApi.clearOverride>) => aiApi.clearOverride(...args),
}

export const metadataService = {
  products: (params: JsonObject = {}) => productApi.list(params),
  projects: (params: JsonObject = {}) => projectApi.list(params),
  tags: () => tagApi.list(),
}

export const productService = { list: (params: JsonObject = {}) => productApi.list(params) }
export const projectService = { list: (params: JsonObject = {}) => projectApi.list(params) }
export const projectRiskService = {
  listSolutionVersions: (...args: Parameters<typeof projectRiskApi.listSolutionVersions>) => projectRiskApi.listSolutionVersions(...args),
  createSolutionVersion: (...args: Parameters<typeof projectRiskApi.createSolutionVersion>) => projectRiskApi.createSolutionVersion(...args),
  confirmSolutionVersion: (...args: Parameters<typeof projectRiskApi.confirmSolutionVersion>) => projectRiskApi.confirmSolutionVersion(...args),
  listRiskCases: (...args: Parameters<typeof projectRiskApi.listRiskCases>) => projectRiskApi.listRiskCases(...args),
  createRiskCase: (...args: Parameters<typeof projectRiskApi.createRiskCase>) => projectRiskApi.createRiskCase(...args),
  addAssessment: (...args: Parameters<typeof projectRiskApi.addAssessment>) => projectRiskApi.addAssessment(...args),
  addReview: (...args: Parameters<typeof projectRiskApi.addReview>) => projectRiskApi.addReview(...args),
}
export const tagService = { list: () => tagApi.list() }

export const customFieldService = {
  list: (params: JsonObject = {}) => customFieldApi.list(params),
  create: (...args: Parameters<typeof customFieldApi.create>) => customFieldApi.create(...args),
  delete: (id: number) => customFieldApi.delete(id),
  remove: (id: number) => customFieldApi.delete(id),
}

export const viewService = {
  update: (...args: Parameters<typeof viewApi.update>) => viewApi.update(...args),
  grouped: (...args: Parameters<typeof viewApi.grouped>) => viewApi.grouped(...args),
  listPatents: (...args: Parameters<typeof viewApi.listPatents>) => viewApi.listPatents(...args),
  updateSharedField: (...args: Parameters<typeof viewApi.updateSharedField>) => viewApi.updateSharedField(...args),
  updateGroupConfig: (...args: Parameters<typeof viewApi.updateGroupConfig>) => viewApi.updateGroupConfig(...args),
  updateConditionalFormatting: (...args: Parameters<typeof viewApi.updateConditionalFormatting>) => viewApi.updateConditionalFormatting(...args),
}

export const relationService = {
  search: (...args: Parameters<typeof linkApi.search>) => linkApi.search(...args),
  create: (...args: Parameters<typeof linkApi.create>) => linkApi.create(...args),
  delete: (...args: Parameters<typeof linkApi.delete>) => linkApi.delete(...args),
  batch: (...args: Parameters<typeof linkApi.batch>) => linkApi.batch(...args),
}

export const searchService = {
  suggest: (...args: Parameters<typeof searchApi.suggest>) => searchApi.suggest(...args),
}

export const analyticsService = {
  columnStats: (...args: Parameters<typeof analyticsApi.columnStats>) => analyticsApi.columnStats(...args),
  statsToTags: (...args: Parameters<typeof analyticsApi.statsToTags>) => analyticsApi.statsToTags(...args),
}

export const dashboardService = {
  list: (...args: Parameters<typeof dashboardApi.list>) => dashboardApi.list(...args),
  create: (...args: Parameters<typeof dashboardApi.create>) => dashboardApi.create(...args),
  data: (...args: Parameters<typeof dashboardApi.data>) => dashboardApi.data(...args),
  addCard: (...args: Parameters<typeof dashboardApi.addCard>) => dashboardApi.addCard(...args),
  removeCard: (...args: Parameters<typeof dashboardApi.removeCard>) => dashboardApi.removeCard(...args),
  remove: (id: number) => dashboardApi.remove(id),
}

export const automationService = {
  listRules: (...args: Parameters<typeof automationApi.listRules>) => automationApi.listRules(...args),
  createRule: (...args: Parameters<typeof automationApi.createRule>) => automationApi.createRule(...args),
  toggleRule: (id: number) => automationApi.toggleRule(id),
  removeRule: (id: number) => automationApi.removeRule(id),
  executeRule: (...args: Parameters<typeof automationApi.executeRule>) => automationApi.executeRule(...args),
  logs: (...args: Parameters<typeof automationApi.logs>) => automationApi.logs(...args),
  scheduleTick: (...args: Parameters<typeof automationApi.scheduleTick>) => automationApi.scheduleTick(...args),
}
