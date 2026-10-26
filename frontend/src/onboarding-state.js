const key = 'rasa-onboarding-v1'

export function shouldShowWelcome() {
  try { return localStorage.getItem(key) !== 'seen' } catch { return true }
}

export function rememberWelcome() {
  try { localStorage.setItem(key, 'seen') } catch { /* Closing still works when browser storage is unavailable. */ }
}
