import { useEffect, useState } from 'react'
import { apiRoutes, requestJson } from '../api/client'
import type { AuditEvent } from '../types/contracts'

export function ApprovalControls({ event, reload }: { event: AuditEvent; reload: () => void }) {
  const [approver, setApprover] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    requestJson<{ approver: boolean }>(apiRoutes.me, 'permissions', { signal: controller.signal })
      .then((identity) => setApprover(identity.approver))
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Cannot load permissions.') })
    return () => controller.abort()
  }, [])
  async function decide(actionId: string, approve: boolean) {
    setBusy(true)
    setError('')
    try {
      await requestJson(approve ? apiRoutes.approveAction(encodeURIComponent(actionId)) : apiRoutes.rejectAction(encodeURIComponent(actionId)), 'the approval decision', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: reason.trim() }),
      })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Decision was not recorded.')
    } finally {
      setBusy(false)
    }
  }
  return <div>
    <p>Decisions are recorded only. No payment, message or purchase is executed.</p>
    {error && <p role="alert">{error}</p>}
    {approver ? <label>Decision reason <input value={reason} maxLength={1000} onChange={(change) => setReason(change.target.value)} /></label> : <p>Only the designated owner can approve or reject.</p>}
    <ul>{event.actions.map((action, index) => <li key={action.action_id ?? index}>
      {action.type}: {action.state ?? action.risk_level}
      {approver && action.action_id && action.state === 'pending' && event.decision !== 'blocked' && <>
        <button disabled={busy || !reason.trim()} onClick={() => void decide(action.action_id!, true)}>Approve draft</button>
        <button disabled={busy || !reason.trim()} onClick={() => void decide(action.action_id!, false)}>Reject draft</button>
      </>}
    </li>)}</ul>
  </div>
}
