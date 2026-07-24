interface Props {
  hidden: boolean
  onOpen: (source: HTMLButtonElement) => void
}

export default function ShopAssistFab({ hidden, onOpen }: Props) {
  if (hidden) return null

  return (
    <button
      type="button"
      className="shopassist-fab"
      aria-label="Open ShopAssist"
      onClick={(event) => onOpen(event.currentTarget)}
    >
      <svg
        aria-hidden="true"
        width="28"
        height="28"
        viewBox="0 0 24 24"
        fill="none"
      >
        <path
          d="M5.5 4.5h13A2.5 2.5 0 0 1 21 7v8a2.5 2.5 0 0 1-2.5 2.5h-7L7 21v-3.5H5.5A2.5 2.5 0 0 1 3 15V7a2.5 2.5 0 0 1 2.5-2.5Z"
          fill="currentColor"
        />
        <circle cx="8" cy="11" r="1.25" fill="var(--primary)" />
        <circle cx="12" cy="11" r="1.25" fill="var(--primary)" />
        <circle cx="16" cy="11" r="1.25" fill="var(--primary)" />
      </svg>
      <span className="shopassist-fab-tooltip" role="tooltip">ShopAssist</span>
    </button>
  )
}
