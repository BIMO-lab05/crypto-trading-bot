VERDICT: UNRECONCILED

Residual **−$0.33900231** on a break of **+$176.90335601**. The reconstruction **overshoots** the
observed break by 34 cents (+0.19%), which exceeds the $0.01 bar this task was given.
**Task 4 is not cleared.**

The residual is **not** an unexplained remainder of the leverage mechanism. It is precisely the
break as it already stood at **2026-08-04 16:07:16 (t93)** — a small *pre-existing negative* break,
entirely pre-flip, that the leverage bug then rode on top of. See §4.3.

# Cash-ledger reconciliation — paper_trading portfolio

- **Measured:** 2026-08-07 (DB stable; auto-trader halted via `safety/EMERGENCY_STOP`, created 2026-08-07 16:55).
- **Task:** Task 1 of `.superpowers/sdd/2026-08-07-stage0-engine-correctness/`.
- **Gate:** Task 4 (one-time cash repair) is gated on `RECONCILED`. **This verdict does not clear that gate.** See §7 for what the owner must decide.

---

## 1. Re-measured live figures

All three queries run against the live DB via
`docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot`.

### 1.1 `portfolios`

```
 portfolio_id  | initial_balance | cash_balance | realized_pnl |        updated_at
---------------+-----------------+--------------+--------------+---------------------------
 paper_trading |    100.00000000 | 255.97305338 |  -0.41002416 | 2026-08-07 15:00:55.18326
(1 row)
```

`updated_at` equals position 63's `closed_at` (15:00:55.155833) to within 28 ms — consistent with
`cash_balance` being written only on position *close*.

### 1.2 `positions`

