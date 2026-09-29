import test from 'node:test'
import assert from 'node:assert/strict'
import { createScheduler, fetchJson, retryDelay } from '../src/api/transport.ts'

test('scheduler caps simultaneous operations and preserves FIFO order', async () => {
  const schedule = createScheduler(2, 0)
  const releases = []
  const starts = []
  const pending = Array.from({ length: 5 }, (_, index) => schedule(async () => {
    starts.push(index)
    await new Promise(resolve => releases.push(resolve))
    return index
  }, new AbortController().signal))
  await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(starts, [0, 1])
  for (let index = 0; index < 5; index++) {
    releases[index]()
    await new Promise(resolve => setImmediate(resolve))
  }
  assert.deepEqual(await Promise.all(pending), [0, 1, 2, 3, 4])
})

test('queued cancellation removes work without using a slot', async () => {
  const schedule = createScheduler(1, 0)
  let release
  const first = schedule(() => new Promise(resolve => { release = resolve }), new AbortController().signal)
  await new Promise(resolve => setImmediate(resolve))
  const controller = new AbortController()
  const cancelled = schedule(async () => assert.fail('Cancelled work started'), controller.signal)
  controller.abort()
  await assert.rejects(cancelled, { name: 'AbortError' })
  release()
  await first
  assert.equal(await schedule(async () => 42, new AbortController().signal), 42)
})

test('failed operations release capacity', async () => {
  const schedule = createScheduler(1, 0)
  await assert.rejects(schedule(async () => { throw new Error('failure') }, new AbortController().signal))
  assert.equal(await schedule(async () => 'ok', new AbortController().signal), 'ok')
})

test('starts are paced', async () => {
  const schedule = createScheduler(2, 40)
  const starts = []
  await Promise.all([0, 1, 2].map(() => schedule(async () => starts.push(Date.now()), new AbortController().signal)))
  assert.ok(starts[1] - starts[0] >= 35)
  assert.ok(starts[2] - starts[1] >= 35)
})

test('Retry-After is respected or fails closed when beyond the retry budget', () => {
  assert.equal(retryDelay('5', 0), 5000)
  assert.equal(retryDelay('60', 0), null)
  assert.equal(retryDelay(new Date(Date.now() + 60000).toUTCString(), 0), null)
  assert.ok(retryDelay('invalid', 0) >= 600)
})

test('GET retries 429 and 503 but stops after three attempts', async context => {
  let calls = 0
  context.mock.method(globalThis, 'fetch', async () => { calls++; return new Response('', { status: calls === 1 ? 429 : 503 }) })
  await assert.rejects(fetchJson('/test', 'test', {}, AbortSignal.timeout(10000)), /HTTP 503/)
  assert.equal(calls, 3)
})

test('GET can recover after a transient error', async context => {
  let calls = 0
  context.mock.method(globalThis, 'fetch', async () => ++calls === 1 ? new Response('', { status: 503 }) : Response.json({ ok: true }))
  assert.deepEqual(await fetchJson('/test', 'test', {}, AbortSignal.timeout(10000)), { ok: true })
  assert.equal(calls, 2)
})

test('POST is never retried; permanent GET errors are never retried', async context => {
  for (const [method, status] of [['POST', 503], ['POST', 429], ['GET', 401], ['GET', 403], ['GET', 404]]) {
    let calls = 0
    context.mock.method(globalThis, 'fetch', async () => { calls++; return new Response('', { status }) })
    await assert.rejects(fetchJson('/test', 'test', { method }, AbortSignal.timeout(10000)), new RegExp(`HTTP ${status}`))
    assert.equal(calls, 1)
    context.mock.restoreAll()
  }
})

test('cancellation during backoff prevents another request', async context => {
  let calls = 0
  const controller = new AbortController()
  context.mock.method(globalThis, 'fetch', async () => {
    calls++
    setTimeout(() => controller.abort(), 20)
    return new Response('', { status: 503 })
  })
  await assert.rejects(fetchJson('/test', 'test', {}, controller.signal), { name: 'AbortError' })
  assert.equal(calls, 1)
})

test('network failures are not retried', async context => {
  let calls = 0
  context.mock.method(globalThis, 'fetch', async () => { calls++; throw new TypeError('Failed to fetch') })
  await assert.rejects(fetchJson('/test', 'test', {}, AbortSignal.timeout(10000)), /Failed to fetch/)
  assert.equal(calls, 1)
})

test('deadline includes time in the queue', async () => {
  const schedule = createScheduler(1, 0)
  let release
  const first = schedule(() => new Promise(resolve => { release = resolve }), new AbortController().signal)
  await new Promise(resolve => setImmediate(resolve))
  const timer = setTimeout(() => release(), 80)
  try {
    await assert.rejects(schedule(async () => assert.fail('Expired work started'), AbortSignal.timeout(20)), { name: 'TimeoutError' })
  } finally {
    clearTimeout(timer)
    release()
    await first
  }
})

test('HEAD succeeds without attempting JSON decoding', async context => {
  context.mock.method(globalThis, 'fetch', async () => new Response(null, { status: 200 }))
  assert.equal(await fetchJson('/test', 'test', { method: 'HEAD' }, AbortSignal.timeout(10000)), undefined)
})
