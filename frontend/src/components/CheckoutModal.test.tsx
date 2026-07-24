import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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

describe('CheckoutModal trusted totals', () => {
  it('does not combine one-time and monthly charges into a fake payable total', () => {
    render(
      <CheckoutModal
        open
        cart={[phone, plan]}
        sessionId="checkout-test"
        oneTimeTotal={699}
        monthlyTotal={85}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    expect(screen.getByText('$699.00')).toBeInTheDocument()
    expect(screen.getByText('$85.00/month')).toBeInTheDocument()
    expect(screen.getByText('No promotional discount is assumed.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm demo order' })).toBeInTheDocument()
    expect(screen.queryByText('$784.00')).not.toBeInTheDocument()
    expect(screen.queryByText(/bundle savings|recovery discount/i)).not.toBeInTheDocument()
  })
})
