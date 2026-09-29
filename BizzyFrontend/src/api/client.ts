import type { AuditEvent, AuditHistoryResponse, AuditRecord, BusinessHealthResponse, QueryRequest, QueryResponse } from '../types/contracts'
import { accessToken } from '../auth'
import { fetchJson } from './transport'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export const apiRoutes = {
  me: `${API_BASE_URL}/me`,
  query: `${API_BASE_URL}/query`,
  businessHealth: `${API_BASE_URL}/business-health`,
  salesSummary: `${API_BASE_URL}/sales/summary`,
  customerOpportunities: `${API_BASE_URL}/customers/opportunities`,
  financeHealth: `${API_BASE_URL}/finance/health`,
  financeSummary: `${API_BASE_URL}/finance/summary`,
  financeReport: `${API_BASE_URL}/finance/report`,
  inventoryStatus: `${API_BASE_URL}/inventory/status`,
  salesInventoryAlerts: `${API_BASE_URL}/sales-inventory/alerts`,
  approveAction: (id: string) => `${API_BASE_URL}/actions/${id}/approve`,
  rejectAction: (id: string) => `${API_BASE_URL}/actions/${id}/reject`,
  auditTrail: (workflowId: string) => `${API_BASE_URL}/audit/${encodeURIComponent(workflowId)}`,
  auditHistory: `${API_BASE_URL}/audit`,
  auditTrace: (traceId: string) => `${API_BASE_URL}/audit/${encodeURIComponent(traceId)}`,
}

export async function requestJson<T>(url: string, label: string, init?: RequestInit): Promise<T> {
  const timeout = AbortSignal.timeout(30000)
  const signal = init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout
  try {
    const token = await accessToken()
    const headers = new Headers(init?.headers)
    if (token) headers.set('Authorization', `Bearer ${token}`)
    return await fetchJson<T>(url, label, { ...init, headers }, signal)
  } catch (error) {
    if (init?.signal?.aborted) throw error
    throw new Error(error instanceof Error ? error.message : `Couldn't reach the BizzyBee backend for ${label}.`)
  }

}

export function queryBusiness(payload: QueryRequest): Promise<QueryResponse> {
  return requestJson<QueryResponse>(apiRoutes.query, 'an answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function fetchBusinessHealth(signal?: AbortSignal): Promise<BusinessHealthResponse> {
  return requestJson<BusinessHealthResponse>(apiRoutes.businessHealth, 'the business health summary', { signal })
}

export function fetchAuditEvent(workflowId: string): Promise<AuditEvent> {
  return requestJson<AuditEvent>(apiRoutes.auditTrail(workflowId), 'the audit record')
}


export function fetchAuditHistory(limit = 20): Promise<AuditHistoryResponse> {
  return requestJson<AuditHistoryResponse>(`${apiRoutes.auditHistory}?limit=${encodeURIComponent(String(limit))}`, 'audit history')
}

export function fetchAuditTrace(traceId: string): Promise<AuditRecord> {
  return requestJson<AuditRecord>(apiRoutes.auditTrace(traceId), 'the audit trace')
}
