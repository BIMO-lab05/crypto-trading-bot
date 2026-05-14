import React, { useState } from 'react'
import { Check } from 'lucide-react'

/**
 * SignificanceBadge — green "✓ in ensemble" pill with on-hover tooltip,
 * or a muted em-dash when the row is not in an ensemble for a
 * win-gate-passed symbol.
 *
 * Decisions referenced:
 *   - D-04  badge column + hover tooltip (not row-tinting)
 *   - D-05  when significance is null (Phase 4 not run) → em-dash with no tooltip
 *
 * No external tooltip library — pure-CSS / useState hover state per UI-SPEC
 * line 145 (no Radix Tooltip in package.json).
 */

// Editorial Trading Floor palette tokens — inlined per phase convention
// (no shared tokens module — out of scope per Phase 6 06-PATTERNS.md).
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

const MINUS = '−' // U+2212 minus, not ASCII hyphen
const EMDASH = '—' // U+2014 em-dash

function formatSignedPct(value) {
  // value is a raw lift in absolute units (e.g. 0.0142 for 1.42pp). Show
  // signed percentage to 2dp.
  if (value == null || !Number.isFinite(value)) return `${EMDASH}`
  const pct = value * 100
  const sign = pct >= 0 ? '+' : MINUS
  return `${sign}${Math.abs(pct).toFixed(2)}%`
}

function formatPValue(p) {
  if (p == null || !Number.isFinite(p)) return `${EMDASH}`
  return p.toFixed(3)
}

export default function SignificanceBadge({ inEnsemble, winGatePassed, significance }) {
  const [hovered, setHovered] = useState(false)
  const showPill = Boolean(inEnsemble) && Boolean(winGatePassed)

  if (!showPill) {
    return (
      <span
        data-testid="significance-badge-none"
        style={{
          color: C.text3,
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: 13,
        }}
      >
        {EMDASH}
      </span>
    )
  }

  const hasTooltipPayload = significance != null

  return (
    <span
      style={{ position: 'relative', display: 'inline-block' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span
        data-testid="significance-badge-pass"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: '2px 8px',
          borderRadius: 4,
          border: `1px solid ${C.gain}`,
          background: 'rgba(94, 234, 212, 0.12)',
          color: C.gain,
          fontFamily: 'Manrope, system-ui, sans-serif',
          fontSize: 11,
          fontWeight: 600,
        }}
      >
        <Check size={11} />
        {'✓ in ensemble'}
      </span>
      {hovered && hasTooltipPayload && (
        <div
          role="tooltip"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            zIndex: 50,
            maxWidth: 280,
            background: C.surface,
            border: `1px solid ${C.borderStrong}`,
            padding: 8,
            borderRadius: 4,
            fontFamily: 'Manrope, system-ui, sans-serif',
            fontSize: 11,
            color: C.text,
            whiteSpace: 'normal',
            pointerEvents: 'none',
          }}
        >
          {'Sharpe lift '}
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontFeatureSettings: '"tnum" 1' }}>
            {formatSignedPct(significance.sharpe_lift)}
          </span>
          {' (p='}
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontFeatureSettings: '"tnum" 1' }}>
            {formatPValue(significance.sharpe_pvalue)}
          </span>
          {') · Dir.Acc lift '}
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontFeatureSettings: '"tnum" 1' }}>
            {formatSignedPct(significance.dir_acc_lift)}
          </span>
          {' (p='}
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontFeatureSettings: '"tnum" 1' }}>
            {formatPValue(significance.dir_acc_pvalue)}
          </span>
          {') · block_size='}
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontFeatureSettings: '"tnum" 1' }}>
            {significance.block_size ?? EMDASH}
          </span>
          {' · n_resamples='}
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontFeatureSettings: '"tnum" 1' }}>
            {significance.n_resamples ?? EMDASH}
          </span>
        </div>
      )}
    </span>
  )
}
