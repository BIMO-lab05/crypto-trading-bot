#!/usr/bin/env python3
"""
Test runner for Statistical Arbitrage testing suite
Provides convenient commands for running tests with various configurations
"""

import sys
import subprocess
from pathlib import Path
from typing import List, Optional


class TestRunner:
    """Convenient test runner for Statistical Arbitrage tests"""

    def __init__(self):
        """Initialize test runner with project paths"""
        self.project_root = Path(__file__).parent.parent
        self.tests_dir = self.project_root / "tests"

    def run_command(self, cmd: List[str]) -> int:
        """
        Run a shell command and return exit code

        Args:
            cmd: Command and arguments as list

        Returns:
            Exit code from command
        """
        print(f"\n{'='*80}")
        print(f"Running: {' '.join(cmd)}")
        print(f"{'='*80}\n")

        result = subprocess.run(cmd, cwd=self.project_root)
        return result.returncode

    def run_all_tests(self, verbose: bool = True) -> int:
        """
        Run all tests with coverage

        Args:
            verbose: Show verbose output

        Returns:
            Exit code
        """
        cmd = ["pytest"]
        if verbose:
            cmd.append("-v")

        return self.run_command(cmd)

    def run_unit_tests(self, verbose: bool = True) -> int:
        """
        Run only unit tests

        Args:
            verbose: Show verbose output

        Returns:
            Exit code
        """
        cmd = ["pytest", "tests/unit/"]
        if verbose:
            cmd.append("-v")

        return self.run_command(cmd)

    def run_integration_tests(self, verbose: bool = True) -> int:
        """
        Run only integration tests

        Args:
            verbose: Show verbose output

        Returns:
            Exit code
        """
        cmd = ["pytest", "tests/integration/"]
        if verbose:
            cmd.append("-v")

        return self.run_command(cmd)

    def run_with_coverage(self, html: bool = True) -> int:
        """
        Run tests with coverage report

        Args:
            html: Generate HTML coverage report

        Returns:
            Exit code
        """
        cmd = [
            "pytest",
            "--cov=app",
            "--cov-report=term-missing"
        ]

        if html:
            cmd.append("--cov-report=html")

        return self.run_command(cmd)

    def run_specific_file(self, file_path: str, verbose: bool = True) -> int:
        """
        Run tests in a specific file

        Args:
            file_path: Path to test file
            verbose: Show verbose output

        Returns:
            Exit code
        """
        cmd = ["pytest", file_path]
        if verbose:
            cmd.append("-v")

        return self.run_command(cmd)

    def run_specific_test(self, test_path: str) -> int:
        """
        Run a specific test

        Args:
            test_path: Path to specific test (file::Class::method)

        Returns:
            Exit code
        """
        cmd = ["pytest", test_path, "-v"]
        return self.run_command(cmd)

    def run_by_marker(self, marker: str, verbose: bool = True) -> int:
        """
        Run tests with a specific marker

        Args:
            marker: Pytest marker (unit, integration, stat_arb, validation)
            verbose: Show verbose output

        Returns:
            Exit code
        """
        cmd = ["pytest", "-m", marker]
        if verbose:
            cmd.append("-v")

        return self.run_command(cmd)

    def run_failed_first(self) -> int:
        """
        Run previously failed tests first

        Returns:
            Exit code
        """
        cmd = ["pytest", "--failed-first", "-v"]
        return self.run_command(cmd)

    def run_parallel(self, num_workers: int = 8) -> int:
        """
        Run tests in parallel

        Args:
            num_workers: Number of parallel workers

        Returns:
            Exit code
        """
        cmd = ["pytest", "-n", str(num_workers), "-v"]
        return self.run_command(cmd)

    def show_duration(self, num_slowest: int = 10) -> int:
        """
        Run tests and show slowest tests

        Args:
            num_slowest: Number of slowest tests to show

        Returns:
            Exit code
        """
        cmd = ["pytest", f"--durations={num_slowest}", "-v"]
        return self.run_command(cmd)

    def run_validation_tests(self) -> int:
        """
        Run only validation tests

        Returns:
            Exit code
        """
        return self.run_by_marker("validation")

    def run_stat_arb_tests(self) -> int:
        """
        Run only Statistical Arbitrage tests

        Returns:
            Exit code
        """
        return self.run_by_marker("stat_arb")

    def quick_check(self) -> int:
        """
        Quick test run (failed tests + unit tests)

        Returns:
            Exit code
        """
        print("\n" + "="*80)
        print("QUICK CHECK: Running failed tests first, then unit tests")
        print("="*80 + "\n")

        # Run failed tests first
        result = self.run_failed_first()

        # If failed tests passed, run unit tests
        if result == 0:
            result = self.run_unit_tests()

        return result

    def full_suite(self) -> int:
        """
        Full test suite with coverage

        Returns:
            Exit code
        """
        print("\n" + "="*80)
        print("FULL SUITE: All tests with coverage report")
        print("="*80 + "\n")

        return self.run_with_coverage(html=True)


