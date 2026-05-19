# T0.1.x Horizon Sweep — Decision Note (FIXTURE)

Fixture for LIVECLOSE-04 harness unit tests. Models the INSUFFICIENT_DATA
branch — the sweep ran but per-symbol n_members < 3 across the board,
so the win_gate emits insufficient_runs reasons and no terminal verdict
of EDGE_FOUND or NO_EDGE_FOUND can be claimed.

## Tournament ID

`t0_1_x_horizon_sweep`

## Bootstrap Methodology

Not applicable — too few members per symbol to compute p-values.

## Per-Symbol Results

| Symbol  | sharpe_pvalue | dir_acc_pvalue | n_members |
| ------- | ------------- | -------------- | --------- |
| SOLUSDT | null          | null           | 1         |

## Verdict Rationale

CD-08 sub-3-member guard fires; no symbol has enough runs to compute
bootstrap p-values. Operator must rerun the sweep with more horizons
or wait for additional accrual.

INSUFFICIENT_DATA
