import type { AgentResponse } from '../types/contracts'
import type { FinanceView, FinanceReport, FinanceReportType } from '../types/finance'
import { indexEvidence, numberMetric, stringMetric } from '../utils/evidence'
import { apiRoutes, requestJson } from './client'

export function fetchFinanceReport(reportType: FinanceReportType, startDate: string, asOfDate: string, signal?: AbortSignal): Promise<FinanceReport> {
  const params = new URLSearchParams({ report_type: reportType, as_of_date: asOfDate })
  if (reportType !== 'receivables') params.set('start_date', startDate)
  return requestJson<FinanceReport>(`${apiRoutes.financeReport}?${params}`, 'the Finance report', { signal })
}

export async function fetchFinanceView(signal?: AbortSignal): Promise<FinanceView> {
  const response = await requestJson<AgentResponse>(
    apiRoutes.financeSummary,
    'the finance summary',
    { signal },
  )
  const evidence = indexEvidence(response.evidence)

  return {
    status: response.status,
    summary: response.summary,
    confidence: response.confidence,
    actions: response.recommended_actions,
    asOfDate: stringMetric(evidence, 'as_of_date'),
    overdueInvoiceCount: numberMetric(evidence, 'overdue_invoice_count'),
    overdueOutstanding: numberMetric(evidence, 'overdue_outstanding_sgd'),
  }
}