```
 id | symbol  | side  | status |   quantity   | remaining_quantity |  entry_price   | rem_notional | entry_fee  |  exit_fee  | realized_pnl |         opened_at          |         closed_at
----+---------+-------+--------+--------------+--------------------+----------------+--------------+------------+------------+--------------+----------------------------+----------------------------
 46 | SOLUSDT | SHORT | CLOSED |   0.68268706 |         0.00000000 |    73.24000000 |   0.00000000 | 0.05000000 | 0.05125500 |  -1.35625501 | 2026-07-29 17:18:55.857953 | 2026-07-30 20:12:33.86205
 47 | BTCUSDT | SHORT | CLOSED |   0.00074698 |         0.00000000 | 63556.10000000 |   0.00000000 | 0.04747500 | 0.04698855 |   0.39211922 | 2026-07-29 20:00:42.322091 | 2026-08-01 17:02:41.171281
 48 | ETHUSDT | SHORT | CLOSED |   0.02789966 |         0.00000000 |  1883.10000000 |   0.00000000 | 0.05253784 | 0.05385655 |  -1.42509442 | 2026-07-29 21:00:42.179691 | 2026-07-30 20:12:38.341936
 49 | BNBUSDT | LONG  | CLOSED |   0.11067325 |         0.00000000 |   593.60000000 |   0.00000000 | 0.06569564 | 0.06405982 |  -1.76557693 | 2026-07-30 17:38:07.844994 | 2026-08-01 16:00:31.094376
 50 | ADAUSDT | LONG  | CLOSED | 292.24495398 |         0.00000000 |     0.17230000 |   0.00000000 | 0.05035381 | 0.04910000 |  -1.35326357 | 2026-07-30 19:33:20.932097 | 2026-07-31 16:28:18.311589
 51 | ETHUSDT | LONG  | CLOSED |   0.04483952 |         0.00000000 |  1861.84000000 |   0.00000000 | 0.08348402 | 0.08230922 |  -1.34058866 | 2026-07-31 16:27:36.068094 | 2026-08-04 14:10:09.101841
 52 | SOLUSDT | LONG  | CLOSED |   1.07850243 |         0.00000000 |    73.05000000 |   0.00000000 | 0.07878460 | 0.07682287 |  -2.11734407 | 2026-07-31 16:28:24.437229 | 2026-08-01 19:00:37.457676
 53 | BNBUSDT | LONG  | CLOSED |   0.13141847 |         0.00000000 |   576.00000000 |   0.00000000 | 0.07569704 | 0.07573646 |  -0.11200796 | 2026-08-01 16:28:56.465102 | 2026-08-04 14:10:12.531397
 54 | ADAUSDT | LONG  | CLOSED | 195.43836643 |         0.00000000 |     0.17410000 |   0.00000000 | 0.03402582 | 0.03347859 |  -0.61473184 | 2026-08-01 17:01:44.382349 | 2026-08-04 14:10:14.946664
 55 | BTCUSDT | LONG  | CLOSED |   0.00116344 |         0.00000000 | 62677.10000000 |   0.00000000 | 0.07292098 | 0.07277468 |  -0.29205641 | 2026-08-01 18:00:59.735199 | 2026-08-04 14:10:18.897299
 56 | SOLUSDT | LONG  | CLOSED |   0.99656724 |         0.00000000 |    71.04000000 |   0.00000000 | 0.07079614 | 0.07079614 |  -0.14159228 | 2026-08-01 19:00:48.413122 | 2026-08-04 14:10:20.368433
 57 | BTCUSDT | LONG  | CLOSED |   0.00153112 |         0.00000000 | 62551.30000000 |   0.00000000 | 0.09577380 | 0.06848451 |   2.26095893 | 2026-08-04 14:10:25.807915 | 2026-08-06 14:10:53.491491
 58 | ETHUSDT | LONG  | CLOSED |   0.04690498 |         0.00000000 |  1835.64000000 |   0.00000000 | 0.08610065 | 0.04915501 |   3.13683574 | 2026-08-04 14:10:28.391864 | 2026-08-06 14:10:55.126098
 59 | SOLUSDT | LONG  | CLOSED |   1.08043760 |         0.00000000 |    71.04000000 |   0.00000000 | 0.07675429 | 0.12366197 |   2.70505224 | 2026-08-04 14:10:30.498334 | 2026-08-04 16:07:16.855918
 60 | BNBUSDT | LONG  | CLOSED |   0.12086119 |         0.00000000 |   576.30000000 |   0.00000000 | 0.06965230 | 0.05033002 |   2.51954151 | 2026-08-04 14:10:33.93189  | 2026-08-05 02:03:05.395708
 61 | BNBUSDT | SHORT | OPEN   |   0.01000000 |         0.01000000 |   602.69000000 |   6.02690000 | 0.00331480 | 0.00000000 |              | 2026-08-06 01:30:15.501459 |
 62 | ADAUSDT | SHORT | CLOSED | 118.00000000 |         0.00000000 |     0.19980000 |   0.00000000 | 0.01296702 | 0.01323960 |  -0.52180662 | 2026-08-06 15:01:12.234207 | 2026-08-06 16:00:58.341681
 63 | ADAUSDT | LONG  | CLOSED |  85.00000000 |         0.00000000 |     0.20230000 |   0.00000000 | 0.00945753 | 0.00925650 |  -0.38421403 | 2026-08-06 20:01:20.494472 | 2026-08-07 15:00:55.155833
 64 | SOLUSDT | LONG  | OPEN   |   0.30000000 |         0.20100000 |    72.68000000 |  14.60868000 | 0.01199220 | 0.00403148 |   0.12665110 | 2026-08-07 00:00:40.22684  |
(19 rows)
```

Aggregates:

```
  sum_all   | sum_closed  |  sum_open
------------+-------------+------------
-0.28337306 | -0.41002416 | 0.12665110
```

The `+0.12665110` gap between `sum_all` and `portfolios.realized_pnl` is position 64's
partial exit, accrued onto a still-OPEN row. `record_position_close` never writes it, by
construction. **This is why the identity must sum realized over ALL positions, not just CLOSED.**

### 1.3 `trades`

41 rows, ids **63–103 contiguous** (no gaps — no trade row was lost). Full dump omitted for
length; every row is reproduced in the reconstruction below and in
`.superpowers/sdd/2026-08-07-stage0-engine-correctness/task-1-report.md`. The load-bearing rows:

