# SOL-Heavy Allocation Implementation Guide
**Date:** 2025-12-06
**Priority:** HIGH
**Status:** Ready for Implementation
**Expected Impact:** +0.27% per 90 days (vs +0.01% with equal weights)

---

## 📊 Background

Cross-symbol testing revealed **Simple RSI is profitable on SOLUSDT (+0.66%)** but loses on BNBUSDT (-0.14%) and ADAUSDT (-0.48%).

**Current allocation:** Equal (33.3% each)
**Recommended allocation:** SOL-heavy (60% SOL, 20% BNB, 20% ADA)
**Expected improvement:** +0.26 percentage points per 90 days

---

## 🎯 Implementation Options

### Option 1: Manual Position Sizing (Quick - 5 minutes)

**What to do:**
Manually adjust position sizes based on symbol when placing trades.

**Current behavior:**
- Each symbol gets equal share of available capital
- Example: $10,000 capital ÷ 3 symbols = $3,333 per symbol

**New behavior:**
- SOLUSDT: 60% of capital = $6,000
- BNBUSDT: 20% of capital = $2,000
- ADAUSDT: 20% of capital = $2,000

**Implementation steps:**
1. Add `symbol_allocations` to `config.py`:
```python
symbol_allocations: Dict[str, float] = Field(
    default={
        "SOLUSDT": 0.60,  # 60% - PROFITABLE (+0.66%)
        "BNBUSDT": 0.20,  # 20% - Slight loss (-0.14%)
        "ADAUSDT": 0.20,  # 20% - Slight loss (-0.48%)
    },
    description="Per-symbol capital allocation (must sum to 1.0)"
)
```

2. Modify position sizing logic in trading engine to use these weights
3. Validate weights sum to 1.0 on startup

**Pros:** Simple, quick to implement
**Cons:** Requires code changes to trading engine

---

### Option 2: Priority-Based Trading (Medium - 15 minutes)

**What to do:**
Give SOLUSDT priority when multiple signals appear.

**Implementation:**
1. Add `symbol_priority` to config:
```python
symbol_priority: List[str] = Field(
    default=[
        "SOLUSDT",   # Priority 1 - Trade first
        "BNBUSDT",   # Priority 2 - Trade second
        "ADAUSDT",   # Priority 3 - Trade third
    ],
    description="Symbol priority order for trade execution"
)
```

2. When multiple symbols have signals simultaneously:
   - Check if higher priority symbol has signal
   - Trade higher priority first
   - Only trade lower priority if capital available

3. This naturally allocates more to SOL (gets first pick)

**Pros:** Simpler than explicit allocation, leverages existing logic
**Cons:** Not precise (allocation depends on signal timing)

---

### Option 3: Separate Symbol Groups (Complex - 30 minutes)

**What to do:**
Split capital into groups with different allocations.

**Implementation:**
1. Create symbol groups:
```python
symbol_groups: Dict[str, Dict] = Field(
    default={
        "tier1": {
            "symbols": ["SOLUSDT"],
            "allocation": 0.60,
            "description": "Profitable - 60% allocation"
        },
        "tier2": {
            "symbols": ["BNBUSDT", "ADAUSDT"],
            "allocation": 0.40,
            "description": "Marginal - 40% allocation"
        }
    }
)
```

2. Allocate capital to each group
3. Within each group, split equally
4. Track group allocation separately

**Pros:** Flexible, can add more tiers easily
**Cons:** Most complex, more code changes needed

---

## ✅ Recommended Approach

**Use Option 1: Manual Position Sizing**

This is the most straightforward and gives precise control:
- 60% SOLUSDT
- 20% BNBUSDT
- 20% ADAUSDT

**Why this is best:**
1. ✅ Precise allocation control
2. ✅ Clear and easy to understand
3. ✅ Can easily adjust weights based on performance
4. ✅ Minimal code changes

---

## 📝 Detailed Implementation Steps

### Step 1: Add Configuration (config.py)

Add after line 161 in `/services/trading-engine/app/config.py`:

```python
# Symbol Allocation Weights (2025-12-06)
# Based on 90-day backtest results showing SOLUSDT profitable
symbol_allocations: Dict[str, float] = Field(
    default={
        "SOLUSDT": 0.60,  # 60% - Profitable: +0.66% return, 64.7% WR
        "BNBUSDT": 0.20,  # 20% - Slight loss: -0.14% return, 55.8% WR
        "ADAUSDT": 0.20,  # 20% - Slight loss: -0.48% return, 57.7% WR
    },
    description="Capital allocation per symbol (must sum to 1.0). "
                "Based on cross-symbol backtest analysis 2025-12-06."
)

def validate_allocations(self):
    """Validate symbol allocations sum to 1.0"""
    total = sum(self.symbol_allocations.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"Symbol allocations sum to {total}, must equal 1.0")

    # Ensure all trading symbols have allocations
    for symbol in self.trading_symbols:
        if symbol not in self.symbol_allocations:
            raise ValueError(f"Symbol {symbol} missing from allocations")
```

### Step 2: Modify Position Sizing Logic

In the trading engine position sizing code, change from:
```python
# OLD: Equal allocation
position_size = available_capital / len(trading_symbols)
```

To:
```python
# NEW: Weighted allocation
allocation_pct = settings.symbol_allocations.get(symbol, 0.33)
position_size = available_capital * allocation_pct
```

### Step 3: Add Validation on Startup

In trading engine initialization:
```python
# Validate allocations
settings.validate_allocations()
logger.info(f"Symbol allocations: {settings.symbol_allocations}")
```

