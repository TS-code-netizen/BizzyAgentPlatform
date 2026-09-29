import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const schema = JSON.parse(readFileSync(new URL('../contracts/backend.openapi.json', import.meta.url), 'utf8'))
const models = schema.components.schemas
for (const [path, verb, model] of [
  ['/query', 'post', 'QueryResponse'], ['/sales/summary', 'get', 'AgentResponse'],
  ['/inventory/status', 'get', 'AgentResponse'], ['/finance/summary', 'get', 'AgentResponse'],
  ['/finance/report', 'get', 'FinanceReport'],
]) {
  const operation = schema.paths[`/api/v1${path}`][verb]
  assert.equal(operation.responses['200'].content['application/json'].schema.$ref, `#/components/schemas/${model}`)
  assert.ok(operation.security.some((entry) => 'HTTPBearer' in entry), `${path} requires authentication`)
}
for (const model of ['AgentResponse', 'Evidence', 'RecommendedAction', 'QueryRequest', 'QueryResponse']) {
  assert.ok(models[model])
  const types = readFileSync(new URL('../src/types/contracts.ts', import.meta.url), 'utf8')
  const declaration = types.match(new RegExp(`export interface ${model} \\{([\\s\\S]*?)\\n\\}`))?.[1]
  assert.ok(declaration, `Missing frontend interface ${model}`)
  for (const field of models[model].required ?? []) {
    assert.match(declaration, new RegExp(`\\b${field}:`), `Required contract field ${model}.${field} missing or optional`)
  }
}
assert.deepEqual(models.RiskLevel.enum, ['GREEN', 'AMBER', 'RED'])
assert.equal(models.QueryRequest.properties.question.maxLength, 4000)
for (const action of ['approve', 'reject']) assert.ok(schema.paths[`/api/v1/actions/{action_id}/${action}`].post)
console.log('Pinned backend OpenAPI route, authentication and required-field contract checks passed.')
const financeTypes = readFileSync(new URL('../src/types/finance.ts', import.meta.url), 'utf8')
const financeDeclaration = financeTypes.match(/export interface FinanceReport \{([\s\S]*?)\n\}/)?.[1]
assert.ok(financeDeclaration)
for (const field of models.FinanceReport.required) assert.match(financeDeclaration, new RegExp(`\\b${field}:`))