```
  id | symbol  | side | quantity     | price          | fee        | realized_pnl | strategy         | executed_at
  89 | BTCUSDT | SELL |   0.00050527 | 63662.90000000 | 0.03216701 |   0.56165920 | partial_exit_tp1 | 2026-08-04 14:12:28.348291
  90 | SOLUSDT | SELL |   0.35654441 |    73.59000000 | 0.02623810 |   0.90918824 | partial_exit_tp1 | 2026-08-04 14:12:33.931338
  91 | BNBUSDT | SELL |   0.03988419 |   588.90000000 | 0.02348780 |   0.50254081 | partial_exit_tp1 | 2026-08-04 14:12:36.312829
  92 | SOLUSDT | SELL |   0.23888475 |    73.59000000 | 0.01757953 |   0.60915612 | partial_exit_tp2 | 2026-08-04 14:13:20.213963
  93 | SOLUSDT | SELL |   1.08043760 |    73.90000000 | 0.07984434 |   3.09005154 | auto_close       | 2026-08-04 16:07:16.919182
  94 | BNBUSDT | SELL |   0.08097700 |   602.69000000 | 0.02684222 |   2.06347377 | auto_close       | 2026-08-05 02:03:05.453272
  96 | BTCUSDT | SELL |   0.00102585 | 64367.90000000 | 0.03631750 |   1.76307319 | auto_close       | 2026-08-06 14:10:53.516856
  97 | ETHUSDT | SELL |   0.04690498 |  1905.40000000 | 0.04915501 |   3.13683574 | auto_close       | 2026-08-06 14:10:55.132078
```

**Trap for later tasks:** trade-row `realized_pnl` semantics flip mid-dataset. t68–t93 record
**gross** (t90 = (73.59−71.04)×0.35654441 = 0.90918824 exactly, no fees netted); t94 onward
records **net**. That is the AUDIT H7 change. Do not use `trades.realized_pnl` as a uniform
cash-delta source.

### 1.4 Tables and columns that carry no signal

- `audit_log`: **0 rows**. `performance_metrics`: **0 rows**. No config-change or equity-curve history exists.
- `positions.cost_basis` stores **full notional**, not posted margin — `entry_price*quantity/cost_basis`
  returns `1.0000` for all 19 rows including the four known 10x positions. It therefore
  **cannot** date the leverage flip, and it confirms `posted_margin` (Task 2 / migration 008)
  is genuinely a new column with no existing equivalent.

---

## 2. The coherent-cash identity (three terms, derived and verified)

```
open:     B  = B0 − M − Fe
partial:  B += m + g − fx ;  position.realized_pnl += g − fx − fe_portion
so:       B + (M−m) + (Fe−fe_portion) == B0 + Σ realized
```

Verified empirically on position 64's partial exit (t102), the only partial in the log window:

- log line: `Margin returned: $7.1953 | Gross P&L: $0.1346 | Net P&L: $0.1267 | Commission: $0.0040 | Balance: $239.1523`
- gross = (74.04−72.68)×0.099 = 0.13464; exit fee = 0.00403148; entry-fee portion = 0.01199220×0.099/0.30 = 0.00395742
- net = 0.13464 − 0.00403148 − 0.00395742 = **0.12665110** = `positions.realized_pnl` exactly.

So the cash ledger debits the **whole** entry fee at open while `realized_pnl` nets only the
**consumed** portion. Both non-obvious terms are load-bearing.

### Coherent cash today

| Term | Value |
|---|---:|
| `initial_balance` | 100.00000000 |
| `+ SUM(realized_pnl)` over **ALL** positions | −0.28337306 |
| `− SUM(posted_margin)` on OPEN (61: 6.02690000, 64: 14.60868000) | −20.63558000 |
| `− SUM(unconsumed entry fee)` on OPEN (61: 0.00331480, 64: 0.00803477) | −0.01134957 |
| **Coherent cash** | **79.06969737** |
| Actual `cash_balance` | 255.97305338 |
| **BREAK** | **+176.90335601** |

**Position 61's posted margin is $6.0269 as a matter of fact, not assumption.** Its *original*
open leverage is unobservable (it opened 2026-08-06 01:30:15, before the current container
started, and those logs have rolled) — but it does not matter. The
2026-08-06 13:48:32 restart **replaced** the in-memory balance via
`sync_balance_with_positions`, re-debiting position 61 at the then-current settings as
`6.02690000/1.0 + 6.02690000×0.00055 = 6.030214795`. Whatever was debited at its open was
discarded by that restart. $6.0269 is what the live ledger currently has deducted for it, so
$6.0269 is what `posted_margin` must be backfilled to in Task 2.

---

## 3. Pinning the leverage flip — and a correction to the brief