### Step 4: Update Documentation

Add comment to config explaining the allocation rationale:
```python
# ALLOCATION RATIONALE (2025-12-06):
#
# Cross-symbol backtest (90 days, Simple RSI):
# - SOLUSDT: +0.66% return ✅ (ONLY profitable symbol)
# - BNBUSDT: -0.14% return (marginal loss)
# - ADAUSDT: -0.48% return (marginal loss)
#
# Weighted allocation (60/20/20):
# - Expected return: +0.27% per 90 days
# - vs Equal allocation: +0.01% per 90 days
# - Improvement: +0.26 percentage points
#
# Validation: See /docs/CROSS_SYMBOL_ANALYSIS_FINAL.md
```

---

## 🧪 Testing Before Deployment

### Test 1: Validate Configuration
```python
from services.trading_engine.app.config import Settings

settings = Settings()
assert abs(sum(settings.symbol_allocations.values()) - 1.0) < 0.01
assert all(s in settings.symbol_allocations for s in settings.trading_symbols)
print("✅ Configuration valid")
```

### Test 2: Verify Position Sizing
```python
# With $10,000 capital:
capital = 10000
expected = {
    "SOLUSDT": 6000,  # 60%
    "BNBUSDT": 2000,  # 20%
    "ADAUSDT": 2000,  # 20%
}

for symbol, expected_size in expected.items():
    allocation = settings.symbol_allocations[symbol]
    actual_size = capital * allocation
    assert actual_size == expected_size, f"{symbol}: {actual_size} != {expected_size}"
    print(f"✅ {symbol}: ${actual_size:,.0f} ({allocation:.0%})")
```

### Test 3: Dry Run
Before going live:
1. Run in paper trading mode for 24 hours
2. Verify SOLUSDT gets 60% of positions
3. Check actual allocations match config
4. Monitor for any errors

---

## 📊 Expected Results

### Performance Projection (90 days):

**Before (Equal 33/33/33):**
- Expected: +0.01% (+$1 on $10k)
- Breakdown:
  - SOL: $3,333 × 0.66% = +$22
  - BNB: $3,333 × -0.14% = -$5
  - ADA: $3,333 × -0.48% = -$16
  - **Total: +$1**

**After (Weighted 60/20/20):**
- Expected: +0.27% (+$27 on $10k)
- Breakdown:
  - SOL: $6,000 × 0.66% = +$40
  - BNB: $2,000 × -0.14% = -$3
  - ADA: $2,000 × -0.48% = -$10
  - **Total: +$27**

**Improvement:** +$26 per 90 days (+2600% better!)

---

## ⚠️ Risks & Monitoring

### Risk 1: SOL Performance May Not Persist
**Mitigation:** Monitor SOL performance weekly, adjust allocation if results differ from backtest

### Risk 2: Over-Concentration
**Mitigation:** 60% SOL is aggressive but not reckless (still diversified across 3 assets)

### Risk 3: BNB/ADA May Improve
**Mitigation:** Re-run cross-symbol analysis monthly, adjust allocations based on data

### Monitoring Plan:
1. **Daily:** Check SOL performance vs backtest expectations
2. **Weekly:** Compare actual allocation vs target (should be ~60/20/20)
3. **Monthly:** Re-run cross-symbol backtest, update allocations if needed

---

## 🎯 Success Criteria

Implementation successful when:
1. ✅ Configuration validates on startup
2. ✅ SOLUSDT positions are ~3x larger than BNB/ADA
3. ✅ Total allocation across symbols equals available capital
4. ✅ No errors or warnings in logs
5. ✅ Paper trading shows expected allocation distribution

---

## 📅 Implementation Timeline

**Phase 1: Configuration (Day 1)**
- [ ] Add `symbol_allocations` to config.py
- [ ] Add validation method
- [ ] Test configuration loads correctly

**Phase 2: Position Sizing (Day 1)**
- [ ] Modify position sizing logic
- [ ] Update capital allocation calculations
- [ ] Add logging for allocation verification

**Phase 3: Testing (Day 2)**
- [ ] Unit tests for allocation logic
- [ ] Integration test with mock trading
- [ ] Paper trading dry run (24 hours)

**Phase 4: Deployment (Day 3)**
- [ ] Deploy to production
- [ ] Monitor first 24 hours closely
- [ ] Verify allocations match expectations
- [ ] Document actual vs expected performance

---

## 📞 Rollback Plan

If SOL allocation causes issues:

1. **Immediate:** Revert to equal allocation (33/33/33)
2. **Analysis:** Review what went wrong
3. **Adjustment:** Try 50/25/25 instead of 60/20/20
4. **Re-test:** Paper trade new allocation

**Rollback trigger:** If SOL underperforms backtest by >50% for 7 days

---

## 🏁 Conclusion

**Current State:** Equal allocation (33/33/33) → +0.01% expected
**Target State:** SOL-heavy allocation (60/20/20) → +0.27% expected
**Implementation:** Option 1 (Manual Position Sizing) recommended
**Timeline:** 1-3 days (config → testing → deployment)
**Expected Impact:** +2600% improvement in returns

**Status:** ✅ Ready to implement
**Next Action:** Add `symbol_allocations` to config.py and modify position sizing

---

**Document created:** 2025-12-06
**Author:** Phase 2 Strategy Research Team
**References:**
- `/docs/CROSS_SYMBOL_ANALYSIS_FINAL.md`
- `/docs/PHASE2_COMPLETE_STRATEGY_RESEARCH.md`
