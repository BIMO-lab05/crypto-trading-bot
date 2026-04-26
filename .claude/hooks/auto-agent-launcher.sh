#!/bin/bash
# Auto Agent Launcher Hook
# Automatically launches appropriate agents based on prompt analysis
# Runs BEFORE Claude sees your message and injects agent launch directives

USER_PROMPT="$1"

# Function to determine which agents to auto-launch
determine_agents() {
    local prompt="$1"
    local prompt_lower=$(echo "$prompt" | tr '[:upper:]' '[:lower:]')
    local launch_directive=""
    local auto_launch=false

    # === HIGH PRIORITY AUTO-LAUNCH SCENARIOS ===

    # 1. Project Startup/Continuation - ALWAYS launch project manager
    if echo "$prompt_lower" | grep -qE "(^start|continue.*project|continue.*work|^resume|let.*work.*project|what.*next|show.*progress|^status|^work on)"; then
        launch_directive="🚀 AUTO-LAUNCHING: crypto-bot-project-manager\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the crypto-bot-project-manager agent with the following prompt:\n"
        launch_directive="${launch_directive}\"Analyze current project status, review progress from last session, identify completed work, check for failing tests or issues, and provide today's priority tasks. User said: ${USER_PROMPT}\"\n\n"
        auto_launch=true

    # 2. Complex Architecture/Refactoring - Launch microservices architect
    elif echo "$prompt_lower" | grep -qE "(refactor.*god class|extract.*microservice|strangler fig|split.*service|bounded context|migrate.*microservice)"; then
        launch_directive="🏗️ AUTO-LAUNCHING: microservices-architect + domain-expert\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch TWO agents in PARALLEL:\n"
        launch_directive="${launch_directive}1. microservices-architect with prompt: \"Analyze the codebase for god classes and microservice extraction opportunities. User request: ${USER_PROMPT}\"\n"
        launch_directive="${launch_directive}2. domain-expert with prompt: \"Identify bounded contexts and service boundaries for: ${USER_PROMPT}\"\n\n"
        auto_launch=true

    # 3. Codebase Exploration - Launch Explore agent
    elif echo "$prompt_lower" | grep -qE "(how does|where is.*implemented|find.*in.*code|explain.*implementation|understand.*work)"; then
        local thoroughness="medium"
        if echo "$prompt_lower" | grep -qE "(entire|all|comprehensive|complex)"; then
            thoroughness="very thorough"
        elif echo "$prompt_lower" | grep -qE "(quick|simple|just)"; then
            thoroughness="quick"
        fi

        launch_directive="🔍 AUTO-LAUNCHING: Explore agent (${thoroughness})\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool with subagent_type=Explore and the following prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}\"\n"
        launch_directive="${launch_directive}Specify thoroughness level: ${thoroughness}\n\n"
        auto_launch=true

    # 4. Testing Tasks - Launch testing-guardian
    elif echo "$prompt_lower" | grep -qE "(write.*test|add.*test|test.*coverage|fix.*test|tdd)"; then
        launch_directive="🧪 AUTO-LAUNCHING: testing-guardian\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the testing-guardian agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Remember to follow TDD principles - write tests before implementation.\"\n\n"
        auto_launch=true

    # 5. Complex Debugging - Launch debugger agent
    elif echo "$prompt_lower" | grep -qE "(debug|fix.*error|not working|fails|crash|investigate.*bug)"; then
        launch_directive="🐛 AUTO-LAUNCHING: debugger\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the debugger agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Perform systematic evidence gathering and root cause analysis.\"\n\n"
        auto_launch=true

    # 6. Security/Compliance Review - Launch security-engineer
    elif echo "$prompt_lower" | grep -qE "(security.*review|audit.*security|check.*vulnerabilit|pen.*test|security.*scan)"; then
        launch_directive="🔒 AUTO-LAUNCHING: security-engineer\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the security-engineer agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Perform comprehensive security analysis including OWASP top 10 checks.\"\n\n"
        auto_launch=true

    # 7. Code Review - Launch code-reviewer
    elif echo "$prompt_lower" | grep -qE "(review.*code|code.*review|check.*code.*quality|analyze.*code)"; then
        launch_directive="👀 AUTO-LAUNCHING: code-reviewer\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the code-reviewer agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Check for code quality, security vulnerabilities, and best practices.\"\n\n"
        auto_launch=true

    # 8. Research/Web Search - Launch web-search-researcher
    elif echo "$prompt_lower" | grep -qE "(what.*latest|current|search.*web|recent.*developments|up.*to.*date)"; then
        launch_directive="🌐 AUTO-LAUNCHING: web-search-researcher\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the web-search-researcher agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Search for current information and synthesize findings.\"\n\n"
        auto_launch=true

    # 9. Frontend Development (Complex) - Launch frontend-developer
    elif echo "$prompt_lower" | grep -qE "(create.*component|build.*dashboard|implement.*ui|data.*grid|complex.*layout)"; then
        launch_directive="💻 AUTO-LAUNCHING: frontend-developer\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the frontend-developer agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Create type-safe, accessible components with modern React patterns.\"\n\n"
        auto_launch=true

    # 10. Database Operations (Complex) - Launch database-administrator
    elif echo "$prompt_lower" | grep -qE "(optimize.*query|database.*performance|migration|schema.*design|index.*optimization)"; then
        launch_directive="💾 AUTO-LAUNCHING: database-administrator\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the database-administrator agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Analyze performance and optimize database operations.\"\n\n"
        auto_launch=true

    # 11. Deployment/DevOps - Launch deployment-engineer
    elif echo "$prompt_lower" | grep -qE "(deploy|ci.*cd.*pipeline|release|rollout|kubernetes|docker.*compose)"; then
        launch_directive="🚀 AUTO-LAUNCHING: deployment-engineer\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the deployment-engineer agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Design deployment strategy with zero-downtime and rollback capabilities.\"\n\n"
        auto_launch=true

    # 12. API Documentation - Launch api-documenter
    elif echo "$prompt_lower" | grep -qE "(document.*api|openapi|swagger|api.*spec|generate.*api.*doc)"; then
        launch_directive="📚 AUTO-LAUNCHING: api-documenter\n\n"
        launch_directive="${launch_directive}DIRECTIVE: Immediately use the Task tool to launch the api-documenter agent with prompt:\n"
        launch_directive="${launch_directive}\"${USER_PROMPT}. Create comprehensive API documentation with examples.\"\n\n"
        auto_launch=true
    fi

    # Output the launch directive if auto-launch is triggered
    if [ "$auto_launch" = true ]; then
        echo -e "╔════════════════════════════════════════════════════════════╗"
        echo -e "║          🤖 AUTOMATIC AGENT LAUNCHER ACTIVATED            ║"
        echo -e "╚════════════════════════════════════════════════════════════╝\n"
        echo -e "$launch_directive"
        echo -e "💡 Note: The agent will be launched automatically. You can still"
        echo -e "   modify the approach or launch additional agents as needed.\n"
        echo -e "────────────────────────────────────────────────────────────\n"
    fi
}

# Run agent determination and output launch directive
determine_agents "$USER_PROMPT"

# Always return success to not block the prompt
exit 0
