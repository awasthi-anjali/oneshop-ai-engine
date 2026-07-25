import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Product } from '../api'
import CheckoutModal from './CheckoutModal'

const phone: Product = {
  id: 'google-pixel-8',
  name: 'Google Pixel 8',
  category: 'phone',
  brand: 'Google',
  price: 699,
  description: 'Camera phone',
  features: [],
  specs: {},
  image_url: '',
  rating: 4.6,
  in_stock: true,
  tags: ['android', 'camera'],
  currency: 'USD',
  billing_period: 'one_time',
}

const plan: Product = {
  ...phone,
  id: 'unlimited-plus',
  name: 'Unlimited Plus Plan',
  category: 'plan',
  brand: 'OneTel',
  price: 85,
  billing_period: 'monthly',
}

describe('CheckoutModal trusted demo review', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('keeps cadence totals separate and clearly labels simulated payment', () => {
    render(
      <CheckoutModal
        open
        cart={[phone, plan]}
        sessionId="checkout-test"
        userId="user_001"
        onClose={vi.fn()}
        onReview={vi.fn()}
      />,
    )

    expect(screen.getByText('$699.00')).toBeInTheDocument()
    expect(screen.getByText('$85.00/month')).toBeInTheDocument()
    expect(screen.getByText('No promotional discount is assumed.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create final review' })).toBeInTheDocument()
    expect(screen.getByText(/raw number stays in this form/i)).toBeInTheDocument()
    expect(screen.queryByText('$784.00')).not.toBeInTheDocument()
  })

  it('maps the approved card to a demo token and never sends the raw number', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        review_id: 'rev_1234567890123456',
        session_id: 'checkout-test',
        status: 'awaiting_confirmation',
        items: [],
        one_time_total_minor: 69900,
        monthly_total_minor: 8500,
        customer_name: 'Demo User',
        email: 'demo@example.com',
        payment_mode: 'demo_simulated',
        payment_status: 'simulated',
        payment_last4: '4242',
        confirmation_token: 'token_1234567890123456',
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(
      <CheckoutModal
        open
        cart={[phone, plan]}
        sessionId="checkout-test"
        userId="user_001"
        onClose={vi.fn()}
        onReview={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Demo User' } })
    fireEvent.change(screen.getByLabelText('Email for this demo receipt'), {
      target: { value: 'demo@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /use 4242/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Create final review' }))

    await screen.findByText('Review your demo order')
    const payload = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(payload.demo_payment_method).toBe('demo_card_success')
    expect(JSON.stringify(payload)).not.toContain('4242424242424242')
    expect(payload).not.toHaveProperty('payment_last4')
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  })
})
