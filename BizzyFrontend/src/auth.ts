import { InMemoryWebStorage, UserManager, WebStorageStateStore } from 'oidc-client-ts'

const authority = import.meta.env.VITE_COGNITO_ISSUER as string | undefined
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined
const domain = import.meta.env.VITE_COGNITO_DOMAIN as string | undefined
export const authEnabled = Boolean(authority && clientId && domain)
export const authConfigurationMissing = !import.meta.env.DEV && !authEnabled

const manager = authEnabled ? new UserManager({
  authority: authority!,
  client_id: clientId!,
  redirect_uri: `${window.location.origin}/`,
  response_type: 'code',
  scope: 'openid email',
  automaticSilentRenew: false,
  loadUserInfo: false,
  revokeTokenTypes: ['refresh_token'],
  userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
  stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  requestTimeoutInSeconds: 10,
}) : null

let initialization: Promise<boolean> | undefined

export function initializeAuth(): Promise<boolean> {
  initialization ??= (async () => {
    if (authConfigurationMissing) throw new Error('Cognito configuration is required for this deployment.')
    if (!manager) return true
    const params = new URLSearchParams(window.location.search)
    if (params.has('code') || params.has('error')) {
      try {
        await manager.signinRedirectCallback()
      } finally {
        window.history.replaceState({}, document.title, '/')
      }
    }
    const user = await manager.getUser()
    return Boolean(user && !user.expired)
  })()
  return initialization
}

export async function accessToken(): Promise<string | undefined> {
  if (authConfigurationMissing) throw new Error('Authentication is not configured.')
  if (!manager) return undefined
  const user = await manager.getUser()
  if (!user || user.expired) throw new Error('Your session expired. Sign out and sign in again.')
  return user.access_token
}

export async function signIn(): Promise<void> {
  if (!manager) throw new Error('Cognito configuration is missing.')
  await manager.clearStaleState()
  await manager.signinRedirect()
}

export async function signOut(): Promise<void> {
  await manager?.removeUser()
  const destination = new URL('/logout', domain)
  destination.searchParams.set('client_id', clientId!)
  destination.searchParams.set('logout_uri', `${window.location.origin}/`)
  window.location.assign(destination)
}
