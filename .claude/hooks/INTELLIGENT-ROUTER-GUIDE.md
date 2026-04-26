# Intelligent Agent Router - Quick Reference

## ✅ What's Enabled

Your Claude Code now has **FULL AUTOMATIC ACCESS** to all agents in `.claude/agents/` directory!

## How It Works

Every time you send a prompt, the intelligent router hook:

1. **Scans** all available agents in `.claude/agents/`
2. **Presents** the complete agent list to Claude with their descriptions
3. **Empowers** Claude to automatically choose and launch the best agent(s)
4. **Provides** clear directives for agent selection and usage

## Configuration

The hook is already configured in your Claude Code settings:

**File:** `~/.config/claude-code/settings.json`

```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\"",
      "/mnt/d/Bimo_max/.claude/hooks/intelligent-agent-router.sh \"$PROMPT\""
    ],
    "stop": [
      "/mnt/d/Bimo_max/.claude/hooks/stop-event.sh"
    ]
  }
}
```

## Available Agents (Auto-Detected)

The router automatically detects **ALL** agents from:
- `/mnt/d/Bimo_max/.claude/agents/*.md` (55+ agents)
- `/mnt/d/Bimo_max/.claude/agents/coordinators/*.md`
- `/mnt/d/Bimo_max/.claude/agents/specialists/*.md`

### Current Agent Count: 55+ Specialized Agents

Including:
- **Architecture:** microservices-architect, domain-expert, architect-reviewer
- **Development:** backend-developer, frontend-developer, blockchain-developer
- **Quality:** code-reviewer, testing-guardian, debugger, error-detective
- **Security:** security-engineer, compliance-auditor
- **Data:** database-administrator, sql-pro, data-researcher
- **DevOps:** deployment-engineer, devops-automator, build-engineer
- **Specialized:** fintech-engineer, websocket-engineer, api-designer
- **Project:** crypto-bot-project-manager, project-workflow-orchestrator
- **Research:** web-search-researcher, research-analyst, market-researcher
- And 30+ more specialized agents!

## Usage Examples

Just ask naturally - Claude will automatically select and launch the right agent(s):

### Example 1: Project Continuation
```
You: "Let's continue working on the crypto bot"
Claude: Analyzes → Launches crypto-bot-project-manager → Shows progress & priorities
```

### Example 2: Code Exploration
```
You: "How does the WebSocket connection work?"
Claude: Analyzes → Launches Explore agent (medium thoroughness) → Explains implementation
```

### Example 3: Database Optimization
```
You: "Optimize the market data queries"
Claude: Analyzes → Launches database-administrator or sql-pro → Optimizes queries
```

### Example 4: Security Review
```
You: "Review security of the API endpoints"
Claude: Analyzes → Launches security-engineer → Performs security audit
```

### Example 5: Complex Task (Multiple Agents)
```
You: "Refactor the god class and ensure tests pass"
Claude: Analyzes → Launches microservices-architect + testing-guardian in parallel → Complete refactor with tests
```

### Example 6: Research
```
You: "What are the latest Bybit API changes?"
Claude: Analyzes → Launches web-search-researcher → Fetches current info
```

## What You'll See

When you send a prompt, you'll see:

```
╔════════════════════════════════════════════════════════════╗
║       🤖 INTELLIGENT AGENT ROUTER - FULL ACCESS          ║
╚════════════════════════════════════════════════════════════╝

📋 USER REQUEST: "your prompt here"

🎯 DIRECTIVE FOR CLAUDE:
You have FULL ACCESS to launch any agent(s) from the available agents list...

⚡ AVAILABLE AGENTS IN YOUR .claude/agents/ DIRECTORY:
  • backend-developer: Senior backend engineer...
  • frontend-developer: Senior frontend engineer...
  • database-administrator: Expert DBA...
  [... all 55+ agents listed ...]

💡 AGENT SELECTION GUIDELINES:
  • For codebase exploration: Use 'Explore' agent
  • For complex tasks: Launch multiple agents in parallel
  [... guidance for Claude ...]
```

