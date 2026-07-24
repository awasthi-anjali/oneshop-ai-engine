import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { getPersonalizationUserId, setPersonalizationUserId } from '../api'
import ProfileSwitcher from './ProfileSwitcher'

describe('ProfileSwitcher', () => {
  beforeEach(() => localStorage.clear())

  it('shows all five personas and persists the selected profile across channels', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn((id: string) => setPersonalizationUserId(id))
    render(<ProfileSwitcher userId="user_001" onChange={onChange} />)

    const select = screen.getByRole('combobox', { name: 'Choose demo profile' })
    expect(screen.getAllByRole('option')).toHaveLength(5)
    await user.selectOptions(select, 'user_021')

    expect(onChange).toHaveBeenCalledWith('user_021')
    expect(getPersonalizationUserId()).toBe('user_021')
  })
})
