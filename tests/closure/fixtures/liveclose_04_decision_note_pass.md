# T0.1.x Horizon Sweep — Decision Note (FIXTURE)

Fixture for LIVECLOSE-04 harness unit tests. Mirrors the real
`.planning/evidence/t0_1_x/decision_note.md` structure: prose body,
trailing terminal-verdict line on the final non-blank line.

## Tournament ID

`t0_1_x_horizon_sweep`

## Bootstrap Methodology

Stationary block bootstrap, B=2000 resamples, block size sqrt(n_oos_bars),
test statistic per-symbol Sharpe lift vs persistence baseline, two-sided.

## Per-Symbol Results

| Symbol  | sharpe_pvalue | dir_acc_pvalue | sharpe_lift | dir_acc_lift |
| ------- | ------------- | -------------- | ----------- | ------------ |
| SOLUSDT | 0.02          | 0.03           | 0.5         | 0.01         |
| BNBUSDT | 0.04          | 0.04           | 0.3         | 0.005        |
| ADAUSDT | 0.10          | 0.15           | 0.1         | 0.002        |

Two of three symbols clear the p<0.05 threshold on both axes with positive lift.

## Verdict Rationale

n_winning_symbols >= 1 (W1 gate); win_gate passes for SOLUSDT and BNBUSDT.
ADAUSDT does not clear p<0.05 but is reported under [insufficient win-gate]
annotation for transparency.

EDGE_FOUND