The brief states the compose comment dates the `DEFAULT_LEVERAGE` 10.0→1.0 change to
**2026-08-04**. **That is wrong.** The commit is:

```
a51e815 2026-08-05 14:50:40 +0100  fix(compose): retire incomplete legacy compose file, align unified stack
-      - DEFAULT_LEVERAGE=${DEFAULT_LEVERAGE:-10.0}
+      - DEFAULT_LEVERAGE=${DEFAULT_LEVERAGE:-1.0}
```

i.e. **2026-08-05 13:50:40 UTC**.

Logs have rolled — `docker logs crypto-bot-trading` reaches back only to 2026-08-06 23:01:14,
and exactly one `x leverage` line survives:

```
2026-08-07 00:00:40,227 - app.paper_trading - INFO - ✓ LONG opened: 0.3 SOLUSDT @ 72.68 (ref 72.64) | Position: $21.804 | Margin: $21.804 (1.0x leverage) + Commission: $0.01199220 | Balance: $231.826381359491150000000
docker inspect: 2026-08-06T13:48:32.552489803Z  RestartCount 0
```

The flip was instead pinned **arithmetically** (§4): the container was at **10x at t93
(2026-08-04 16:07:16)** and at **1x at t94 (2026-08-05 02:03:05)**.

> **Finding worth recording:** the running container adopted 1x roughly **11.8 hours before**
> the committed compose default changed. `DEFAULT_LEVERAGE=${DEFAULT_LEVERAGE:-1.0}` is a
> *default*; the live container env (`docker inspect` → `DEFAULT_LEVERAGE=1.0`) comes from the
> gitignored `.env` override. **Git history does not bound this container's config.** Any later
> task that tries to date engine behaviour from compose commits will be wrong.

The commission rate flipped in the same window: t93's fee is 0.1% of notional, t94's is 0.055%
(`config.py:575` default is now `0.055`, "Was 0.1 until 2026-08-04"). One container recreation
carried leverage, fee rate, migration 007, and the one-time repair.

---

## 4. Reconstruction

### 4.1 Backward chain from a verified anchor (exact)

The current container has `RestartCount 0` and `StartedAt 2026-08-06T13:48:32Z`, so cash has
evolved continuously since then. Starting from the surviving log balance and walking the engine's
own rules (`paper_trading.py:325` credit, `:445` debit) **forward** reproduces the live row exactly:

```
after pos64 open (log)   231.826381359491150000000
after t102 partial       239.152309879491150000000   (log: $239.1523)      ✓
after t103 close         255.973053379491150000000   (DB: 255.97305338)    ✓  (agrees to 8 dp)
```

Walking the same chain **backward** through every event since the restart:

```
A. cash before pos64 open (08-07 00:00:40)   253.64237356
B. undo pos63 open        (08-06 20:01:20)   270.84733109
C. undo t99  pos62 close  (08-06 16:00:58)   247.77977069
D. undo pos62 open        (08-06 15:01:12)   271.36913771
E. undo t97  pos58 close  (08-06 14:10:55)   182.04554383
F. undo t96  pos57 close  (08-06 14:10:53)   116.05005111   <- = cash just AFTER the restart
   + _open_position_cost(pos61) @ L=1        6.030214795
G. persisted_cash at t94   (08-05 02:03:05) = 122.08026591
```

Row F is both the t96 undo and the post-restart figure: t96 (2026-08-06 14:10:53) is the **first**
cash event after the 13:48:32 restart, so undoing it lands exactly on the balance
`sync_balance_with_positions` produced. Every close between the restart and now — t96, t97, t99,
t102, t103 — is undone, and the two opens (pos62, pos63) are re-added; nothing in the window is
skipped. *(An earlier revision of this table folded the t96 step into row F's label without naming
it, which made the chain look like it skipped t96. The arithmetic always included it —
`recon.py:48` — and no figure changed.)*

**Corroboration of G.** The value implied for the ledger immediately *before* t94 is
**$73.30308000**. `AUDIT.md §8.1` and `progress.md:885` record the contemporaneous figure as
**`portfolios.cash_balance=73.30`** — agreeing to the cent with a computation made two days later
from data those documents never touched.

