#!/usr/bin/env python3
"""Fix risk score calculation to be less punitive"""

with open('app/risk_engine.py', 'r') as f:
    content = f.read()

# The issue is that when exposure_ratio equals max_exposure, it gets full 25 points
# But that's actually acceptable risk, not maximum risk
# We should only give full points when exposure significantly exceeds max

old_scoring = """        # Capital risk (0-20 points)
        capital_score = min(capital_metrics.capital_utilization, 1.0) * 20
        scores.append(capital_score)

        # Exposure risk (0-25 points)
        # Normalize to max_exposure threshold
        exposure_score = min(exposure_metrics.exposure_ratio / settings.max_exposure, 1.0) * 25
        scores.append(exposure_score)"""

new_scoring = """        # Capital risk (0-20 points)
        # Only penalize when utilization is high (> 70%)
        capital_score = max(0, (capital_metrics.capital_utilization - 0.50) * 40)
        scores.append(min(capital_score, 20))

        # Exposure risk (0-25 points)
        # Penalize when approaching or exceeding max exposure
        # Full points only when significantly over max exposure (> 1.5x)
        exposure_normalized = exposure_metrics.exposure_ratio / settings.max_exposure
        if exposure_normalized <= 0.5:
            exposure_score = 0
        elif exposure_normalized <= 1.0:
            # Linear scale from 0.5x to 1.0x max: 0 to 12.5 points
            exposure_score = (exposure_normalized - 0.5) * 25
        else:
            # Over max: scale from 12.5 to 25 points
            exposure_score = 12.5 + min((exposure_normalized - 1.0) * 25, 12.5)
        scores.append(exposure_score)"""

content = content.replace(old_scoring, new_scoring)

with open('app/risk_engine.py', 'w') as f:
    f.write(content)

print("✅ Fixed risk score calculation")
