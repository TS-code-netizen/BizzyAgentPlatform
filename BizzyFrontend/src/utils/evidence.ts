import type { Evidence, JsonRecord, JsonValue } from '../types/contracts'
import { formatDate, formatNumber, formatSgd, formatWindow, parsePeriod } from './format'

export type EvidenceIndex = ReadonlyMap<string, Evidence>

const MAX_LIST_ITEMS = 8

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/

export function indexEvidence(evidence: Evidence[]): EvidenceIndex {
  return new Map(evidence.map((item) => [item.metric, item]))
}

export function isRecord(value: JsonValue | undefined): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function asNumber(value: JsonValue | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function asString(value: JsonValue | undefined): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

export function asBoolean(value: JsonValue | undefined): boolean {
  return value === true
}

export function numberMetric(index: EvidenceIndex, metric: string): number | null {
  return asNumber(index.get(metric)?.value)
}

export function stringMetric(index: EvidenceIndex, metric: string): string | null {
  return asString(index.get(metric)?.value)
}

export function recordsMetric(index: EvidenceIndex, metric: string): JsonRecord[] {
  const value = index.get(metric)?.value
  return Array.isArray(value) ? value.filter(isRecord) : []
}

export function humaniseKey(key: string): string {
  const words = key
    .split('_')
    .filter((word) => word && word !== 'sgd')
    .map((word) => (word === 'pct' ? '%' : word))
  const text = words.join(' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function formatText(value: string): string {
  const period = parsePeriod(value)
  if (period) return formatWindow(period)
  return ISO_DAY.test(value) ? formatDate(value, true) : value
}

function isMoney(item: Evidence): boolean {
  return item.unit === 'SGD' || /(^|_)sgd(_|$)/.test(item.metric)
}

function isPercent(item: Evidence): boolean {
  return item.unit === 'percent' || item.metric.endsWith('_pct')
}

function formatScalar(value: JsonValue): string {
  if (value === null) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return formatNumber(value)
  if (typeof value === 'string') return formatText(value)
  return Array.isArray(value) ? `${value.length} items` : '1 record'
}

export function describeRecord(record: JsonRecord): string {
  return Object.entries(record)
    .map(([key, entry]) => `${humaniseKey(key)}: ${formatScalar(entry)}`)
    .join(' · ')
}

export function formatEvidenceValue(item: Evidence): string {
  const { value } = item

  if (typeof value === 'number') {
    if (isMoney(item)) return formatSgd(value)
    if (isPercent(item)) return `${formatNumber(value)}%`
    return item.unit ? `${formatNumber(value)} ${item.unit}` : formatNumber(value)
  }

  if (Array.isArray(value)) {
    if (value.some((entry) => typeof entry === 'object' && entry !== null)) {
      return `${value.length} rows`
    }
    const shown = value.slice(0, MAX_LIST_ITEMS).map(formatScalar).join(', ')
    const hidden = value.length - MAX_LIST_ITEMS
    return hidden > 0 ? `${shown} and ${hidden} more` : shown
  }

  if (isRecord(value)) return describeRecord(value)

  return formatScalar(value)
}
