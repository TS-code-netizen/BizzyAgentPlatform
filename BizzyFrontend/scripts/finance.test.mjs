import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const source = readFileSync(new URL('../src/components/FinancePanel.tsx', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText
const jsx = await import('react/jsx-runtime')
const module = { exports: {} }
const dependencies = {
  react: React,
  'react/jsx-runtime': jsx,
  '../api/finance': { fetchFinanceReport: () => { throw new Error('No network permitted in rendering tests') } },
  '../utils/evidence': { humaniseKey: value => value },
}
new Function('require', 'module', 'exports', compiled)(name => {
  assert.ok(name in dependencies, `Unexpected dependency ${name}`)
  return dependencies[name]
}, module, module.exports)

test('Finance panel offers four reports and explicit fixed dates without initial inference or fetch', () => {
  const html = renderToStaticMarkup(React.createElement(module.exports.FinancePanel))
  for (const report of ['profitability', 'operating_expenses', 'cash_flow', 'receivables']) assert.ok(html.includes(`value="${report}"`))
  assert.ok(html.includes('value="2026-09-23"'))
  assert.ok(html.includes('value="2026-09-01"'))
  assert.ok(html.includes('Read-only synthetic SGD reports'))
})

function harness(fetchReport) {
  const states = []
  let cursor = 0
  const reference = { current: null }
  const hooks = {
    useState(initial) {
      const index = cursor++
      if (!(index in states)) states[index] = initial
      return [states[index], value => { states[index] = value }]
    },
    useRef: () => reference,
    useEffect: () => {},
  }
  const local = { exports: {} }
  new Function('require', 'module', 'exports', compiled)(name => name === 'react' ? hooks
    : name === '../api/finance' ? { fetchFinanceReport: fetchReport } : dependencies[name], local, local.exports)
  return {
    render() { cursor = 0; return local.exports.FinancePanel() },
    states,
  }
}

function elements(tree, type) {
  if (Array.isArray(tree)) return tree.flatMap(child => elements(child, type))
  if (!tree || typeof tree !== 'object') return []
  return [...(tree.type === type ? [tree] : []), ...elements(tree.props?.children, type)]
}

test('report requests use selected dates and render unavailable margins without zero', async () => {
  const ui = harness(async (type, start, end) => {
    assert.deepEqual([type, start, end], ['profitability', '2026-09-01', '2026-09-23'])
    return { report_type: type, start_date: start, as_of_date: end, currency: 'SGD', summary: 'Report',
      evidence: [{ metric: 'margin', value: null, unit: 'percent' }, { metric: 'cash', value: 1234.5, unit: 'SGD' }] }
  })
  await elements(ui.render(), 'form')[0].props.onSubmit({ preventDefault() {} })
  const html = renderToStaticMarkup(ui.render())
  assert.ok(html.includes('Not available'))
  assert.ok(html.includes('1,234.50'))
})

test('receivables hides start date and failed retry clears stale figures', async () => {
  const ui = harness(async () => { throw new Error('HTTP 503') })
  elements(ui.render(), 'select')[0].props.onChange({ target: { value: 'receivables' } })
  assert.equal(elements(ui.render(), 'input').length, 1)
  ui.states[3] = { report_type: 'receivables', summary: 'Old report', evidence: [] }
  await elements(ui.render(), 'form')[0].props.onSubmit({ preventDefault() {} })
  assert.equal(ui.states[3], null)
  assert.ok(renderToStaticMarkup(ui.render()).includes('HTTP 503'))
})

test('invalid date ordering does not call the API', async () => {
  const ui = harness(async () => { assert.fail('Unexpected request') })
  elements(ui.render(), 'input')[0].props.onChange({ target: { value: '2026-09-24' } })
  await elements(ui.render(), 'form')[0].props.onSubmit({ preventDefault() {} })
  assert.ok(renderToStaticMarkup(ui.render()).includes('Start date must not follow'))
})
