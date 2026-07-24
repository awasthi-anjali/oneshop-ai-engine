import { useState, type ComponentProps } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  CartProposal,
  ChatAction,
  Product,
  ShoppingNeed,
  ShopAssistRecommendation,
} from '../api'
import ShopAssistDrawer from './ShopAssistDrawer'

const phone: Product = {
  id: 'google-pixel-8',
  name: 'Google Pixel 8',
  category: 'phone',
  brand: 'Google',
  price: 699,
  description: 'Camera phone',
  features: ['Google Tensor G3'],
  specs: {},
  image_url: '',
  rating: 4.6,
  in_stock: true,
  tags: ['android', 'camera'],
  currency: 'USD',
  billing_period: 'one_time',
}

const plan: Product = {
  id: 'unlimited-plus',
  name: 'Unlimited Plus Plan',
  category: 'plan',
  brand: 'OneTel',
  price: 85,
  description: 'International plan',
  features: ['International roaming'],
  specs: {},
  image_url: '',
  rating: 4.5,
  in_stock: true,
  tags: ['international'],
  currency: 'USD',
  billing_period: 'monthly',
}

const alternativePhone: Product = {
  ...phone,
  id: 'oneplus-12',
  name: 'OnePlus 12',
  brand: 'OnePlus',
  price: 799,
}

const recommendations: ShopAssistRecommendation[] = [
  {
    product: phone,
    slot: 'primary_phone',
    reason_codes: ['CAMERA_MATCH'],
    reason: 'Catalog camera match.',
  },
  {
    product: plan,
    slot: 'recommended_plan',
    reason_codes: ['ROAMING_MATCH'],
    reason: 'Catalog roaming match.',
  },
]

const need: ShoppingNeed = {
  categories: ['phone', 'plan'],
  use_cases: ['photography'],
  device_budget_max: 700,
  monthly_budget_max: 90,
  platform: 'android',
  roaming_required: true,
  must_haves: [],
  nice_to_haves: [],
}

const proposal: ChatAction = {
  type: 'PROPOSE_ADD_BUNDLE',
  label: 'Review Google Pixel 8 + Unlimited Plus Plan',
  product_ids: [phone.id, plan.id],
}

function baseProps(overrides: Partial<ComponentProps<typeof ShopAssistDrawer>> = {}) {
  return {
    open: true,
    messages: [{ role: 'assistant' as const, content: 'Grounded result' }],
    draft: '',
    loading: false,
    error: null,
    status: 'recommended' as const,
    mode: 'fallback' as const,
    need,
    context: null,
    contextProduct: null,
    recommendations,
    recommendationMode: 'request' as const,
    recommendationHeading: 'ShopAssist recommends',
    comparison: [],
    actions: [],
    cartProposal: null,
    confirming: false,
    confirmed: false,
    onClose: vi.fn(),
    onDraftChange: vi.fn(),
    onSend: vi.fn(),
    onRetry: vi.fn(),
    onRemoveContext: vi.fn(),
    onRemoveNeed: vi.fn(),
    onAction: vi.fn(),
    onConfirmProposal: vi.fn(),
    onViewPicks: vi.fn(),
    ...overrides,
  }
}

const cartProposal: CartProposal = {
  proposal_id: 'proposal_1234567890',
  products: [phone, plan],
  product_ids: [phone.id, plan.id],
  excluded_product_ids: [],
  one_time_total: 699,
  monthly_total: 85,
}

class MockSpeechRecognition {
  lang = 'en-US'
  continuous = false
  interimResults = true
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
  onresult: ((event: {
    resultIndex: number
    results: Array<{ isFinal: boolean; 0: { transcript: string } }>
  }) => void) | null = null

  start = vi.fn(() => {
    this.onstart?.()
    this.onresult?.({
      resultIndex: 0,
      results: [{ isFinal: true, 0: { transcript: 'Android camera phone under $700' } }],
    })
    this.onend?.()
  })