def print_usage():
    """Print usage information"""
    usage = """
Statistical Arbitrage Test Runner
==================================

Usage: python scripts/run_stat_arb_tests.py [command]

Commands:
  all                 Run all tests with coverage (default)
  unit                Run only unit tests
  integration         Run only integration tests
  coverage            Run tests with HTML coverage report
  quick               Quick check (failed + unit tests)
  full                Full suite with coverage

  marker <name>       Run tests with specific marker
                      Markers: unit, integration, stat_arb, validation

  file <path>         Run specific test file
  test <path>         Run specific test (file::Class::method)

  failed              Run previously failed tests first
  parallel [n]        Run tests in parallel (default: 8 workers)
  duration [n]        Show N slowest tests (default: 10)

Examples:
  python scripts/run_stat_arb_tests.py all
  python scripts/run_stat_arb_tests.py unit
  python scripts/run_stat_arb_tests.py marker validation
  python scripts/run_stat_arb_tests.py file tests/unit/test_stat_arb_models.py
  python scripts/run_stat_arb_tests.py test tests/unit/test_stat_arb_models.py::TestInitializeManagerRequest::test_valid_initialization
  python scripts/run_stat_arb_tests.py parallel 4
  python scripts/run_stat_arb_tests.py duration 5

Quick Commands:
  python scripts/run_stat_arb_tests.py quick      # Fast feedback loop
  python scripts/run_stat_arb_tests.py full       # Complete validation
"""
    print(usage)


def main():
    """Main entry point"""
    runner = TestRunner()

    # Parse command line arguments
    if len(sys.argv) < 2:
        # Default: run all tests
        sys.exit(runner.run_all_tests())

    command = sys.argv[1].lower()

    # Command routing
    if command in ["help", "-h", "--help"]:
        print_usage()
        sys.exit(0)

    elif command == "all":
        sys.exit(runner.run_all_tests())

    elif command == "unit":
        sys.exit(runner.run_unit_tests())

    elif command == "integration":
        sys.exit(runner.run_integration_tests())

    elif command == "coverage":
        sys.exit(runner.run_with_coverage(html=True))

    elif command == "quick":
        sys.exit(runner.quick_check())

    elif command == "full":
        sys.exit(runner.full_suite())

    elif command == "marker":
        if len(sys.argv) < 3:
            print("Error: marker name required")
            print("Available markers: unit, integration, stat_arb, validation")
            sys.exit(1)
        marker = sys.argv[2]
        sys.exit(runner.run_by_marker(marker))

    elif command == "file":
        if len(sys.argv) < 3:
            print("Error: file path required")
            sys.exit(1)
        file_path = sys.argv[2]
        sys.exit(runner.run_specific_file(file_path))

    elif command == "test":
        if len(sys.argv) < 3:
            print("Error: test path required (file::Class::method)")
            sys.exit(1)
        test_path = sys.argv[2]
        sys.exit(runner.run_specific_test(test_path))

    elif command == "failed":
        sys.exit(runner.run_failed_first())

    elif command == "parallel":
        num_workers = 8
        if len(sys.argv) >= 3:
            try:
                num_workers = int(sys.argv[2])
            except ValueError:
                print(f"Error: invalid number of workers: {sys.argv[2]}")
                sys.exit(1)
        sys.exit(runner.run_parallel(num_workers))

    elif command == "duration":
        num_slowest = 10
        if len(sys.argv) >= 3:
            try:
                num_slowest = int(sys.argv[2])
            except ValueError:
                print(f"Error: invalid number: {sys.argv[2]}")
                sys.exit(1)
        sys.exit(runner.show_duration(num_slowest))

    elif command == "validation":
        sys.exit(runner.run_validation_tests())

    elif command == "stat_arb":
        sys.exit(runner.run_stat_arb_tests())

    else:
        print(f"Error: unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
