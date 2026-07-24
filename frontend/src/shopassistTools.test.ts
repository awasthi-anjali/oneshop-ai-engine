import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  confirmShopAssistCartProposal,
  sendMessage,
  type ChatResponse,
} from './api'

const baseResponse: ChatResponse = {
  session_id: 'session-1',
  status: 'recommended',
  message: 'Cart proposal only—your cart is unchanged.',
  need_profile: {
    categories: ['phone'],
    use_cases: [],
    must_haves: [],
    nice_to_haves: [],
  },
  recommendations: [],
  comparison: null,
  actions: [{
    type: 'PROPOSE_ADD_TO_CART',
    label: 'Review Google Pixel 8',
    product_ids: ['google-pixel-8'],
    proposal_id: 'proposal_1234567890',
  }],
  mode: 'fallback',
  suggested_actions: [],
  cart_updated: false,
  open_checkout: false,
  selected_tool: 'propose_add_to_cart',
  cart_summary: null,
  cart_proposal: {
    proposal_id: 'proposal_1234567890',
    products: [],
    product_ids: ['google-pixel-8'],
    excluded_product_ids: [],
    one_time_total: 699,
    monthly_total: 0,
  },
}

describe('ShopAssist cart tool API', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('preserves trusted tool selection, proposal identifiers, exclusions, and totals', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => baseResponse,
    }))

    const response = await sendMessage(
      'Add Pixel 8',
      'session-1',
      undefined,
      'oneshop',
      'user_001',
    )

    expect(response.selected_tool).toBe('propose_add_to_cart')
    expect(response.cart_proposal?.proposal_id).toBe('proposal_1234567890')
    expect(response.cart_proposal?.one_time_total).toBe(699)
    expect(response.cart_proposal?.excluded_product_ids).toEqual([])
    expect(response.cart_updated).toBe(false)
  })

  it('confirms by opaque proposal and stable idempotency key without sending product facts', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-1',
        proposal_id: 'proposal_1234567890',
        added_product_ids: ['google-pixel-8'],
        excluded_product_ids: [],
        idempotent_replay: false,
        cart_summary: {
          items: [],
          total_items: 1,
          one_time_total: 699,
          monthly_total: 0,
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const response = await confirmShopAssistCartProposal(
      'proposal_1234567890',
      'confirm-key-123',
      'session-1',
      'user_001',
      'oneshop',
    )
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)

    expect(body).toEqual({
      proposal_id: 'proposal_1234567890',
      idempotency_key: 'confirm-key-123',
      session_id: 'session-1',
      user_id: 'user_001',
      channel: 'oneshop',
    })
    expect(body).not.toHaveProperty('product_ids')
    expect(body).not.toHaveProperty('price')
    expect(response.cart_summary.one_time_total).toBe(699)
  })

  it('surfaces a backend confirmation failure without claiming a cart update', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Cart proposal pricing changed. Nothing was added.' }),
    }))

    await expect(confirmShopAssistCartProposal(
      'proposal_1234567890',
      'confirm-key-123',
      'session-1',
      'user_001',
    )).rejects.toThrow('pricing changed')
  })
})
