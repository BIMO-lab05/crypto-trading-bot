import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * useDialog - accessibility primitive for modal dialogs.
 *
 * - Closes on Escape.
 * - Traps Tab focus inside the container.
 * - Focuses the first focusable element on mount.
 * - Restores focus to the previously-focused element on unmount.
 *
 * Pair the returned `containerRef` with a wrapper that has
 * role="dialog", aria-modal="true", and aria-labelledby pointing at the title.
 *
 * @param {boolean} open - whether the dialog is mounted/visible
 * @param {() => void} onClose - close handler invoked on Escape
 */
export function useDialog(open, onClose) {
  const containerRef = useRef(null)
  const previousActiveRef = useRef(null)

  useEffect(() => {
    if (!open) return

    previousActiveRef.current = document.activeElement

    const container = containerRef.current
    if (container) {
      const focusables = container.querySelectorAll(FOCUSABLE_SELECTOR)
      const initial = focusables[0] || container
      initial.focus()
    }

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        onClose?.()
        return
      }
      if (event.key !== 'Tab' || !container) return

      const focusables = Array.from(
        container.querySelectorAll(FOCUSABLE_SELECTOR),
      ).filter((el) => !el.hasAttribute('disabled') && el.offsetParent !== null)
      if (focusables.length === 0) {
        event.preventDefault()
        container.focus()
        return
      }

      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement

      if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      const previous = previousActiveRef.current
      if (previous && typeof previous.focus === 'function') {
        previous.focus()
      }
    }
  }, [open, onClose])

  return containerRef
}
