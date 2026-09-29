import { useState } from 'react'
import type { AuditEvent, QueryResponse } from '../types/contracts'
import { agentDirectory, hiveState } from '../utils/hive'
import { formatEvidenceValue, humaniseKey } from '../utils/evidence'

export function HivePanel({ result, loading, error, audit, auditStatus }: {
  result: QueryResponse | null
  loading: boolean
  error: string | null
  audit: AuditEvent | null
  auditStatus?: string
}) {
  const [selected, setSelected] = useState<string>('queen')
  const agent = agentDirectory.find((item) => item.id === selected)!
  const response = selected === 'advisor' ? result?.advisor_result : result?.specialist_results.find((item) => item.agent === selected)
  return <section className="panel" id="hive" aria-labelledby="hive-heading">
    <p className="eyebrow">EIGHT ROLES · ONE WORKFLOW</p>
    <h2 id="hive-heading">Meet your agent hive</h2>
    <p className="hint">Select a Bee to inspect its findings. Activity is based on returned results, not a live execution stream.</p>
    <div className="hive-layout">
      <div className="bee-grid" aria-label="Select agent">
        {agentDirectory.map((item) => <button key={item.id} type="button" className={`bee-card ${selected === item.id ? 'bee-selected' : ''}`} aria-pressed={selected === item.id} aria-controls="bee-detail" onClick={() => setSelected(item.id)}>
          <span className="bee-glyph" aria-hidden="true">{item.glyph}</span>
          <strong>{item.name}</strong>
          <span>{hiveState(item.id, result, loading, error, audit, auditStatus)}</span>
        </button>)}
      </div>
      <article className="bee-detail" id="bee-detail" aria-live="polite">
        <h3>{agent.name}</h3><p>{agent.purpose}</p>
        {loading ? <p>Waiting for the query response.</p> : error ? <p role="alert">No verified result is available for the failed request.</p> : !result ? <p>Ask a business question to inspect evidence.</p> : <>
          {selected === 'queen' && <p>{result.invoked_agents.length ? `Routed to: ${result.invoked_agents.map(humaniseKey).join(', ')}` : 'No specialist selected. Clarify your question.'}</p>}
          {selected === 'guard' && <><p>{humaniseKey(result.guard_decision)}</p><p>GREEN: read-only. AMBER: owner approval. RED: blocked. Approval never executes a business action.</p></>}
          {selected === 'audit' && <p>{audit ? `Workflow ${audit.workflow_id}: ${audit.evidence_count} evidence items recorded. See the current workflow below.` : 'The stored audit record is not available yet. This does not confirm persistence.'}</p>}
          {response && <><p>{response.summary}</p><p className="hint">Status: {response.status}</p>
            <dl className="bee-evidence">{response.evidence.map((item, index) => <div key={`${item.metric}-${index}`}><dt>{humaniseKey(item.metric)}</dt><dd>{formatEvidenceValue(item)}</dd>{item.source && <dd className="hint">Source: {item.source}</dd>}</div>)}</dl>
          </>}
          {!response && !['queen', 'guard', 'audit'].includes(selected) && <p>{result.invoked_agents.includes(selected) ? 'Selected, but no result returned.' : 'Not selected for this question.'}</p>}
        </>}
      </article>
    </div>
  </section>
}
