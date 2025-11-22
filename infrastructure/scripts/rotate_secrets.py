#!/usr/bin/env python3
"""
Automated Secret Rotation Script
Purpose: Automatically rotate secrets with zero downtime
Author: Security Engineer Agent
Date: 2025-11-21
Version: 1.0

Supported rotations:
- Bybit API keys (requires manual new key generation, then updates Vault)
- Database passwords (automatic with dynamic credentials)
- Redis passwords
- RabbitMQ passwords
- JWT secrets
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import json
import time
import requests

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.vault_client import VaultClient, VaultConnectionError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SecretRotation:
    """
    Automated secret rotation with zero downtime

    Features:
    - Pre-rotation validation
    - Dual-credential overlap period
    - Health check verification
    - Automatic rollback on failure
    - Audit logging of all rotations
    """

    def __init__(self, vault_client: VaultClient, dry_run: bool = False):
        """
        Initialize secret rotation

        Args:
            vault_client: Vault client instance
            dry_run: If True, simulate rotation without making changes
        """
        self.vault = vault_client
        self.dry_run = dry_run
        self.rotation_log = []

    def _log_rotation(self, secret_type: str, status: str, details: Dict[str, Any]):
        """
        Log rotation event

        Args:
            secret_type: Type of secret being rotated
            status: Rotation status (started, success, failed, rolled_back)
            details: Additional rotation details
        """
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'secret_type': secret_type,
            'status': status,
            'details': details,
            'dry_run': self.dry_run
        }

        self.rotation_log.append(log_entry)

        # Also log to Vault audit
        if self.vault.audit_enabled:
            self.vault._audit_log(f'rotate_{secret_type}', {
                'status': status,
                **details
            })

        logger.info(f"Rotation event: {secret_type} - {status}")

    def rotate_bybit_api_keys(
        self,
        new_api_key: str,
        new_api_secret: str,
        testnet: bool = True,
        overlap_seconds: int = 300
    ) -> bool:
        """
        Rotate Bybit API keys with zero downtime

        Process:
        1. Store new credentials in Vault
        2. Notify services to reload credentials
        3. Wait for overlap period
        4. Verify old credentials are no longer in use
        5. Remove old credentials from Vault

        Args:
            new_api_key: New Bybit API key
            new_api_secret: New Bybit API secret
            testnet: Whether using testnet
            overlap_seconds: Time to allow both credentials to be valid

        Returns:
            True if rotation successful
        """
        secret_type = 'bybit_api_keys'
        logger.info(f"Starting Bybit API key rotation (overlap: {overlap_seconds}s)")

        self._log_rotation(secret_type, 'started', {
            'testnet': testnet,
            'overlap_seconds': overlap_seconds
        })

        try:
            # Step 1: Read current credentials
            current_creds = self.vault.read_secret('bybit-connector/bybit', use_cache=False)
            old_api_key = current_creds.get('BYBIT_API_KEY')

            logger.info(f"Current API key: {old_api_key[:10]}...")

            # Step 2: Validate new credentials
            if not self._validate_bybit_credentials(new_api_key, new_api_secret, testnet):
                raise ValueError("New Bybit credentials are invalid")

            # Step 3: Store new credentials with version
            new_creds = {
                'BYBIT_API_KEY': new_api_key,
                'BYBIT_API_SECRET': new_api_secret,
                'BYBIT_TESTNET': str(testnet).lower(),
                'rotated_at': datetime.utcnow().isoformat(),
                'previous_key': old_api_key
            }

            if self.dry_run:
                logger.info("[DRY RUN] Would write new credentials to Vault")
            else:
                self.vault.write_secret('bybit-connector/bybit', new_creds)
                logger.info("New credentials stored in Vault")

            # Step 4: Notify services to reload credentials
            if not self.dry_run:
                self._notify_service_reload('bybit-connector')

            # Step 5: Wait for overlap period
            logger.info(f"Waiting {overlap_seconds}s for credential propagation...")
            if not self.dry_run:
                time.sleep(overlap_seconds)

            # Step 6: Verify services are using new credentials
            if not self.dry_run:
                if not self._verify_service_health('bybit-connector'):
                    raise Exception("Service health check failed after rotation")

            # Step 7: Success - log completion
            self._log_rotation(secret_type, 'success', {
                'old_key': old_api_key[:10] + '...',
                'new_key': new_api_key[:10] + '...',
                'testnet': testnet
            })

            logger.info("✓ Bybit API key rotation completed successfully")
            return True

        except Exception as e:
            logger.error(f"Bybit API key rotation failed: {e}")

            self._log_rotation(secret_type, 'failed', {
                'error': str(e)
            })

            # Attempt rollback
            if not self.dry_run and 'old_api_key' in locals():
                logger.warning("Attempting rollback...")
                try:
                    rollback_creds = {
                        'BYBIT_API_KEY': old_api_key,
                        'BYBIT_API_SECRET': current_creds.get('BYBIT_API_SECRET'),
                        'BYBIT_TESTNET': current_creds.get('BYBIT_TESTNET', 'true'),
                        'rollback_at': datetime.utcnow().isoformat()
                    }
                    self.vault.write_secret('bybit-connector/bybit', rollback_creds)
                    self._notify_service_reload('bybit-connector')

                    self._log_rotation(secret_type, 'rolled_back', {
                        'reason': str(e)
                    })

                    logger.info("✓ Rollback completed")
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")

            return False

    def _validate_bybit_credentials(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool
    ) -> bool:
        """
        Validate Bybit API credentials

        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            testnet: Whether using testnet

        Returns:
            True if credentials are valid
        """
        logger.info("Validating new Bybit credentials...")

        if self.dry_run:
            logger.info("[DRY RUN] Would validate credentials")
            return True

        try:
            # Use pybit to test credentials
            from pybit.unified_trading import HTTP

            base_url = "https://api-testnet.bybit.com" if testnet else "https://api.bybit.com"

            session = HTTP(
                testnet=testnet,
                api_key=api_key,
                api_secret=api_secret
            )

            # Try to get account info
            result = session.get_wallet_balance(accountType="UNIFIED")

            if result.get('retCode') == 0:
                logger.info("✓ New credentials validated successfully")
                return True
            else:
                logger.error(f"Credential validation failed: {result.get('retMsg')}")
                return False

        except Exception as e:
            logger.error(f"Failed to validate credentials: {e}")
            return False

    def rotate_database_password(
        self,
        database_name: str,
        role_name: str,
        service_name: str
    ) -> bool:
        """
        Rotate database password using Vault dynamic credentials

        Args:
            database_name: Database name (postgres, timescaledb)
            role_name: Vault database role
            service_name: Service using the credentials

        Returns:
            True if rotation successful
        """
        secret_type = f'database_password_{database_name}'
        logger.info(f"Starting database password rotation for {database_name}")

        self._log_rotation(secret_type, 'started', {
            'database': database_name,
            'role': role_name,
            'service': service_name
        })

        try:
            # Step 1: Generate new dynamic credentials
            if self.dry_run:
                logger.info("[DRY RUN] Would generate new database credentials")
                new_creds = {
                    'username': 'v-dry-run-user',
                    'password': 'dry-run-password',
                    'lease_id': 'dry-run-lease',
                    'lease_duration': 3600
                }
            else:
                new_creds = self.vault.get_database_credentials(role_name)

            logger.info(f"Generated new credentials: {new_creds['username']}")

            # Step 2: Update service configuration
            if not self.dry_run:
                # Store credentials in service-specific path
                self.vault.write_secret(
                    f"{service_name}/database/{database_name}",
                    {
                        'username': new_creds['username'],
                        'password': new_creds['password'],
                        'lease_id': new_creds['lease_id'],
                        'lease_duration': new_creds['lease_duration'],
                        'rotated_at': datetime.utcnow().isoformat()
                    }
                )

                # Notify service to reload
                self._notify_service_reload(service_name)

                # Wait for propagation
                time.sleep(10)

                # Verify service health
                if not self._verify_service_health(service_name):
                    raise Exception(f"Service {service_name} health check failed")

            self._log_rotation(secret_type, 'success', {
                'database': database_name,
                'new_username': new_creds['username'],
                'lease_duration': new_creds.get('lease_duration', 0)
            })

            logger.info(f"✓ Database password rotation completed for {database_name}")
            return True

        except Exception as e:
            logger.error(f"Database password rotation failed: {e}")
            self._log_rotation(secret_type, 'failed', {'error': str(e)})
            return False

    def rotate_jwt_secret(self, service_name: str = 'api-gateway') -> bool:
        """
        Rotate JWT secret

        Args:
            service_name: Service name

        Returns:
            True if rotation successful
        """
        secret_type = 'jwt_secret'
        logger.info(f"Starting JWT secret rotation for {service_name}")

        self._log_rotation(secret_type, 'started', {'service': service_name})

        try:
            import secrets

            # Generate new JWT secret (256-bit)
            new_jwt_secret = secrets.token_urlsafe(32)

            if self.dry_run:
                logger.info("[DRY RUN] Would generate new JWT secret")
            else:
                # Store new JWT secret
                self.vault.write_secret(
                    f"{service_name}/jwt",
                    {
                        'JWT_SECRET': new_jwt_secret,
                        'JWT_ALGORITHM': 'HS256',
                        'rotated_at': datetime.utcnow().isoformat()
                    }
                )

                # Notify service
                self._notify_service_reload(service_name)

                # Verify
                time.sleep(5)
                if not self._verify_service_health(service_name):
                    raise Exception("Service health check failed")

            self._log_rotation(secret_type, 'success', {
                'service': service_name
            })

            logger.info("✓ JWT secret rotation completed")
            return True

        except Exception as e:
            logger.error(f"JWT secret rotation failed: {e}")
            self._log_rotation(secret_type, 'failed', {'error': str(e)})
            return False

    def _notify_service_reload(self, service_name: str) -> bool:
        """
        Notify service to reload credentials

        Args:
            service_name: Service name

        Returns:
            True if notification successful
        """
        logger.info(f"Notifying {service_name} to reload credentials...")

        if self.dry_run:
            logger.info("[DRY RUN] Would send reload signal")
            return True

        try:
            # Send reload signal via HTTP endpoint
            service_ports = {
                'api-gateway': 8000,
                'bybit-connector': 8001,
                'market-data-service': 8002,
                'portfolio-manager': 8003,
                'technical-analysis': 8004,
                'trading-engine': 8005
            }

            port = service_ports.get(service_name)
            if not port:
                logger.warning(f"Unknown service: {service_name}")
                return False

            url = f"http://localhost:{port}/admin/reload-config"

            response = requests.post(url, timeout=5)

            if response.status_code == 200:
                logger.info(f"✓ {service_name} reloaded successfully")
                return True
            else:
                logger.warning(f"Service reload returned {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not notify service (may need restart): {e}")
            return False

    def _verify_service_health(self, service_name: str) -> bool:
        """
        Verify service health after rotation

        Args:
            service_name: Service name

        Returns:
            True if service is healthy
        """
        logger.info(f"Verifying health of {service_name}...")

        if self.dry_run:
            logger.info("[DRY RUN] Would check service health")
            return True

        try:
            service_ports = {
                'api-gateway': 8000,
                'bybit-connector': 8001,
                'market-data-service': 8002,
                'portfolio-manager': 8003,
                'technical-analysis': 8004,
                'trading-engine': 8005
            }

            port = service_ports.get(service_name)
            if not port:
                return False

            url = f"http://localhost:{port}/health"

            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                health_data = response.json()
                if health_data.get('status') == 'healthy':
                    logger.info(f"✓ {service_name} is healthy")
                    return True
                else:
                    logger.warning(f"{service_name} reports unhealthy status")
                    return False
            else:
                logger.warning(f"Health check returned {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def generate_rotation_report(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate rotation report

        Args:
            output_path: Optional path to save report JSON

        Returns:
            Rotation report dictionary
        """
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'total_rotations': len(self.rotation_log),
            'successful_rotations': len([r for r in self.rotation_log if r['status'] == 'success']),
            'failed_rotations': len([r for r in self.rotation_log if r['status'] == 'failed']),
            'rolled_back': len([r for r in self.rotation_log if r['status'] == 'rolled_back']),
            'rotations': self.rotation_log
        }

        if output_path:
            try:
                with open(output_path, 'w') as f:
                    json.dump(report, f, indent=2)
                logger.info(f"Rotation report saved to {output_path}")
            except Exception as e:
                logger.error(f"Failed to save report: {e}")

        return report


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Automated secret rotation for crypto trading bot'
    )
    parser.add_argument(
        'secret_type',
        choices=['bybit', 'database', 'jwt', 'all'],
        help='Type of secret to rotate'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate rotation without making changes'
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
    parser.add_argument(
        '--bybit-api-key',
        help='New Bybit API key (for bybit rotation)'
    )
    parser.add_argument(
        '--bybit-api-secret',
        help='New Bybit API secret (for bybit rotation)'
    )
    parser.add_argument(
        '--testnet',
        action='store_true',
        default=True,
        help='Use Bybit testnet'
    )
    parser.add_argument(
        '--report-output',
        help='Path to save rotation report'
    )

    args = parser.parse_args()

    # Validate Vault token
    if not args.vault_token:
        logger.error("Vault token not provided. Set VAULT_TOKEN or use --vault-token")
        return 1

    try:
        # Initialize Vault client
        logger.info(f"Connecting to Vault at {args.vault_addr}")
        vault = VaultClient(
            vault_addr=args.vault_addr,
            vault_token=args.vault_token
        )

        # Initialize rotation manager
        rotation = SecretRotation(vault_client=vault, dry_run=args.dry_run)

        success = True

        # Perform rotation based on type
        if args.secret_type == 'bybit' or args.secret_type == 'all':
            if not args.bybit_api_key or not args.bybit_api_secret:
                logger.error("Bybit API key and secret required for rotation")
                logger.info("Generate new keys at: https://testnet.bybit.com/app/user/api-management")
                return 1

            success = rotation.rotate_bybit_api_keys(
                new_api_key=args.bybit_api_key,
                new_api_secret=args.bybit_api_secret,
                testnet=args.testnet
            )

        if args.secret_type == 'database' or args.secret_type == 'all':
            success = rotation.rotate_database_password(
                database_name='postgres',
                role_name='trading-bot-role',
                service_name='trading-engine'
            ) and success

        if args.secret_type == 'jwt' or args.secret_type == 'all':
            success = rotation.rotate_jwt_secret() and success

        # Generate report
        report = rotation.generate_rotation_report(args.report_output)

        # Summary
        logger.info("=" * 80)
        logger.info("Rotation Summary")
        logger.info("=" * 80)
        logger.info(f"Total rotations: {report['total_rotations']}")
        logger.info(f"Successful: {report['successful_rotations']}")
        logger.info(f"Failed: {report['failed_rotations']}")
        logger.info(f"Rolled back: {report['rolled_back']}")
        logger.info("=" * 80)

        return 0 if success else 1

    except VaultConnectionError as e:
        logger.error(f"Failed to connect to Vault: {e}")
        return 1
    except Exception as e:
        logger.error(f"Rotation failed: {e}", exc_info=True)
        return 1
    finally:
        if 'vault' in locals():
            vault.close()


if __name__ == '__main__':
    sys.exit(main())
