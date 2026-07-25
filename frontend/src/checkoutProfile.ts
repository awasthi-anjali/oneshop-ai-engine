import { DEMO_USERS, type CheckoutProfile } from './api'

const CHECKOUT_PROFILE_KEY = 'oneshop_checkout_profile'

const LOCAL_DEFAULTS: Record<string, CheckoutProfile> = {
  user_001: {
    full_name: 'Anjali',
    email: 'anjali00223@gmail.com',
    card_number: '4242424242424242',
  },
  user_011: {
    full_name: 'Dev Patel',
    email: 'dev.patel@techmail.demo',
    card_number: '5555555555554444',
  },
  user_021: {
    full_name: 'Morgan Brooks',
    email: 'morgan.brooks@workmail.demo',
    card_number: '378282246310005',
  },
  user_031: {
    full_name: 'Greta Lindstrom',
    email: 'greta.lindstrom@seniormail.demo',
    card_number: '6011111111111117',
  },
  user_041: {
    full_name: 'Chris Nguyen',
    email: 'chris.nguyen@familymail.demo',
    card_number: '4000000000009995',
  },
}

function storageKey(userId: string) {
  return `${CHECKOUT_PROFILE_KEY}:${userId}`
}

function readLocal(userId: string): CheckoutProfile | null {
  try {
    const raw = localStorage.getItem(storageKey(userId))
    if (!raw) return null
    return JSON.parse(raw) as CheckoutProfile
  } catch {
    return null
  }
}

function writeLocal(userId: string, profile: CheckoutProfile) {
  localStorage.setItem(storageKey(userId), JSON.stringify(profile))
}

export function getDefaultCheckoutProfile(userId: string): CheckoutProfile {
  const demo = DEMO_USERS.find((user) => user.id === userId)
  const fallback = LOCAL_DEFAULTS[userId] ?? LOCAL_DEFAULTS.user_001
  if (demo?.full_name) {
    return {
      full_name: demo.full_name,
      email: demo.email ?? fallback.email,
      card_number: demo.card_number ?? fallback.card_number,
    }
  }
  return fallback
}

export function formatCardNumber(value: string): string {
  const digits = value.replace(/\D/g, '').slice(0, 19)
  return digits.replace(/(\d{4})(?=\d)/g, '$1 ').trim()
}

export async function fetchCheckoutProfile(userId: string): Promise<CheckoutProfile> {
  try {
    const res = await fetch(`/api/recommendations/${userId}/checkout-profile`)
    if (!res.ok) throw new Error('Failed to load checkout profile')
    const profile = (await res.json()) as CheckoutProfile
    writeLocal(userId, profile)
    return profile
  } catch {
    return readLocal(userId) ?? getDefaultCheckoutProfile(userId)
  }
}

export async function saveCheckoutProfile(
  userId: string,
  patch: Partial<CheckoutProfile>,
): Promise<CheckoutProfile> {
  const current = readLocal(userId) ?? getDefaultCheckoutProfile(userId)
  const next: CheckoutProfile = {
    full_name: patch.full_name?.trim() || current.full_name,
    email: patch.email?.trim() || current.email,
    card_number: (patch.card_number ?? current.card_number).replace(/\D/g, ''),
  }
  writeLocal(userId, next)
  try {
    const res = await fetch(`/api/recommendations/${userId}/checkout-profile`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
    if (res.ok) {
      const profile = (await res.json()) as CheckoutProfile
      writeLocal(userId, profile)
      return profile
    }
  } catch {
    /* keep local copy */
  }
  return next
}

export function applyCheckoutProfileFromChat(userId: string, profile: CheckoutProfile) {
  writeLocal(userId, profile)
}
