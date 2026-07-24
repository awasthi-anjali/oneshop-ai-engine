import { DEMO_USERS } from '../api'

interface Props {
  userId: string
  onChange: (userId: string) => void
}

export default function ProfileSwitcher({ userId, onChange }: Props) {
  const selected = DEMO_USERS.find((user) => user.id === userId) ?? DEMO_USERS[0]
  return (
    <section className="profile-switcher" aria-label="Demo personalization profile">
      <div>
        <span className="profile-switcher-label">Demo profile</span>
        <strong>{selected.emoji} {selected.name}</strong>
        <small>{selected.description} · shared across Web + Mobile</small>
      </div>
      <label>
        <span className="sr-only">Choose demo profile</span>
        <select value={userId} onChange={(event) => onChange(event.target.value)}>
          {DEMO_USERS.map((user) => (
            <option key={user.id} value={user.id}>
              {user.emoji} {user.name} — {user.description}
            </option>
          ))}
        </select>
      </label>
    </section>
  )
}
