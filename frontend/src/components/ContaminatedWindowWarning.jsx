import React from 'react'
import { AlertTriangle } from 'lucide-react'

/**
 * ContaminatedWindowWarning — full-width footer strip rendered above the
 * regular tournament footer line when ANY snapshot row has
 * `train_window_includes_contaminated=true`.
 *
 * Decisions referenced:
 *   - D-08 (Phase 3) — contamination flag set when train window crosses
 *     the 2026-04-25 testnet→mainnet flip
 *   - D-10 (Phase 7) — footer warning, visually unmissable
 */

// Editorial Trading Floor palette tokens — inlined per phase convention.
const C = {
  bg: '#0a0a0b',
  surface: '#18181c',
  surface2: '#1f1f24',
  border: '#2a2a32',
  borderStrong: '#3a3a44',
  text: '#f5f3ee',
  text2: '#a09e98',
  text3: '#8a8982',
  gain: '#5eead4',
  loss: '#fb7185',
  gold: '#d4af6a',
}

export default function ContaminatedWindowWarning({ visible }) {
  if (!visible) return null
  return (
    <div
      data-testid="contaminated-warning"
      style={{
        width: '100%',
        borderTop: `1px solid ${C.loss}`,
        paddingTop: 24,
        paddingBottom: 24,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        alignItems: 'center',
        textAlign: 'center',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <AlertTriangle
          size={14}
          stroke={C.loss}
          aria-hidden="true"
          // Native browser tooltip — no custom hover stack; the strip body
          // already carries the warning. Title text mirrors UI-SPEC line 286.
          // eslint-disable-next-line react/no-unknown-property
          {...{ title: 'Pre-2026-04-25 testnet history may be polluting metrics — see Phase 3 D-08.' }}
        />
        <span
          style={{
            color: C.loss,
            fontFamily: 'Manrope, system-ui, sans-serif',
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          Train window includes contaminated candles
        </span>
      </div>
      <div
        style={{
          color: C.text3,
          fontFamily: 'Manrope, system-ui, sans-serif',
          fontSize: 11,
          fontWeight: 500,
        }}
      >
        Pre-2026-04-25 testnet history flagged per Phase 3 D-08. DSR / Sharpe figures may be polluted.
      </div>
    </div>
  )
}
