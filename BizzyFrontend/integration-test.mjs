const backendOrigin = (process.env.BIZZY_BACKEND_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')
const frontendOrigin = (process.env.BIZZY_FRONTEND_URL ?? 'http://127.0.0.1:5173').replace(/\/$/, '')
const apiBase = `${backendOrigin}/api/v1`

function check(condition, message) {
  if (!condition) throw new Error(message)
}

async function requestJson(url, init) {
  const response = await fetch(url, init)
  check(response.ok, `${url} returned HTTP ${response.status}`)
  return response.json()
}

function evidenceMap(response) {
  return Object.fromEntries(response.evidence.map((item) => [item.metric, item.value]))
}

const health = await requestJson(`${backendOrigin}/health`)
check(health.status === 'ok', 'Backend health check did not return ok')

const [sales, inventory, finance, businessHealth, alerts] = await Promise.all([
  requestJson(`${apiBase}/sales/summary?language=zh-CN`),
  requestJson(`${apiBase}/inventory/status?language=zh-CN`),
  requestJson(`${apiBase}/finance/summary`),
  requestJson(`${apiBase}/business-health`),
  requestJson(`${apiBase}/sales-inventory/alerts`),
])

check(sales.status === 'success', 'Sales Bee did not succeed')
check(inventory.status === 'success', 'Inventory Bee did not succeed')
check(finance.status === 'success', 'Finance Bee did not succeed')
check(sales.summary.includes('下降'), 'Chinese sales overview does not emphasize the revenue decline')
check(/缺货|断货/.test(inventory.summary), 'Chinese inventory overview does not emphasize stockouts')

const financeEvidence = evidenceMap(finance)
check(
  Number(financeEvidence.overdue_invoice_count) > 0,
  'Finance summary is missing a dynamic overdue invoice count',
)
check(
  Number(financeEvidence.overdue_outstanding_sgd) > 0,
  'Finance summary is missing the overdue outstanding amount',
)
check(typeof businessHealth.score === 'number', 'Business health is missing its numeric score')
check(Array.isArray(alerts), 'Alerts endpoint did not return an array')

const query = await requestJson(`${apiBase}/query`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    question: 'Why did sales fall this week?',
    language: 'en',
    user: 'integration-test',
  }),
})
check(
  query.invoked_agents.join(',') === 'sales,inventory',
  `Causal query invoked unexpected agents: ${query.invoked_agents.join(',')}`,
)
check(query.advisor_result?.agent === 'advisor', 'Advisor result is missing')
check(typeof query.approval_required === 'boolean', 'Guard decision is missing')

const audit = await requestJson(`${apiBase}/audit/${encodeURIComponent(query.workflow_id)}`)
check(audit.workflow_id === query.workflow_id, 'Audit workflow ID does not match the query')
check(audit.user === 'owner', 'Local audit must use the server identity, not the caller-controlled user field')

const frontendResponse = await fetch(frontendOrigin)
check(frontendResponse.ok, `Frontend returned HTTP ${frontendResponse.status}`)
check((await frontendResponse.text()).includes('id="root"'), 'Frontend HTML is missing the React root')

const proxiedFinance = await requestJson(`${frontendOrigin}/api/v1/finance/summary`)
const proxiedEvidence = evidenceMap(proxiedFinance)
check(
  proxiedEvidence.overdue_invoice_count === financeEvidence.overdue_invoice_count,
  'Vite proxy changed or lost the Finance Bee response',
)

console.log(
  `Integration passed: Sales + Inventory routed, Finance=${financeEvidence.overdue_invoice_count} overdue, audit=${query.workflow_id}`,
)
