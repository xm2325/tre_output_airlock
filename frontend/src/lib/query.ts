import type { SubmissionFilters } from '../types/api'

export function buildSubmissionQuery(filters: SubmissionFilters): string {
  const params = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.pageSize),
    sort: filters.sort,
  })
  if (filters.decision) params.set('decision', filters.decision)
  if (filters.workflowStatus) params.set('workflow_status', filters.workflowStatus)
  if (filters.projectCode?.trim()) params.set('project_code', filters.projectCode.trim())
  if (filters.search?.trim()) params.set('search', filters.search.trim())
  return params.toString()
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

export function formatAge(value: string, now = Date.now()): string {
  const ageMinutes = Math.max(0, Math.floor((now - new Date(value).getTime()) / 60_000))
  if (ageMinutes < 60) return `${ageMinutes} min`
  const hours = Math.floor(ageMinutes / 60)
  if (hours < 24) return `${hours} hr`
  return `${Math.floor(hours / 24)} d`
}
