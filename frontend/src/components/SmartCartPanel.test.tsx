import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import type { BundleSuggestion, CrossSellItem, Product } from '../api'
import SmartCartPanel from './SmartCartPanel'

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

const compatiblePlan: BundleSuggestion = {
  name: 'Device + Plan',
  products: [plan],
  product_ids: [plan.id],
  total_price: 85,
  original_price: 85,
  discount_percent: 0,
  savings: 0,
  reason: 'A plan option selected from the current catalog.',
}

const addOn: CrossSellItem = {
  product: plan,
  rate: 0,
  reason: 'Compatible catalog add-on',
}

function renderPanel(overrides: Partial<ComponentProps<typeof SmartCartPanel>> = {}) {
  const props: ComponentProps<typeof SmartCartPanel> = {
    bundles: [compatiblePlan],
    crossSell: [addOn],
    nudge: 'Review your cart and compatible add-ons before checkout.',
    checkoutTip: '',
    aiPowered: false,
    cartCount: 2,
    cartItems: [phone, plan],
    oneTimeTotal: 699,
    monthlyTotal: 85,
    onCheckout: vi.fn(),
    onAddBundle: vi.fn(),
    onAddCrossSell: vi.fn(),
    onRemoveFromCart: vi.fn(),
    ...overrides,
  }
  return { ...render(<SmartCartPanel {...props} />), props }
}

describe('SmartCartPanel trusted totals', () => {
  it('separates one-time and monthly totals without inventing savings', () => {
    renderPanel()

    expect(screen.getByText('$699.00')).toBeInTheDocument()
    expect(screen.getByText('$85.00/month')).toBeInTheDocument()
    expect(screen.getByText('Catalog compatible')).toBeInTheDocument()
    expect(screen.getByText('No offer assumed')).toBeInTheDocument()
    expect(screen.queryByText(/saved|% off|free shipping/i)).not.toBeInTheDocument()
  })

  it('mutates only after the explicit compatible-bundle button is clicked', async () => {
    const user = userEvent.setup()
    const { props } = renderPanel()

    expect(props.onAddBundle).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Allow & add bundle' }))
    expect(props.onAddBundle).toHaveBeenCalledOnce()
    expect(props.onAddBundle).toHaveBeenCalledWith(['unlimited-plus'])
  })
})