**This is one record, not two.** Both lines were added by the same commit — `f946cbc`,
2026-08-05 14:58:10 +0100, `AUDIT.md` (+293) and `progress.md` (+54) together — so they are a
single figure duplicated into two files, and must be counted once. It remains the only external
check in this document, and it is a real one: a contemporaneous 2026-08-05 observation of
`cash_balance` matching today's independent backward chain. The anchor is sound.

### 4.2 Attribution table

Break moves only when a position is closed at a leverage different from the one it was opened at:

```
break_delta = entry_price × close_qty × (1/L_close − 1/L_open)
```

| Event | Position | close_qty | Entry notional | L_open → L_close | Break contribution |
|---|---|---:|---:|---|---:|
| t94 · 08-05 02:03:05 | 60 BNB | 0.08097700 | 46.66704510 | 10 → 1 | **+42.00034059** |
| t96 · 08-06 14:10:53 | 57 BTC | 0.00102585 | 64.16825111 | 10 → 1 | **+57.75142599** |
| t97 · 08-06 14:10:55 | 58 ETH | 0.04690498 | 86.10065749 | 10 → 1 | **+77.49059174** |
| | | | | **Explained** | **+177.24235832** |
| | | | | **Observed** | **+176.90335601** |
| | | | | **Residual** | **−0.33900231** |

**t96 + t97 are proven, not fitted.** Independently computing the break at the 08-05 anchor gives
**+41.66133828**, and `break_now − break_then = +135.24201774`, which equals
`(64.16825111 + 86.10065749) × 0.9 = 135.24201773` — agreement to **1e-8** by two separate routes.
This also proves positions 57 and 58 were opened at **10x** (at 1x the same computation returns a
break delta of exactly zero, which contradicts the measured movement).

All closes before the flip (t68–t93, positions 46–56 and 59) contribute **zero** — they were
opened and closed at the same 10x.

### 4.3 The residual is the pre-flip break, dated exactly

Subtracting the three post-flip contributions from the observed break leaves the break as it stood
**before any of them**:

```
176.90335601 − 42.00034059 − 57.75142599 − 77.49059174 = −0.33900231
```

Computed independently from state — coherent cash just after t93 (2026-08-04 16:07:16), using
today's rewritten `realized_pnl` values and 10x posted margin on the then-open positions 57/58/60:

```
sum realized just after t93 =  −6.46738621
open margin @10x            =  19.69359537
unconsumed entry fee        =   0.19693611
coherent just after t93     =  73.64208231
actual   just after t93     =  73.30308000   (from §4.1; matches the single 2026-08-05 record)
BREAK at t93 (pre-flip)     =  −0.33900231
```

The two routes agree to **1e-9**. They are genuinely different computations — the first works
backward from the live `portfolios` row and never touches the §4.1 chain; the second works forward
from position state through that chain — though both necessarily read the same `positions` rows, so
a defect in those rows would move both. So the residual is **dated to on-or-before 2026-08-04 16:07:16**,
it is **negative** (the ledger held 34 cents *less* than coherent), and the leverage flip — which
happened after — had nothing to do with it. The flip mechanism accounts for 100% of the break it
created; this is a separate, older, sub-dollar defect it was layered on top of.

### 4.4 What did *not* explain the residual (each tested and rejected)

1. **Every position's P&L identity holds exactly.** For all 19 rows,
   `Σ gross − entry_fee − Σ exit_fee == positions.realized_pnl` to 1e-8. (Position 64 differs by
   0.00803478 only because, as an OPEN row, it has consumed just the prorated entry fee — the
   expected behaviour, not an anomaly.) **The residual is purely cash-side; the P&L ledger is clean.**
2. **A full forward simulation from $100** through all 41 events, with the flip between t93 and t94
   and no restarts, lands at **122.41926400** vs the derived **122.08026591** — overshoot
   **+0.33899810**. *Caveat for the reader: this is **not** independent corroboration.* A no-restart
   simulation in which every close has `L_close == L_open` is the §2 coherent identity re-evaluated
   event by event, so it necessarily agrees with the §4.3 figure — it is the same fact restated, and
   must not be counted twice. Its actual value is diagnostic: it confirms the residual is a single
   out-of-band displacement rather than an accumulation across events. **The only external check in
   this document is the `$73.30` figure** (§4.1) — a single contemporaneous 2026-08-05 record, since
   `AUDIT.md` and `progress.md` received it in one commit (`f946cbc`). That one record is what shows
   the residual is not an artifact of the backward chain.
