import { Activity, CheckCircle2, ClipboardCheck, RefreshCw, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import './styles.css'
import { DetailPanel } from './components/DetailPanel'
import { IdentityBar } from './components/IdentityBar'
import { MetricCard } from './components/MetricCard'
import { OperationsPanel } from './components/OperationsPanel'
import { PolicyCatalogue } from './components/PolicyCatalogue'
import { PolicyLab } from './components/PolicyLab'
import { ReviewQueue } from './components/ReviewQueue'
import { SubmissionTable } from './components/SubmissionTable'
import { UploadPanel } from './components/UploadPanel'
import { api, DEMO_SEED_COUNT, isStaticDemo, setApiActor } from './lib/api'
import type {
  Actor, DecisionReport, Metrics, Policy, PolicySimulationInput, SubmissionDetail,
  SubmissionFilters, SubmissionPage, SubmissionSummary, UploadMetadata,
} from './types/api'

const emptyMetrics: Metrics = {
  total: 0, allow: 0, review: 0, block: 0, awaiting_review: 0, claimed_reviews: 0,
  automated_allow: 0, automated_review: 0, automated_block: 0, completed_reviews: 0,
  automation_rate: 0, review_completion_rate: 0, manual_block_rate: 0, average_risk: 0,
  average_queue_age_minutes: 0, oldest_queue_age_minutes: 0, deleted_files: 0,
  top_findings: [], policy_version: 'loading',
}
const emptyPage: SubmissionPage = { items: [], page: 1, page_size: 25, total: 0, pages: 1 }
const initialFilters: SubmissionFilters = { page: 1, pageSize: 25, sort: 'newest' }
const initialActor: Actor = isStaticDemo
  ? { name: 'xiaomei-reviewer', role: 'reviewer' }
  : { name: 'xiaomei-researcher', role: 'researcher' }

function downloadJson(report: DecisionReport, filename: string) {
  const safeBase = filename.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9-_]+/g, '-')
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${safeBase}-decision-report.json`
  document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url)
}

function App() {
  const [actor, setActor] = useState<Actor>(initialActor)
  const [metrics, setMetrics] = useState<Metrics>(emptyMetrics)
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [submissions, setSubmissions] = useState<SubmissionPage>(emptyPage)
  const [filters, setFilters] = useState<SubmissionFilters>(initialFilters)
  const [reviewQueue, setReviewQueue] = useState<SubmissionSummary[]>([])
  const [selected, setSelected] = useState<SubmissionDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  useEffect(() => { setApiActor(actor) }, [actor])

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const queuePromise = actor.role === 'researcher' ? Promise.resolve([]) : api.reviewQueue()
      const [nextMetrics, nextPolicy, nextSubmissions, nextQueue] = await Promise.all([
        api.metrics(), api.policy(), api.submissions(filters), queuePromise,
      ])
      setMetrics(nextMetrics); setPolicy(nextPolicy); setSubmissions(nextSubmissions)
      setReviewQueue(nextQueue); setLastUpdated(new Date()); setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The API could not be reached.')
    } finally { setRefreshing(false) }
  }, [actor.role, filters])

  useEffect(() => { void refresh() }, [refresh, actor.name])
  useEffect(() => {
    const interval = window.setInterval(() => void refresh(), 30_000)
    return () => window.clearInterval(interval)
  }, [refresh])

  async function action<T>(work: () => Promise<T>, fallback: string): Promise<T | null> {
    setBusy(true)
    try { const result = await work(); setError(null); return result }
    catch (reason) { setError(reason instanceof Error ? reason.message : fallback); return null }
    finally { setBusy(false) }
  }

  async function upload(file: File, metadata: UploadMetadata) {
    const result = await action(() => api.upload(file, metadata), 'Upload failed.')
    if (result) { setSelected(result); await refresh() }
  }
  async function openSubmission(id: string) {
    const result = await action(() => api.submission(id), 'Submission could not be loaded.')
    if (result) setSelected(result)
  }
  async function updateSelected(work: () => Promise<SubmissionDetail>, fallback: string) {
    const result = await action(work, fallback)
    if (result) { setSelected(result); await refresh() }
  }
  async function verify(id: string) {
    const result = await action(async () => ({ report: await api.verifyReport(id), audit: await api.verifyAudit(id) }), 'Verification failed.')
    if (!result) throw new Error('Verification failed.')
    return result
  }

  function changeActor(next: Actor) {
    setApiActor(next); setActor(next); setSelected(null); setFilters(initialFilters)
  }

  return (
    <div className="app-shell">
      <header className="topbar"><div className="brand-mark"><ShieldAlert /></div><div>
        <p className="eyebrow">Trusted research environment</p><h1>Output Airlock</h1></div>
        <div className="topbar__meta"><span className={`service-status ${error ? 'service-status--error' : ''}`}>
          <i /> {error ? 'Service attention required' : isStaticDemo ? 'Static demo operational' : 'Service operational'}</span>
          <span>{policy?.policy_version ?? metrics.policy_version}</span></div></header>
      <main>
        {isStaticDemo && <section className="demo-mode-banner" role="status"><strong>Static portfolio demo</strong><span>{DEMO_SEED_COUNT} synthetic outputs are preloaded in reviewer view. Switch roles to demonstrate researcher ownership filtering and administrator controls. No backend or real data is connected.</span></section>}
        <section className="hero"><div><p className="eyebrow">Release assurance workflow</p>
          <h2>Transparent checks, controlled review, verifiable decisions.</h2>
          <p>A production-minded demonstration of output checking before research files leave a controlled environment.</p></div>
          <div className="hero__side"><div className="hero__flow"><span>Quarantine</span><i>→</i><span>Check</span><i>→</i><span>Review</span><i>→</i><span>Release</span></div>
            <button className="refresh-button" onClick={() => void refresh(true)} disabled={refreshing}><RefreshCw className={refreshing ? 'spin' : ''} size={15} />
              {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : 'Refresh data'}</button></div></section>

        <IdentityBar actor={actor} onChange={changeActor} />
        {error && <div className="error-banner" role="alert"><strong>Dashboard action failed.</strong><span>{error}</span><button onClick={() => setError(null)}>Dismiss</button></div>}

        <section className="metrics-grid">
          <MetricCard label="Total outputs" value={metrics.total} helper="Registered submissions" icon={<Activity />} />
          <MetricCard label="Automation rate" value={`${Math.round(metrics.automation_rate * 100)}%`} helper="Allow or block without review" icon={<CheckCircle2 />} />
          <MetricCard label="Awaiting review" value={metrics.awaiting_review} helper={`${metrics.claimed_reviews} currently claimed`} icon={<ClipboardCheck />} />
          <MetricCard label="Final blocks" value={metrics.block} helper="Release prevented after final decision" icon={<ShieldAlert />} />
        </section>

        <section className="dashboard-grid dashboard-grid--primary">
          <UploadPanel busy={busy} onUpload={upload} /><OperationsPanel metrics={metrics} />
        </section>
        <section className="dashboard-grid dashboard-grid--secondary">
          <ReviewQueue actor={actor} rows={reviewQueue} onSelect={(id) => void openSubmission(id)} />
          <PolicyCatalogue policy={policy} />
        </section>
        <section className="dashboard-grid dashboard-grid--secondary">
          <PolicyLab actor={actor} busy={busy} onSimulate={async (input: PolicySimulationInput) => {
            const result = await action(() => api.simulatePolicy(input), 'Policy simulation failed.')
            if (!result) throw new Error('Policy simulation failed.')
            return result
          }} />
          <section className="panel evidence-panel"><p className="eyebrow">Engineering evidence</p><h2>Controls demonstrated in this version</h2>
            <div className="evidence-list"><span>Role-based access</span><span>Review claim locking</span><span>Optimistic concurrency</span>
              <span>Signed reports</span><span>Hash-linked audit events</span><span>Retention workflow</span><span>Policy simulation</span><span>Server-side pagination</span></div></section>
        </section>

        <SubmissionTable data={submissions} filters={filters} onFiltersChange={setFilters} onSelect={(id) => void openSubmission(id)} />
      </main>
      <footer>Synthetic demonstration by Xiaomei Mi · No affiliation with UK Biobank · No real participant data</footer>

      {selected && <DetailPanel actor={actor} submission={selected} busy={busy} onClose={() => setSelected(null)}
        onReview={(id, decision, rationale, version) => updateSelected(() => api.review(id, decision, rationale, version), 'Review could not be saved.')}
        onRecheck={(id) => updateSelected(() => api.recheck(id), 'Recheck could not be completed.')}
        onClaim={(id) => updateSelected(() => api.claim(id), 'Review claim failed.')}
        onReleaseClaim={(id) => updateSelected(() => api.releaseClaim(id), 'Review claim could not be released.')}
        onDeleteFile={(id) => updateSelected(() => api.deleteFile(id), 'File retention action failed.')}
        onDownload={async (id, filename) => { const report = await action(() => api.report(id), 'Report could not be generated.'); if (report) downloadJson(report, filename) }}
        onVerify={verify} />}
    </div>
  )
}
export default App
