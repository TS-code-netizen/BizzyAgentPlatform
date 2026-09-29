import type { DateWindow } from '../types/salesInventory'

const amount = new Intl.NumberFormat('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const number = new Intl.NumberFormat('en-SG', { maximumFractionDigits: 2 })

// Dates arrive as ISO calendar days; formatting in UTC keeps them from shifting across time zones.
const shortDate = new Intl.DateTimeFormat('en-SG', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const longDate = new Intl.DateTimeFormat('en-SG', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })

const DAY_MS = 24 * 60 * 60 * 1000

function isoDay(isoDate: string): Date {
  return new Date(`${isoDate}T00:00:00Z`)
}

export function formatSgd(value: number): string {
  const sign = value < 0 ? '−' : ''
  return `${sign}SGD ${amount.format(Math.abs(value))}`
}

export function formatNumber(value: number): string {
  const sign = value < 0 ? '−' : ''
  return `${sign}${number.format(Math.abs(value))}`
}

export function formatPct(value: number | null): string {
  if (value === null) return '—'
  const sign = value > 0 ? '+' : value < 0 ? '−' : ''
  return `${sign}${Math.abs(value).toFixed(2)}%`
}

export function formatDate(isoDate: string, withYear = false): string {
  return (withYear ? longDate : shortDate).format(isoDay(isoDate))
}

export function formatWindow(window: DateWindow): string {
  return `${formatDate(window.start)} – ${formatDate(window.end)}`
}

export function parsePeriod(period: string | null): DateWindow | null {
  const match = period?.match(/^(\d{4}-\d{2}-\d{2})\/(\d{4}-\d{2}-\d{2})$/)
  return match ? { start: match[1], end: match[2] } : null
}

export function daysBetween(fromIsoDate: string, toIsoDate: string): number {
  return Math.round((isoDay(toIsoDate).getTime() - isoDay(fromIsoDate).getTime()) / DAY_MS)
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${formatNumber(count)} ${count === 1 ? singular : pluralForm}`
}
