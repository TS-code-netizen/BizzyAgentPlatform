import type { ReactNode } from 'react'
import type { LoadState } from '../hooks/useSalesInventory'

interface PanelStateProps<T> {
  state: LoadState<T>
  onRetry: () => void
  children: (data: T) => ReactNode
}

export function PanelState<T>({ state, onRetry, children }: PanelStateProps<T>) {
  if (state.status === 'loading') {
    return (
      <p className="bee-muted" role="status">
        Loading…
      </p>
    )
  }

  if (state.status === 'error') {
    return (
      <div className="bee-error" role="alert">
        <p>{state.message}</p>
        <button type="button" className="secondary" onClick={onRetry}>
          Retry
        </button>
      </div>
    )
  }

  return <>{children(state.data)}</>
}