  stop = vi.fn(() => this.onend?.())
  abort = vi.fn(() => this.onend?.())
}

describe('ShopAssistDrawer', () => {
  beforeEach(() => {
    ;(window as Window & { SpeechRecognition?: typeof MockSpeechRecognition }).SpeechRecognition =
      MockSpeechRecognition
  })

  afterEach(() => {
    delete (window as Window & { SpeechRecognition?: typeof MockSpeechRecognition }).SpeechRecognition
  })

  it('renders compact request pills, expands the best match, and requires explicit shop handoff', async () => {
    const user = userEvent.setup()
    const onViewPicks = vi.fn()

    render(<ShopAssistDrawer {...baseProps({ onViewPicks })} />)

    expect(screen.getByRole('heading', { name: 'ShopAssist recommends' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Best match: Google Pixel 8/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /Plan: Unlimited Plus Plan/ })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('Catalog camera match.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'View in shop' }))
    expect(onViewPicks).toHaveBeenCalledOnce()
  })

  it('shows collapsed profile recommendation pills as soon as the drawer opens', async () => {
    const user = userEvent.setup()
    render(
      <ShopAssistDrawer
        {...baseProps({
          messages: [],
          recommendationMode: 'profile',
          recommendationHeading: 'Recommended for Alex',
        })}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Recommended for Alex' })).toBeInTheDocument()
    const topPick = screen.getByRole('button', { name: /Top pick: Google Pixel 8/ })
    expect(topPick).toHaveAttribute('aria-pressed', 'false')
    expect(screen.queryByText('Catalog camera match.')).not.toBeInTheDocument()
    topPick.focus()
    await user.keyboard('{Enter}')
    expect(topPick).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Catalog camera match.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View For You' })).toBeInTheDocument()
  })

  it('uses direct quick replies and a grounded AI disclosure', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(
      <ShopAssistDrawer
        {...baseProps({
          messages: [{ role: 'assistant', content: 'Hi! Tell me what you need.' }],
          status: 'clarifying',
          need: {
            ...need,
            categories: [],
            use_cases: [],
            device_budget_max: null,
            monthly_budget_max: null,
          },
          recommendations: [],
          onSend,
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Find a phone' }))
    expect(onSend).toHaveBeenCalledWith('Help me find a phone for my needs.')
    expect(screen.getByText(/AI-guided answers can be inaccurate/i)).toBeInTheDocument()
    expect(screen.getByText(/prices, and cart changes are validated by OneShop/i)).toBeInTheDocument()
  })

  it('offers concise budget replies for a phone-and-plan clarification', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(
      <ShopAssistDrawer
        {...baseProps({
          messages: [{ role: 'assistant', content: 'What are your budgets?' }],
          status: 'clarifying',
          recommendations: [],
          need: { ...need, device_budget_max: null, monthly_budget_max: null },
          onSend,
        })}
      />,
    )

    await user.click(screen.getByRole('button', { name: '$500 phone + $60 plan' }))
    expect(onSend).toHaveBeenCalledWith(
      'Android phone under $500 and plan under $60 per month.',
    )
  })

  it('removes welcome picks after chat starts and hides stale request picks during the next turn', () => {
    const { rerender } = render(
      <ShopAssistDrawer
        {...baseProps({
          messages: [],
          recommendationMode: 'profile',
          recommendationHeading: 'Recommended for Alex',
        })}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Recommended for Alex' })).toBeInTheDocument()

    rerender(
      <ShopAssistDrawer
        {...baseProps({
          messages: [{ role: 'user', content: 'Help me choose a phone' }],
          recommendationMode: 'profile',
          recommendationHeading: 'Recommended for Alex',
          loading: true,
        })}
      />,
    )
    expect(screen.queryByRole('heading', { name: 'Recommended for Alex' })).not.toBeInTheDocument()

    rerender(
      <ShopAssistDrawer
        {...baseProps({
          messages: [{ role: 'user', content: 'Show me something cheaper' }],
          recommendationMode: 'request',
          recommendationHeading: 'ShopAssist recommends',
          loading: true,
        })}
      />,
    )
    expect(screen.queryByRole('heading', { name: 'ShopAssist recommends' })).not.toBeInTheDocument()
  })

  it('uses one compact header and hides demo or generic catalog context rows', () => {
    const { rerender } = render(
      <ShopAssistDrawer
        {...baseProps({
          context: {
            surface: 'catalog',
            entry_point: 'help_me_choose',
            visible_product_ids: [phone.id],
          },
        })}
      />,
    )

    expect(screen.getByRole('heading', { name: 'ShopAssist' })).toBeInTheDocument()
    expect(screen.getByText('Catalog mode')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Close ShopAssist' })).toHaveLength(1)
    expect(screen.queryByText(/synthetic demo data/i)).not.toBeInTheDocument()
    expect(screen.queryByText('Context: catalog')).not.toBeInTheDocument()

    rerender(
      <ShopAssistDrawer
        {...baseProps({
          context: {
            surface: 'product',
            entry_point: 'product_detail',
            product_id: phone.id,
          },
          contextProduct: phone,
        })}
      />,
    )
    expect(screen.getByText('Helping with Google Pixel 8')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove context: Helping with Google Pixel 8' })).toBeInTheDocument()
  })

  it('keeps conversation and draft state when closed and reopened', async () => {
    const user = userEvent.setup()

    function Harness() {
      const [open, setOpen] = useState(true)
      const [draft, setDraft] = useState('')
      return (
        <>
          <button onClick={() => setOpen(true)}>Open guide</button>
          <ShopAssistDrawer
            {...baseProps({
              open,
              draft,
              onClose: () => setOpen(false),
              onDraftChange: setDraft,
            })}
          />
        </>
      )
    }

    render(<Harness />)
    const input = screen.getByRole('textbox', { name: 'Describe what you need' })
    await user.type(input, 'keep this draft')
    await user.click(screen.getByRole('button', { name: 'Close ShopAssist' }))
    expect(screen.getByLabelText('ShopAssist purchase guide')).toHaveAttribute('aria-hidden', 'true')

    await user.click(screen.getByRole('button', { name: 'Open guide' }))
    expect(screen.getByRole('textbox', { name: 'Describe what you need' })).toHaveValue('keep this draft')
    expect(screen.getByText('Grounded result')).toBeInTheDocument()
  })

  it('auto-sends voice input after speech is converted to text', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    const onDraftChange = vi.fn()
    render(<ShopAssistDrawer {...baseProps({ onSend, onDraftChange })} />)

    await user.click(screen.getByRole('button', { name: 'Start voice input' }))
    expect(onDraftChange).toHaveBeenCalledWith('Android camera phone under $700')
    expect(onSend).toHaveBeenCalledWith('Android camera phone under $700')
  })

  it('sends on Enter, preserves a newline on Shift+Enter, and blocks loading duplicates', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    const { rerender } = render(
      <ShopAssistDrawer {...baseProps({ draft: 'ready', onSend })} />
    )
    const input = screen.getByRole('textbox', { name: 'Describe what you need' })
    await user.click(input)
    await user.keyboard('{Shift>}{Enter}{/Shift}')
    expect(onSend).not.toHaveBeenCalled()
    await user.keyboard('{Enter}')
    expect(onSend).toHaveBeenCalledTimes(1)

    rerender(<ShopAssistDrawer {...baseProps({ draft: 'ready', loading: true, onSend })} />)
    expect(screen.getByRole('button', { name: 'Send to ShopAssist' })).toBeDisabled()
  })

  it('shows exact cadence and totals and submits only validated proposal IDs', async () => {
    const user = userEvent.setup()
    const onConfirmProposal = vi.fn()
    const { container } = render(
      <ShopAssistDrawer
        {...baseProps({ actions: [proposal], cartProposal, onConfirmProposal })}
      />
    )

    expect(container.querySelectorAll('.proposal-item-pill')).toHaveLength(2)
    expect(container.querySelector('.proposal-card li')).not.toBeInTheDocument()
    expect(screen.getByText('Due once: $699.00')).toBeInTheDocument()
    expect(screen.getByText('Monthly: $85.00/month')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirm and add exact bundle' }))
    expect(onConfirmProposal).toHaveBeenCalledOnce()
    expect(onConfirmProposal).toHaveBeenCalledWith(cartProposal.proposal_id)
  })

  it('shows trusted duplicate exclusions and distinguishes single-item confirmation', () => {
    render(
      <ShopAssistDrawer
        {...baseProps({
          cartProposal: {
            ...cartProposal,
            products: [phone],
            product_ids: [phone.id],
            excluded_product_ids: [phone.id],
            monthly_total: 0,
          },
        })}
      />,
    )

    expect(screen.getByText(/already in your cart will not be added twice/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm and add exact item' })).toBeInTheDocument()
  })

  it('removes a consumed proposal instead of leaving it below the next response', () => {
    const { rerender } = render(
      <ShopAssistDrawer
        {...baseProps({ cartProposal })}
      />,
    )
    expect(screen.getByRole('region', { name: 'Cart proposal' })).toBeInTheDocument()

    rerender(
      <ShopAssistDrawer
        {...baseProps({
          cartProposal: null,
          confirmed: true,
          messages: [
            { role: 'assistant', content: 'Added Google Pixel 8 to your cart.' },
            { role: 'user', content: "What's in my cart?" },
          ],
          loading: true,
        })}
      />,
    )

    expect(screen.queryByRole('region', { name: 'Cart proposal' })).not.toBeInTheDocument()
    expect(screen.getByText('Added Google Pixel 8 to your cart.')).toBeInTheDocument()
  })

  it('suppresses generated actions already represented by the compact recommendation controls', () => {
    render(
      <ShopAssistDrawer
        {...baseProps({
          actions: [
            { type: 'OPEN_PRODUCT', label: 'Open Pixel duplicate', product_ids: [phone.id] },
            { type: 'COMPARE', label: 'Compare duplicate', product_ids: [phone.id] },
            { type: 'REFINE', label: 'Refine duplicate', product_ids: [] },
            { type: 'HANDOFF_SERVICE', label: 'Specialist handoff available', product_ids: [] },
          ],
        })}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Open Pixel duplicate' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Compare duplicate' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Refine duplicate' })).not.toBeInTheDocument()
    expect(screen.getByText('Specialist handoff available')).toBeInTheDocument()
  })

  it('offers comparison only when the trusted backend action allows it', () => {
    const twoPhones: ShopAssistRecommendation[] = [
      recommendations[0],
      {
        product: alternativePhone,
        slot: 'alternative_phone',
        reason_codes: [],
        reason: 'Catalog alternative.',
      },
    ]
    const { rerender } = render(
      <ShopAssistDrawer {...baseProps({ recommendations: twoPhones })} />,
    )
    expect(screen.queryByRole('button', { name: 'Compare phones' })).not.toBeInTheDocument()

    rerender(
      <ShopAssistDrawer
        {...baseProps({
          recommendations: twoPhones,
          actions: [{
            type: 'COMPARE',
            label: 'Compare recommended phones',
            product_ids: [phone.id, alternativePhone.id],
          }],
        })}
      />,
    )
    expect(screen.getByRole('button', { name: 'Compare phones' })).toBeInTheDocument()
  })

  it('fails closed for stale proposal IDs and closes with Escape', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <ShopAssistDrawer
        {...baseProps({
          cartProposal: { ...cartProposal, product_ids: [phone.id, 'stale-plan'] },
          onClose,
        })}
      />
    )

    expect(screen.getByText(/proposal is stale or incomplete/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm and add exact bundle' })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })
})
