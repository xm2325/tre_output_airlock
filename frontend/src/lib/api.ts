import { buildSubmissionQuery } from './query'
import { createMockApi, DEMO_SEED_COUNT } from './mockApi'
import type {
  Actor,
  AuditVerification,
  DecisionReport,
  Metrics,
  Policy,
  PolicySimulation,
  PolicySimulationInput,
  SubmissionDetail,
  SubmissionFilters,
  SubmissionPage,
  SubmissionSummary,
  UploadMetadata,
  VerificationResult,
} from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
export const isStaticDemo = import.meta.env.VITE_DEMO_MODE === 'true'
export { DEMO_SEED_COUNT }

let currentActor: Actor = isStaticDemo
  ? { name: 'xiaomei-reviewer', role: 'reviewer' }
  : { name: 'xiaomei-researcher', role: 'researcher' }

export function setApiActor(actor: Actor) {
  currentActor = actor
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  headers.set('X-Demo-User', currentActor.name)
  headers.set('X-Demo-Role', currentActor.role)
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: string; request_id?: string }
      detail = payload.detail ?? detail
      if (payload.request_id) detail = `${detail} Request ID: ${payload.request_id}`
    } catch {
      // Preserve the generic message when the response is not JSON.
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

const liveApi = {
  me: () => request<Actor>('/api/v1/me'),
  metrics: () => request<Metrics>('/api/v1/metrics'),
  policy: () => request<Policy>('/api/v1/policy'),
  simulatePolicy: (payload: PolicySimulationInput) =>
    request<PolicySimulation>('/api/v1/policy/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  submissions: (filters: SubmissionFilters) =>
    request<SubmissionPage>(`/api/v1/submissions?${buildSubmissionQuery(filters)}`),
  reviewQueue: () => request<SubmissionSummary[]>('/api/v1/review-queue'),
  submission: (id: string) => request<SubmissionDetail>(`/api/v1/submissions/${id}`),
  report: (id: string) => request<DecisionReport>(`/api/v1/submissions/${id}/report`),
  verifyReport: (id: string) =>
    request<VerificationResult>(`/api/v1/submissions/${id}/report/verify`),
  verifyAudit: (id: string) =>
    request<AuditVerification>(`/api/v1/submissions/${id}/audit/verify`),
  recheck: (id: string) =>
    request<SubmissionDetail>(`/api/v1/submissions/${id}/recheck`, { method: 'POST' }),
  claim: (id: string) =>
    request<SubmissionDetail>(`/api/v1/submissions/${id}/claim`, { method: 'POST' }),
  releaseClaim: (id: string) =>
    request<SubmissionDetail>(`/api/v1/submissions/${id}/release-claim`, { method: 'POST' }),
  deleteFile: (id: string) =>
    request<SubmissionDetail>(`/api/v1/submissions/${id}/file`, { method: 'DELETE' }),
  upload: async (file: File, metadata: UploadMetadata) => {
    const body = new FormData()
    body.append('file', file)
    body.append('project_code', metadata.projectCode)
    body.append('output_type', metadata.outputType)
    body.append('output_description', metadata.outputDescription)
    return request<SubmissionDetail>('/api/v1/submissions', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body,
    })
  },
  review: (id: string, decision: 'ALLOW' | 'BLOCK', rationale: string, expectedVersion: number) =>
    request<SubmissionDetail>(`/api/v1/submissions/${id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, rationale, expected_version: expectedVersion }),
    }),
}

export const api = isStaticDemo ? createMockApi(() => currentActor) : liveApi
