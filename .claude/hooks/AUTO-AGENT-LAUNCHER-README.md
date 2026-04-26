# Auto Agent Launcher Hook

## Overview

This hook **automatically launches** appropriate agents based on your prompt, making your workflow more efficient by eliminating the need to manually invoke agents for common tasks.

## How It Works

1. **Analyzes your prompt** before Claude sees it
2. **Detects patterns** that indicate specific agent needs
3. **Injects launch directives** that instruct Claude to immediately run the appropriate agent(s)
4. **Works seamlessly** with your existing hooks

## Auto-Launch Scenarios

The hook automatically launches agents for these scenarios:

### 1. Project Startup/Continuation
**Triggers:** `start`, `continue`, `resume`, `let's work`, `what's next`, `show progress`, `status`
**Launches:** `crypto-bot-project-manager`
**Example:**
```
You: "Let's continue working on the project"
→ Auto-launches crypto-bot-project-manager to load context and show priorities
```

### 2. Architecture/Refactoring
**Triggers:** `refactor god class`, `extract microservice`, `strangler fig`, `split service`
**Launches:** `microservices-architect` + `domain-expert` (in parallel)
**Example:**
```
You: "Refactor the god class in trading service"
→ Auto-launches both architecture specialists
```

### 3. Codebase Exploration
**Triggers:** `how does`, `where is`, `find in code`, `explain implementation`
**Launches:** `Explore` agent (with auto-detected thoroughness)
**Example:**
```
You: "How does authentication work in this codebase?"
→ Auto-launches Explore agent with medium thoroughness
```

### 4. Testing Tasks
**Triggers:** `write test`, `add test`, `test coverage`, `fix test`, `tdd`
**Launches:** `testing-guardian`
**Example:**
```
You: "Write tests for the order service"
→ Auto-launches testing-guardian with TDD reminders
```

### 5. Debugging
**Triggers:** `debug`, `fix error`, `not working`, `fails`, `crash`, `investigate bug`
**Launches:** `debugger`
**Example:**
```
You: "Debug why the WebSocket connection keeps failing"
→ Auto-launches debugger for systematic analysis
```

### 6. Security Review
**Triggers:** `security review`, `audit security`, `check vulnerabilities`, `pen test`
**Launches:** `security-engineer`
**Example:**
```
You: "Security review of the API endpoints"
→ Auto-launches security-engineer for OWASP checks
```

### 7. Code Review
**Triggers:** `review code`, `code review`, `check code quality`, `analyze code`
**Launches:** `code-reviewer`
**Example:**
```
You: "Review the code I just wrote"
→ Auto-launches code-reviewer for quality analysis
```

### 8. Research/Web Search
**Triggers:** `what's latest`, `current`, `search web`, `recent developments`
**Launches:** `web-search-researcher`
**Example:**
```
You: "What are the latest Bybit API changes?"
→ Auto-launches web-search-researcher
```

### 9. Frontend Development
**Triggers:** `create component`, `build dashboard`, `implement UI`, `data grid`
**Launches:** `frontend-developer`
**Example:**
```
You: "Create a trading dashboard component"
→ Auto-launches frontend-developer
```

### 10. Database Operations
**Triggers:** `optimize query`, `database performance`, `migration`, `schema design`
**Launches:** `database-administrator`
**Example:**
```
You: "Optimize the market data queries"
→ Auto-launches database-administrator
```

### 11. Deployment/DevOps
**Triggers:** `deploy`, `CI/CD pipeline`, `release`, `kubernetes`, `docker compose`
**Launches:** `deployment-engineer`
**Example:**
```
You: "Setup CI/CD pipeline for the services"
→ Auto-launches deployment-engineer
```

### 12. API Documentation
**Triggers:** `document API`, `openapi`, `swagger`, `API spec`
**Launches:** `api-documenter`
**Example:**
```
You: "Generate OpenAPI spec for the trading API"
→ Auto-launches api-documenter
```

## Installation

### Option 1: Replace Agent Selector (Recommended)

If you want automatic launching instead of recommendations:

```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\"",
      "/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh \"$PROMPT\""
    ],
    "stop": [
      "/mnt/d/Bimo_max/.claude/hooks/stop-event.sh"
    ]
  }
}
```

### Option 2: Add Alongside Agent Selector

If you want both recommendations AND automatic launching:

```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\"",
      "/mnt/d/Bimo_max/.claude/hooks/agent-selector.sh \"$PROMPT\"",
      "/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh \"$PROMPT\""
    ],
    "stop": [
      "/mnt/d/Bimo_max/.claude/hooks/stop-event.sh"
    ]
  }
}
```

### Option 3: Only Auto-Launch (Minimal)

If you only want automatic agent launching:

```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh \"$PROMPT\""
    ]
  }
}
```

## Configuration File Location

Update the hooks in your Claude Code settings file:

- **Linux/WSL:** `~/.config/claude-code/settings.json`
- **macOS:** `~/Library/Application Support/claude-code/settings.json`
- **Windows:** `%APPDATA%\claude-code\settings.json`

## Testing

Test the hook manually to see what it detects:

```bash
# Test project startup detection
/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh "let's continue working"

# Test exploration detection
/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh "how does authentication work?"

# Test debugging detection
/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh "debug the websocket error"
```

## Behavior

### What You'll See

When a pattern is detected, you'll see:

