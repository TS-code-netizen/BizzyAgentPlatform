import test from 'node:test'
import assert from 'node:assert/strict'
import { agentDirectory, hiveState } from '../src/utils/hive.ts'

const result = {
  workflow_id: 'workflow-1', invoked_agents: ['customer'],
  specialist_results: [{ agent: 'customer', status: 'partial' }],
  advisor_result: { agent: 'advisor', status: 'success' },
  guard_decision: 'approval_required', approval_required: true,
}

test('all eight logical roles are present exactly once', () => {
  assert.equal(new Set(agentDirectory.map((agent) => agent.id)).size, 8)
  assert.equal(agentDirectory.length, 8)
})

test('loading never invents specialist progress or completed audit', () => {
  assert.equal(hiveState('queen', result, true, null, null), 'Processing')
  assert.equal(hiveState('customer', result, true, null, null), 'Waiting')
  assert.equal(hiveState('audit', result, true, null, null), 'Waiting')
})

test('failure does not reuse previous success', () => {
  assert.equal(hiveState('queen', result, false, 'Failed', null), 'Request failed')
  assert.equal(hiveState('advisor', result, false, 'Failed', null), 'Unknown')
})

test('specialist status comes from response and unselected roles remain distinct', () => {
  assert.equal(hiveState('customer', result, false, null, null), 'partial')
  assert.equal(hiveState('sales', result, false, null, null), 'Not selected')
  assert.equal(hiveState('customer', { ...result, specialist_results: [] }, false, null, null), 'Result missing')
})

test('guard state does not confuse blocked actions with approval', () => {
  assert.equal(hiveState('guard', result, false, null, null), 'approval required')
  assert.equal(hiveState('guard', { ...result, guard_decision: 'blocked' }, false, null, null), 'blocked')
})

test('audit persistence is confirmed only by a retrieved record', () => {
  assert.equal(hiveState('audit', result, false, null, null, 'loading'), 'Loading')
  assert.equal(hiveState('audit', result, false, null, null, 'error'), 'Unavailable')
  assert.equal(hiveState('audit', result, false, null, { workflow_id: 'workflow-1' }, 'ready'), 'Recorded')
})

test('no routing is represented as clarification, not success', () => {
  assert.equal(hiveState('queen', { ...result, invoked_agents: [] }, false, null, null), 'Needs clarification')
  assert.equal(hiveState('queen', null, false, null, null), 'Idle')
})
