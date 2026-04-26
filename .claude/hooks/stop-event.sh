#!/bin/bash
# Stop Event Hook - Code Quality Checker
# Runs AFTER Claude finishes responding
# Analyzes edited files and provides gentle reminders

# Function to get recently modified files (within last 5 minutes)
get_recent_files() {
    find . -type f -mmin -5 \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) 2>/dev/null
}

# Function to check for risky patterns
check_code_quality() {
    local file="$1"
    local warnings=""
    local has_issues=false

    # Skip if file doesn't exist
    [ ! -f "$file" ] && return

    # Python file checks
    if [[ "$file" == *.py ]]; then
        # Check for try-catch without logging
        if grep -q "try:" "$file" && ! grep -q "logger\|logging\|log\." "$file"; then
            warnings="${warnings}  ⚠️  Try-catch blocks found - Did you add logging?\n"
            has_issues=true
        fi

        # Check for async functions
        if grep -q "async def\|await " "$file"; then
            if ! grep -qE "asyncio\.TimeoutError|asyncio\.wait_for|timeout" "$file"; then
                warnings="${warnings}  ⏱️  Async operations found - Consider adding timeouts\n"
                has_issues=true
            fi
        fi

        # Check for database operations (Prisma/SQLAlchemy patterns)
        if grep -qE "prisma\.|session\.|query\.|execute\(" "$file"; then
            if ! grep -q "repository\|Repository" "$file"; then
                warnings="${warnings}  🗄️  Database operations found - Are you using repository pattern?\n"
                has_issues=true
            fi
        fi

        # Check for API keys or secrets
        if grep -qiE "api_key\s*=\s*['\"]|secret\s*=\s*['\"]|password\s*=\s*['\"]" "$file"; then
            warnings="${warnings}  🔐 CRITICAL: Potential hardcoded secrets detected!\n"
            has_issues=true
        fi

        # Check for proper error handling in Bybit operations
        if grep -qE "bybit|place_order|get_balance" "$file"; then
            if ! grep -qE "try:|except|raise|HTTPException" "$file"; then
                warnings="${warnings}  💹 Trading operations found - Add comprehensive error handling!\n"
                has_issues=true
            fi
        fi
    fi

    # TypeScript/JavaScript file checks
    if [[ "$file" =~ \.(ts|tsx|js|jsx)$ ]]; then
        # Check for try-catch without logging
        if grep -q "try {" "$file" && ! grep -qE "console\.(error|warn|log)|logger\." "$file"; then
            warnings="${warnings}  ⚠️  Try-catch blocks found - Did you add logging?\n"
            has_issues=true
        fi

        # Check for async/await
        if grep -qE "async |await " "$file"; then
            if ! grep -qE "\.catch\(|try \{" "$file"; then
                warnings="${warnings}  ⏱️  Async operations found - Add error handling\n"
                has_issues=true
            fi
        fi

        # Check for API calls without error handling
        if grep -qE "fetch\(|axios\.|api\." "$file"; then
            if ! grep -qE "\.catch\(|try \{|onError" "$file"; then
                warnings="${warnings}  🌐 API calls found - Add error handling\n"
                has_issues=true
            fi
        fi
    fi

    # General checks for all files
    # Check for TODO/FIXME comments
    if grep -qiE "TODO|FIXME|HACK|XXX" "$file"; then
        warnings="${warnings}  📝 TODO/FIXME comments found - Track in issue tracker?\n"
        has_issues=true
    fi

    # Check for console.log in production code (excluding test files)
    if [[ ! "$file" =~ test|spec ]] && grep -q "console\.log" "$file"; then
        warnings="${warnings}  🐛 console.log found - Replace with proper logging\n"
        has_issues=true
    fi

    if [ "$has_issues" = true ]; then
        echo -e "\n📁 $file:\n$warnings"
    fi
}

# Main execution
RECENT_FILES=$(get_recent_files)
ISSUES_FOUND=false

if [ -n "$RECENT_FILES" ]; then
    echo -e "\n╔════════════════════════════════════════════════════════════╗"
    echo -e "║           CODE QUALITY SELF-CHECK REMINDER                ║"
    echo -e "╚════════════════════════════════════════════════════════════╝"

    while IFS= read -r file; do
        result=$(check_code_quality "$file")
        if [ -n "$result" ]; then
            echo -e "$result"
            ISSUES_FOUND=true
        fi
    done <<< "$RECENT_FILES"

    if [ "$ISSUES_FOUND" = false ]; then
        echo -e "\n✅ No obvious quality issues detected in recently modified files"
    else
        echo -e "\n💡 Gentle Reminders:"
        echo -e "  • All errors should be logged with context"
        echo -e "  • Database operations should use repository pattern"
        echo -e "  • Async operations need timeout handling"
        echo -e "  • Never hardcode secrets - use environment variables"
        echo -e "  • Trading operations require comprehensive error handling"
    fi

    echo -e "\n📋 Quick Checklist:"
    echo -e "  ☐ Error handling implemented?"
    echo -e "  ☐ Logging added with context?"
    echo -e "  ☐ Tests written/updated?"
    echo -e "  ☐ Documentation updated?"
    echo -e "  ☐ No hardcoded secrets?"
    echo -e "\n────────────────────────────────────────────────────────────\n"
fi

# Always return success (non-blocking)
exit 0
