import type { AgentStatus, Evidence, RecommendedAction } from './contracts'

export type FinanceReportType = 'profitability' | 'operating_expenses' | 'cash_flow' | 'receivables'

export interface FinanceReport {
  report_type: FinanceReportType
  start_date: string | null
  as_of_date: string
  currency: 'SGD'
  summary: string
  evidence: Evidence[]
}

export interface FinanceView {
  status: AgentStatus
  summary: string
  confidence: number
  actions: RecommendedAction[]
  asOfDate: string | null
  overdueInvoiceCount: number | null
  overdueOutstanding: number | null
}
