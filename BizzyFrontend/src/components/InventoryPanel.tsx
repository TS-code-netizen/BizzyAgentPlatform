import { useState } from 'react'
import type { LoadState } from '../hooks/useSalesInventory'
import type { FocusStock, InventoryView, StockRisk, StockRow } from '../types/salesInventory'
import { daysBetween, formatDate, formatNumber, formatSgd, formatWindow, plural } from '../utils/format'
import { BeeActions, BeeSummary } from './BeeSections'
import { PanelState } from './PanelState'
import './SalesInventory.css'

const WATCH_LIST_PREVIEW = 5

const RISK_ORDER: StockRisk[] = ['out_of_stock', 'at_risk', 'ok']

const RISK_LABEL: Record<StockRisk, string> = {
  out_of_stock: 'Out of stock',
  at_risk: 'May run out before restock',
  ok: 'Healthy',
}

const RISK_TONE: Record<StockRisk, 'red' | 'amber' | 'green'> = {
  out_of_stock: 'red',
  at_risk: 'amber',
  ok: 'green',
}

function nextDelivery(focus: FocusStock, asOfDate: string | null): string {
  if (!focus.nextReceiptDate) return 'Not scheduled'
  const days = asOfDate ? daysBetween(asOfDate, focus.nextReceiptDate) : 0
  const when = days > 0 ? `${formatDate(focus.nextReceiptDate)} (in ${plural(days, 'day')})` : formatDate(focus.nextReceiptDate)
  return focus.incomingQtyStatus === 'unknown' ? `${when}, quantity not confirmed` : when
}

function orderQuantity(quantity: number, provisional: boolean): string {
  return provisional ? `~${plural(quantity, 'unit')} (provisional)` : plural(quantity, 'unit')
}

