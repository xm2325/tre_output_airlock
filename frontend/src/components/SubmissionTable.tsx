import { ChevronLeft, ChevronRight, FileText, Search, SlidersHorizontal } from 'lucide-react'
import type { Decision, SubmissionFilters, SubmissionPage } from '../types/api'
import { formatBytes } from '../lib/query'
import { DecisionBadge } from './DecisionBadge'
import { RiskBadge } from './RiskBadge'

interface SubmissionTableProps {
  data: SubmissionPage
  filters: SubmissionFilters
  onFiltersChange: (next: SubmissionFilters) => void
  onSelect: (id: string) => void
}

export function SubmissionTable({ data, filters, onFiltersChange, onSelect }: SubmissionTableProps) {
  function patch(patchValue: Partial<SubmissionFilters>) {
    onFiltersChange({ ...filters, ...patchValue, page: patchValue.page ?? 1 })
  }

  return (
    <section className="panel table-panel">
      <div className="panel__header table-heading">
        <div>
          <p className="eyebrow">Controlled register</p>
          <h2>Submission search and traceability</h2>
        </div>
        <span className="record-count">{data.total} records</span>
      </div>

      <div className="table-tools">
        <label className="search-control">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">Search submissions</span>
          <input
            value={filters.search ?? ''}
            onChange={(event) => patch({ search: event.target.value })}
            placeholder="Search file, project or description"
          />
        </label>
        <label className="select-control">
          <SlidersHorizontal size={15} aria-hidden="true" />
          <select
            aria-label="Filter by automated decision"
            value={filters.decision ?? 'ALL'}
            onChange={(event) => patch({
              decision: event.target.value === 'ALL' ? undefined : event.target.value as Decision,
            })}
          >
            <option value="ALL">All decisions</option>
            <option value="ALLOW">Allow</option>
            <option value="REVIEW">Review</option>
            <option value="BLOCK">Block</option>
          </select>
        </label>
        <label className="select-control">
          <select
            aria-label="Sort submissions"
            value={filters.sort}
            onChange={(event) => patch({ sort: event.target.value as SubmissionFilters['sort'] })}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="risk_desc">Highest risk</option>
          </select>
        </label>
      </div>

      {data.items.length === 0 ? (
        <div className="empty-state">No submissions match the current query or role scope.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Output</th><th>Project</th><th>Workflow</th><th>Automated</th>
                <th>Final</th><th>Risk</th><th>Owner</th><th aria-label="Open" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((row) => (
                <tr key={row.id} onClick={() => onSelect(row.id)} tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') onSelect(row.id)
                  }}>
                  <td><div className="file-cell"><FileText size={18} /><div>
                    <strong>{row.filename}</strong>
                    <span>{row.output_type} · {formatBytes(row.size_bytes)}</span>
                  </div></div></td>
                  <td><strong>{row.project_code}</strong></td>
                  <td><span className="workflow-status">{row.status.replaceAll('_', ' ')}</span></td>
                  <td><DecisionBadge decision={row.automated_decision} /></td>
                  <td><DecisionBadge decision={row.final_decision} /></td>
                  <td><RiskBadge band={row.risk_band} score={row.risk_score} /></td>
                  <td>{row.claimed_by ? `Claimed: ${row.claimed_by}` : row.submitted_by}</td>
                  <td><ChevronRight size={18} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pagination">
        <button disabled={data.page <= 1} onClick={() => patch({ page: data.page - 1 })}>
          <ChevronLeft size={16} /> Previous
        </button>
        <span>Page {data.page} of {data.pages}</span>
        <button disabled={data.page >= data.pages} onClick={() => patch({ page: data.page + 1 })}>
          Next <ChevronRight size={16} />
        </button>
      </div>
    </section>
  )
}
