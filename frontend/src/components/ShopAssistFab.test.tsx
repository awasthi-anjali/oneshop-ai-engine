import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ShopAssistFab from './ShopAssistFab'

describe('ShopAssistFab', () => {
  it('opens Ava from an accessible global launcher and hides with the drawer', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    const { rerender } = render(<ShopAssistFab hidden={false} onOpen={onOpen} />)

    const launcher = screen.getByRole('button', { name: 'Open Ava' })
    expect(launcher).toBeInTheDocument()
    expect(screen.getByRole('tooltip')).toHaveTextContent('Ava')

    await user.click(launcher)
    expect(onOpen).toHaveBeenCalledOnce()
    expect(onOpen).toHaveBeenCalledWith(launcher)

    rerender(<ShopAssistFab hidden onOpen={onOpen} />)
    expect(screen.queryByRole('button', { name: 'Open Ava' })).not.toBeInTheDocument()
  })
})
