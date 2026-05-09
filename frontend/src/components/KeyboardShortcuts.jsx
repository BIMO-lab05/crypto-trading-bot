import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../contexts/ToastContext'

/**
 * KeyboardShortcuts — global vim-ish nav bindings.
 *
 * `g` then a target key navigates:
 *   g d → /              Main Dashboard
 *   g o → /portfolio     Portfolio
 *   g p → /performance   Performance Analytics
 *   g 1 → /phase1
 *   g 3 → /phase3
 *   g s → /settings
 *
 * The `g` prefix is held in state for 1.2s. If the next key matches a
 * target, navigation fires and a toast confirms. Bindings are skipped
 * inside inputs, textareas, and contenteditable to avoid eating typing.
 */

const TARGETS = {
  d: { path: '/', label: 'Main Dashboard' },
  o: { path: '/portfolio', label: 'Portfolio' },
  p: { path: '/performance', label: 'Performance' },
  '1': { path: '/phase1', label: 'Phase 1' },
  '3': { path: '/phase3', label: 'Phase 3' },
  s: { path: '/settings', label: 'Settings' },
}

const isTextEntry = (el) => {
  if (!el) return false
  if (el.isContentEditable) return true
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

export default function KeyboardShortcuts() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const armedRef = useRef(false)
  const armedTimerRef = useRef(null)

  useEffect(() => {
    const disarm = () => {
      armedRef.current = false
      if (armedTimerRef.current) {
        clearTimeout(armedTimerRef.current)
        armedTimerRef.current = null
      }
    }

    const onKey = (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (isTextEntry(document.activeElement)) return

      const k = e.key.toLowerCase()

      if (armedRef.current) {
        const target = TARGETS[k]
        disarm()
        if (target) {
          e.preventDefault()
          navigate(target.path)
          toast(`→ ${target.label}`, { ttl: 1500 })
        }
        return
      }

      if (k === 'g') {
        // Don't eat 'g' in case the user just typed it inside something we
        // missed; only arm if next key is one of our targets.
        armedRef.current = true
        armedTimerRef.current = setTimeout(disarm, 1200)
      }
    }

    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      disarm()
    }
  }, [navigate, toast])

  return null
}
