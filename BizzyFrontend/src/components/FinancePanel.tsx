import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchFinanceReport } from '../api/finance'
import type { FinanceReport, FinanceReportType } from '../types/finance'
import { humaniseKey } from '../utils/evidence'

function displayValue(value: unknown, unit?: string | null): string {
  if (value === null || value === undefined) return 'Not available'
  if (typeof value === 'number') {
    if (unit === 'SGD') return new Intl.NumberFormat('en-SG', { style: 'currency', currency: 'SGD' }).format(value)
    return `${value.toLocaleString('en-SG')}${unit === 'percent' ? '%' : ''}`
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export function FinancePanel() {
  const [reportType, setReportType] = useState<FinanceReportType>('profitability')
  const [startDate, setStartDate] = useState('2026-09-01')
  const [asOfDate, setAsOfDate] = useState('2026-09-23')
  const [report, setReport] = useState<FinanceReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => active.current?.abort(), [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setReport(null)
    setError(null)
    if (reportType !== 'receivables' && startDate > asOfDate) {
      setLoading(false)
      setError('Start date must not follow the reporting date.')
      return
    }
    setLoading(true)
    try {
      const result = await fetchFinanceReport(reportType, startDate, asOfDate, controller.signal)
      if (!controller.signal.aborted) setReport(result)
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Finance report unavailable.')
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  return <section className="panel" aria-label="Finance reports">
    <h2>Finance Bee</h2>
    <p>Read-only synthetic SGD reports. Data ends 23 September 2026. Report summaries are currently in English.</p>
    <form className="query-form" onSubmit={submit}>
      <label>Report<select value={reportType} onChange={event => setReportType(event.target.value as FinanceReportType)}>
        <option value="profitability">Profitability</option>
        <option value="operating_expenses">Operating expenses</option>
        <option value="cash_flow">Cash flow</option>
        <option value="receivables">Receivables</option>
      </select></label>
      {reportType !== 'receivables' && <label>Start date<input type="date" required min="2023-01-01" max={asOfDate} value={startDate} onChange={event => setStartDate(event.target.value)} /></label>}
      <label>As of date<input type="date" required min="2023-01-01" max="2026-09-23" value={asOfDate} onChange={event => setAsOfDate(event.target.value)} /></label>
      <button type="submit" disabled={loading}>{loading ? 'Loading Finance report…' : 'Run Finance report'}</button>
    </form>
    {error && <p role="alert">{error} No financial result is shown. Check the dates or retry.</p>}
    <div aria-live="polite" aria-busy={loading}>
      {report && <>
        <h3>{humaniseKey(report.report_type)} · {report.start_date ? `${report.start_date} to ` : 'As of '}{report.as_of_date} · {report.currency}</h3>
        <p>{report.summary}</p>
        <dl className="bee-evidence">{report.evidence.map(item => <div key={item.metric}>
          <dt>{humaniseKey(item.metric)}</dt>
          <dd>{typeof item.value === 'object' && item.value !== null
            ? <table><caption>{humaniseKey(item.metric)}</caption><thead><tr><th scope="col">Item</th><th scope="col">Value ({item.unit ?? 'detail'})</th></tr></thead><tbody>{Object.entries(item.value).map(([key, value]) => <tr key={key}><th scope="row">{key}</th><td>{displayValue(value, item.unit)}</td></tr>)}</tbody></table>
            : displayValue(item.value, item.unit)}</dd>
          {(item.source || item.period) && <dd>Source: {item.source ?? 'Report metadata'}{item.period ? ` · Period: ${item.period}` : ''}</dd>}
        </div>)}</dl>
      </>}
    </div>
  </section>
}
