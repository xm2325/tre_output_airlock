import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, setApiActor } from './api'

const ok = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), {
  status,
  headers: { 'Content-Type': 'application/json' },
})

describe('live API client contract', () => {
  beforeEach(() => {
    setApiActor({ name: 'xiaomei-reviewer', role: 'reviewer' })
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => vi.unstubAllGlobals())

  it('sends actor headers on reviewer operations', async () => {
    vi.mocked(fetch).mockResolvedValue(ok({ id: 'sub-1' }))
    await api.claim('sub-1')
    const [, options] = vi.mocked(fetch).mock.calls[0]
    const headers = new Headers(options?.headers)
    expect(headers.get('X-Demo-User')).toBe('xiaomei-reviewer')
    expect(headers.get('X-Demo-Role')).toBe('reviewer')
    expect(options?.method).toBe('POST')
  })

  it('sends optimistic row version with a review decision', async () => {
    vi.mocked(fetch).mockResolvedValue(ok({ id: 'sub-1', row_version: 4 }))
    await api.review('sub-1', 'ALLOW', 'Synthetic output was corrected and rechecked.', 3)
    const [, options] = vi.mocked(fetch).mock.calls[0]
    expect(JSON.parse(String(options?.body))).toEqual({
      decision: 'ALLOW',
      rationale: 'Synthetic output was corrected and rechecked.',
      expected_version: 3,
    })
  })

  it('surfaces the API request ID on a concurrency conflict', async () => {
    vi.mocked(fetch).mockResolvedValue(ok({ detail: 'Submission version is stale.', request_id: 'req-409' }, 409))
    await expect(api.review('sub-1', 'BLOCK', 'Disclosure concern remains unresolved.', 2))
      .rejects.toThrow('Submission version is stale. Request ID: req-409')
  })

  it('uses DELETE for the administrator retention action', async () => {
    vi.mocked(fetch).mockResolvedValue(ok({ id: 'sub-1', file_available: false }))
    await api.deleteFile('sub-1')
    const [, options] = vi.mocked(fetch).mock.calls[0]
    expect(options?.method).toBe('DELETE')
  })
})
