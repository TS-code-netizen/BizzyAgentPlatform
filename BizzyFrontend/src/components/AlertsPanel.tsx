import { useState } from 'react'
import type { LoadState } from '../hooks/useSalesInventory'
import type { AlertSeverity, BusinessAlert } from '../types/contracts'
import { humaniseKey } from '../utils/evidence'
import { formatDate, plural } from '../utils/format'
import { PanelState } from './PanelState'
import './SalesInventory.css'

const ALERT_PREVIEW = 5

const SEVERITY_ORDER: AlertSeverity[] = ['critical', 'warning', 'info']

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
}

const SEVERITY_TONE: Record<AlertSeverity, 'red' | 'amber' | 'idle'> = {
  critical: 'red',
  warning: 'amber',
  info: 'idle',
}

function severityOf(alert: BusinessAlert): AlertSeverity {
  return SEVERITY_ORDER.includes(alert.severity) ? alert.severity : 'info'
}

function AlertList({ alerts }: { alerts: BusinessAlert[] }) {
  const [expanded, setExpanded] = useState(false)

  if (alerts.length === 0) {
    return <p className="bee-muted">No sales or inventory issues need attention right now.</p>
  }

  const sorted = [...alerts].sort(
    (a, b) => SEVERITY_ORDER.indexOf(severityOf(a)) - SEVERITY_ORDER.indexOf(severityOf(b)),
  )
  const visible = expanded ? sorted : sorted.slice(0, ALERT_PREVIEW)
  const asOf = sorted[0]?.as_of

  return (
    <>
      <ul className="bee-chips" aria-label="Alert counts by severity">
        {SEVERITY_ORDER.map((severity) => (
          <li key={severity} className={`bee-chip ${SEVERITY_TONE[severity]}`}>
            <span className="bee-chip-count">{sorted.filter((alert) => severityOf(alert) === severity).length}</span>
            <span>{SEVERITY_LABEL[severity]}</span>
          </li>
        ))}
      </ul>

      <ul className="bee-rows">
        {visible.map((alert) => {
          const severity = severityOf(alert)
          const action = alert.recommended_action
          return (
            <li key={alert.alert_id}>
              <div className="bee-row-head">
                <span className={`badge ${SEVERITY_TONE[severity]}`}>{SEVERITY_LABEL[severity]}</span>
                <strong>{alert.title}</strong>
                <span className="bee-id">{humaniseKey(alert.agent)} Bee</span>
              </div>
              <p>{alert.message}</p>
              {action ? (
                <p className="bee-params">
                  Next step: {humaniseKey(action.type)} ({action.risk_level}
                  {action.risk_level === 'GREEN' ? '' : ', needs approval'})
                </p>
              ) : null}
            </li>
          )
        })}
      </ul>

      {sorted.length > ALERT_PREVIEW ? (
        <button type="button" className="secondary bee-toggle" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Show fewer' : `Show all ${plural(sorted.length, 'alert')}`}
        </button>
      ) : null}

      {asOf ? <p className="bee-footnote">Monitoring as of {formatDate(asOf, true)}.</p> : null}
    </>
  )
}

interface AlertsPanelProps {
  state: LoadState<BusinessAlert[]>
  onRetry: () => void
}

export function AlertsPanel({ state, onRetry }: AlertsPanelProps) {
  return (
    <section className="panel bee-panel" aria-labelledby="alerts-heading">
      <header className="bee-panel-header">
        <h2 id="alerts-heading">Priority alerts</h2>
        <p className="bee-muted">Sales and inventory monitoring</p>
      </header>
      <PanelState state={state} onRetry={onRetry}>
        {(alerts) => <AlertList alerts={alerts} />}
      </PanelState>
    </section>
  )
}
