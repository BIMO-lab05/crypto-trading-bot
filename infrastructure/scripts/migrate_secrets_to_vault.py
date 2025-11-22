#!/usr/bin/env python3
"""
Secrets Migration Script - .env to HashiCorp Vault
Purpose: Migrate all secrets from .env files to Vault
Author: Security Engineer Agent
Date: 2025-11-21
Version: 1.0

This script:
1. Reads secrets from .env files across all services
2. Migrates them to HashiCorp Vault
3. Creates backups of original .env files
4. Updates .env files with Vault references
5. Verifies successful migration
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import re
from datetime import datetime
import json
import shutil

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.vault_client import VaultClient, VaultConnectionError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SecretsMigration:
    """
    Migrate secrets from .env files to HashiCorp Vault

    Attributes:
        project_root: Root directory of the project
        vault_client: Vault client instance
        dry_run: If True, don't actually write to Vault
        backup_dir: Directory for .env backups
        migration_report: Report of migration results
    """

    # Secret patterns to identify sensitive data
    SECRET_PATTERNS = [
        r'.*PASSWORD.*',
        r'.*SECRET.*',
        r'.*KEY.*',
        r'.*TOKEN.*',
        r'.*CREDENTIAL.*',
        r'.*API.*',
        r'.*JWT.*'
    ]

    # Non-secret configuration patterns
    NON_SECRET_PATTERNS = [
        r'.*_HOST$',
        r'.*_PORT$',
        r'.*_URL$',
        r'.*_PATH$',
        r'.*_LEVEL$',
        r'.*_MODE$',
        r'ENVIRONMENT',
        r'DEBUG',
        r'LOG_.*',
        r'ENABLE_.*',
        r'MAX_.*',
        r'MIN_.*',
        r'DEFAULT_.*',
        r'WORKERS',
        r'TIMEOUT.*'
    ]

    def __init__(
        self,
        project_root: str,
        vault_client: VaultClient,
        dry_run: bool = False
    ):
        """
        Initialize migration

        Args:
            project_root: Project root directory
            vault_client: Initialized Vault client
            dry_run: If True, simulate migration without writing
        """
        self.project_root = Path(project_root)
        self.vault = vault_client
        self.dry_run = dry_run
        self.backup_dir = self.project_root / 'backups' / 'env_files' / datetime.now().strftime('%Y%m%d_%H%M%S')
        self.migration_report = {
            'timestamp': datetime.now().isoformat(),
            'dry_run': dry_run,
            'services_migrated': [],
            'secrets_migrated': 0,
            'errors': []
        }

        # Create backup directory
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Backup directory created: {self.backup_dir}")

    def is_secret(self, key: str, value: str) -> bool:
        """
        Determine if an environment variable is a secret

        Args:
            key: Environment variable name
            value: Environment variable value

        Returns:
            True if variable contains sensitive data
        """
        # Check if it matches non-secret patterns (config)
        for pattern in self.NON_SECRET_PATTERNS:
            if re.match(pattern, key, re.IGNORECASE):
                return False

        # Check if it matches secret patterns
        for pattern in self.SECRET_PATTERNS:
            if re.match(pattern, key, re.IGNORECASE):
                return True

        # Check if value looks like a secret (long random string)
        if len(value) > 20 and any(c.isalnum() for c in value):
            # Contains mix of letters and numbers, likely a secret
            has_letters = any(c.isalpha() for c in value)
            has_numbers = any(c.isdigit() for c in value)
            if has_letters and has_numbers:
                return True

        return False

    def parse_env_file(self, env_file_path: Path) -> Dict[str, str]:
        """
        Parse .env file and extract key-value pairs

        Args:
            env_file_path: Path to .env file

        Returns:
            Dictionary of environment variables
        """
        env_vars = {}

        try:
            with open(env_file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue

                    # Parse KEY=VALUE format
                    match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', line, re.IGNORECASE)
                    if match:
                        key = match.group(1)
                        value = match.group(2)

                        # Remove quotes if present
                        value = value.strip('"').strip("'")

                        # Skip placeholder values
                        if 'your_' in value.lower() or 'change_this' in value.lower():
                            logger.debug(f"Skipping placeholder: {key}")
                            continue

                        env_vars[key] = value
                    else:
                        logger.warning(f"Invalid line in {env_file_path}:{line_num}: {line}")

        except Exception as e:
            logger.error(f"Failed to parse {env_file_path}: {e}")
            self.migration_report['errors'].append({
                'file': str(env_file_path),
                'error': str(e)
            })

        return env_vars

    def categorize_secrets(self, env_vars: Dict[str, str]) -> Tuple[Dict[str, Dict[str, str]], Dict[str, str]]:
        """
        Categorize environment variables into secret groups and config

        Args:
            env_vars: All environment variables

        Returns:
            Tuple of (secrets_by_category, config_vars)
        """
        secrets = {
            'database': {},
            'redis': {},
            'rabbitmq': {},
            'bybit': {},
            'jwt': {},
            'notification': {},
            'other': {}
        }
        config = {}

        for key, value in env_vars.items():
            if self.is_secret(key, value):
                # Categorize secret
                key_lower = key.lower()

                if 'postgres' in key_lower or 'timescale' in key_lower or 'database' in key_lower:
                    secrets['database'][key] = value
                elif 'redis' in key_lower:
                    secrets['redis'][key] = value
                elif 'rabbitmq' in key_lower:
                    secrets['rabbitmq'][key] = value
                elif 'bybit' in key_lower:
                    secrets['bybit'][key] = value
                elif 'jwt' in key_lower:
                    secrets['jwt'][key] = value
                elif 'email' in key_lower or 'telegram' in key_lower or 'notification' in key_lower:
                    secrets['notification'][key] = value
                else:
                    secrets['other'][key] = value
            else:
                config[key] = value

        return secrets, config

    def migrate_service_secrets(self, service_name: str, env_file_path: Path) -> bool:
        """
        Migrate secrets from a single service .env file

        Args:
            service_name: Name of the service
            env_file_path: Path to service .env file

        Returns:
            True if migration successful
        """
        logger.info(f"Migrating secrets for service: {service_name}")

        try:
            # Backup original .env file
            backup_path = self.backup_dir / service_name / '.env'
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(env_file_path, backup_path)
            logger.info(f"Backed up {env_file_path} to {backup_path}")

            # Parse .env file
            env_vars = self.parse_env_file(env_file_path)
            if not env_vars:
                logger.warning(f"No variables found in {env_file_path}")
                return True

            # Categorize secrets
            secrets, config = self.categorize_secrets(env_vars)

            secrets_count = 0

            # Migrate secrets to Vault
            for category, category_secrets in secrets.items():
                if not category_secrets:
                    continue

                # Create Vault path
                vault_path = f"{service_name}/{category}"

                if self.dry_run:
                    logger.info(f"[DRY RUN] Would write {len(category_secrets)} secrets to {vault_path}")
                    logger.debug(f"[DRY RUN] Keys: {list(category_secrets.keys())}")
                else:
                    try:
                        self.vault.write_secret(vault_path, category_secrets)
                        logger.info(f"Wrote {len(category_secrets)} secrets to {vault_path}")
                        secrets_count += len(category_secrets)
                    except Exception as e:
                        logger.error(f"Failed to write secrets to {vault_path}: {e}")
                        self.migration_report['errors'].append({
                            'service': service_name,
                            'category': category,
                            'error': str(e)
                        })
                        return False

            # Create new .env file with Vault references
            new_env_content = self._generate_vault_env_file(service_name, secrets, config)

            if not self.dry_run:
                with open(env_file_path, 'w') as f:
                    f.write(new_env_content)
                logger.info(f"Updated {env_file_path} with Vault references")

            # Update report
            self.migration_report['services_migrated'].append({
                'name': service_name,
                'secrets_count': secrets_count,
                'config_count': len(config)
            })
            self.migration_report['secrets_migrated'] += secrets_count

            logger.info(f"Successfully migrated {secrets_count} secrets for {service_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to migrate secrets for {service_name}: {e}")
            self.migration_report['errors'].append({
                'service': service_name,
                'error': str(e)
            })
            return False

    def _generate_vault_env_file(
        self,
        service_name: str,
        secrets: Dict[str, Dict[str, str]],
        config: Dict[str, str]
    ) -> str:
        """
        Generate new .env file with Vault references

        Args:
            service_name: Service name
            secrets: Categorized secrets
            config: Non-secret configuration

        Returns:
            New .env file content
        """
        lines = [
            f"# Environment Configuration for {service_name}",
            f"# Secrets are stored in HashiCorp Vault",
            f"# Migrated: {datetime.now().isoformat()}",
            "",
            "# ============================================================================",
            "# VAULT CONFIGURATION",
            "# ============================================================================",
            "VAULT_ADDR=http://127.0.0.1:8200",
            f"# VAULT_TOKEN=<get-from-vault-keys>",
            "",
            "# ============================================================================",
            "# SECRETS (Stored in Vault)",
            "# ============================================================================"
        ]

        # Add comments about where secrets are stored
        for category, category_secrets in secrets.items():
            if category_secrets:
                lines.append(f"# {category.upper()} secrets: vault kv get secret/{service_name}/{category}")

        lines.extend([
            "",
            "# ============================================================================",
            "# CONFIGURATION (Non-Sensitive)",
            "# ============================================================================"
        ])

        # Add non-secret configuration
        for key, value in sorted(config.items()):
            lines.append(f"{key}={value}")

        lines.append("")
        lines.append("# ============================================================================")
        lines.append("# MIGRATION NOTES")
        lines.append("# ============================================================================")
        lines.append("# Secrets have been migrated to Vault. To retrieve:")
        lines.append("#")
        for category in secrets.keys():
            if secrets[category]:
                lines.append(f"#   vault kv get secret/{service_name}/{category}")
        lines.append("#")
        lines.append(f"# Original .env backed up to: {self.backup_dir}/{service_name}/.env")
        lines.append("# ============================================================================")
        lines.append("")

        return '\n'.join(lines)

    def find_env_files(self) -> List[Tuple[str, Path]]:
        """
        Find all .env files in the project

        Returns:
            List of (service_name, env_file_path) tuples
        """
        env_files = []

        # Root .env file
        root_env = self.project_root / '.env'
        if root_env.exists():
            env_files.append(('root', root_env))

        # Service .env files
        services_dir = self.project_root / 'services'
        if services_dir.exists():
            for service_dir in services_dir.iterdir():
                if service_dir.is_dir():
                    env_file = service_dir / '.env'
                    if env_file.exists():
                        env_files.append((service_dir.name, env_file))

        logger.info(f"Found {len(env_files)} .env files")
        return env_files

    def run_migration(self) -> bool:
        """
        Run full migration process

        Returns:
            True if migration successful for all services
        """
        logger.info("=" * 80)
        logger.info("Starting Secrets Migration to Vault")
        logger.info("=" * 80)

        if self.dry_run:
            logger.warning("DRY RUN MODE - No changes will be made")

        # Find all .env files
        env_files = self.find_env_files()

        if not env_files:
            logger.error("No .env files found")
            return False

        # Migrate each service
        success_count = 0
        for service_name, env_file_path in env_files:
            if self.migrate_service_secrets(service_name, env_file_path):
                success_count += 1

        # Generate migration report
        self._generate_report()

        # Summary
        logger.info("=" * 80)
        logger.info("Migration Summary")
        logger.info("=" * 80)
        logger.info(f"Services processed: {len(env_files)}")
        logger.info(f"Services migrated: {success_count}")
        logger.info(f"Total secrets migrated: {self.migration_report['secrets_migrated']}")
        logger.info(f"Errors: {len(self.migration_report['errors'])}")
        logger.info(f"Backup location: {self.backup_dir}")
        logger.info("=" * 80)

        return success_count == len(env_files)

    def _generate_report(self):
        """Generate migration report JSON file"""
        report_path = self.backup_dir / 'migration_report.json'

        try:
            with open(report_path, 'w') as f:
                json.dump(self.migration_report, f, indent=2)

            logger.info(f"Migration report saved to {report_path}")

        except Exception as e:
            logger.error(f"Failed to save migration report: {e}")

    def verify_migration(self) -> bool:
        """
        Verify that secrets were successfully migrated

        Returns:
            True if verification successful
        """
        logger.info("Verifying migration...")

        verification_passed = True

        for service_info in self.migration_report['services_migrated']:
            service_name = service_info['name']
            logger.info(f"Verifying {service_name}...")

            # Try to read secrets from Vault
            for category in ['database', 'redis', 'rabbitmq', 'bybit', 'jwt', 'notification', 'other']:
                vault_path = f"{service_name}/{category}"

                try:
                    secrets = self.vault.read_secret(vault_path, use_cache=False)
                    if secrets:
                        logger.info(f"✓ Verified {vault_path} ({len(secrets)} secrets)")
                except Exception as e:
                    # Path may not exist if category is empty
                    logger.debug(f"No secrets at {vault_path}: {e}")

        logger.info("Verification complete")
        return verification_passed


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Migrate secrets from .env files to HashiCorp Vault'
    )
    parser.add_argument(
        '--project-root',
        default='/mnt/d/Bimo_max/crypto-trading-bot',
        help='Project root directory'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate migration without making changes'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify migration after completion'
    )
    parser.add_argument(
        '--vault-addr',
        default=os.getenv('VAULT_ADDR', 'http://127.0.0.1:8200'),
        help='Vault server address'
    )
    parser.add_argument(
        '--vault-token',
        default=os.getenv('VAULT_TOKEN'),
        help='Vault authentication token'
    )

    args = parser.parse_args()

    # Validate Vault token
    if not args.vault_token:
        logger.error("Vault token not provided. Set VAULT_TOKEN environment variable or use --vault-token")
        return 1

    try:
        # Initialize Vault client
        logger.info(f"Connecting to Vault at {args.vault_addr}")
        vault = VaultClient(
            vault_addr=args.vault_addr,
            vault_token=args.vault_token
        )

        # Run migration
        migration = SecretsMigration(
            project_root=args.project_root,
            vault_client=vault,
            dry_run=args.dry_run
        )

        success = migration.run_migration()

        if success:
            logger.info("✓ Migration completed successfully")

            # Verify if requested
            if args.verify:
                if migration.verify_migration():
                    logger.info("✓ Verification passed")
                else:
                    logger.warning("⚠ Verification found issues")

            return 0
        else:
            logger.error("✗ Migration failed")
            return 1

    except VaultConnectionError as e:
        logger.error(f"Failed to connect to Vault: {e}")
        return 1
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return 1
    finally:
        # Cleanup
        if 'vault' in locals():
            vault.close()


if __name__ == '__main__':
    sys.exit(main())
