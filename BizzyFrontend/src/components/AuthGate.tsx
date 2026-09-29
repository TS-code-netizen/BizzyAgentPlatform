import { type ReactNode, useEffect, useState } from 'react'
import { authEnabled, initializeAuth, signIn, signOut } from '../auth'

export function AuthGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState<boolean | null>(null)
  const [error, setError] = useState('')
  const showError = (cause: unknown) => setError(cause instanceof Error ? cause.message : 'Authentication failed.')
  useEffect(() => {
    let active = true
    initializeAuth().then((signedIn) => { if (active) setReady(signedIn) })
      .catch((cause: unknown) => { if (active) showError(cause) })
    return () => { active = false }
  }, [])
  if (ready !== true) return <main style={{ padding: '3rem' }}>
    <h1>BizzyBee AI</h1><p>Private hackathon demo. Invited users only.</p>
    {error && <p role="alert">{error}</p>}
    {ready === null && !error ? <p>Checking session…</p> :
      <button onClick={() => void signIn().catch(showError)}>Sign in</button>}
  </main>
  return <>{authEnabled && <header style={{ padding: '1rem' }}>
    <button onClick={() => void signOut().catch(showError)}>Sign out</button>
    {error && <span role="alert">{error}</span>}
  </header>}{children}</>
}
