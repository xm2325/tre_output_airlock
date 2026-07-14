import { FlaskConical, LockKeyhole } from 'lucide-react'
import { useState } from 'react'
import type { Actor, Decision, PolicySimulation, PolicySimulationInput } from '../types/api'

interface PolicyLabProps {
  actor: Actor
  busy: boolean
  onSimulate: (input: PolicySimulationInput) => Promise<PolicySimulation>
}

const defaults: PolicySimulationInput = {
  critical_action: 'BLOCK', high_action: 'REVIEW', medium_action: 'REVIEW', low_action: 'ALLOW',
}

export function PolicyLab({ actor, busy, onSimulate }: PolicyLabProps) {
  const [input, setInput] = useState(defaults)
  const [result, setResult] = useState<PolicySimulation | null>(null)
  if (actor.role === 'researcher') return (
    <section className="panel restricted-panel"><LockKeyhole /><div><p className="eyebrow">Policy governance</p>
      <h2>Simulation restricted</h2><p>Only reviewer and admin roles can run retrospective workflow simulations.</p></div></section>
  )

  const levels: Array<keyof PolicySimulationInput> = ['critical_action', 'high_action', 'medium_action', 'low_action']
  async function run() {
    try {
      setResult(await onSimulate(input))
    } catch {
      setResult(null)
    }
  }
  return (
    <section className="panel policy-lab">
      <div className="panel__header"><div><p className="eyebrow">What-if analysis</p><h2>Policy workload simulator</h2></div><FlaskConical /></div>
      <p className="policy-logic">Change severity actions and estimate how stored findings would route under a candidate policy.</p>
      <div className="simulation-grid">{levels.map((level) => <label key={level}>
        <span>{level.replace('_action', '').toUpperCase()}</span>
        <select value={input[level]} onChange={(event) => setInput({ ...input, [level]: event.target.value as Decision })}>
          <option value="ALLOW">ALLOW</option><option value="REVIEW">REVIEW</option><option value="BLOCK">BLOCK</option>
        </select>
      </label>)}</div>
      <button className="secondary-button" disabled={busy} onClick={() => void run()}>Run retrospective simulation</button>
      {result && <div className="simulation-result">
        <div><span>Allow</span><strong>{result.allow}</strong></div><div><span>Review</span><strong>{result.review}</strong></div>
        <div><span>Block</span><strong>{result.block}</strong></div><div><span>Changed</span><strong>{result.changed_decisions}</strong></div>
        <p>{result.note}</p>
      </div>}
    </section>
  )
}
