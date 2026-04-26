#!/bin/bash
# Agent Selection Hook - Intelligent Agent Router
# Analyzes prompt and recommends optimal agent/subagent
# Can be used as part of UserPromptSubmit or standalone

USER_PROMPT="$1"

# Function to analyze prompt and recommend agent
recommend_agent() {
    local prompt="$1"
    local prompt_lower=$(echo "$prompt" | tr '[:upper:]' '[:lower:]')
    local recommended_agents=""
    local priority="MEDIUM"

    # HIGH PRIORITY - Architecture & Refactoring
    if echo "$prompt_lower" | grep -qE "(refactor god class|extract microservice|strangler fig|split service|bounded context)"; then
        recommended_agents="🎯 PRIMARY AGENT: microservices-architect\n"
        recommended_agents="${recommended_agents}   📋 Supporting: domain-expert, refactoring-specialist\n"
        recommended_agents="${recommended_agents}   🎓 This is a complex architectural task requiring systematic analysis\n"
        priority="HIGH"

    # Codebase Exploration
    elif echo "$prompt_lower" | grep -qE "(how does|where is|find.*in codebase|explore|understand.*work|explain.*implementation)"; then
        recommended_agents="🎯 PRIMARY AGENT: Explore (subagent)\n"
        if echo "$prompt_lower" | grep -qE "(complex|entire|all|comprehensive)"; then
            recommended_agents="${recommended_agents}   ⚙️  Thoroughness: very thorough\n"
        elif echo "$prompt_lower" | grep -qE "(quick|simple|just)"; then
            recommended_agents="${recommended_agents}   ⚙️  Thoroughness: quick\n"
        else
            recommended_agents="${recommended_agents}   ⚙️  Thoroughness: medium\n"
        fi
        recommended_agents="${recommended_agents}   🎓 Use Explore for codebase discovery and understanding\n"
        priority="HIGH"

    # Frontend Development
    elif echo "$prompt_lower" | grep -qE "(react|component|ui|frontend|dashboard|layout|grid)"; then
        if echo "$prompt_lower" | grep -qE "(data grid|catalog|table|complex grid)"; then
            recommended_agents="🎯 PRIMARY AGENT: frontend-developer\n"
            recommended_agents="${recommended_agents}   📋 Consider: react-specialist for advanced patterns\n"
        else
            recommended_agents="🎯 PRIMARY AGENT: react-specialist\n"
        fi
        recommended_agents="${recommended_agents}   🎓 Specialized in modern React patterns and UI development\n"
        priority="MEDIUM"

    # Backend Development
    elif echo "$prompt_lower" | grep -qE "(api|endpoint|backend|server|fastapi|microservice implementation)"; then
        recommended_agents="🎯 PRIMARY AGENT: backend-developer\n"
        recommended_agents="${recommended_agents}   📋 Supporting: api-designer (for new APIs)\n"
        recommended_agents="${recommended_agents}   🎓 Specialized in scalable API development\n"
        priority="MEDIUM"

    # Database Operations
    elif echo "$prompt_lower" | grep -qE "(database|postgres|timescaledb|prisma|sql|query|migration)"; then
        if echo "$prompt_lower" | grep -qE "(optimize|performance|slow query|index)"; then
            recommended_agents="🎯 PRIMARY AGENT: database-administrator\n"
            recommended_agents="${recommended_agents}   📋 Supporting: sql-pro for complex queries\n"
        else
            recommended_agents="🎯 PRIMARY AGENT: sql-pro\n"
        fi
        recommended_agents="${recommended_agents}   🎓 Specialized in database design and optimization\n"
        priority="MEDIUM"

    # Testing & Quality
    elif echo "$prompt_lower" | grep -qE "(test|tdd|coverage|pytest|jest|unit test)"; then
        recommended_agents="🎯 PRIMARY AGENT: testing-guardian\n"
        recommended_agents="${recommended_agents}   📋 Remember: Write tests BEFORE implementation (TDD)\n"
        recommended_agents="${recommended_agents}   🎓 Ensures comprehensive test coverage and quality gates\n"
        priority="HIGH"

    # Code Review
    elif echo "$prompt_lower" | grep -qE "(review|check.*code|code quality|improve|optimize)"; then
        recommended_agents="🎯 PRIMARY AGENT: code-reviewer\n"
        recommended_agents="${recommended_agents}   📋 Supporting: refactoring-specialist for improvements\n"
        recommended_agents="${recommended_agents}   🎓 Specializes in quality, security, and best practices\n"
        priority="MEDIUM"

    # Trading Bot Specific
    elif echo "$prompt_lower" | grep -qE "(bybit|trading|bot|indicator|strategy|technical analysis)"; then
        recommended_agents="🎯 PRIMARY AGENT: backend-developer\n"
        recommended_agents="${recommended_agents}   📋 Supporting: python-pro for financial calculations\n"
        recommended_agents="${recommended_agents}   ⚠️  CRITICAL: Always implement risk management!\n"
        recommended_agents="${recommended_agents}   🎓 Remember: Testnet only, 2% max risk per trade\n"
        priority="HIGH"

    # Security & Authentication
    elif echo "$prompt_lower" | grep -qE "(security|auth|vulnerability|encrypt|api key|secret)"; then
        recommended_agents="🎯 PRIMARY AGENT: security-engineer\n"
        recommended_agents="${recommended_agents}   📋 Supporting: compliance-auditor for regulatory checks\n"
        recommended_agents="${recommended_agents}   🎓 Specializes in DevSecOps and security best practices\n"
        priority="HIGH"

    # Documentation
    elif echo "$prompt_lower" | grep -qE "(document|readme|api spec|openapi|swagger)"; then
        if echo "$prompt_lower" | grep -qE "(api|endpoint|swagger|openapi)"; then
            recommended_agents="🎯 PRIMARY AGENT: api-documenter\n"
        else
            recommended_agents="🎯 PRIMARY AGENT: technical-writer\n"
        fi
        recommended_agents="${recommended_agents}   🎓 Creates comprehensive, developer-friendly documentation\n"
        priority="LOW"

    # Deployment & Infrastructure
    elif echo "$prompt_lower" | grep -qE "(deploy|docker|kubernetes|ci/cd|pipeline|infrastructure)"; then
        if echo "$prompt_lower" | grep -qE "(deploy|release|rollout)"; then
            recommended_agents="🎯 PRIMARY AGENT: deployment-engineer\n"
        else
            recommended_agents="🎯 PRIMARY AGENT: devops-automator\n"
        fi
        recommended_agents="${recommended_agents}   📋 Supporting: build-engineer for build optimization\n"
        recommended_agents="${recommended_agents}   🎓 Specializes in CI/CD and deployment automation\n"
        priority="MEDIUM"

    # Error Debugging
    elif echo "$prompt_lower" | grep -qE "(error|bug|debug|fix|not working|fails|crash)"; then
        recommended_agents="🎯 PRIMARY AGENT: debugger\n"
        recommended_agents="${recommended_agents}   📋 Supporting: error-detective for complex patterns\n"
        recommended_agents="${recommended_agents}   🎓 Systematic evidence gathering for complex debugging\n"
        priority="HIGH"

    # Research & Web Search
    elif echo "$prompt_lower" | grep -qE "(latest|current|search.*web|what is.*now|recent)"; then
        recommended_agents="🎯 PRIMARY AGENT: web-search-researcher\n"
        recommended_agents="${recommended_agents}   🎓 Gathers current information from web sources\n"
        priority="MEDIUM"

    # Project Management
    elif echo "$prompt_lower" | grep -qE "(plan|roadmap|track|progress|what.*next|priority)"; then
        if echo "$prompt_lower" | grep -qE "(crypto.*bot|trading.*bot|bybit)"; then
            recommended_agents="🎯 PRIMARY AGENT: crypto-bot-project-manager\n"
            recommended_agents="${recommended_agents}   🎓 Specialized for crypto trading bot project\n"
        else
            recommended_agents="🎯 PRIMARY AGENT: project-manager\n"
        fi
        priority="MEDIUM"

    # General Development (fallback)
    else
        recommended_agents="💡 SUGGESTED APPROACH:\n"
        if echo "$prompt_lower" | grep -qE "(create|build|implement|add)"; then
            recommended_agents="${recommended_agents}   1. Start with Plan agent to design approach\n"
            recommended_agents="${recommended_agents}   2. Use appropriate specialist agent for implementation\n"
        else
            recommended_agents="${recommended_agents}   • Consider using general-purpose agent\n"
            recommended_agents="${recommended_agents}   • Or Explore agent if researching codebase\n"
        fi
        priority="LOW"
    fi

    # Add priority indicator
    local priority_emoji
    case $priority in
        HIGH) priority_emoji="🔴" ;;
        MEDIUM) priority_emoji="🟡" ;;
        LOW) priority_emoji="🟢" ;;
    esac

    echo -e "\n╔════════════════════════════════════════════════════════════╗"
    echo -e "║        🤖 INTELLIGENT AGENT RECOMMENDATION ${priority_emoji}              ║"
    echo -e "╚════════════════════════════════════════════════════════════╝"
    echo -e "\n$recommended_agents"
    echo -e "\n📊 Task Priority: ${priority}"

    # Add general reminders based on task type
    if [ "$priority" = "HIGH" ]; then
        echo -e "\n⚡ HIGH PRIORITY TASK:"
        echo -e "  • Break down into smaller steps"
        echo -e "  • Use TodoWrite to track progress"
        echo -e "  • Consider multiple agents for complex tasks"
    fi

    echo -e "\n💡 Pro Tips:"
    echo -e "  • Launch multiple agents in parallel when tasks are independent"
    echo -e "  • Use Explore agent first for unfamiliar codebases"
    echo -e "  • Always verify agent has necessary context before starting"
    echo -e "\n────────────────────────────────────────────────────────────\n"
}

# Run recommendation
recommend_agent "$USER_PROMPT"

# Always return success
exit 0
