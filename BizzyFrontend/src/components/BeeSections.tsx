import type { AgentStatus, RecommendedAction } from '../types/contracts'
import { describeRecord, humaniseKey } from '../utils/evidence'

export function BeeSummary({ status, summary }: { status: AgentStatus; summary: string }) {
  return (
    <>
      {status === 'partial' ? (
        <p className="bee-warning" role="note">
          Some source data was missing, so these figures may be incomplete.
        </p>
      ) : null}
      <p className="bee-summary">{summary}</p>
    </>
  )
}

export function BeeActions({ actions }: { actions: RecommendedAction[] }) {
  if (actions.length === 0) return null

  return (
    <>
      <h3 className="bee-subheading">Suggested next step</h3>
      <ul className="bee-rows">
        {actions.map((action, index) => (
          <li key={`${action.type}-${index}`}>
            <div className="bee-row-head">
              <span className={`badge ${action.risk_level.toLowerCase()}`}>{action.risk_level}</span>
              <strong>{humaniseKey(action.type)}</strong>
            </div>
            {action.reason ? <p>{action.reason}</p> : null}
            {action.parameters && Object.keys(action.parameters).length > 0 ? (
              <p className="bee-params">{describeRecord(action.parameters)}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  )
}
