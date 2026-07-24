import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  getPersonalizedRecommendations,
  subscribeToPersonalizedRecommendations,
  trackInteraction,
} from './api'

const product = {
  id: 'phone-1',
  name: 'Phone 1',
  category: 'phone',
  brand: 'Demo',
  price: 399,
  description: 'Demo phone',
  features: [],
  specs: {},
  image_url: '',
  rating: 4,
  in_stock: true,
  tags: [],
}

function response(version = 3) {
  return {
    user_id: 'user_001',
    session_id: 'session-1',
    channel: 'oneshop',
    version,
    profile: {
      brand_affinity: { Demo: 1 },
      category_affinity: { phone: 1 },
      price_signal: { centroid: 399 },
      recent_views: [],
      cart_exclusions: [],
      wishlist_exclusions: [],
      channels: ['oneshop'],
      interaction_counts: { product_view: 2 },
      total_interactions: 2,
      cold_start: false,
    },
    recommendations: [{
      product,
      score: 0.9,
      explanation: 'Matches recorded Demo affinity.',
      reason_codes: ['BRAND_AFFINITY'],
      score_breakdown: { brand_affinity: 1, popularity: 0.5 },
    }],
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('personalization API', () => {
  it('normalizes backend profile evidence and ranking versions', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => response(),
    }))
    const result = await getPersonalizedRecommendations('user_001', 'session-1', 'oneshop')
    expect(result.profile_version).toBe(3)
    expect(result.profile.price_centroid).toBe(399)
    expect(result.profile.channels_used).toEqual(['oneshop'])
    expect(result.recommendations[0].reason_codes).toEqual(['BRAND_AFFINITY'])
  })

  it('rejects failed initial fetches with a resilient user-facing error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    await expect(
      getPersonalizedRecommendations('user_001', null, 'oneapp')
    ).rejects.toThrow('temporarily unavailable')
  })

  it('sends a client-generated event_id and never derives negative non-click events', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ accepted: true }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await trackInteraction({
      user_id: 'user_001',
      event_type: 'rec_click',
      product_id: product.id,
      channel: 'oneshop',
      session_id: 'session-1',
      metadata: { rec_position: 1, surface: 'for_you' },
    })
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(payload.event_id).toMatch(/.+/)
    expect(payload.event_type).toBe('rec_click')
    expect(payload.metadata).toEqual({ rec_position: 1, surface: 'for_you' })
  })

  it('sends one schema-valid neutral impression for a visible product', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ accepted: true }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await trackInteraction({
      user_id: 'user_001',
      event_type: 'impression',
      product_id: product.id,
      channel: 'oneapp',
      session_id: 'session-1',
      metadata: { surface: 'for_you', visible: true },
    })
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(payload.product_id).toBe(product.id)
    expect(payload.metadata).toEqual({ surface: 'for_you', visible: true })
    expect(payload.metadata).not.toHaveProperty('product_ids')
    expect(payload.metadata).not.toHaveProperty('profile_version')
  })

  it('applies a versioned update and can be cleanly stopped', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => response(4),
    })
    vi.stubGlobal('fetch', fetchMock)
    const onUpdate = vi.fn()
    const stop = subscribeToPersonalizedRecommendations(
      'user_001', 'session-1', 'oneshop', 'general', 6, onUpdate, vi.fn()
    )
    await vi.runOnlyPendingTimersAsync()
    expect(onUpdate).toHaveBeenCalled()
    expect(onUpdate.mock.calls[0][0].profile_version).toBe(4)
    expect(fetchMock.mock.calls[0][0]).toContain('after_version=0')
    stop()
  })

  it('does not replace visible rankings for an unchanged update response', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        changed: false,
        user_id: 'user_001',
        version: 4,
        recommendations: [],
      }),
    }))
    const onUpdate = vi.fn()
    const stop = subscribeToPersonalizedRecommendations(
      'user_001', null, 'oneapp', 'general', 6, onUpdate, vi.fn()
    )
    await vi.runOnlyPendingTimersAsync()
    expect(onUpdate).not.toHaveBeenCalled()
    stop()
  })
})
