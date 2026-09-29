import { type FormEvent, useEffect, useMemo, useState } from 'react'
import './App.css'
import {
  fetchAuditEvent,
  fetchAuditHistory,
  fetchAuditTrace,
  queryBusiness,
} from './api/client'
import { AlertsPanel } from './components/AlertsPanel'
import { FinancePanel } from './components/FinancePanel'
import { ApprovalControls } from './components/ApprovalControls'
import { InventoryPanel } from './components/InventoryPanel'
import { SalesPanel } from './components/SalesPanel'
import { useSalesInventory, valueWhenReady } from './hooks/useSalesInventory'
import { formatPct } from './utils/format'
import { DEFAULT_LANGUAGE, LANGUAGES, hasLocalisedSummaries, languageLabel } from './utils/languages'
import type {
  AuditEvent,
  AgentResponse,
  AuditRecord,
  GuardActionExplanation,
  QueryResponse,
  RecommendedAction,
  RiskLevel,
} from './types/contracts'

type HiveState = 'Active' | 'Idle' | 'Routing' | 'Working' | 'Success' | 'Partial' | 'Failure'
type ActionState = 'Proposed' | 'Awaiting Approval' | 'Blocked' | 'Executed'

interface HiveAgent {
  id: string
  name: string
  state: HiveState
  note: string
  glyph: string
  color: string
  selectedByQueen: boolean
}

interface EvidenceItem {
  label: string
  value: string
}

interface Recommendation {
  title: string
  action: string
  risk: RiskLevel | 'DENY' | 'Unknown'
  state: ActionState
  detail: string
  evidenceReferences: string[]
}

// Language codes are shared with the team backend contract.

const agentDirectory = [
  { id: 'queen', name: 'Queen Bee', glyph: '♛', color: 'gold', purpose: 'Routes each business question to relevant specialists.' },
  { id: 'sales', name: 'Sales Bee', glyph: '↗', color: 'blue', purpose: 'Analyzes sales trend and product performance.' },
  { id: 'customer', name: 'Customer Bee', glyph: '♡', color: 'coral', purpose: 'Reviews complaints, defects and enquiry response.' },
  { id: 'finance', name: 'Finance Bee', glyph: '$', color: 'green', purpose: 'Reviews invoices and receivables.' },
  { id: 'inventory', name: 'Inventory Bee', glyph: '▦', color: 'orange', purpose: 'Checks stock and reorder thresholds.' },
  { id: 'advisor', name: 'Advisor Bee', glyph: '✦', color: 'violet', purpose: 'Synthesizes available specialist findings.' },
  { id: 'guard', name: 'Guard Bee', glyph: '⬡', color: 'red', purpose: 'Classifies recommendations and approval gates.' },
  { id: 'audit', name: 'Audit Bee', glyph: '◷', color: 'teal', purpose: 'Stores query traces and action status.' },
]

function readEvidence(result: AgentResponse | undefined, metric: string): unknown {
  return result?.evidence.find((item) => item.metric === metric)?.value
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatNumber(value: number | null, maximumFractionDigits = 1): string {
  return value === null
    ? '—'
    : new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value)
}

function guardState(decision: string): string {
  return decision.split(':', 1)[0] ?? 'not_evaluated'
}

function splitActionEvidence(actionType: string): { action: string; references: string[] } {
  const match = actionType.match(/\s+\[evidence:\s*(.*?)\]\s*$/i)
  return {
    action: match ? actionType.slice(0, match.index).trim() : actionType,
    references: match
      ? match[1].split(',').map((reference) => reference.trim()).filter(Boolean)
      : [],
  }
}

function parseGuardExplanations(decision: string): GuardActionExplanation[] {
  const detailStart = decision.indexOf(': ')
  if (detailStart < 0) return []

  return decision.slice(detailStart + 2).split('; ').flatMap((entry) => {
    const match = entry.match(/^(.*?): (GREEN|AMBER|RED|DENY) - (.+)$/)
    return match
      ? [{ action: match[1], classification: match[2] as GuardActionExplanation['classification'], reason: match[3] }]
      : []
  })
}

function auditConfirmsExecution(action: string, record: AuditRecord | null): boolean {
  if (!record) return false
  return record.executed_actions.some((item) => {
    const parsed = splitActionEvidence(item.type)
    return parsed.action === action && item.executed === true && item.status === 'executed'
  })
}

function actionState(
  action: string,
  explanation: GuardActionExplanation | undefined,
  record: AuditRecord | null,
): ActionState {
  if (auditConfirmsExecution(action, record)) return 'Executed'
  if (explanation?.classification === 'RED' || explanation?.classification === 'DENY') return 'Blocked'
  if (explanation?.classification === 'AMBER') return 'Awaiting Approval'
  return 'Proposed'
}

function stateClass(state: ActionState): string {
  return state.toLowerCase().replaceAll(' ', '-')
}

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value
  return JSON.stringify(value) ?? String(value)
}

