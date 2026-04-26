#!/bin/bash
# UserPromptSubmit Hook - Analyzes prompt and suggests skills/contexts
# Runs BEFORE Claude sees your message
# Input: User's prompt passed as argument

USER_PROMPT="$1"

# Function to check for keywords and return injection message
analyze_prompt() {
    local prompt="$1"
    local injection=""

    # Convert to lowercase for case-insensitive matching
    local prompt_lower=$(echo "$prompt" | tr '[:upper:]' '[:lower:]')

    # Microservices & Architecture Keywords
    if echo "$prompt_lower" | grep -qE "(microservice|service|refactor|god class|strangler|architecture|split|extract|decouple)"; then
        injection="${injection}🏗️  ARCHITECTURE FOCUS DETECTED\n"
        injection="${injection}• Consider using: microservices-architect, domain-expert, or architect-reviewer agents\n"
        injection="${injection}• Remember: Strangler Fig pattern for God class extraction\n"
        injection="${injection}• Check: .claude/memory/SESSION_LOG.json for context\n\n"
    fi

    # Trading Bot & Bybit Keywords
    if echo "$prompt_lower" | grep -qE "(bybit|trading|bot|order|position|market|technical analysis|indicator|rsi|macd|bollinger)"; then
        injection="${injection}💹 TRADING BOT CONTEXT ACTIVATED\n"
        injection="${injection}• Project: Crypto Trading Bot with Bybit integration\n"
        injection="${injection}• Remember: Always use testnet, implement risk management (max 2% per trade)\n"
        injection="${injection}• Check: CLAUDE.md for service contracts and API specifications\n"
        injection="${injection}• Risk rules: Stop-loss at 5% portfolio loss, paper trading by default\n\n"
    fi

    # Data Grid & Frontend Keywords
    if echo "$prompt_lower" | grep -qE "(layout|grid|catalog|data grid|frontend|react|component|ui|dashboard)"; then
        injection="${injection}🎯 FRONTEND/DATA GRID CONTEXT\n"
        injection="${injection}• Consider using: frontend-developer or react-specialist agent\n"
        injection="${injection}• For complex data grids: Check project-catalog patterns\n"
        injection="${injection}• Remember: Comment everything for AI understanding\n\n"
    fi

    # Database & Data Operations
    if echo "$prompt_lower" | grep -qE "(database|prisma|postgres|timescaledb|redis|sql|query|repository pattern)"; then
        injection="${injection}💾 DATABASE OPERATIONS DETECTED\n"
        injection="${injection}• Consider using: database-administrator or sql-pro agent\n"
        injection="${injection}• Remember: Use repository pattern for Prisma operations\n"
        injection="${injection}• Always implement connection pooling and error handling\n\n"
    fi

    # Testing Keywords
    if echo "$prompt_lower" | grep -qE "(test|tdd|coverage|pytest|jest|unit test|integration test)"; then
        injection="${injection}🧪 TESTING FOCUS DETECTED\n"
        injection="${injection}• Consider using: testing-guardian agent\n"
        injection="${injection}• Remember: TDD - Write tests BEFORE implementation\n"
        injection="${injection}• Target: >80% coverage for unit tests\n\n"
    fi

    # Security & Error Handling
    if echo "$prompt_lower" | grep -qE "(security|auth|api key|secret|vulnerability|error handling|try catch)"; then
        injection="${injection}🔒 SECURITY/ERROR HANDLING FOCUS\n"
        injection="${injection}• Consider using: security-engineer agent\n"
        injection="${injection}• Remember: Never commit API keys, use environment variables\n"
        injection="${injection}• Always implement proper error handling and logging\n\n"
    fi

    # Documentation Keywords
    if echo "$prompt_lower" | grep -qE "(document|readme|api spec|openapi|swagger|architecture decision)"; then
        injection="${injection}📚 DOCUMENTATION TASK DETECTED\n"
        injection="${injection}• Consider using: technical-writer or api-documenter agent\n"
        injection="${injection}• Auto-update: SERVICE_CONTRACTS.md, openapi.yaml, DECISIONS.md\n"
        injection="${injection}• Remember: Update progress.md after session\n\n"
    fi

    # Deployment & DevOps
    if echo "$prompt_lower" | grep -qE "(deploy|docker|kubernetes|ci/cd|pipeline|infrastructure)"; then
        injection="${injection}🚀 DEPLOYMENT/DEVOPS DETECTED\n"
        injection="${injection}• Consider using: deployment-engineer or devops-automator agent\n"
        injection="${injection}• Check: infrastructure/docker-compose.yml and kubernetes/ configs\n\n"
    fi

    # Code Review & Quality
    if echo "$prompt_lower" | grep -qE "(review|refactor|improve|optimize|code quality|clean code)"; then
        injection="${injection}🔍 CODE REVIEW/QUALITY FOCUS\n"
        injection="${injection}• Consider using: code-reviewer or refactoring-specialist agent\n"
        injection="${injection}• Remember: Run black, isort, mypy before committing\n\n"
    fi

    # Research & Exploration
    if echo "$prompt_lower" | grep -qE "(how does|where is|find|search|explore|understand|explain)"; then
        injection="${injection}🔎 RESEARCH/EXPLORATION MODE\n"
        injection="${injection}• Consider using: Explore agent with appropriate thoroughness level\n"
        injection="${injection}• For complex searches: Use 'very thorough' level\n"
        injection="${injection}• Remember: Use Task tool for multi-step exploration\n\n"
    fi

    # General project context reminder
    if [ -n "$injection" ]; then
        injection="╔════════════════════════════════════════════════════════════╗\n${injection}╚════════════════════════════════════════════════════════════╝\n"
    fi

    echo -e "$injection"
}

# Run analysis and output injection
INJECTION=$(analyze_prompt "$USER_PROMPT")

if [ -n "$INJECTION" ]; then
    echo "$INJECTION"
fi

# Always return success to not block the prompt
exit 0