3. **Single-restart search.** A restart inserted at *every* inter-event gap from 2026-08-04 onward,
   across `L_now ∈ {1,10} × comm ∈ {0.1%, 0.055%}` — nearest results −0.15886269 and −2.04715787.
   **No fit within $0.01.**
4. **The H5 "resurrected-quantity" bug**, which is real and documented. It made t93 close position
   59 on the full 1.08043760 rather than the remaining 0.48500844. Its two phantoms reproduce the
   repo's own recorded figures exactly:
   - cash margin phantom = `71.04 × 0.59542916 / 10` = **4.22992875** → `AUDIT.md §8.1` "~$4.23 phantom margin"
   - realized phantom = `2.86 × 0.59542916` = **1.70292740** → repair record "exactly the $1.7029 phantom"

   Modelling it (with and without the partial-exit credits surviving a restart) gives
   **+6.27185425** or **−5.90017572**. **No fit.**
5. **Trade-row loss.** Trade ids 63–103 are contiguous; no `_spawn_trade_log` fire-and-forget row
   is missing.
6. **A per-close leak in the persist path** — the last mechanism standing, since `portfolios.realized_pnl`
   is known to accumulate SQL-side and an SQL-side `cash_balance` whose delta differed from the
   engine's would leak a little on every close (the right shape for −$0.339 spread over 15 pre-flip
   closes). **Rejected by reading the write path.** `repositories.py:565-575` sets
   `cash_balance=cash_balance` — a plain bound parameter — while only `realized_pnl` uses
   `func.coalesce(...) + delta`. The value bound is `get_paper_engine().get_balance()`
   (`position_manager.py:475-490`), i.e. the engine's in-memory ledger verbatim. There is no
   SQL-side cash arithmetic to drift. This also confirms the model used throughout: `record_position_close`
   is invoked only from `close_position`, so **partial exits never persist cash** — the single
   assumption the whole backward chain rests on.

### 4.5 Why the residual is not recoverable from available evidence

Per §4.3 the residual is dated to **on or before 2026-08-04 16:07:16 (t93)**. It cannot be
localised further *within* that window because only one anchor exists in it. That window contains a
documented one-time data repair — `database/migrations/one_time_repairs/2026-08-04-fee-backfill-and-balance-repair.sql`,
whose own header states:

> "The exact UPDATE statements were executed interactively and **were not captured verbatim**."

That repair rewrote `initial_balance`, backfilled `entry_fee`/`exit_fee` for all 15 then-existing
positions, rewrote `realized_pnl` net of both fee legs, and corrected position 59. Its timing is
pinned to **inside the same window**: `portfolios.realized_pnl = −7.42133969` recorded at repair
time equals the sum of exactly the positions closed as of t93 (46–56, 59) using today's values —
reproduced here to the cent. The window also contains migration 007, a leverage change, a fee-rate
change, and at least one container recreation.

**A sub-dollar residual originating inside an uncaptured interactive rewrite of the same rows is
not reconstructable.** Manufacturing a term to close it would be fabrication.

---

## 5. Verdict

**UNRECONCILED.** Residual **−$0.33900231** — the reconstruction *overshoots* the observed break by
0.19%; the ledger holds 34 cents *less* than the identified over-credits predict.

The leverage mechanism itself reconciles **exactly**: three closes of 10x-opened positions credited
back at 1x, agreeing to 1e-8 by two separate computations (§4.2). What remains is a **separate, older,
negative** discrepancy of 34 cents that already existed at 2026-08-04 16:07:16, before the flip.
Every mechanism capable of producing it was tested and rejected (§4.4), and it originates inside a
window whose one documented repair was, by its own record, executed interactively and not captured.

The brief's bar is $0.01. This does not clear it, so the verdict is UNRECONCILED and Task 4 stays
gated — notwithstanding that the repair value in §6 is unaffected by the residual.

---

## 6. Proposed repair statement (NOT AUTHORISED — Task 4 is gated and this verdict does not open it)