Then Claude will:
1. Analyze your request
2. Choose the most appropriate agent(s)
3. Launch them automatically
4. Provide you with the results

## Advantages Over Manual Selection

### Before (Manual)
```
You: "Optimize database queries"
You: "Use the database-administrator agent"
Claude: Launches agent
```

### Now (Automatic)
```
You: "Optimize database queries"
Claude: Automatically chooses and launches database-administrator agent
```

**Saved steps:** You don't need to know which agent to use!

## Advanced Usage

### Override Automatic Selection
If you want a specific agent, just ask:
```
You: "Use the backend-developer agent to implement the REST API"
Claude: Uses backend-developer as requested (overrides automatic selection)
```

### Request Multiple Agents
```
You: "Review and refactor the code"
Claude: May launch code-reviewer + refactoring-specialist in parallel
```

### Explore Before Implementing
```
You: "First explore the auth system, then add 2FA"
Claude: 1) Launches Explore agent, 2) Then appropriate implementation agent
```

## Benefits

✅ **Automatic Intelligence** - Claude chooses the best agent for your task
✅ **Full Access** - All 55+ agents available automatically
✅ **No Manual Selection** - Just describe what you want
✅ **Parallel Execution** - Multiple agents can run simultaneously
✅ **Context Aware** - Combines with your existing hooks for full context
✅ **Dynamic Updates** - New agents added to `.claude/agents/` are automatically detected

## How Claude Chooses Agents

The router provides Claude with:

1. **Your prompt** - What you want to accomplish
2. **All available agents** - Complete list with descriptions
3. **Selection guidelines** - Best practices for agent choice
4. **Usage examples** - How to launch agents properly

Claude then uses its intelligence to:
- Understand your request
- Match it to agent capabilities
- Choose the most appropriate agent(s)
- Launch them with proper configuration

## Troubleshooting

### Hook Not Working
```bash
# Test manually
/mnt/d/Bimo_max/.claude/hooks/intelligent-agent-router.sh "test prompt"

# Should show the full agent list and directives
```

### Claude Not Launching Agents
- The hook provides directives but doesn't force Claude to act
- You can explicitly ask: "Please launch the appropriate agent"
- Check if agent name exists in the displayed list

### New Agent Not Appearing
```bash
# Verify agent file exists
ls -la /mnt/d/Bimo_max/.claude/agents/

# Agent files must be .md format
# Router scans on every prompt (no caching)
```

## Customization

### Add More Agents
Just drop new `.md` files into `/mnt/d/Bimo_max/.claude/agents/`
- They'll be auto-detected immediately
- No configuration needed

### Modify Router Logic
Edit `/mnt/d/Bimo_max/.claude/hooks/intelligent-agent-router.sh`

### Disable Router
Remove from settings.json:
```json
{
  "hooks": {
    "userPromptSubmit": [
      "/mnt/d/Bimo_max/.claude/hooks/user-prompt-submit.sh \"$PROMPT\""
      // Remove the intelligent-agent-router line
    ]
  }
}
```

## Files Involved

1. **Hook Script:** `/mnt/d/Bimo_max/.claude/hooks/intelligent-agent-router.sh`
2. **Settings:** `~/.config/claude-code/settings.json`
3. **Agents Dir:** `/mnt/d/Bimo_max/.claude/agents/`
4. **This Guide:** `/mnt/d/Bimo_max/.claude/hooks/INTELLIGENT-ROUTER-GUIDE.md`

## Summary

You now have an **intelligent, automatic agent routing system** that:
- Scans all available agents
- Presents them to Claude with context
- Empowers Claude to choose and launch the best agent(s)
- Works seamlessly with your existing hooks

**Result:** Just ask for what you want, and Claude will handle the agent selection and execution automatically!

---

**Need Help?**
- Test the hook: `bash /mnt/d/Bimo_max/.claude/hooks/intelligent-agent-router.sh "your prompt"`
- View agents: `ls /mnt/d/Bimo_max/.claude/agents/`
- Check settings: `cat ~/.config/claude-code/settings.json`