function FocusProduct({ focus, view }: { focus: FocusStock; view: InventoryView }) {
  const period = view.recentWindow ? ` (${formatWindow(view.recentWindow)})` : ''
  const facts: { label: string; value: string }[] = []

  if (focus.currentStock !== null) {
    const reorder = focus.reorderLevel === null ? '' : ` (reorder at ${formatNumber(focus.reorderLevel)})`
    facts.push({ label: 'Current stock', value: `${plural(focus.currentStock, 'unit')}${reorder}` })
  }
  if (focus.avgDailyDemand !== null) {
    facts.push({ label: 'Avg daily demand', value: plural(focus.avgDailyDemand, 'unit') })
  }
  if (focus.unfulfilledUnits) {
    facts.push({ label: `Unfulfilled demand${period}`, value: plural(focus.unfulfilledUnits, 'unit') })
  }
  if (focus.lostRevenue) {
    facts.push({ label: `Lost sales${period}`, value: formatSgd(focus.lostRevenue) })
  }
  facts.push({ label: 'Next delivery', value: nextDelivery(focus, view.asOfDate) })
  if (focus.lostRevenueUntilRestock) {
    facts.push({ label: 'Further lost sales before restock', value: formatSgd(focus.lostRevenueUntilRestock) })
  }
  if (focus.suggestedOrderQty) {
    facts.push({
      label: 'Suggested order',
      value: orderQuantity(focus.suggestedOrderQty, focus.suggestedOrderQtyIsProvisional),
    })
  }
  if (focus.supplier) {
    const leadTime = focus.leadTimeDays === null ? '' : ` · ${formatNumber(focus.leadTimeDays)}-day lead time`
    facts.push({ label: 'Supplier', value: `${focus.supplier}${leadTime}` })
  }

  return (
    <div className={`bee-focus ${RISK_TONE[focus.risk]}`}>
      <div className="bee-row-head">
        <span className={`badge ${RISK_TONE[focus.risk]}`}>{RISK_LABEL[focus.risk]}</span>
        <strong>{focus.product}</strong>
        <span className="bee-id">{focus.productId}</span>
      </div>
      <dl className="bee-facts">
        {facts.map((fact) => (
          <div key={fact.label}>
            <dt>{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
      {focus.suggestedOrderQtyIsProvisional ? (
        <p className="bee-note bee-focus-note">
          The quantity of the incoming delivery isn't known yet, so the order size is an estimate. Confirm the inbound
          quantity with the supplier before drafting a purchase order.
        </p>
      ) : null}
    </div>
  )
}

function describeCover(row: StockRow): string {
  const parts = [`${plural(row.currentStock, 'unit')} in stock`]
  if (row.daysOfCover !== null) {
    const leadTime = row.leadTimeDays === null ? '' : ` vs ${formatNumber(row.leadTimeDays)}-day lead time`
    parts.push(`${formatNumber(row.daysOfCover)} days of cover${leadTime}`)
  }
  if (row.projectedStockoutDate) parts.push(`runs out ${formatDate(row.projectedStockoutDate)}`)
  if (row.suggestedOrderQty) {
    parts.push(`order ${orderQuantity(row.suggestedOrderQty, row.suggestedOrderQtyIsProvisional)}`)
  }
  return parts.join(' · ')
}

function WatchList({ rows }: { rows: StockRow[] }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? rows : rows.slice(0, WATCH_LIST_PREVIEW)

  return (
    <>
      <h3 className="bee-subheading">Watch list</h3>
      <ul className="bee-rows">
        {visible.map((row) => (
          <li key={row.productId}>
            <div className="bee-row-head">
              <span className={`badge ${RISK_TONE[row.risk]}`}>{RISK_LABEL[row.risk]}</span>
              <strong>{row.product}</strong>
              <span className="bee-id">{row.productId}</span>
            </div>
            <p>{describeCover(row)}</p>
          </li>
        ))}
      </ul>
      {rows.length > WATCH_LIST_PREVIEW ? (
        <button type="button" className="secondary bee-toggle" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Show fewer' : `Show all ${rows.length}`}
        </button>
      ) : null}
    </>
  )
}

function InventoryDetails({ view }: { view: InventoryView }) {
  const footnote = [
    view.productCount > 0 ? `${plural(view.productCount, 'product')} monitored` : null,
    view.totalStockValue === null ? null : `stock value ${formatSgd(view.totalStockValue)}`,
    view.asOfDate ? `as of ${formatDate(view.asOfDate, true)}` : null,
    `confidence ${Math.round(view.confidence * 100)}%`,
  ].filter(Boolean)

  return (
    <>
      <BeeSummary status={view.status} summary={view.summary} />

      <ul className="bee-chips" aria-label="Stock risk counts">
        {RISK_ORDER.map((risk) => (
          <li key={risk} className={`bee-chip ${RISK_TONE[risk]}`}>
            <span className="bee-chip-count">{view.riskCounts[risk]}</span>
            <span>{RISK_LABEL[risk]}</span>
          </li>
        ))}
      </ul>

      {view.reorderCandidateCount ? (
        <p className="bee-note">
          {plural(view.reorderCandidateCount, 'product')} to reorder
          {view.totalSuggestedOrderUnits ? ` · ${plural(view.totalSuggestedOrderUnits, 'unit')} suggested in total` : ''}
          {view.provisionalReorderCount
            ? ` · ${formatNumber(view.provisionalReorderCount)} provisional until inbound quantities are confirmed`
            : ''}
        </p>
      ) : null}

      {view.focus ? <FocusProduct focus={view.focus} view={view} /> : null}
      {view.watchList.length > 0 ? <WatchList rows={view.watchList} /> : null}
      {!view.focus && view.watchList.length === 0 ? (
        <p className="bee-muted">All monitored products have healthy stock levels.</p>
      ) : null}

      <BeeActions actions={view.actions} />

      <p className="bee-footnote">{footnote.join(' · ')}.</p>
    </>
  )
}

interface InventoryPanelProps {
  state: LoadState<InventoryView>
  onRetry: () => void
}

export function InventoryPanel({ state, onRetry }: InventoryPanelProps) {
  return (
    <article className="bee-panel" aria-labelledby="inventory-bee-heading">
      <header className="bee-panel-header">
        <h2 id="inventory-bee-heading">Inventory Bee</h2>
        <p className="bee-muted">Stock risk</p>
      </header>
      <PanelState state={state} onRetry={onRetry}>
        {(view) => <InventoryDetails view={view} />}
      </PanelState>
    </article>
  )
}
