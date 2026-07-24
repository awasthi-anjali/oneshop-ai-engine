import { useState, type ComponentProps } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
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
    comparison: [],
    actions: [],
    confirming: false,
    confirmed: false,
    onClose: vi.fn(),
    onDraftChange: vi.fn(),
    onSend: vi.fn(),
    onRetry: vi.fn(),
    onRemoveContext: vi.fn(),
    onRemoveNeed: vi.fn(),
    onAction: vi.fn(),
    onConfirmBundle: vi.fn(),
    ...overrides,
  }
}

class MockSpeechRecognition {
  lang = 'en-US'
  continuous = false
  interimResults = true
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
  onresult: ((event: { resultIndex: number; results: Array<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null = null

  start = vi.fn(() => {
    this.onstart?.()
    this.onresult?.({
      resultIndex: 0,
      results: [{ isFinal: true, 0: { transcript: 'Android camera phone under $700' } }],
    })
    this.onend?.()
  })

  stop = vi.fn(() => {
    this.onend?.()
  })

  abort = vi.fn(() => {
    this.onend?.()
  })
}

describe('ShopAssistDrawer', () => {
  beforeEach(() => {
    ;(window as Window & { SpeechRecognition?: typeof MockSpeechRecognition }).SpeechRecognition =
      MockSpeechRecognition
  })

  afterEach(() => {
    delete (window as Window & { SpeechRecognition?: typeof MockSpeechRecognition }).SpeechRecognition
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

  it('auto-sends voice input after speech is converted to text', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    const onDraftChange = vi.fn()
    render(
      <ShopAssistDrawer {...baseProps({ onSend, onDraftChange })} />
    )

    await user.click(screen.getByRole('button', { name: 'Start voice input' }))
    expect(onDraftChange).toHaveBeenCalledWith('Android camera phone under $700')
    expect(onSend).toHaveBeenCalledWith('Android camera phone under $700')
  })

  it('shows exact cadence and totals and submits only validated proposal IDs', async () => {
    const user = userEvent.setup()
    const onConfirmBundle = vi.fn()
    render(
      <ShopAssistDrawer
        {...baseProps({ actions: [proposal], onConfirmBundle })}
      />
    )

    expect(screen.getByText('Due once: $699.00')).toBeInTheDocument()
    expect(screen.getByText('Monthly: $85.00/month')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Confirm and add exact bundle' }))
    expect(onConfirmBundle).toHaveBeenCalledOnce()
    expect(onConfirmBundle).toHaveBeenCalledWith([phone.id, plan.id])
  })

  it('fails closed for stale proposal IDs and closes with Escape', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <ShopAssistDrawer
        {...baseProps({
          actions: [{ ...proposal, product_ids: [phone.id, 'stale-plan'] }],
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
