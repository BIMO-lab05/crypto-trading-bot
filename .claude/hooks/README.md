# Claude Code Intelligent Hooks System

This directory contains three powerful hooks that enhance your Claude Code workflow with intelligent context awareness, agent recommendations, and code quality checks.

## 📋 Table of Contents
- [Overview](#overview)
- [Hook Types](#hook-types)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)

---

## Overview

These hooks run automatically during your Claude Code sessions to:
1. **Inject relevant context** before Claude sees your prompt
2. **Recommend optimal agents** for your specific tasks
3. **Check code quality** after Claude finishes responding

### Benefits
- 🎯 **Automatic context activation** - No need to remember project specifics
- 🤖 **Smart agent routing** - Get recommendations for the best agent to use
- ✅ **Quality reminders** - Gentle nudges about error handling, testing, etc.
- ⚡ **Non-blocking** - Never interrupts your workflow

---

## Hook Types

### 1. User Prompt Submit Hook
**File:** `user-prompt-submit.sh`
**When:** Runs BEFORE Claude sees your message
**Purpose:** Analyzes your prompt and injects relevant context/reminders

**Detects:**
- Microservices & architecture tasks → Suggests microservices-architect agent
- Trading bot operations → Activates Bybit/trading context
- Database operations → Reminds about repository pattern
- Frontend/React work → Suggests react-specialist agent
- Testing tasks → Reminds about TDD practices
- Security concerns → Activates security checklist
- Documentation needs → Suggests technical-writer agent

### 2. Stop Event Hook
**File:** `stop-event.sh`
**When:** Runs AFTER Claude finishes responding
**Purpose:** Analyzes edited files and provides code quality reminders

**Checks for:**
- Try-catch blocks without logging
- Async operations without timeouts
- Database operations not using repository pattern
- Hardcoded API keys or secrets ⚠️
- Trading operations without error handling
- console.log in production code
- TODO/FIXME comments

### 3. Agent Selection Hook
**File:** `agent-selector.sh`
**When:** Can run as part of UserPromptSubmit or standalone
**Purpose:** Recommends the optimal agent for your specific task

**Recommends agents for:**
- Architecture refactoring → microservices-architect
- Codebase exploration → Explore agent (with thoroughness level)
- Frontend development → react-specialist or frontend-developer
- Backend APIs → backend-developer
- Database work → database-administrator or sql-pro
- Testing → testing-guardian
- Code review → code-reviewer
- Debugging → debugger or error-detective
- And many more...

---

## Installation

### Step 1: Verify Hook Files
Ensure all three hook scripts are in `.claude/hooks/` and executable:

```bash
ls -la /mnt/d/Bimo_max/.claude/hooks/
```

You should see:
```
-rwxr-xr-x user-prompt-submit.sh
-rwxr-xr-x stop-event.sh
-rwxr-xr-x agent-selector.sh
```

### Step 2: Configure Claude Code Settings

You need to add hooks to your Claude Code configuration. The configuration file location varies by platform:

- **Linux/WSL:** `~/.config/claude-code/settings.json`
- **macOS:** `~/Library/Application Support/claude-code/settings.json`
- **Windows:** `%APPDATA%\claude-code\settings.json`

### Step 3: Add Hook Configuration

Open your Claude Code settings file and add the hooks configuration:

```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\"",
      "/mnt/d/Bimo_max/.claude/hooks/agent-selector.sh \"$PROMPT\""
    ],
    "stop": [
      "/mnt/d/Bimo_max/.claude/hooks/stop-event.sh"
    ]
  }
}
```

**Notes:**
- The `userPromptSubmit` hook runs both context injection AND agent recommendation
- The `stop` hook runs after each Claude response
- `$PROMPT` is automatically replaced with your actual prompt text
- Adjust paths if your project is in a different location

---

## Configuration

### Option 1: Both Hooks Together (Recommended)
```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\"",
      "/mnt/d/Bimo_max/.claude/hooks/agent-selector.sh \"$PROMPT\""
    ],
    "stop": [
      "/mnt/d/Bimo_max/.claude/hooks/stop-event.sh"
    ]
  }
}
```
**Best for:** Full-featured experience with both context and agent recommendations

### Option 2: Only Agent Recommendations
```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/agent-selector.sh \"$PROMPT\""
    ]
  }
}
```
**Best for:** When you only want agent suggestions

### Option 3: Only Context Injection
```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\""
    ],
    "stop": [
      "/mnt/d/Bimo_max/.claude/hooks/stop-event.sh"
    ]
  }
}
```
**Best for:** When you want project context reminders and code quality checks

### Option 4: Minimal (Only Code Quality)
```json
{
  "hooks": {
    "stop": [
      "/mnt/d/Bimo_max/.claude/hooks/stop-event.sh"
    ]
  }
}
```
**Best for:** Just post-response code quality reminders

---

## Usage Examples

### Example 1: Exploring Codebase
**Your prompt:**
```
How does the authentication system work?
```

**What you'll see:**
```
╔════════════════════════════════════════════════════════════╗
║        🤖 INTELLIGENT AGENT RECOMMENDATION 🔴              ║
╚════════════════════════════════════════════════════════════╝

🎯 PRIMARY AGENT: Explore (subagent)
   ⚙️  Thoroughness: medium
   🎓 Use Explore for codebase discovery and understanding

📊 Task Priority: HIGH

⚡ HIGH PRIORITY TASK:
  • Break down into smaller steps
  • Use TodoWrite to track progress
  • Consider multiple agents for complex tasks

💡 Pro Tips:
  • Launch multiple agents in parallel when tasks are independent
  • Use Explore agent first for unfamiliar codebases
  • Always verify agent has necessary context before starting
```

### Example 2: Trading Bot Feature
**Your prompt:**
```
Add a new RSI indicator to the technical analysis service
```

**What you'll see:**
```
╔════════════════════════════════════════════════════════════╗
🏗️  ARCHITECTURE FOCUS DETECTED
💹 TRADING BOT CONTEXT ACTIVATED
• Project: Crypto Trading Bot with Bybit integration
• Remember: Always use testnet, implement risk management (max 2% per trade)
• Check: CLAUDE.md for service contracts and API specifications
• Risk rules: Stop-loss at 5% portfolio loss, paper trading by default

🎯 PRIMARY AGENT: backend-developer
   📋 Supporting: python-pro for financial calculations
   ⚠️  CRITICAL: Always implement risk management!
   🎓 Remember: Testnet only, 2% max risk per trade
╚════════════════════════════════════════════════════════════╝
```

### Example 3: After Editing Code
**After Claude modifies files:**
```
╔════════════════════════════════════════════════════════════╗
║           CODE QUALITY SELF-CHECK REMINDER                ║
╚════════════════════════════════════════════════════════════╝

📁 services/trading-engine/strategy.py:
  ⚠️  Try-catch blocks found - Did you add logging?
  ⏱️  Async operations found - Consider adding timeouts
  💹 Trading operations found - Add comprehensive error handling!

💡 Gentle Reminders:
  • All errors should be logged with context
  • Database operations should use repository pattern
  • Async operations need timeout handling
  • Never hardcode secrets - use environment variables
  • Trading operations require comprehensive error handling

📋 Quick Checklist:
  ☐ Error handling implemented?
  ☐ Logging added with context?
  ☐ Tests written/updated?
  ☐ Documentation updated?
  ☐ No hardcoded secrets?
```

---

## Customization

### Adding New Keywords

Edit any hook file to add your own keyword patterns:

**Example: Adding a new framework detection**
```bash
# In user-prompt-submit.sh, add:
if echo "$prompt_lower" | grep -qE "(nextjs|next.js|ssr)"; then
    injection="${injection}⚡ NEXT.JS CONTEXT ACTIVATED\n"
    injection="${injection}• Consider using: react-specialist agent\n"
    injection="${injection}• Remember: SSR considerations for performance\n\n"
fi
```

### Customizing Code Quality Checks

**Example: Add check for specific pattern**
```bash
# In stop-event.sh, add:
if grep -q "your_pattern" "$file"; then
    warnings="${warnings}  ⚡ Custom warning message\n"
    has_issues=true
fi
```

### Customizing Agent Recommendations

**Example: Add recommendation for specific task**
```bash
# In agent-selector.sh, add:
elif echo "$prompt_lower" | grep -qE "(your|keywords)"; then
    recommended_agents="🎯 PRIMARY AGENT: your-agent-name\n"
    recommended_agents="${recommended_agents}   🎓 Description of when to use\n"
    priority="HIGH"
fi
```

---

## Troubleshooting

### Hooks Not Running

**Check 1: Verify hooks are executable**
```bash
ls -la .claude/hooks/*.sh
```
Should show `-rwxr-xr-x` permissions. If not:
```bash
chmod +x .claude/hooks/*.sh
```

**Check 2: Verify configuration path**
Ensure the paths in your settings.json match your actual file locations:
```bash
# Test the hook manually
/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh "test prompt"
```

**Check 3: Check Claude Code logs**
Look for hook-related errors in Claude Code output.

### Hooks Running But No Output

**Issue:** Hooks might be running but conditions not met.

**Solution:** Test with a keyword that should trigger output:
```bash
# Should show trading context
./user-prompt-submit.sh "bybit trading bot"

# Should show agent recommendation
./agent-selector.sh "refactor god class"
```

### Hook Errors Breaking Workflow

**Issue:** Hook returns non-zero exit code.

**Solution:** All hooks end with `exit 0` to prevent blocking. If edited, ensure this remains:
```bash
# Always at the end of each hook
exit 0
```

### Performance Issues

**Issue:** Hooks are slow.

**Solutions:**
1. Reduce file search scope in stop-event.sh:
   ```bash
   # Change from all directories to specific ones
   find ./services -type f -mmin -5 ...
   ```

2. Increase time threshold:
   ```bash
   # Check files modified in last 10 minutes instead of 5
   find . -type f -mmin -10 ...
   ```

### Windows/WSL Path Issues

**Issue:** Paths don't work in WSL.

**Solution:** Use WSL paths (`/mnt/d/...`) in configuration:
```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\""
    ]
  }
}
```

---

## Advanced Configuration

### Conditional Hook Execution

Create a wrapper script that only runs hooks in certain conditions:

```bash
#!/bin/bash
# .claude/hooks/conditional-wrapper.sh

# Only run in crypto-trading-bot project
if [[ "$PWD" == *"crypto-trading-bot"* ]]; then
    /mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh "$1"
fi
```

### Logging Hook Activity

Add logging to track hook execution:

```bash
# Add to any hook
LOG_FILE=".claude/hooks/hook.log"
echo "$(date): Hook executed with prompt: $USER_PROMPT" >> "$LOG_FILE"
```

### Integration with Git Hooks

Combine with git pre-commit hooks for comprehensive quality checks:

```bash
# .git/hooks/pre-commit
#!/bin/bash
/mnt/d/Bimo_max/.claude/hooks/stop-event.sh
```

---

## Summary

You now have three powerful hooks:

1. **user-prompt-submit.sh** - Context injection
2. **agent-selector.sh** - Smart agent recommendations
3. **stop-event.sh** - Code quality checks

Configure them in your Claude Code settings, and they'll work automatically to enhance your development workflow!

For questions or issues, check the troubleshooting section or examine the hook scripts directly - they're well-commented for easy understanding.

Happy coding! 🚀