```
╔════════════════════════════════════════════════════════════╗
║          🤖 AUTOMATIC AGENT LAUNCHER ACTIVATED            ║
╚════════════════════════════════════════════════════════════╝

🔍 AUTO-LAUNCHING: Explore agent (medium)

DIRECTIVE: Immediately use the Task tool with subagent_type=Explore and the following prompt:
"how does authentication work?"
Specify thoroughness level: medium

💡 Note: The agent will be launched automatically. You can still
   modify the approach or launch additional agents as needed.

────────────────────────────────────────────────────────────
```

### What Claude Will Do

Claude will see the directive and immediately:
1. Launch the specified agent(s)
2. Use the recommended prompt and configuration
3. Provide you with the agent's findings

### You Can Still Override

Even with auto-launch, you can:
- Ask Claude to use a different agent instead
- Request additional agents to run in parallel
- Modify the approach before proceeding

## Customization

### Adding New Auto-Launch Patterns

Edit `/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh` and add your pattern:

```bash
# Example: Add auto-launch for performance optimization
elif echo "$prompt_lower" | grep -qE "(optimize.*performance|slow|speed.*up|improve.*latency)"; then
    launch_directive="⚡ AUTO-LAUNCHING: performance-optimizer\n\n"
    launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the performance-optimizer agent with prompt:\n"
    launch_directive="${launch_directive}\"${USER_PROMPT}. Analyze performance bottlenecks and provide optimization recommendations.\"\n\n"
    auto_launch=true
```

### Adjusting Trigger Keywords

Modify the `grep -qE` patterns to match your workflow:

```bash
# Make it more/less sensitive
grep -qE "(more|specific|keywords)"  # More specific (fewer triggers)
grep -qE "(broad|general)"           # More general (more triggers)
```

### Disabling Specific Auto-Launches

Comment out scenarios you don't want:

```bash
# # 7. Code Review - Launch code-reviewer
# elif echo "$prompt_lower" | grep -qE "(review.*code|code.*review)"; then
#     ...
# fi
```

## Pro Tips

### 1. Combine with Manual Agent Selection
The auto-launch doesn't prevent you from asking for specific agents:
```
You: "Use the backend-developer agent to implement the REST API"
→ Your explicit request takes precedence
```

### 2. Use Clear Intent Keywords
Frame your prompts to trigger the right auto-launch:
```
Good: "Debug the authentication error"        → Triggers debugger
Bad:  "There's a problem with auth"           → Might not trigger
```

### 3. Check the Directive
The injected directive shows exactly what will be launched - verify it's what you want before Claude proceeds.

### 4. Launch Multiple Agents
Use prompts that trigger multiple needs:
```
"Review and refactor the god class in payment service"
→ Could trigger both code-reviewer and microservices-architect
```

## Troubleshooting

### Hook Not Triggering

**Problem:** Expected auto-launch didn't happen
**Solution:** Test manually to see if keywords match:
```bash
/mnt/d/Bimo_max/.claude/hooks/auto-agent-launcher.sh "your prompt"
```

### Wrong Agent Launched

**Problem:** Auto-launched agent isn't optimal
**Solution:**
1. Use more specific keywords in your prompt
2. Override by asking for different agent
3. Customize the hook to adjust trigger patterns

### Multiple Auto-Launches Conflict

**Problem:** Multiple patterns match and create confusion
**Solution:** The hook uses `elif` to ensure only ONE auto-launch per prompt. The order matters - higher priority checks come first.

## Comparison with Agent Selector

| Feature | Agent Selector | Auto-Launcher |
|---------|---------------|---------------|
| **Action** | Recommends agents | Launches agents |
| **User Action** | You decide to launch | Automatic launch |
| **Best For** | Learning, exploration | Production workflow |
| **Flexibility** | High (you choose) | Medium (auto + override) |
| **Speed** | Slower (manual) | Faster (automatic) |

**Recommendation:** Use both together! Agent selector helps you learn, auto-launcher speeds up common tasks.

## Integration with Your Workflow

### Typical Session Flow

1. **Start:** `"Let's work on the project"`
   - Auto-launches: crypto-bot-project-manager
   - Shows: Current status, priorities, progress

2. **Explore:** `"How does the trading engine work?"`
   - Auto-launches: Explore agent
   - Provides: Code analysis and explanation

3. **Implement:** `"Create the RSI indicator service"`
   - Auto-launches: backend-developer
   - Builds: Service with best practices

4. **Test:** `"Write tests for the RSI service"`
   - Auto-launches: testing-guardian
   - Creates: Comprehensive test suite

5. **Review:** `"Review the code quality"`
   - Auto-launches: code-reviewer
   - Analyzes: Quality, security, patterns

6. **Deploy:** `"Setup deployment pipeline"`
   - Auto-launches: deployment-engineer
   - Creates: CI/CD configuration

## Summary

The Auto Agent Launcher hook:
- ✅ Automatically detects 12+ common task patterns
- ✅ Launches appropriate agents without manual intervention
- ✅ Provides clear directives Claude can follow immediately
- ✅ Works alongside existing hooks
- ✅ Fully customizable for your workflow
- ✅ Speeds up development by eliminating manual agent selection

**Result:** More time coding, less time managing agents!

---

For questions or customization help, examine the hook script - it's well-commented and easy to modify.
