import type { AgentResponse, BusinessAlert, JsonRecord, JsonValue } from '../types/contracts'
import type {
  ChannelSalesChange,
  FocusStock,
  InventoryView,
  ProductSalesChange,
  SalesView,
  StockRisk,
  StockRow,
} from '../types/salesInventory'
import {
  asBoolean,
  asNumber,
  asString,
  indexEvidence,
  numberMetric,
  recordsMetric,
  stringMetric,
} from '../utils/evidence'
import { parsePeriod } from '../utils/format'
import { DEFAULT_LANGUAGE } from '../utils/languages'
import { apiRoutes, requestJson } from './client'

const STOCK_RISKS: readonly StockRisk[] = ['out_of_stock', 'at_risk', 'ok']

const RISK_RANK: Record<StockRisk, number> = { out_of_stock: 0, at_risk: 1, ok: 2 }

interface OrderSuggestion {
  quantity: number
  provisional: boolean
}

function withLanguage(url: string, language: string): string {
  return language === DEFAULT_LANGUAGE ? url : `${url}?${new URLSearchParams({ language })}`
}

async function fetchBee(url: string, label: string, signal?: AbortSignal): Promise<AgentResponse> {
  const response = await requestJson<AgentResponse>(url, label, { signal })
  if (response.status === 'failed') {
    throw new Error(response.summary || `The backend couldn't produce ${label}.`)
  }
  return response
}

function beeFields(response: AgentResponse) {
  return {
    status: response.status,
    summary: response.summary,
    confidence: response.confidence,
    actions: response.recommended_actions,
  }
}

function toProductChange(record: JsonRecord): Omit<ProductSalesChange, 'shareOfDeclinePct'> | null {
  const productId = asString(record.product_id)
  const revenueChange = asNumber(record.revenue_change_sgd)
  if (!productId || revenueChange === null) return null
  return {
    productId,
    product: asString(record.product) ?? productId,
    baselineRevenue: asNumber(record.baseline_revenue_sgd) ?? 0,
    recentRevenue: asNumber(record.recent_revenue_sgd) ?? 0,
    revenueChange,
    baselineUnits: asNumber(record.baseline_units) ?? 0,
    recentUnits: asNumber(record.recent_units) ?? 0,
  }
}

function toChannelChange(record: JsonRecord): ChannelSalesChange | null {
  const channel = asString(record.channel)
  const revenueChange = asNumber(record.revenue_change_sgd)
  if (!channel || revenueChange === null) return null
  return {
    channel,
    baselineRevenue: asNumber(record.baseline_revenue_sgd) ?? 0,
    recentRevenue: asNumber(record.recent_revenue_sgd) ?? 0,
    revenueChange,
  }
}

function isPresent<T>(value: T | null): value is T {
  return value !== null
}

export function toSalesView(response: AgentResponse): SalesView {
  const evidence = indexEvidence(response.evidence)
  const revenueChange = numberMetric(evidence, 'revenue_change_sgd')
  const totalDecline = revenueChange !== null && revenueChange < 0 ? revenueChange : null

  const decliners = recordsMetric(evidence, 'product_performance_details')
    .map(toProductChange)
    .filter(isPresent)
    .filter((product) => product.revenueChange < 0)
    .sort((a, b) => a.revenueChange - b.revenueChange)
    .map((product) => ({
      ...product,
      shareOfDeclinePct: totalDecline === null ? null : (product.revenueChange / totalDecline) * 100,
    }))

  return {
    ...beeFields(response),
    baselineWindow: parsePeriod(stringMetric(evidence, 'baseline_period')),
    recentWindow: parsePeriod(stringMetric(evidence, 'recent_period')),
    baselineRevenue: numberMetric(evidence, 'baseline_revenue_sgd'),
    recentRevenue: numberMetric(evidence, 'recent_revenue_sgd'),
    revenueChange,
    revenueChangePct: numberMetric(evidence, 'revenue_change_pct'),
    volumeEffect: numberMetric(evidence, 'volume_effect_sgd'),
    priceMixEffect: numberMetric(evidence, 'price_mix_effect_sgd'),
    focusProductId: stringMetric(evidence, 'focus_product_id'),
    focusProductLastSaleDate: stringMetric(evidence, 'focus_product_last_sale_date'),
    decliners,
    channels: recordsMetric(evidence, 'channel_performance_details').map(toChannelChange).filter(isPresent),
  }
}

// Unknown risk labels are treated as at-risk so a new backend category is never shown as healthy.
function toStockRisk(value: JsonValue | undefined): StockRisk {
  return STOCK_RISKS.find((risk) => risk === value) ?? 'at_risk'
}

