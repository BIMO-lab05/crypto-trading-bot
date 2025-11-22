#!/usr/bin/env python3
"""Final fix for risk score calculation"""

with open('app/risk_engine.py', 'r') as f:
    lines = f.readlines()

# Find the line with "# Capital risk (0-20 points)" and replace the next 5 scoring sections
new_lines = []
i = 0
while i < len(lines):
    if '# Capital risk (0-20 points)' in lines[i]:
        # Add the comment line
        new_lines.append(lines[i])
        i += 1
        
        # Skip old capital score lines and add new ones
        while i < len(lines) and not '# Exposure risk' in lines[i]:
            i += 1
        
        # Add new capital score
        new_lines.append("        # Only penalize when utilization is high (> 70%)\n")
        new_lines.append("        capital_score = max(0, (capital_metrics.capital_utilization - 0.70) * 66.67)\n")
        new_lines.append("        scores.append(min(capital_score, 20))\n")
        new_lines.append("\n")
        
        # Add exposure comment
        new_lines.append(lines[i])  # # Exposure risk comment
        i += 1
        
        # Skip old exposure lines
        while i < len(lines) and not '# Concentration risk' in lines[i]:
            i += 1
        
        # Add new exposure score
        new_lines.append("        # Penalize when approaching or exceeding max exposure\n")
        new_lines.append("        # Full points only when significantly over max exposure (> 1.5x)\n")
        new_lines.append("        exposure_normalized = exposure_metrics.exposure_ratio / settings.max_exposure\n")
        new_lines.append("        if exposure_normalized <= 0.5:\n")
        new_lines.append("            exposure_score = 0\n")
        new_lines.append("        elif exposure_normalized <= 1.0:\n")
        new_lines.append("            # Linear scale from 0.5x to 1.0x max: 0 to 12.5 points\n")
        new_lines.append("            exposure_score = (exposure_normalized - 0.5) * 25\n")
        new_lines.append("        else:\n")
        new_lines.append("            # Over max: scale from 12.5 to 25 points\n")
        new_lines.append("            exposure_score = 12.5 + min((exposure_normalized - 1.0) * 25, 12.5)\n")
        new_lines.append("        scores.append(exposure_score)\n")
        new_lines.append("\n")
        
        # Continue with the rest
        new_lines.append(lines[i])  # # Concentration risk
        i += 1
    else:
        new_lines.append(lines[i])
        i += 1

with open('app/risk_engine.py', 'w') as f:
    f.writelines(new_lines)

print("✅ Applied final risk score fix")
