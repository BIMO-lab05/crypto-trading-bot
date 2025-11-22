#!/usr/bin/env python3
"""
Automated Backup and Restore Testing
Tests backup integrity and restore procedures

Run daily to ensure disaster recovery readiness
"""

import subprocess
import sys
import time
import psycopg2
import redis
import json
from datetime import datetime
from typing import Tuple, Dict, Any
import os

# Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': 'cryptobot_test',  # Use test database
    'user': os.getenv('DB_USER', 'cryptobot'),
    'password': os.getenv('DB_PASSWORD', '')
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', '6379')),
    'db': 1  # Use test DB
}


class BackupRestoreTest:
    """Automated backup and restore testing"""

    def __init__(self):
        self.test_results = []
        self.start_time = time.time()

    def log(self, message: str, level: str = "INFO"):
        """Log test message"""
        timestamp = datetime.now().isoformat()
        print(f"[{timestamp}] [{level}] {message}")

    def record_result(self, test_name: str, passed: bool, details: str = ""):
        """Record test result"""
        self.test_results.append({
            'test': test_name,
            'passed': passed,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })

    def run_command(self, command: str) -> Tuple[bool, str]:
        """Execute shell command"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes max
            )
            return result.returncode == 0, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def test_postgres_backup_create(self) -> bool:
        """Test PostgreSQL backup creation"""
        self.log("Testing PostgreSQL backup creation...")

        success, output = self.run_command(
            "bash scripts/backup/postgres_backup.sh"
        )

        if success:
            self.log("✅ PostgreSQL backup created successfully", "SUCCESS")
            self.record_result("postgres_backup_create", True)
            return True
        else:
            self.log(f"❌ PostgreSQL backup failed: {output}", "ERROR")
            self.record_result("postgres_backup_create", False, output)
            return False

    def test_postgres_backup_integrity(self) -> bool:
        """Test PostgreSQL backup file integrity"""
        self.log("Testing PostgreSQL backup integrity...")

        # Get latest backup
        success, output = self.run_command(
            "ls -t /backups/postgres/cryptobot_*.dump.gz | head -1"
        )

        if not success:
            self.log("❌ No backup file found", "ERROR")
            self.record_result("postgres_backup_integrity", False, "No backup found")
            return False

        backup_file = output.strip()

        # Verify with pg_restore
        success, output = self.run_command(
            f"pg_restore --list {backup_file} > /dev/null 2>&1"
        )

        if success:
            self.log(f"✅ Backup integrity verified: {backup_file}", "SUCCESS")
            self.record_result("postgres_backup_integrity", True)
            return True
        else:
            self.log(f"❌ Backup integrity check failed: {output}", "ERROR")
            self.record_result("postgres_backup_integrity", False, output)
            return False

    def test_postgres_restore(self) -> bool:
        """Test PostgreSQL restore procedure"""
        self.log("Testing PostgreSQL restore procedure...")

        try:
            # Connect to database
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Create test data
            cur.execute("""
                CREATE TABLE IF NOT EXISTS test_restore (
                    id SERIAL PRIMARY KEY,
                    test_data TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute(
                "INSERT INTO test_restore (test_data) VALUES (%s)",
                (f"Test data at {datetime.now()}",)
            )
            conn.commit()

            # Get record count before
            cur.execute("SELECT COUNT(*) FROM test_restore")
            count_before = cur.fetchone()[0]

            cur.close()
            conn.close()

            # Create backup
            self.log("Creating backup...")
            success, _ = self.run_command("bash scripts/backup/postgres_backup.sh")

            if not success:
                self.log("❌ Backup creation failed", "ERROR")
                return False

            # Perform restore in test mode
            self.log("Performing restore...")
            success, output = self.run_command(
                "bash scripts/recovery/restore_postgres.sh --test"
            )

            if not success:
                self.log(f"❌ Restore failed: {output}", "ERROR")
                self.record_result("postgres_restore", False, output)
                return False

            # Verify data after restore
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM test_restore")
            count_after = cur.fetchone()[0]

            cur.close()
            conn.close()

            if count_after >= count_before:
                self.log(f"✅ Restore successful (records: {count_after})", "SUCCESS")
                self.record_result("postgres_restore", True)
                return True
            else:
                self.log(f"❌ Data loss detected (before: {count_before}, after: {count_after})", "ERROR")
                self.record_result("postgres_restore", False, "Data loss detected")
                return False

        except Exception as e:
            self.log(f"❌ Restore test failed: {e}", "ERROR")
            self.record_result("postgres_restore", False, str(e))
            return False

    def test_redis_backup(self) -> bool:
        """Test Redis backup and restore"""
        self.log("Testing Redis backup...")

        try:
            # Connect to Redis
            r = redis.Redis(**REDIS_CONFIG)

            # Create test data
            test_key = f"test:backup:{int(time.time())}"
            test_value = f"Test value at {datetime.now()}"
            r.set(test_key, test_value)

            # Trigger backup
            success, output = self.run_command("bash scripts/backup/redis_backup.sh")

            if not success:
                self.log(f"❌ Redis backup failed: {output}", "ERROR")
                self.record_result("redis_backup", False, output)
                return False

            # Verify backup file exists
            success, output = self.run_command(
                "ls -t /backups/redis/dump_*.rdb.gz | head -1"
            )

            if success and output.strip():
                self.log(f"✅ Redis backup created: {output.strip()}", "SUCCESS")
                self.record_result("redis_backup", True)
                return True
            else:
                self.log("❌ Redis backup file not found", "ERROR")
                self.record_result("redis_backup", False, "File not found")
                return False

        except Exception as e:
            self.log(f"❌ Redis backup test failed: {e}", "ERROR")
            self.record_result("redis_backup", False, str(e))
            return False

    def test_backup_retention(self) -> bool:
        """Test backup retention policy"""
        self.log("Testing backup retention policy...")

        # Check number of PostgreSQL backups
        success, output = self.run_command(
            "ls -1 /backups/postgres/cryptobot_*.dump.gz | wc -l"
        )

        if success:
            count = int(output.strip())
            if count > 0 and count <= 30:  # Should keep max 30 days
                self.log(f"✅ Backup retention OK ({count} backups)", "SUCCESS")
                self.record_result("backup_retention", True)
                return True
            elif count > 30:
                self.log(f"⚠️ Too many backups ({count}), cleanup may have failed", "WARNING")
                self.record_result("backup_retention", False, "Too many backups")
                return False
            else:
                self.log("⚠️ No backups found", "WARNING")
                self.record_result("backup_retention", False, "No backups")
                return False
        else:
            self.log(f"❌ Failed to check backups: {output}", "ERROR")
            self.record_result("backup_retention", False, output)
            return False

    def test_backup_monitoring(self) -> bool:
        """Test backup monitoring and alerts"""
        self.log("Testing backup monitoring...")

        # Check if backup log exists
        if os.path.exists("/var/log/backups.log"):
            # Read last line
            with open("/var/log/backups.log", "r") as f:
                lines = f.readlines()
                if lines:
                    last_backup = lines[-1]
                    self.log(f"Last backup log: {last_backup.strip()}", "INFO")
                    self.record_result("backup_monitoring", True)
                    return True

        self.log("⚠️ Backup log not found or empty", "WARNING")
        self.record_result("backup_monitoring", False, "Log not found")
        return False

    def generate_report(self):
        """Generate test report"""
        duration = time.time() - self.start_time

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['passed'])
        failed_tests = total_tests - passed_tests

        print("\n" + "=" * 70)
        print("BACKUP & RESTORE TEST REPORT")
        print("=" * 70)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests} ✅")
        print(f"Failed: {failed_tests} ❌")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")
        print(f"Duration: {duration:.2f} seconds")
        print("=" * 70)

        print("\nDetailed Results:")
        for result in self.test_results:
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            print(f"{status} - {result['test']}")
            if result['details']:
                print(f"       Details: {result['details'][:100]}")

        print("=" * 70)

        # Save report to file
        report_file = f"/var/log/backup_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump({
                'summary': {
                    'total': total_tests,
                    'passed': passed_tests,
                    'failed': failed_tests,
                    'success_rate': passed_tests / total_tests * 100,
                    'duration': duration
                },
                'results': self.test_results
            }, f, indent=2)

        print(f"\nReport saved to: {report_file}")

        return failed_tests == 0

    def run_all_tests(self):
        """Run all backup/restore tests"""
        self.log("Starting Backup & Restore Test Suite...")

        tests = [
            self.test_postgres_backup_create,
            self.test_postgres_backup_integrity,
            self.test_postgres_restore,
            self.test_redis_backup,
            self.test_backup_retention,
            self.test_backup_monitoring
        ]

        for test in tests:
            try:
                test()
            except Exception as e:
                self.log(f"❌ Test failed with exception: {e}", "ERROR")
                self.record_result(test.__name__, False, str(e))

        success = self.generate_report()

        if success:
            self.log("✅ All tests passed!", "SUCCESS")
            return 0
        else:
            self.log("❌ Some tests failed!", "ERROR")
            return 1


def main():
    """Main entry point"""
    tester = BackupRestoreTest()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
