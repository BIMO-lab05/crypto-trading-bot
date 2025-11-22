#!/usr/bin/env python3
"""
Infrastructure Integration Script
Automatically integrates shared utilities (structured logging, graceful shutdown, etc.)
into all microservices

Usage:
    python scripts/integrate_infrastructure.py --service trading-engine
    python scripts/integrate_infrastructure.py --all
"""

import argparse
import re
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).parent.parent
SERVICES_DIR = PROJECT_ROOT / "services"

SERVICES = [
    "api-gateway",
    "trading-engine",
    "market-data-service",
    "technical-analysis",
    "portfolio-manager",
    "bybit-connector",
    "risk-metrics-service",
    "ml-prediction-service",
    "sentiment-analysis-service",
    "notification-service"
]


def check_service_exists(service_name: str) -> bool:
    """Check if service directory exists"""
    service_path = SERVICES_DIR / service_name
    return service_path.exists() and (service_path / "app" / "main.py").exists()


def backup_file(file_path: Path) -> Path:
    """Create backup of file before modification"""
    backup_path = file_path.with_suffix(file_path.suffix + '.bak')
    if file_path.exists():
        import shutil
        shutil.copy2(file_path, backup_path)
        print(f"  ✅ Backed up: {backup_path}")
    return backup_path


def add_structured_logging_imports(content: str) -> str:
    """Add structured logging imports to the file"""

    # Check if already imported
    if "from utils.structured_logging import" in content:
        print("  ⏭️  Structured logging already imported")
        return content

    # Find the import section
    import_pattern = r"(from fastapi import.*?\n)"

    # Add the imports
    new_imports = """import sys
import uuid
from pathlib import Path

# Add shared utilities to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
from utils.structured_logging import setup_logging, RequestContextLogger
from utils.graceful_shutdown import GracefulShutdownHandler

"""

    # Replace first fastapi import
    content = re.sub(
        import_pattern,
        r"\1" + new_imports,
        content,
        count=1
    )

    return content


def replace_basic_logging(content: str, service_name: str) -> str:
    """Replace basic logging with structured logging"""

    # Check if already using structured logging
    if "setup_logging(" in content:
        print("  ⏭️  Already using structured logging")
        return content

    # Pattern to match basic logging setup
    basic_logging_pattern = r"# Configure logging\nlogging\.basicConfig\([^)]+\)\nlogger = logging\.getLogger\(__name__\)"

    # Replacement with structured logging
    structured_logging = f"""# Configure structured logging
logger = setup_logging(
    service_name="{service_name}",
    environment=getattr(settings, 'environment', 'development'),
    log_level=settings.log_level,
    log_file=str(LOG_DIR / 'service.log')
)

# Initialize graceful shutdown handler
shutdown_handler = GracefulShutdownHandler(
    shutdown_timeout=30.0,
    service_name="{service_name}"
)"""

    content = re.sub(
        basic_logging_pattern,
        structured_logging,
        content
    )

    return content


def update_lifespan_function(content: str) -> str:
    """Update lifespan function to use graceful shutdown"""

    # Check if already using graceful shutdown
    if "shutdown_handler.setup_signal_handlers()" in content:
        print("  ⏭️  Lifespan already uses graceful shutdown")
        return content

    # Pattern to match lifespan function
    lifespan_start_pattern = r"(@asynccontextmanager\nasync def lifespan\(app: FastAPI\):[^\n]+\n)"

    # Add shutdown handler setup at the beginning
    lifespan_start_replacement = r"""\1    # Setup signal handlers for graceful shutdown
    shutdown_handler.setup_signal_handlers()

"""

    content = re.sub(
        lifespan_start_pattern,
        lifespan_start_replacement,
        content
    )

    # Pattern to match shutdown section
    shutdown_pattern = r"(    # Shutdown\n    logger\.info\([^)]+\))"

    # Replace with graceful shutdown
    shutdown_replacement = r"""    # Graceful shutdown
    logger.info("Initiating graceful shutdown", service=settings.service_name)
    await shutdown_handler.shutdown()"""

    content = re.sub(
        shutdown_pattern,
        shutdown_replacement,
        content
    )

    return content


