import type { LoadState } from '../hooks/useSalesInventory'
import type { DateWindow, ProductSalesChange, SalesView } from '../types/salesInventory'
import { formatDate, formatNumber, formatPct, formatSgd, formatWindow } from '../utils/format'
import { BeeActions, BeeSummary } from './BeeSections'
import { PanelState } from './PanelState'
import './SalesInventory.css'

const MAX_DECLINERS = 5

function trendTone(change: number | null): 'red' | 'green' | 'idle' {
  if (change === null || change === 0) return 'idle'
  return change < 0 ? 'red' : 'green'
}

function windowLabel(window: DateWindow | null, fallback: string): string {
  return window ? formatWindow(window) : fallback
}

function stalledLabel(product: ProductSalesChange, sales: SalesView): string | null {
  if (product.recentUnits > 0 || product.baselineUnits === 0) return null
  if (product.productId === sales.focusProductId && sales.focusProductLastSaleDate) {
    return `No sales since ${formatDate(sales.focusProductLastSaleDate)}`
  }
  return 'No sales this period'
}

function Decliners({ sales }: { sales: SalesView }) {
  const decliners = sales.decliners.slice(0, MAX_DECLINERS)

  if (decliners.length === 0) {
    return <p className="bee-muted">No product lost revenue compared with the previous period.</p>
  }

  return (
    <ul className="bee-rows">
      {decliners.map((product) => {
        const stalled = stalledLabel(product, sales)
        const share = product.shareOfDeclinePct
        return (
          <li key={product.productId}>
            <div className="bee-row-head">
              <strong>{product.product}</strong>
              <span className="bee-id">{product.productId}</span>
              {stalled ? <span className="badge red">{stalled}</span> : null}
            </div>
            {share !== null ? (
              <div className="bee-bar" role="img" aria-label={`${formatNumber(share)}% of the decline`}>
                <span style={{ width: `${Math.min(Math.max(share, 0), 100)}%` }} />
              </div>
            ) : null}
            <p>
              {formatSgd(product.baselineRevenue)} → {formatSgd(product.recentRevenue)}
              {share !== null ? ` · ${formatNumber(share)}% of the decline` : null}
            </p>
          </li>
        )
      })}
    </ul>
  )
}

function SalesDetails({ sales }: { sales: SalesView }) {
  return (
    <>
      <BeeSummary status={sales.status} summary={sales.summary} />

      <div className="bee-stats">
        <div className="bee-stat">
          <p className="bee-stat-label">{windowLabel(sales.baselineWindow, 'Previous period')}</p>
          <p className="bee-stat-value">{sales.baselineRevenue === null ? '—' : formatSgd(sales.baselineRevenue)}</p>
        </div>
        <div className="bee-stat">
          <p className="bee-stat-label">{windowLabel(sales.recentWindow, 'This period')}</p>
          <p className="bee-stat-value">{sales.recentRevenue === null ? '—' : formatSgd(sales.recentRevenue)}</p>
        </div>
        <div className="bee-stat">
          <p className="bee-stat-label">Week-on-week</p>
          <p className="bee-stat-value">
            <span className={`badge ${trendTone(sales.revenueChange)}`}>{formatPct(sales.revenueChangePct)}</span>
          </p>
          {sales.revenueChange !== null ? <p className="bee-stat-note">{formatSgd(sales.revenueChange)}</p> : null}
        </div>
      </div>

      <h3 className="bee-subheading">Where the decline came from</h3>
      <Decliners sales={sales} />
      {sales.volumeEffect !== null && sales.priceMixEffect !== null ? (
        <p className="bee-note">
          Volume effect {formatSgd(sales.volumeEffect)} · price/mix effect {formatSgd(sales.priceMixEffect)}
        </p>
      ) : null}

      {sales.channels.length > 0 ? (
        <>
          <h3 className="bee-subheading">By channel</h3>
          <ul className="bee-compact" aria-label="Revenue by channel this period">
            {sales.channels.map((channel) => (
              <li key={channel.channel}>
                <span className="bee-compact-label">{channel.channel}</span>
                <span>{formatSgd(channel.recentRevenue)}</span>
                <span className={`bee-delta ${trendTone(channel.revenueChange)}`}>{formatSgd(channel.revenueChange)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <BeeActions actions={sales.actions} />

      <p className="bee-footnote">
        Calculated from sales records
        {sales.recentWindow ? ` up to ${formatDate(sales.recentWindow.end, true)}` : ''} · confidence{' '}
        {Math.round(sales.confidence * 100)}%.
      </p>
    </>
  )
}

interface SalesPanelProps {
  state: LoadState<SalesView>
  onRetry: () => void
}

export function SalesPanel({ state, onRetry }: SalesPanelProps) {
  return (
    <article className="bee-panel" aria-labelledby="sales-bee-heading">
      <header className="bee-panel-header">
        <h2 id="sales-bee-heading">Sales Bee</h2>
        <p className="bee-muted">Weekly revenue</p>
      </header>
      <PanelState state={state} onRetry={onRetry}>
        {(sales) => <SalesDetails sales={sales} />}
      </PanelState>
    </article>
  )
}
