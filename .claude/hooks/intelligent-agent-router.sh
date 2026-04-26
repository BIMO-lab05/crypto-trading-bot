#!/bin/bash
# Intelligent Agent Router Hook
# Scans .claude/agents/ directory and gives Claude full access to choose
# the most appropriate agent(s) based on the user's prompt
# Runs BEFORE Claude sees your message

USER_PROMPT="$1"
AGENTS_DIR="/mnt/d/Bimo_max/.claude/agents"

# Function to get all available agents
get_available_agents() {
    local agents_list=""

    # Scan agents directory for all .md files
    if [ -d "$AGENTS_DIR" ]; then
        for agent_file in "$AGENTS_DIR"/*.md; do
            if [ -f "$agent_file" ]; then
                # Extract agent name (filename without .md extension)
                local agent_name=$(basename "$agent_file" .md)

                # Extract description from the agent file (first few lines)
                local description=$(head -20 "$agent_file" | grep -E "^(#|description:|specializes|masters)" | head -3 | sed 's/^# *//' | tr '\n' ' ')

                # If no description found, use a generic one
                if [ -z "$description" ]; then
                    description="Specialized agent for $agent_name tasks"
                fi

                agents_list="${agents_list}  • ${agent_name}: ${description}\n"
            fi
        done

        # Also check subdirectories (coordinators, specialists, etc.)
        for subdir in "$AGENTS_DIR"/*/; do
            if [ -d "$subdir" ]; then
                local category=$(basename "$subdir")
                for agent_file in "$subdir"/*.md; do
                    if [ -f "$agent_file" ]; then
                        local agent_name=$(basename "$agent_file" .md)
                        local description=$(head -20 "$agent_file" | grep -E "^(#|description:|specializes|masters)" | head -3 | sed 's/^# *//' | tr '\n' ' ')

                        if [ -z "$description" ]; then
                            description="[$category] Specialized agent"
                        fi

                        agents_list="${agents_list}  • ${category}/${agent_name}: ${description}\n"
                    fi
                done
            fi
        done
    fi

    echo -e "$agents_list"
}

# Function to analyze prompt and provide intelligent routing directive
provide_routing_directive() {
    local prompt="$1"
    local available_agents="$2"

    echo -e "╔════════════════════════════════════════════════════════════╗"
    echo -e "║       🤖 INTELLIGENT AGENT ROUTER - FULL ACCESS          ║"
    echo -e "╚════════════════════════════════════════════════════════════╝\n"

    echo -e "📋 USER REQUEST: \"${prompt}\"\n"

    echo -e "🎯 DIRECTIVE FOR CLAUDE:\n"
    echo -e "You have FULL ACCESS to launch any agent(s) from the available agents list below."
    echo -e "Analyze the user's request and determine which agent(s) would be most appropriate.\n"

    echo -e "INSTRUCTIONS:"
    echo -e "1. Read the user's prompt carefully"
    echo -e "2. Review the available agents and their capabilities"
    echo -e "3. Choose the most appropriate agent(s) - you can launch multiple in parallel if needed"
    echo -e "4. Use the Task tool with subagent_type=<agent-name> to launch the agent(s)"
    echo -e "5. Provide the agent with clear context and instructions\n"

    echo -e "⚡ AVAILABLE AGENTS IN YOUR .claude/agents/ DIRECTORY:\n"
    echo -e "$available_agents"

    echo -e "\n💡 AGENT SELECTION GUIDELINES:"
    echo -e "  • For codebase exploration: Use 'Explore' agent (specify thoroughness: quick/medium/very thorough)"
    echo -e "  • For complex tasks: Consider launching multiple agents in parallel"
    echo -e "  • For project management: Use 'crypto-bot-project-manager' or 'project-workflow-orchestrator'"
    echo -e "  • For architecture: Use 'microservices-architect' or 'domain-expert'"
    echo -e "  • For debugging: Use 'debugger' or 'error-detective'"
    echo -e "  • For specialized work: Choose the most relevant specialist agent\n"

    echo -e "🚀 RECOMMENDED APPROACH:"
    echo -e "  1. If unsure about codebase structure: Start with Explore agent first"
    echo -e "  2. For implementation tasks: Use appropriate specialist agent"
    echo -e "  3. For complex workflows: Launch multiple agents in parallel"
    echo -e "  4. For project continuation: Start with project manager to load context\n"

    echo -e "⚙️  USAGE EXAMPLES:"
    echo -e "  Single agent:  Task(subagent_type='backend-developer', prompt='...')"
    echo -e "  Multiple:      Task(subagent_type='architect-reviewer', ...) + Task(subagent_type='code-reviewer', ...)"
    echo -e "  Explore:       Task(subagent_type='Explore', prompt='...', thoroughness='medium')\n"

    echo -e "✨ You have the intelligence to choose wisely. Proceed with launching the appropriate agent(s).\n"
    echo -e "────────────────────────────────────────────────────────────\n"
}

# Get list of all available agents
AVAILABLE_AGENTS=$(get_available_agents)

# Provide the intelligent routing directive
provide_routing_directive "$USER_PROMPT" "$AVAILABLE_AGENTS"

# Always return success to not block the prompt
exit 0
