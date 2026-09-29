import type { AgentStatus, RecommendedAction } from './contracts'

export interface DateWindow {
  start: string
  end: string
}

interface BeeView {
  status: AgentStatus
  summary: string
  confidence: number
  actions: RecommendedAction[]
}

export interface ProductSalesChange {
  productId: string
  product: string
  baselineRevenue: number
  recentRevenue: number
  revenueChange: number
  baselineUnits: number
  recentUnits: number
  shareOfDeclinePct: number | null
}

export interface ChannelSalesChange {
  channel: string
  baselineRevenue: number
  recentRevenue: number
  revenueChange: number
}

export interface SalesView extends BeeView {
  baselineWindow: DateWindow | null
  recentWindow: DateWindow | null
  baselineRevenue: number | null
  recentRevenue: number | null
  revenueChange: number | null
  revenueChangePct: number | null
  volumeEffect: number | null
  priceMixEffect: number | null
  focusProductId: string | null
  focusProductLastSaleDate: string | null
  decliners: ProductSalesChange[]
  channels: ChannelSalesChange[]
}

export type StockRisk = 'out_of_stock' | 'at_risk' | 'ok'

export interface StockRow {
  productId: string
  product: string
  risk: StockRisk
  currentStock: number
  reorderLevel: number | null
  avgDailyDemand: number | null
  daysOfCover: number | null
  leadTimeDays: number | null
  projectedStockoutDate: string | null
  suggestedOrderQty: number | null
  suggestedOrderQtyIsProvisional: boolean
}

export interface FocusStock {
  productId: string
  product: string
  risk: StockRisk
  currentStock: number | null
  reorderLevel: number | null
  leadTimeDays: number | null
  supplier: string | null
  avgDailyDemand: number | null
  daysOfCover: number | null
  unfulfilledUnits: number | null
  lostRevenue: number | null
  nextReceiptDate: string | null
  incomingQtyStatus: string | null
  lostRevenueUntilRestock: number | null
  suggestedOrderQty: number | null
  suggestedOrderQtyIsProvisional: boolean
}

export interface InventoryView extends BeeView {
  asOfDate: string | null
  recentWindow: DateWindow | null
  productCount: number
  riskCounts: Record<StockRisk, number>
  totalStockValue: number | null
  reorderCandidateCount: number | null
  provisionalReorderCount: number | null
  totalSuggestedOrderUnits: number | null
  focus: FocusStock | null
  watchList: StockRow[]
}
