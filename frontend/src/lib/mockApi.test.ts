import { describe, expect, it } from 'vitest'
import type { Actor, SubmissionFilters } from '../types/api'
import { createMockApi, DEMO_SEED_COUNT } from './mockApi'

const filters: SubmissionFilters = { page: 1, pageSize: 50, sort: 'newest' }

function makeApi(actor: Actor) {
  return createMockApi(() => actor)
}

describe('static demo records', () => {
  it('shows the complete operations dataset to a reviewer', async () => {
    const api = makeApi({ name: 'xiaomei-reviewer', role: 'reviewer' })
    const page = await api.submissions(filters)
    const metrics = await api.metrics()

    expect(DEMO_SEED_COUNT).toBe(18)
    expect(page.total).toBe(18)
    expect(metrics.total).toBe(18)
    expect(metrics.awaiting_review).toBe(6)
    expect(metrics.claimed_reviews).toBe(2)
  })

  it('preserves researcher ownership filtering', async () => {
    const api = makeApi({ name: 'xiaomei-researcher', role: 'researcher' })
    const page = await api.submissions(filters)

    expect(page.total).toBe(8)
    expect(page.items.every((row) => row.submitted_by === 'xiaomei-researcher')).toBe(true)
  })

  it('returns the review queue in descending risk order', async () => {
    const api = makeApi({ name: 'xiaomei-reviewer', role: 'reviewer' })
    const queue = await api.reviewQueue()

    expect(queue).toHaveLength(6)
    for (let index = 1; index < queue.length; index += 1) {
      expect(queue[index - 1].risk_score).toBeGreaterThanOrEqual(queue[index].risk_score)
    }
  })
})