`positions.posted_margin` **does not exist yet**; it is created by Task 2 (migration 008), which
runs before Task 4. The statement below is written against the post-008 schema and will be valid
when Task 4 executes. The *numeric* value beside it was computed today from
`entry_price * remaining_quantity / leverage`, which is what is measurable pre-008. **Task 4 must
re-derive, not copy** — this drifts on every close, and the auto-trader was halted only for this
measurement.

```sql
-- Coherent cash = initial_balance
--               + SUM(realized_pnl over ALL positions)      <- not just CLOSED
--               - SUM(posted_margin on OPEN)
--               - SUM(unconsumed entry fee on OPEN)         <- not optional
UPDATE portfolios p
SET cash_balance = p.initial_balance
                 + COALESCE((SELECT SUM(realized_pnl) FROM positions
                              WHERE portfolio_id = 'paper_trading'), 0)
                 - COALESCE((SELECT SUM(posted_margin) FROM positions
                              WHERE portfolio_id = 'paper_trading' AND status = 'OPEN'), 0)
                 - COALESCE((SELECT SUM(entry_fee
                                        * COALESCE(remaining_quantity, quantity)
                                        / quantity)
                               FROM positions
                              WHERE portfolio_id = 'paper_trading' AND status = 'OPEN'), 0),
    updated_at = NOW()
WHERE p.portfolio_id = 'paper_trading';
```

Value as measured 2026-08-07: **`cash_balance = 79.06969737`** (from `255.97305338`, a reduction of
`176.90335601`).

**`remaining_quantity` is nullable and the engine treats NULL as "full"**
(`paper_trading.py:97-101`, `pos.remaining_quantity if ... is not None else pos.quantity`). A bare
`entry_fee * remaining_quantity / quantity` yields NULL on such a row and `SUM` **silently drops
it** — under-subtracting the unconsumed fee. Both OPEN rows happen to be populated today, so the
bug is latent, but Task 4 re-derives at execution time. `COALESCE(remaining_quantity, quantity)` is
mandatory here, and in the `posted_margin` backfill Task 2 writes.

**Do not run the brief's verification query before migration 008 exists** — it references
`posted_margin`.

Task 2 must backfill `posted_margin` for the two OPEN rows as: **position 61 → `6.02690000`**,
**position 64 → `14.60868000`** (see §2 for why 61 is $6.0269 as fact, not assumption).

---

## 7. What the owner must decide

> **Ruling given (2026-08-08): Task 4 is AUTHORIZED despite this UNRECONCILED verdict** — the
> residual is 12× smaller than the $4.23 `AUDIT.md §8.1` already accepted, and it does not change
> the value written. The override is recorded in the SDD ledger, not here; the verdict line at the
> top of this file stands as measured and is deliberately left unchanged. The rest of this section
> is the analysis that ruling was made against.

**The residual does not change the number Task 4 would write.** `79.06969737` is computed from
*current state* — today's `realized_pnl`, `posted_margin` and unconsumed fees — so it is the
coherent value whether or not the 34 cents is ever explained. What the residual bears on is
*confidence that no other mechanism is still lurking*. That, and only that, is what the gate
decision turns on.

The gate is not mine to open. Two coherent options:

1. **Accept the $0.34 and authorise Task 4.** This is the same call `AUDIT.md §8.1` already made
   on 2026-08-05 at a **$4.23** magnitude ("accepted as-is… no reconstruction, no baseline reset —
   paper money"). The residual here is **12× smaller** than one already accepted, it is bounded, it
   is signed, and its origin window is identified. Under this option the repair writes
   `79.06969737` and the account carries ≤$0.34 of legacy noise.
2. **Reset the paper account to $100** and abandon reconstruction entirely. Cleaner, and the
   existing history has no edge worth preserving (CLAUDE.md §2 — no strategy is positive), but it
   discards the trade history the killtests evidence base draws on.

**Recommendation: option 1.** The residual is smaller than an already-accepted one, and the
mechanism behind the other 99.81% is proven to 1e-8. But this is explicitly the owner's ruling,
not this task's — Task 4 stays blocked until it is given.

---

## 8. Constraints observed

- Auto-trader left halted; `safety/EMERGENCY_STOP` untouched.
- No application code changed. No file under `services/`, `backtesting/`, or `database/` modified.
- `scripts/repair_testnet_pollution.sql` **not** run.
- No `git status` bare, no `git add -A`; committed with an explicit pathspec.
