# Claude Code Hooks - Quick Reference

## 🚀 Quick Start

### 1. Verify Installation
```bash
cd /mnt/d/Bimo_max/.claude/hooks
./setup-verify.sh
```

### 2. Test Hooks
```bash
./test-hooks.sh
```

### 3. Configure Claude Code
Add to your `settings.json`:

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

**Settings location:**
- Linux/WSL: `~/.config/claude-code/settings.json`
- macOS: `~/Library/Application Support/claude-code/settings.json`
- Windows: `%APPDATA%\claude-code\settings.json`

---

## 📚 What Each Hook Does

### UserPromptSubmit Hook
**Triggers:** Before Claude sees your message
**Actions:**
- Detects keywords in your prompt
- Injects relevant project context
- Reminds you of best practices

**Example keywords:**
- `bybit`, `trading` → Trading bot context
- `microservice`, `refactor` → Architecture focus
- `test`, `pytest` → TDD reminders
- `database`, `prisma` → Repository pattern reminder

### Agent Selector Hook
**Triggers:** Before Claude sees your message (with UserPromptSubmit)
**Actions:**
- Analyzes your task
- Recommends best agent to use
- Provides priority level

**Example recommendations:**
- "how does X work?" → Explore agent
- "refactor god class" → microservices-architect
- "add feature" → backend-developer or frontend-developer
- "fix bug" → debugger

### Stop Event Hook
**Triggers:** After Claude finishes responding
**Actions:**
- Scans recently modified files
- Checks for code quality issues
- Provides gentle reminders

**Checks for:**
- Missing error handling
- Missing logging
- Hardcoded secrets ⚠️
- Missing timeouts on async
- console.log in production
- TODO comments

---

## 💡 Common Use Cases

### Use Case 1: Starting a New Feature
**Your prompt:** "Add authentication to the API"

**What you get:**
- Security context activation
- Recommendation: `security-engineer` agent
- Reminder about secrets management
- Checklist for auth best practices

### Use Case 2: Debugging
**Your prompt:** "Fix the order execution error"

**What you get:**
- Recommendation: `debugger` or `error-detective` agent
- Trading bot context (error handling critical)
- Reminder about comprehensive logging

### Use Case 3: Code Review
**Your prompt:** "Review the trading service code"

**What you get:**
- Recommendation: `code-reviewer` agent
- Quality standards checklist
- Security reminders for trading operations

### Use Case 4: Exploring Code
**Your prompt:** "How does the market data service work?"

**What you get:**
- Recommendation: `Explore` agent with thoroughness level
- Reminder to check documentation
- Suggestion to use Task tool for multi-step exploration

---

## 🔧 Manual Testing

### Test UserPromptSubmit Hook
```bash
cd /mnt/d/Bimo_max/.claude/hooks
./user-prompt-submit.sh "Add RSI indicator to trading bot"
```

### Test Agent Selector Hook
```bash
./agent-selector.sh "Refactor the God class"
```

### Test Stop Event Hook
```bash
# Create a file with issues, then:
./stop-event.sh
```

---

## 🎯 Keywords That Trigger Context

### Architecture & Microservices
`microservice`, `service`, `refactor`, `god class`, `strangler`, `architecture`, `split`, `extract`, `decouple`

### Trading Bot
`bybit`, `trading`, `bot`, `order`, `position`, `market`, `technical analysis`, `indicator`, `rsi`, `macd`, `bollinger`

### Frontend
`layout`, `grid`, `catalog`, `data grid`, `frontend`, `react`, `component`, `ui`, `dashboard`

### Database
`database`, `prisma`, `postgres`, `timescaledb`, `redis`, `sql`, `query`, `repository pattern`

### Testing
`test`, `tdd`, `coverage`, `pytest`, `jest`, `unit test`, `integration test`

### Security
`security`, `auth`, `api key`, `secret`, `vulnerability`, `error handling`, `try catch`

### Documentation
`document`, `readme`, `api spec`, `openapi`, `swagger`, `architecture decision`

### Deployment
`deploy`, `docker`, `kubernetes`, `ci/cd`, `pipeline`, `infrastructure`

### Code Quality
`review`, `refactor`, `improve`, `optimize`, `code quality`, `clean code`

### Research
`how does`, `where is`, `find`, `search`, `explore`, `understand`, `explain`

---

## 🛠️ Customization Examples

### Add Your Own Keyword Detection
Edit `user-prompt-submit.sh`:
```bash
if echo "$prompt_lower" | grep -qE "(your|keywords)"; then
    injection="${injection}🎯 YOUR CUSTOM CONTEXT\n"
    injection="${injection}• Your custom reminder\n\n"
fi
```

### Add Custom Code Quality Check
Edit `stop-event.sh`:
```bash
if grep -q "your_pattern" "$file"; then
    warnings="${warnings}  ⚡ Your custom warning\n"
    has_issues=true
fi
```

### Add Custom Agent Recommendation
Edit `agent-selector.sh`:
```bash
elif echo "$prompt_lower" | grep -qE "(your|keywords)"; then
    recommended_agents="🎯 PRIMARY AGENT: your-agent\n"
    priority="HIGH"
fi
```

---

## 🐛 Troubleshooting

### Hooks Not Running?
```bash
# Check permissions
ls -la /mnt/d/Bimo_max/.claude/hooks/*.sh

# Should show: -rwxr-xr-x
# If not, fix with:
chmod +x /mnt/d/Bimo_max/.claude/hooks/*.sh
```

### No Output from Hooks?
```bash
# Test manually
./user-prompt-submit.sh "test bybit"
./agent-selector.sh "test refactor"

# Should show context/recommendations
```

### Configuration Not Working?
1. Check settings.json path is correct
2. Verify paths in settings.json match your system
3. Restart Claude Code after configuration changes
4. Check Claude Code logs for errors

---

## 📊 Hook Performance

- **UserPromptSubmit:** <10ms (keyword matching)
- **Agent Selector:** <20ms (pattern analysis)
- **Stop Event:** <100ms (scans modified files in last 5 minutes)

All hooks are **non-blocking** - they never interrupt your workflow.

---

## 📝 Files Overview

```
.claude/hooks/
├── user-prompt-submit.sh    # Context injection
├── stop-event.sh             # Code quality checks
├── agent-selector.sh         # Agent recommendations
├── setup-verify.sh           # Installation verification
├── test-hooks.sh             # Interactive demo
├── README.md                 # Full documentation
└── QUICK-REFERENCE.md        # This file
```

---

## 🎓 Best Practices

1. **Use both UserPromptSubmit hooks** for full context + agent recommendations
2. **Always enable Stop Event hook** for code quality reminders
3. **Customize keywords** for your specific project needs
4. **Test hooks manually** before configuring in Claude Code
5. **Review hook output** to understand what Claude sees
6. **Update keywords** as your project evolves

---

## 🚨 Important Notes

- Hooks run automatically - no user action required
- All hooks return `exit 0` (non-blocking)
- Stop Event hook scans files modified in last 5 minutes
- Hooks are project-aware (detect crypto-trading-bot context)
- Sensitive data (API keys) triggers critical warnings

---

## 📞 Need Help?

1. Run `./setup-verify.sh` to diagnose issues
2. Run `./test-hooks.sh` to see hooks in action
3. Check `README.md` for detailed documentation
4. Review hook scripts (they're well-commented)

---

**Remember:** These hooks enhance your workflow by providing intelligent context and reminders. They never block or interrupt your work!
