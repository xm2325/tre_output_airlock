import { describe, expect, it } from 'vitest'
import { buildSubmissionQuery, formatAge, formatBytes } from './query'

describe('buildSubmissionQuery', () => {
  it('includes paging and selected filters', () => {
    const query = buildSubmissionQuery({
      page: 2,
      pageSize: 25,
      decision: 'REVIEW',
      search: ' small cell ',
      sort: 'risk_desc',
    })
    const params = new URLSearchParams(query)
    expect(params.get('page')).toBe('2')
    expect(params.get('page_size')).toBe('25')
    expect(params.get('decision')).toBe('REVIEW')
    expect(params.get('search')).toBe('small cell')
    expect(params.get('sort')).toBe('risk_desc')
  })

  it('omits empty optional filters', () => {
    const params = new URLSearchParams(buildSubmissionQuery({
      page: 1,
      pageSize: 10,
      search: '   ',
      sort: 'newest',
    }))
    expect(params.has('search')).toBe(false)
    expect(params.has('decision')).toBe(false)
  })
})

describe('format helpers', () => {
  it('formats file sizes', () => {
    expect(formatBytes(900)).toBe('900 B')
    expect(formatBytes(2048)).toBe('2.0 KB')
  })

  it('formats queue age using a fixed clock', () => {
    const now = new Date('2026-07-14T12:00:00Z').getTime()
    expect(formatAge('2026-07-14T10:00:00Z', now)).toBe('2 hr')
  })
})