def update_log_statements(content: str) -> str:
    """Update log statements to use structured format"""

    # Update logger.info with f-strings to structured format
    # Pattern: logger.info(f"Message {var}")
    # Replace with: logger.info("Message", var=var)

    # This is a simplified replacement - in production you'd want more sophisticated parsing
    # For now, we'll leave existing log statements and let developers migrate manually

    return content


def integrate_service(service_name: str, dry_run: bool = False) -> bool:
    """Integrate infrastructure utilities into a service"""

    print(f"\n{'='*60}")
    print(f"Integrating: {service_name}")
    print(f"{'='*60}")

    if not check_service_exists(service_name):
        print(f"  ❌ Service not found: {service_name}")
        return False

    main_file = SERVICES_DIR / service_name / "app" / "main.py"

    if not main_file.exists():
        print(f"  ❌ main.py not found: {main_file}")
        return False

    # Read current content
    with open(main_file, 'r') as f:
        original_content = f.read()

    content = original_content

    # Step 1: Add imports
    print("\n  📦 Adding structured logging imports...")
    content = add_structured_logging_imports(content)

    # Step 2: Replace basic logging
    print("  🔄 Replacing basic logging with structured logging...")
    content = replace_basic_logging(content, service_name)

    # Step 3: Update lifespan function
    print("  🔄 Updating lifespan function...")
    content = update_lifespan_function(content)

    # Step 4: Update log statements (manual for now)
    print("  📝 Log statements (manual migration recommended)")

    # Check if anything changed
    if content == original_content:
        print("\n  ✅ No changes needed - service already integrated!")
        return True

    if dry_run:
        print("\n  🔍 DRY RUN - No files modified")
        print(f"\n  Preview of changes for {service_name}:")
        print("  " + "-" * 60)
        # Show diff summary
        return True

    # Backup original file
    print("\n  💾 Creating backup...")
    backup_file(main_file)

    # Write updated content
    print("  ✍️  Writing updated file...")
    with open(main_file, 'w') as f:
        f.write(content)

    print(f"\n  ✅ Successfully integrated: {service_name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Integrate infrastructure utilities into microservices"
    )
    parser.add_argument(
        '--service',
        type=str,
        help='Service name to integrate'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Integrate all services'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )

    args = parser.parse_args()

    if not args.service and not args.all:
        parser.print_help()
        return

    services_to_process = []

    if args.all:
        services_to_process = SERVICES
    elif args.service:
        if args.service not in SERVICES:
            print(f"❌ Unknown service: {args.service}")
            print(f"\nAvailable services:")
            for svc in SERVICES:
                print(f"  - {svc}")
            return
        services_to_process = [args.service]

    print("\n" + "="*70)
    print("  INFRASTRUCTURE INTEGRATION SCRIPT")
    print("="*70)
    print(f"\nServices to process: {len(services_to_process)}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")

    results = []
    for service in services_to_process:
        success = integrate_service(service, dry_run=args.dry_run)
        results.append((service, success))

    # Print summary
    print("\n" + "="*70)
    print("  INTEGRATION SUMMARY")
    print("="*70)

    successful = [svc for svc, success in results if success]
    failed = [svc for svc, success in results if not success]

    print(f"\n✅ Successful: {len(successful)}")
    for svc in successful:
        print(f"   - {svc}")

    if failed:
        print(f"\n❌ Failed: {len(failed)}")
        for svc in failed:
            print(f"   - {svc}")

    print("\n" + "="*70)
    print("\n📋 Next Steps:")
    print("  1. Review the changes in each service's main.py")
    print("  2. Update individual log statements to use structured format:")
    print("     logger.info('message', key=value, ...)")
    print("  3. Test each service to ensure proper integration")
    print("  4. Commit changes with descriptive message")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