function toStockRow(record: JsonRecord, orders: ReadonlyMap<string, OrderSuggestion>): StockRow | null {
  const productId = asString(record.product_id)
  const currentStock = asNumber(record.current_stock)
  if (!productId || currentStock === null) return null
  const order = orders.get(productId)
  return {
    productId,
    product: asString(record.product) ?? productId,
    risk: toStockRisk(record.risk),
    currentStock,
    reorderLevel: asNumber(record.reorder_level),
    avgDailyDemand: asNumber(record.avg_daily_demand),
    daysOfCover: asNumber(record.days_of_cover),
    leadTimeDays: asNumber(record.lead_time_days),
    projectedStockoutDate: asString(record.projected_stockout_date),
    suggestedOrderQty: order?.quantity ?? null,
    suggestedOrderQtyIsProvisional: order?.provisional ?? false,
  }
}

function coverShortfallDays(row: StockRow): number {
  if (row.daysOfCover === null) return Number.MAX_SAFE_INTEGER
  return row.daysOfCover - (row.leadTimeDays ?? 0)
}

function mostUrgentFirst(a: StockRow, b: StockRow): number {
  return RISK_RANK[a.risk] - RISK_RANK[b.risk] || coverShortfallDays(a) - coverShortfallDays(b)
}

export function toInventoryView(response: AgentResponse): InventoryView {
  const evidence = indexEvidence(response.evidence)

  const orders = new Map<string, OrderSuggestion>()
  for (const record of recordsMetric(evidence, 'reorder_recommendation_details')) {
    const productId = asString(record.product_id)
    const quantity = asNumber(record.suggested_order_qty)
    if (productId && quantity !== null) {
      orders.set(productId, { quantity, provisional: asBoolean(record.suggested_order_qty_is_provisional) })
    }
  }

  const rows = recordsMetric(evidence, 'stock_risk_details')
    .map((record) => toStockRow(record, orders))
    .filter(isPresent)

  const riskCounts: Record<StockRisk, number> = { out_of_stock: 0, at_risk: 0, ok: 0 }
  if (rows.length > 0) {
    for (const row of rows) riskCounts[row.risk] += 1
  } else {
    riskCounts.out_of_stock = numberMetric(evidence, 'out_of_stock_product_count') ?? 0
    riskCounts.at_risk = numberMetric(evidence, 'at_risk_product_count') ?? 0
  }

  const focusId = stringMetric(evidence, 'product_id')
  const focusOrder = focusId ? orders.get(focusId) : undefined
  const focus: FocusStock | null = focusId
    ? {
        productId: focusId,
        product: stringMetric(evidence, 'product') ?? focusId,
        risk: toStockRisk(evidence.get('stock_risk')?.value),
        currentStock: numberMetric(evidence, 'current_stock'),
        reorderLevel: numberMetric(evidence, 'reorder_level'),
        leadTimeDays: numberMetric(evidence, 'lead_time_days'),
        supplier: stringMetric(evidence, 'supplier'),
        avgDailyDemand: numberMetric(evidence, 'avg_daily_demand_units'),
        daysOfCover: numberMetric(evidence, 'days_of_cover'),
        unfulfilledUnits: numberMetric(evidence, 'recent_unfulfilled_demand_units'),
        lostRevenue: numberMetric(evidence, 'recent_lost_revenue_sgd'),
        nextReceiptDate: stringMetric(evidence, 'next_expected_receipt_date'),
        incomingQtyStatus: stringMetric(evidence, 'incoming_qty_status'),
        lostRevenueUntilRestock: numberMetric(evidence, 'projected_lost_revenue_sgd_until_restock'),
        suggestedOrderQty: numberMetric(evidence, 'suggested_order_qty') ?? focusOrder?.quantity ?? null,
        suggestedOrderQtyIsProvisional:
          asBoolean(evidence.get('suggested_order_qty_is_provisional')?.value) || (focusOrder?.provisional ?? false),
      }
    : null

  return {
    ...beeFields(response),
    asOfDate: stringMetric(evidence, 'as_of_date'),
    recentWindow: parsePeriod(stringMetric(evidence, 'recent_period')),
    productCount: rows.length,
    riskCounts,
    totalStockValue: numberMetric(evidence, 'total_stock_value_sgd'),
    reorderCandidateCount: numberMetric(evidence, 'reorder_candidate_count'),
    provisionalReorderCount: numberMetric(evidence, 'provisional_reorder_candidate_count'),
    totalSuggestedOrderUnits: numberMetric(evidence, 'total_suggested_order_units'),
    focus,
    watchList: rows.filter((row) => row.risk !== 'ok' && row.productId !== focusId).sort(mostUrgentFirst),
  }
}

export async function fetchSalesView(language: string, signal?: AbortSignal): Promise<SalesView> {
  const url = withLanguage(apiRoutes.salesSummary, language)
  return toSalesView(await fetchBee(url, 'the sales summary', signal))
}

export async function fetchInventoryView(language: string, signal?: AbortSignal): Promise<InventoryView> {
  const url = withLanguage(apiRoutes.inventoryStatus, language)
  return toInventoryView(await fetchBee(url, 'the inventory status', signal))
}

export function fetchAlerts(signal?: AbortSignal): Promise<BusinessAlert[]> {
  return requestJson<BusinessAlert[]>(apiRoutes.salesInventoryAlerts, 'the sales and inventory alerts', { signal })
}