export default function App() {
  const [selectedLanguage, setSelectedLanguage] = useState(DEFAULT_LANGUAGE)
  const [question, setQuestion] = useState('Why did customer complaints increase?')
  const [lastSubmitted, setLastSubmitted] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null)
  const { sales, inventory, finance, health, alerts, reload } = useSalesInventory(selectedLanguage)
  const [workflowAudit, setWorkflowAudit] = useState<AuditEvent | null>(null)
  const [workflowAuditError, setWorkflowAuditError] = useState<string | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState('queen')
  const [auditHistory, setAuditHistory] = useState<AuditRecord[]>([])
  const [auditHistoryLoading, setAuditHistoryLoading] = useState(true)
  const [auditHistoryError, setAuditHistoryError] = useState<string | null>(null)
  const [selectedTrace, setSelectedTrace] = useState<AuditRecord | null>(null)
  const [auditDetailLoading, setAuditDetailLoading] = useState(false)
  const [auditDetailError, setAuditDetailError] = useState<string | null>(null)

  const languageHint = useMemo(
    () =>
      `Critical values such as SGD, invoice IDs and quantities stay structured regardless of language (${languageLabel(selectedLanguage)}).${hasLocalisedSummaries(selectedLanguage) ? '' : ' Summaries may be shown in English.'}`, 
    [selectedLanguage],
  )

  async function refreshAuditHistory(selectLatest = false) {
    setAuditHistoryLoading(true)
    setAuditHistoryError(null)
    try {
      const response = await fetchAuditHistory(20)
      setAuditHistory(response.items)
      if (selectLatest && response.items.length > 0) {
        await openAuditTrace(response.items[0].trace_id)
      }
    } catch (err) {
      setAuditHistoryError(err instanceof Error ? err.message : 'Unable to load audit history.')
    } finally {
      setAuditHistoryLoading(false)
    }
  }

  async function openAuditTrace(traceId: string) {
    setAuditDetailLoading(true)
    setAuditDetailError(null)
    try {
      setSelectedTrace(await fetchAuditTrace(traceId))
    } catch (err) {
      setAuditDetailError(err instanceof Error ? err.message : 'Unable to load audit trace.')
    } finally {
      setAuditDetailLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    fetchAuditHistory(20)
      .then((response) => {
        if (!cancelled) setAuditHistory(response.items)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setAuditHistoryError(err instanceof Error ? err.message : 'Unable to load audit history.')
        }
      })
      .finally(() => {
        if (!cancelled) setAuditHistoryLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function submitQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!question.trim()) return

    setLoading(true)
    setError(null)
    setQueryResult(null)
    setSelectedTrace(null)
    setLastSubmitted(question.trim())

    try {
      const response = await queryBusiness({
        question: question.trim(),
        language: selectedLanguage,
        user: 'owner@bizzybee',
      })
      setQueryResult(response)
      setWorkflowAudit(null)
      setWorkflowAuditError(null)
      void fetchAuditEvent(response.workflow_id)
        .then(setWorkflowAudit)
        .catch((err: unknown) => setWorkflowAuditError(err instanceof Error ? err.message : 'Workflow audit event unavailable'))
      void refreshAuditHistory()
      void openAuditTrace(response.workflow_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to query business API')
      void refreshAuditHistory(true)
    } finally {
      setLoading(false)
    }
  }

  // Map Backend Response -> UI Displays
  const activeAgentsList = useMemo<HiveAgent[]>(() => agentDirectory.map((agent) => {
    const sourceResults = queryResult?.specialist_results ?? selectedTrace?.specialist_results ?? []
    const sourceAdvisor = queryResult?.advisor_result ?? selectedTrace?.advisor_result ?? null
    const sourceDecision = queryResult?.guard_decision ?? selectedTrace?.guard.decision ?? ''
    const sourceInvoked = queryResult?.invoked_agents ?? selectedTrace?.invoked_agents ?? []
    const result = sourceResults.find((item) => item.agent === agent.id)
    let state: HiveState = 'Idle'
    let note = agent.purpose
    let selectedByQueen = false

    if (loading) {
      if (agent.id === 'queen') {
        state = 'Routing'
        note = 'Routing the current question'
      } else if (agent.id === 'audit') {
        state = 'Working'
        note = 'Waiting to record this query'
      } else {
        note = agent.id === 'advisor' || agent.id === 'guard'
          ? 'Waiting for specialist results'
          : 'Waiting for Queen Bee routing'
      }
    } else if (selectedTrace?.status === 'failed' && (!queryResult || selectedTrace.trace_id === queryResult.workflow_id)) {
      if (agent.id === 'queen' || agent.id === 'audit') {
        state = 'Failure'
        note = agent.id === 'queen' ? 'Query pipeline failed before routing completed' : 'Failed query trace recorded'
      } else if (['sales', 'customer', 'finance', 'inventory'].includes(agent.id)) {
        selectedByQueen = sourceInvoked.includes(agent.id)
        state = result?.status === 'success'
          ? 'Success'
          : result?.status === 'partial'
            ? 'Partial'
            : result?.status === 'failed'
              ? 'Failure'
              : 'Idle'
        note = result?.summary ?? 'No result recorded before pipeline failure'
      } else if (agent.id === 'advisor') {
        state = sourceAdvisor?.status === 'success' ? 'Success' : sourceAdvisor?.status === 'partial' ? 'Partial' : sourceAdvisor ? 'Failure' : 'Idle'
        note = sourceAdvisor?.summary ?? 'Advisor did not receive a complete specialist result'
      } else if (agent.id === 'guard') {
        state = sourceDecision ? 'Success' : 'Idle'
        note = sourceDecision || 'Guard was not reached'
      }
    } else if (!queryResult && !selectedTrace) {
      state = agent.id === 'audit' && !auditHistoryLoading && auditHistory.length > 0 ? 'Success' : 'Idle'
      note = agent.id === 'audit' ? `${auditHistory.length} persisted trace${auditHistory.length === 1 ? '' : 's'}` : agent.purpose
    } else if (agent.id === 'queen') {
      state = 'Success'
      note = `Routed to ${sourceInvoked.join(', ') || 'no specialists'}`
    } else if (['sales', 'customer', 'finance', 'inventory'].includes(agent.id)) {
      selectedByQueen = sourceInvoked.includes(agent.id)
      state = result?.status === 'success'
        ? 'Success'
        : result?.status === 'partial'
          ? 'Partial'
          : result?.status === 'failed'
            ? 'Failure'
            : 'Idle'
      note = result?.summary ?? 'Not selected for this query'
    } else if (agent.id === 'advisor') {
      state = sourceAdvisor?.status === 'success'
        ? 'Success'
        : sourceAdvisor?.status === 'partial'
          ? 'Partial'
          : sourceAdvisor ? 'Failure' : 'Idle'
      note = sourceAdvisor?.summary ?? 'No Advisor result was recorded'
    } else if (agent.id === 'guard') {
      state = sourceDecision ? 'Success' : 'Idle'
      note = sourceDecision || 'No Guard decision was recorded'
    } else if (agent.id === 'audit') {
      state = selectedTrace?.status === 'failed' ? 'Failure' : selectedTrace ? 'Success' : 'Working'
      note = selectedTrace ? `Trace ${selectedTrace.trace_id} · ${selectedTrace.status}` : 'Persisting query trace'
    }

    return { ...agent, state, note, selectedByQueen }
  }), [queryResult, loading, auditHistory.length, auditHistoryLoading, selectedTrace])

  const contextSpecialists = selectedTrace?.specialist_results ?? queryResult?.specialist_results ?? []
  const contextAdvisor = selectedTrace?.advisor_result ?? queryResult?.advisor_result ?? null
  const contextGuardDecision = selectedTrace?.guard.decision ?? queryResult?.guard_decision ?? ''
  const contextGuardExplanations = contextGuardDecision ? parseGuardExplanations(contextGuardDecision) : []
  const contextInvokedAgents = queryResult?.invoked_agents ?? selectedTrace?.invoked_agents ?? []

  const evidenceList = useMemo<EvidenceItem[]>(() => {
    if (!queryResult) return []
    const items: EvidenceItem[] = []

    // Collect evidence from specialists
    queryResult.specialist_results.forEach((spec: AgentResponse) => {
      spec.evidence.forEach((ev) => {
        items.push({
          label: `${spec.agent.toUpperCase()} - ${ev.metric}`,
          value: displayValue(ev.value),
        })
      })
    })

    // Add advisor summary if available
    if (queryResult.advisor_result) {
      items.push({
        label: 'ADVISOR SUMMARY',
        value: queryResult.advisor_result.summary,
      })
      queryResult.advisor_result.evidence.forEach((ev) => {
        items.push({
          label: `ADVISOR - ${ev.metric}`,
          value: displayValue(ev.value),
        })
      })
    }

    return items
  }, [queryResult])

  const recommendationsList = useMemo<Recommendation[]>(() => {
    if (!queryResult) return []
    const recs: Recommendation[] = []
    const explanations = parseGuardExplanations(queryResult.guard_decision)
    const allResults: AgentResponse[] = [queryResult.advisor_result]
    const matchingAudit = selectedTrace?.trace_id === queryResult.workflow_id ? selectedTrace : null
    allResults.forEach((res) => {
      res.recommended_actions.forEach((act: RecommendedAction) => {
        const { action, references } = splitActionEvidence(act.type)
        const explanation = explanations.find((item) => item.action === action)
        recs.push({
          title: `${res.agent.toUpperCase()}: ${action.replace(/_/g, ' ')}`,
          action,
          risk: explanation?.classification ?? 'Unknown',
          state: actionState(action, explanation, matchingAudit),
          detail: explanation?.reason ?? 'Guard classification is unavailable.',
          evidenceReferences: references,
        })
      })
    })

    return recs
  }, [queryResult, selectedTrace])

  const guardExplanations = queryResult ? parseGuardExplanations(queryResult.guard_decision) : []
  const guardStatus = queryResult ? guardState(queryResult.guard_decision) : 'not_evaluated'
  const businessMetrics = [
    {
      label: 'Business health',
      value: valueWhenReady(health, (data) => `${data.score}/100`),
      detail: 'Backend demo summary',
      tone: 'gold',
    },
    {
      label: 'Specialists routed',
      value: queryResult ? String(queryResult.invoked_agents.length) : '—',
      detail: queryResult ? queryResult.invoked_agents.join(', ') || 'No specialist selected' : 'Run a query to measure',
      tone: 'blue',
    },
    {
      label: 'Evidence points',
      value: queryResult
        ? String(queryResult.specialist_results.reduce((count, item) => count + item.evidence.length, 0))
        : '—',
      detail: 'From this query response',
      tone: 'green',
    },
    {
      label: 'Approval gate',
      value: queryResult ? (queryResult.approval_required ? 'Required' : 'Clear') : '—',
      detail: queryResult?.approval_required ? 'Proposals await human review' : 'No approval indicated',
      tone: queryResult?.approval_required ? 'coral' : 'green',
    },
  ]
  const customerResult = queryResult?.specialist_results.find((item) => item.agent === 'customer')
  const comparisonValues = customerResult
    ? {
        previousCount: numberValue(readEvidence(customerResult, 'previous_period_complaints')),
        currentCount: numberValue(readEvidence(customerResult, 'current_period_complaints')),
        previousRate: numberValue(readEvidence(customerResult, 'previous_period_complaint_rate_pct')),
        currentRate: numberValue(readEvidence(customerResult, 'current_period_complaint_rate_pct')),
        previousStart: readEvidence(customerResult, 'previous_period_start'),
        previousEnd: readEvidence(customerResult, 'previous_period_end'),
        currentStart: readEvidence(customerResult, 'current_period_start'),
        currentEnd: readEvidence(customerResult, 'current_period_end'),
      }
    : null
  const selectedAgent = agentDirectory.find((agent) => agent.id === selectedAgentId) ?? agentDirectory[0]
  const selectedAgentResult = contextSpecialists.find(
    (result) => result.agent === selectedAgentId,
  )
  const quantitativeEvidence = queryResult?.specialist_results.flatMap((result) =>
    result.evidence.flatMap((item) => {
      const value = numberValue(item.value)
      return value === null ? [] : [{ label: `${result.agent} · ${item.metric}`, value }]
    }),
  ) ?? []
  const maxEvidenceValue = Math.max(1, ...quantitativeEvidence.map((item) => Math.abs(item.value)))

  return (
    <div className="dashboard-shell">
      <aside className="sidebar">
        <a className="brand-lockup" href="#overview" aria-label="BizzyBee dashboard home">
          <span className="brand-bee">🐝</span>
          <span><strong>BizzyBee</strong><small>AI BUSINESS DESK</small></span>
        </a>
        <nav className="sidebar-nav" aria-label="Dashboard sections">
          <a className="nav-link selected" href="#overview"><span>⌂</span> Overview</a>
          <a className="nav-link" href="#ask"><span>✳</span> Ask Bizzy</a>
          <a className="nav-link" href="#hive"><span>⬡</span> Agent hive</a>
          <a className="nav-link" href="#analytics"><span>▥</span> Analytics</a>
          <a className="nav-link" href="#governance"><span>◈</span> Governance</a>
          <a className="nav-link" href="#audit"><span>◷</span> Audit trail</a>
        </nav>
        <div className="sidebar-note">
          <span className="live-dot" />
          <div><strong>Local demo</strong><small>Synthetic sample data</small></div>
        </div>
        <div className="sidebar-footer">BIZZYBEE AI <span>v0.1</span></div>
      </aside>

      <main className="dashboard-main" id="overview">
        <header className="topbar">
          <div>
            <p className="eyebrow">WORKSPACE / OVERVIEW</p>
            <h1>Good day, business owner <span className="wave">✦</span></h1>
            <p className="subline">Here’s the latest read on your business operations.</p>
          </div>
          <div className="topbar-tools">
            <span className="demo-tag"><span className="live-dot" /> SYNTHETIC DEMO</span>
            <button className="icon-button" type="button" title="Refresh audit history" aria-label="Refresh audit history" onClick={() => void refreshAuditHistory()} disabled={auditHistoryLoading}>↻</button>
            <div className="profile-mark" aria-label="Business owner">BO</div>
          </div>
        </header>

        <section className="welcome-band" aria-label="Welcome">
          <div className="welcome-copy">
            <p className="welcome-kicker">YOUR BUSINESS, IN THE CLEAR</p>
            <h2>Small signals. <span>Smarter moves.</span></h2>
            <p>Ask your hive a question and get answers grounded in the data returned by your local demo.</p>
            <a href="#ask" className="welcome-link">Ask your hive <span>→</span></a>
          </div>
          <div className="honeycomb-art" aria-hidden="true">
            <span className="honey-cell cell-one">✦</span>
            <span className="honey-cell cell-two">●</span>
            <span className="honey-cell cell-three">🐝</span>
            <span className="honey-cell cell-four">✧</span>
            <span className="honey-cell cell-five">●</span>
          </div>
        </section>

        <section className="kpi-grid" aria-label="Business health KPIs">
          {businessMetrics.map((metric) => (
            <article className={`kpi-card tone-${metric.tone}`} key={metric.label}>
              <div className="kpi-topline"><span>{metric.label}</span><span className="kpi-glyph">{metric.tone === 'gold' ? '✦' : metric.tone === 'blue' ? '⬡' : metric.tone === 'coral' ? '◉' : '✓'}</span></div>
              <strong className="kpi-value">{metric.value}</strong>
              <p>{metric.detail}</p>
            </article>
          ))}
        </section>
        <p className="provenance-note">Business health score is the backend’s synthetic demo summary. Query metrics below come from specialist evidence.</p>

        <section className="kpi-grid" aria-label="Live specialist summaries">
          <article className="kpi-card tone-blue"><div className="kpi-topline"><span>Sales trend (WoW)</span></div><strong className="kpi-value">{valueWhenReady(sales, (view) => formatPct(view.revenueChangePct))}</strong><p>Sales service summary</p></article>
          <article className="kpi-card tone-green"><div className="kpi-topline"><span>Overdue invoices</span></div><strong className="kpi-value">{valueWhenReady(finance, (view) => view.overdueInvoiceCount === null ? '—' : String(view.overdueInvoiceCount))}</strong><p>Finance service summary</p></article>
          <article className="kpi-card tone-coral"><div className="kpi-topline"><span>Out of stock</span></div><strong className="kpi-value">{valueWhenReady(inventory, (view) => String(view.riskCounts.out_of_stock))}</strong><p>Inventory service summary</p></article>
        </section>
        <div className="team-panels" aria-label="Sales inventory and alerts">
          <AlertsPanel state={alerts} onRetry={reload} />
          <div className="team-panel-grid">
            <SalesPanel state={sales} onRetry={reload} />
            <InventoryPanel state={inventory} onRetry={reload} />
          </div>
        </div>
        <FinancePanel />

        <section className="panel ask-panel" id="ask">
          <div className="section-heading">
            <div className="section-icon honey-icon">✳</div>
            <div><p className="section-kicker">YOUR AI ASSISTANT</p><h2>Ask BizzyBee</h2></div>
            <span className="section-side-note">Local data · No external actions</span>
          </div>
          <form className="query-form" onSubmit={submitQuery}>
            <label className="language-field">
              <span>Language</span>
              <select value={selectedLanguage} onChange={(event) => setSelectedLanguage(event.target.value)}>
                {LANGUAGES.map((language) => <option key={language.code} value={language.code}>{language.label}</option>)}
              </select>
            </label>
            <label className="question-field">
              <span>Your business question</span>
              <textarea rows={2} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about sales, customers, cash flow or inventory..." />
            </label>
            <button className="primary-button" type="submit" disabled={loading || !question.trim()}>
              {loading ? <><span className="spinner" /> Reading data...</> : <>Ask the hive <span>→</span></>}
            </button>
          </form>
          <div className="query-footnote">
            <span>{languageHint}</span>
            {lastSubmitted && <span className="last-submitted">Last asked: {lastSubmitted}</span>}
          </div>
          {error && <p className="inline-error" role="alert">{error}</p>}
        </section>

        <section className="panel hive-panel" id="hive">
          <div className="section-heading">
            <div className="section-icon hive-icon">⬡</div>
            <div><p className="section-kicker">SPECIALISTS AT WORK</p><h2>Your agent hive</h2></div>
            <span className="section-side-note">{queryResult ? `${queryResult.invoked_agents.length} specialists routed` : '8 agents · Ready to help'}</span>
          </div>
          <div className="hive-grid">
            {activeAgentsList.map((agent) => (
              <button
                className={`agent-card ${selectedAgentId === agent.id ? 'agent-selected' : ''}`}
                data-routed={agent.selectedByQueen ? 'true' : 'false'}
                type="button"
                key={agent.id}
                aria-pressed={selectedAgentId === agent.id}
                onClick={() => setSelectedAgentId(agent.id)}
              >
                <span className={`agent-hex hex-${agent.color}`}>{agent.glyph}</span>
                <span className="agent-card-copy"><strong>{agent.name}</strong><small>{agent.note}</small></span>
                <span className={`agent-state state-${agent.state.toLowerCase()}`}><i />{agent.state}</span>
                {agent.selectedByQueen && <span className="queen-route-mark" title="Selected by Queen Bee">ROUTED</span>}
              </button>
            ))}
          </div>
          <div className="bee-detail-panel" aria-live="polite">
            <div className="bee-detail-heading">
              <span className={`agent-hex detail-bee-hex hex-${selectedAgent.color}`}>{selectedAgent.glyph}</span>
              <div className="bee-detail-title"><p className="section-kicker">BEE WORKSPACE</p><h3>{selectedAgent.name}</h3><p>{selectedAgent.purpose}</p></div>
              <span className={`detail-status state-${(activeAgentsList.find((agent) => agent.id === selectedAgentId)?.state ?? 'Idle').toLowerCase()}`}>
                <i />{activeAgentsList.find((agent) => agent.id === selectedAgentId)?.state ?? 'Idle'}
              </span>
            </div>
            <div className="bee-detail-content">
              {selectedAgentId === 'queen' && <div className="detail-section">
                <div className="detail-section-title"><strong>Routing decision</strong><span>{contextInvokedAgents.length} selected</span></div>
                {loading ? <p className="empty-state">Queen Bee is classifying this question.</p> : contextInvokedAgents.length === 0 ? (
                  <p className="empty-state">Queen Bee has not selected any specialists for a completed query.</p>
                ) : <>
                  <p className="detail-summary">{selectedTrace?.query ?? lastSubmitted ?? 'Latest business question'}</p>
                  <div className="route-chips">{contextInvokedAgents.map((agentId) => {
                    const agent = agentDirectory.find((item) => item.id === agentId)
                    return <span className={`route-chip ${agent ? `route-${agent.color}` : ''}`} key={agentId}>{agent?.glyph ?? '⬡'} {agent?.name ?? agentId}</span>
                  })}</div>
                  {selectedTrace?.status === 'failed' && <p className="inline-error">This query failed before routing completed.</p>}
                </>}
              </div>}

              {['sales', 'customer', 'finance', 'inventory'].includes(selectedAgentId) && <div className="detail-section">
                {!selectedAgentResult ? (
                  <p className="empty-state">{contextInvokedAgents.includes(selectedAgentId) ? 'This agent was selected, but no result was recorded.' : queryResult || selectedTrace ? 'Queen Bee did not route this agent for the selected query.' : 'Run a query to see this Bee’s actual backend findings.'}</p>
                ) : <>
                  <div className="detail-section-title"><strong>Latest findings</strong><span className={`badge status-${selectedAgentResult.status}`}>{selectedAgentResult.status}</span></div>
                  <p className="detail-summary">{selectedAgentResult.summary}</p>
                  {selectedAgentResult.evidence.length === 0 ? <p className="empty-state">No evidence fields were returned.</p> : (
                    <div className="bee-evidence-grid">{selectedAgentResult.evidence.map((item, index) => <div className="bee-evidence-tile" key={`${item.metric}-${index}`}><span>{item.metric.replace(/_/g, ' ')}</span><strong>{displayValue(item.value)}</strong></div>)}</div>
                  )}
                  {selectedAgentResult.recommended_actions.length > 0 && <div className="detail-proposals"><strong>Agent proposals</strong>{selectedAgentResult.recommended_actions.map((action, index) => <span key={`${action.type}-${index}`}>{splitActionEvidence(action.type).action.replace(/_/g, ' ')} · agent label {action.risk_level}</span>)}</div>}
                  {selectedAgentId === 'customer' && <p className="data-origin-note">Complaint comparison uses the added synthetic customer feedback, returns, refunds, product and dated customer-sales CSVs.</p>}
                </>}
              </div>}

              {selectedAgentId === 'advisor' && <div className="detail-section">
                {!contextAdvisor ? <p className="empty-state">Advisor has no result for the selected query.</p> : <>
                  <div className="detail-section-title"><strong>Evidence-based guidance</strong><span className={`badge status-${contextAdvisor.status}`}>{contextAdvisor.status}</span></div>
                  <p className="detail-summary">{contextAdvisor.summary}</p>
                  <h4>Recommendations</h4>
                  {contextAdvisor.recommended_actions.length === 0 ? <p className="empty-state">No recommendations were supported by the returned evidence.</p> : <div className="bee-recommendations">{contextAdvisor.recommended_actions.map((action, index) => {
                    const parsed = splitActionEvidence(action.type)
                    const explanation = contextGuardExplanations.find((item) => item.action === parsed.action)
                    const state = actionState(parsed.action, explanation, selectedTrace)
                    return <div className="bee-recommendation" key={`${parsed.action}-${index}`}><div><span className={`badge ${stateClass(state)}`}>{state}</span><strong>{parsed.action.replace(/_/g, ' ')}</strong></div><p>{explanation?.reason ?? 'Guard explanation unavailable.'}</p>{parsed.references.length > 0 && <small>Evidence · {parsed.references.join(', ')}</small>}</div>
                  })}</div>}
                  <h4>Supporting evidence</h4>
                  {contextAdvisor.evidence.length === 0 ? <p className="empty-state">Advisor returned no evidence.</p> : <div className="bee-evidence-grid">{contextAdvisor.evidence.map((item, index) => <div className="bee-evidence-tile" key={`${item.metric}-${index}`}><span>{item.metric.replace(/_/g, ' ')}</span><strong>{displayValue(item.value)}</strong></div>)}</div>}
                </>}
              </div>}

              {selectedAgentId === 'guard' && <div className="detail-section">
                {!contextGuardDecision ? <p className="empty-state">Guard has not evaluated actions for the selected query.</p> : <>
                  <div className="detail-section-title"><strong>Policy evaluation</strong><span className={`badge guard-${guardState(contextGuardDecision)}`}>{guardState(contextGuardDecision).replaceAll('_', ' ')}</span></div>
                  <p className="detail-summary">{contextGuardDecision}</p>
                  <p className={`approval-state ${(selectedTrace?.approval_required ?? queryResult?.approval_required) ? 'approval-needed' : 'approval-clear'}`}>{(selectedTrace?.approval_required ?? queryResult?.approval_required) ? 'Awaiting Approval · Human review required' : 'No approval required by this evaluation'}</p>
                  {contextGuardExplanations.length === 0 ? <p className="empty-state">No per-action explanations were returned.</p> : <div className="guard-explanations">{contextGuardExplanations.map((item, index) => <div className="guard-explanation" key={`${item.action}-${index}`}><span className={`risk-dot risk-dot-${item.classification.toLowerCase()}`} /><div><strong>{item.action.replace(/_/g, ' ')}</strong><p>{item.classification} · {item.reason}</p></div></div>)}</div>}
                  <p className="data-origin-note">Guard evaluates proposals only. Approval controls may record authorised decisions; this frontend does not execute external business actions.</p>
                </>}
              </div>}

              {selectedAgentId === 'audit' && <div className="detail-section">
                {selectedTrace ? <>
                  <div className="detail-section-title"><strong>Persisted trace</strong><span className={`badge ${selectedTrace.status === 'completed' ? 'status-success' : 'status-failed'}`}>{selectedTrace.status}</span></div>
                  <p className="detail-summary">{selectedTrace.query || 'Query text unavailable'}</p>
                  <div className="bee-evidence-grid audit-evidence-grid">
                    <div className="bee-evidence-tile"><span>Trace ID</span><strong>{selectedTrace.trace_id}</strong></div>
                    <div className="bee-evidence-tile"><span>Agents routed</span><strong>{selectedTrace.invoked_agents.join(', ') || 'None recorded'}</strong></div>
                    <div className="bee-evidence-tile"><span>Proposed</span><strong>{selectedTrace.proposed_actions.length}</strong></div>
                    <div className="bee-evidence-tile"><span>Executed in audit</span><strong>{selectedTrace.executed_actions.length}</strong></div>
                  </div>
                  <a className="detail-anchor-link" href="#audit">Open full trace detail <span>→</span></a>
                </> : auditHistoryLoading ? <p className="empty-state">Loading persisted audit history…</p> : auditHistoryError ? <p className="inline-error">{auditHistoryError}</p> : auditHistory.length === 0 ? <p className="empty-state">No audit traces have been persisted.</p> : <>
                  <p className="detail-summary">{auditHistory.length} recent persisted traces are available.</p>
                  <div className="route-chips">{auditHistory.slice(0, 5).map((record) => <button className="trace-chip" key={record.trace_id} type="button" onClick={() => void openAuditTrace(record.trace_id)}>{record.status} · {record.trace_id.slice(0, 8)}</button>)}</div>
                </>}
              </div>}
            </div>
          </div>
        </section>

        <section className="analytics-grid" id="analytics">
          <article className="panel analytics-panel">
            <div className="section-heading compact-heading">
              <div className="section-icon chart-icon">▥</div>
              <div><p className="section-kicker">QUERY-DERIVED METRICS</p><h2>Business analytics</h2></div>
              <span className="section-side-note">{queryResult ? 'Latest analysis' : 'Waiting for query'}</span>
            </div>
            {comparisonValues && comparisonValues.previousCount !== null && comparisonValues.currentCount !== null ? (
              <div className="comparison-chart">
                <div className="chart-title-row"><div><strong>Customer complaint reports</strong><small>Two equal seven-day windows</small></div><span className="chart-badge">SYNTHETIC</span></div>
                <div className="chart-axis"><span>0</span><span>{formatNumber(Math.max(comparisonValues.previousCount, comparisonValues.currentCount))} reports</span></div>
                <div className="chart-row">
                  <div className="chart-label"><strong>Previous</strong><small>{String(comparisonValues.previousStart)} – {String(comparisonValues.previousEnd)}</small></div>
                  <div className="bar-track"><div className="bar-fill bar-previous" style={{ width: `${Math.max(3, comparisonValues.previousCount / Math.max(1, comparisonValues.previousCount, comparisonValues.currentCount) * 100)}%` }} /></div>
                  <strong className="bar-value">{formatNumber(comparisonValues.previousCount, 0)}</strong>
                </div>
                <div className="chart-row">
                  <div className="chart-label"><strong>Current</strong><small>{String(comparisonValues.currentStart)} – {String(comparisonValues.currentEnd)}</small></div>
                  <div className="bar-track"><div className="bar-fill bar-current" style={{ width: `${Math.max(3, comparisonValues.currentCount / Math.max(1, comparisonValues.previousCount, comparisonValues.currentCount) * 100)}%` }} /></div>
                  <strong className="bar-value">{formatNumber(comparisonValues.currentCount, 0)}</strong>
                </div>
                <div className="chart-insight"><span>↗</span> Complaint reports changed by <strong>{formatNumber(numberValue(readEvidence(customerResult, 'complaint_count_change_pct')))}%</strong>; affected-unit rate moved from <strong>{formatNumber(comparisonValues.previousRate, 4)}%</strong> to <strong>{formatNumber(comparisonValues.currentRate, 4)}%</strong>.</div>
              </div>
            ) : queryResult ? (
              <div className="snapshot-chart">
                <p className="empty-state">This query returned point-in-time evidence rather than a dated comparison.</p>
                {quantitativeEvidence.length > 0 ? quantitativeEvidence.slice(0, 5).map((item) => (
                  <div className="snapshot-row" key={item.label}><span>{item.label}</span><strong>{formatNumber(item.value)}</strong><div className="bar-track"><div className="bar-fill bar-current" style={{ width: `${Math.max(3, Math.abs(item.value) / maxEvidenceValue * 100)}%` }} /></div></div>
                )) : <p className="empty-state">No numeric evidence was returned by the specialists.</p>}
              </div>
            ) : (
              <div className="empty-chart"><div className="empty-chart-mark">▥</div><strong>Your analytics will appear here</strong><p>Run a query to chart values returned by the specialists. No sample chart values are prefilled.</p></div>
            )}
            {queryResult && <p className="chart-source">Source: current query’s specialist evidence · Synthetic demonstration data</p>}
          </article>

          <article className="panel evidence-panel">
            <div className="section-heading compact-heading">
              <div className="section-icon evidence-icon">⌕</div>
              <div><p className="section-kicker">TRACEABLE OUTPUT</p><h2>SQL evidence</h2></div>
              <span className="count-pill">{evidenceList.length}</span>
            </div>
            {evidenceList.length === 0 ? (
              <p className="empty-state">Evidence from specialist results will appear after a query.</p>
            ) : (
              <ul className="evidence-list">
                {evidenceList.map((item, index) => (
                  <li key={`${item.label}-${index}`}><span className="evidence-check">✓</span><div><strong>{item.label}</strong><p>{item.value}</p></div></li>
                ))}
              </ul>
            )}
            <div className="source-records"><span className="source-dot" /> Source records are local synthetic CSV data; no live business system is connected.</div>
          </article>
        </section>

        <section className="governance-grid" id="governance">
          <article className="panel advisor-panel">
            <div className="section-heading compact-heading">
              <div className="agent-hex hex-violet">✦</div>
              <div><p className="section-kicker">SYNTHESIS & GUIDANCE</p><h2>Advisor Bee</h2></div>
              {queryResult && <span className={`badge status-${queryResult.advisor_result.status}`}>{queryResult.advisor_result.status}</span>}
            </div>
            {!queryResult ? <p className="empty-state">Advisor findings will appear after a query.</p> : <>
              <p className="advisor-summary">{queryResult.advisor_result.summary}</p>
              {recommendationsList.length === 0 ? <p className="empty-state">No recommendations supported by the returned evidence.</p> : (
                <ul className="recommendation-list">
                  {recommendationsList.map((item, index) => <li key={`${item.action}-${index}`}>
                    <div className="recommendation-top"><span className={`badge ${stateClass(item.state)}`}>{item.state}</span><span className={`risk-tag risk-${item.risk.toLowerCase()}`}>{item.risk}</span></div>
                    <strong>{item.title}</strong><p>{item.detail}</p>
                    {item.evidenceReferences.length > 0 && <small>Evidence refs · {item.evidenceReferences.join(', ')}</small>}
                  </li>)}
                </ul>
              )}
              <div className="approval-disclaimer">Recommendations are proposals only. This demo does not execute external actions.</div>
            </>}
          </article>

          <article className="panel guard-panel">
            <div className="section-heading compact-heading">
              <div className="agent-hex hex-red">⬡</div>
              <div><p className="section-kicker">POLICY & APPROVAL</p><h2>Guard Bee</h2></div>
              {queryResult && <span className={`badge guard-${guardStatus}`}>{guardStatus.replaceAll('_', ' ')}</span>}
            </div>
            {!queryResult ? <p className="empty-state">Guard decisions will appear after a query.</p> : <>
              <div className={`guard-callout ${queryResult.approval_required ? 'callout-amber' : guardStatus === 'blocked' ? 'callout-red' : 'callout-green'}`}>
                <strong>{queryResult.approval_required ? 'Human approval required' : guardStatus === 'blocked' ? 'Action blocked' : 'No approval required'}</strong>
                <p>{queryResult.guard_decision}</p>
              </div>
              {guardExplanations.length === 0 ? <p className="empty-state">No per-action explanations returned.</p> : <ul className="guard-list">
                {guardExplanations.map((item, index) => <li key={`${item.action}-${index}`}><span className={`risk-dot risk-dot-${item.classification.toLowerCase()}`} /><div><strong>{item.action.replace(/_/g, ' ')}</strong><p>{item.classification} · {item.reason}</p></div></li>)}
              </ul>}
              <div className="approval-disclaimer">Awaiting Approval is not Approved. Only an audit record can confirm execution.</div>
            </>}
          </article>
        </section>

        {workflowAudit && (
          <section className="panel" aria-label="Latest workflow audit event">
            <div className="section-heading"><div><p className="section-kicker">WORKFLOW EVENT</p><h2>Latest workflow audit</h2></div></div>
            <p>Workflow {workflowAudit.workflow_id} · {workflowAudit.evidence_count} evidence items · Guard: {workflowAudit.decision}</p>
            <p>Agents: {workflowAudit.agents.map((agent) => `${agent} (${workflowAudit.statuses[agent] ?? 'unknown'})`).join(', ')}</p>
          </section>
        )}
        {workflowAudit && (
          <section className="panel" aria-label="Workflow approval controls">
            <h2>Approval gate</h2>
            <p>Authorised decisions are recorded only. No external business action is executed.</p>
            <ApprovalControls
              key={workflowAudit.workflow_id}
              event={workflowAudit}
              reload={() => {
                void fetchAuditEvent(workflowAudit.workflow_id)
                  .then(setWorkflowAudit)
                  .catch((err: unknown) => setWorkflowAuditError(err instanceof Error ? err.message : 'Workflow audit event unavailable'))
              }}
            />
          </section>
        )}
        {workflowAuditError && <p className="inline-error">Workflow event unavailable: {workflowAuditError}. Persisted audit history remains separate.</p>}

        <section className="panel audit-panel" id="audit">
          <div className="section-heading">
            <div className="agent-hex hex-teal">◷</div>
            <div><p className="section-kicker">PERSISTENT LOCAL HISTORY</p><h2>Audit Bee</h2></div>
            <button className="quiet-button" type="button" onClick={() => void refreshAuditHistory()} disabled={auditHistoryLoading}>{auditHistoryLoading ? 'Refreshing…' : '↻ Refresh'}</button>
          </div>
          <div className="audit-layout">
            <div className="audit-history-column">
              <h3>Recent traces <span>{auditHistory.length}</span></h3>
              {auditHistoryLoading ? <p className="empty-state" role="status">Loading local audit history…</p> : auditHistoryError ? <p className="inline-error" role="alert">{auditHistoryError}</p> : auditHistory.length === 0 ? <p className="empty-state">No audit history has been recorded.</p> : (
                <div className="trace-list">{auditHistory.map((record) => <button className={`trace-row ${selectedTrace?.trace_id === record.trace_id ? 'trace-selected' : ''}`} key={record.trace_id} type="button" onClick={() => void openAuditTrace(record.trace_id)}>
                  <span className={`trace-status ${record.status === 'completed' ? 'trace-ok' : 'trace-failed'}`} />
                  <span className="trace-row-copy"><strong>{record.query || 'Business query'}</strong><small>{new Date(record.timestamp).toLocaleString()} · {record.trace_id}</small></span>
                  <span className="trace-chevron">›</span>
                </button>)}</div>
              )}
            </div>
            <div className="trace-detail-column">
              <h3>Trace detail</h3>
              {auditDetailLoading ? <p className="empty-state" role="status">Loading trace…</p> : auditDetailError ? <p className="inline-error" role="alert">{auditDetailError}</p> : !selectedTrace ? <p className="empty-state">Select a recent trace to inspect results and action status.</p> : <>
                <div className="trace-meta"><span>{selectedTrace.trace_id}</span><span>{new Date(selectedTrace.timestamp).toLocaleString()}</span></div>
                <p className="trace-question">{selectedTrace.query || 'Query text unavailable'}</p>
                <div className="trace-counts"><span><strong>{selectedTrace.invoked_agents.length}</strong> agents routed</span><span><strong>{selectedTrace.proposed_actions.length}</strong> proposed</span><span><strong>{selectedTrace.executed_actions.length}</strong> executed</span></div>
                <div className="trace-guard"><span className={`badge ${selectedTrace.approval_required ? 'awaiting-approval' : 'proposed'}`}>{selectedTrace.approval_required ? 'Awaiting Approval' : 'No approval required'}</span><p>{selectedTrace.guard.decision}</p></div>
                {selectedTrace.proposed_actions.length > 0 && <div className="trace-actions"><h4>Action status</h4>{selectedTrace.proposed_actions.map((action, index) => {
                  const explanation = selectedTrace.guard.action_explanations.find((item) => item.action === action.type)
                  const state = actionState(action.type, explanation, selectedTrace)
                  return <div className="trace-action" key={`${action.type}-${index}`}><div><strong>{action.type.replace(/_/g, ' ')}</strong><small>{explanation?.reason ?? 'Awaiting policy details'}</small></div><span className={`badge ${stateClass(state)}`}>{state}</span></div>
                })}</div>}
                {selectedTrace.specialist_results.length > 0 && <div className="trace-agents"><h4>Source results</h4>{selectedTrace.specialist_results.map((result, index) => <details key={`${result.agent}-${index}`}><summary>{result.agent} · {result.status}</summary><p>{result.summary}</p>{result.evidence.map((item, evidenceIndex) => <small key={`${item.metric}-${evidenceIndex}`}>{item.metric}: {displayValue(item.value)}</small>)}</details>)}</div>}
                {selectedTrace.failure_type && <p className="inline-error">Pipeline failed: {selectedTrace.failure_type}</p>}
              </>}
            </div>
          </div>
        </section>
        <footer className="dashboard-footer"><span>🐝 BizzyBee AI</span><span>Local demonstration · Synthetic data · No actions executed</span></footer>
      </main>
    </div>
  )
}