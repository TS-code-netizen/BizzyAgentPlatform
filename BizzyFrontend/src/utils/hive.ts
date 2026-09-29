import type { AuditEvent, QueryResponse } from '../types/contracts'

export const agentDirectory = [
  { id: 'queen', name: 'Queen Bee', glyph: '♛', purpose: 'Interprets questions and routes specialists.' },
  { id: 'sales', name: 'Sales Bee', glyph: '↗', purpose: 'Revenue, historical costs and margins.' },
  { id: 'finance', name: 'Finance Bee', glyph: '$', purpose: 'Invoices, expenses and cash flow.' },
  { id: 'inventory', name: 'Inventory Bee', glyph: '▦', purpose: 'Stock availability and replenishment risk.' },
  { id: 'customer', name: 'Customer Bee', glyph: '♡', purpose: 'Complaints, enquiries and buying behaviour.' },
  { id: 'advisor', name: 'Advisor Bee', glyph: '✦', purpose: 'Combines evidence into recommendations.' },
  { id: 'guard', name: 'Guard Bee', glyph: '⬡', purpose: 'Deterministic action policy and approvals.' },
  { id: 'audit', name: 'Audit Bee', glyph: '◷', purpose: 'Persists evidence and decisions.' },
] as const

export function hiveState(agent: string, result: QueryResponse | null, loading: boolean, error: string | null, audit: AuditEvent | null, auditStatus?: string): string {
  if (loading) return agent === 'queen' ? 'Processing' : 'Waiting'
  if (error) return agent === 'queen' ? 'Request failed' : 'Unknown'
  if (!result) return 'Idle'
  if (agent === 'queen') return result.invoked_agents.length ? 'Routed' : 'Needs clarification'
  if (agent === 'guard') return result.guard_decision.split(':', 1)[0].replaceAll('_', ' ')
  if (agent === 'audit') return audit ? 'Recorded' : auditStatus === 'error' ? 'Unavailable' : 'Loading'
  const response = agent === 'advisor' ? result.advisor_result : result.specialist_results.find((item) => item.agent === agent)
  return response?.status ?? (result.invoked_agents.includes(agent) ? 'Result missing' : 'Not selected')
}
