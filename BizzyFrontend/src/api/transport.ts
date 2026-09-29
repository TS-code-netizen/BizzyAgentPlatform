type Pending = { start: () => void; signal: AbortSignal; abort: () => void }

export function createScheduler(concurrency = 2, spacingMs = 600) {
  const queue: Pending[] = []
  let active = 0
  let nextStart = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  function pump() {
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
    if (!queue.length || active >= concurrency) return
    const delay = nextStart - Date.now()
    if (delay > 0) {
      timer = setTimeout(pump, delay)
      return
    }
    const pending = queue.shift()!
    pending.signal.removeEventListener('abort', pending.abort)
    active++
    nextStart = Date.now() + spacingMs
    pending.start()
    pump()
  }

  return function schedule<T>(operation: () => Promise<T>, signal: AbortSignal): Promise<T> {
    signal.throwIfAborted()
    return new Promise((resolve, reject) => {
      const pending: Pending = {
        signal,
        abort() {
          const index = queue.indexOf(pending)
          if (index >= 0) queue.splice(index, 1)
          reject(signal.reason)
          pump()
        },
        start() {
          Promise.resolve().then(() => {
            signal.throwIfAborted()
            return operation()
          }).then(resolve, reject).finally(() => { active--; pump() })
        },
      }
      signal.addEventListener('abort', pending.abort, { once: true })
      queue.push(pending)
      pump()
    })
  }
}

function sleep(delay: number, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted()
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, delay)
    function abort() { clearTimeout(timer); reject(signal.reason) }
    signal.addEventListener('abort', abort, { once: true })
  })
}

export function retryDelay(header: string | null, attempt: number): number | null {
  const backoff = 600 * 2 ** attempt + Math.random() * 300
  if (!header) return backoff
  const seconds = /^\d+(\.\d+)?$/.test(header.trim()) ? Number(header) : NaN
  const requested = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(header) - Date.now()
  if (!Number.isFinite(requested)) return backoff
  return requested > 10000 ? null : Math.max(backoff, requested)
}

const schedule = createScheduler()

export async function fetchJson<T>(url: string, label: string, init: RequestInit, signal: AbortSignal): Promise<T> {
  const readOnly = ['GET', 'HEAD'].includes((init.method ?? 'GET').toUpperCase())
  for (let attempt = 0; ; attempt++) {
    const result = await schedule(async () => {
      const response = await fetch(url, { ...init, signal })
      if (readOnly && attempt < 2 && [429, 503].includes(response.status)) {
        const delay = retryDelay(response.headers.get('Retry-After'), attempt)
        if (delay !== null) {
          await response.body?.cancel()
          return { retry: true as const, delay }
        }
      }
      if (!response.ok) {
        await response.body?.cancel()
        throw new Error(`The backend couldn't return ${label} (HTTP ${response.status}).`)
      }
      return { retry: false as const, value: init.method?.toUpperCase() === 'HEAD' ? undefined as T : await response.json() as T }
    }, signal)
    if (!result.retry) return result.value
    await sleep(result.delay, signal)
  }
}
