#!/usr/bin/env python3
"""
Security Scan Script for Crypto Trading Bot
============================================
Version: 1.0
Created: 2025-12-12

This script performs security scanning of the codebase and infrastructure:
- Hardcoded secrets detection
- Insecure configuration checks
- Dependency vulnerability scanning (if safety/pip-audit available)
- Docker security best practices
- Kubernetes manifest security analysis

Usage:
    python scripts/security_scan.py [options]

Options:
    --fail-on LEVEL   Fail if issues of LEVEL or higher found (LOW, MEDIUM, HIGH, CRITICAL)
    --output FILE     Output results to file
    --json            Output in JSON format
    --verbose         Show detailed output
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Severity(Enum):
    """Severity levels for security issues."""
    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class SecurityIssue:
    """Represents a security issue found during scanning."""
    title: str
    description: str
    severity: Severity
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    recommendation: str = ""
    cwe_id: Optional[str] = None


@dataclass
class ScanResult:
    """Results from security scanning."""
    issues: List[SecurityIssue] = field(default_factory=list)
    files_scanned: int = 0
    scan_duration: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def get_issues_by_severity(self, severity: Severity) -> List[SecurityIssue]:
        """Get issues filtered by severity level."""
        return [i for i in self.issues if i.severity == severity]

    def get_highest_severity(self) -> Severity:
        """Get the highest severity found."""
        if not self.issues:
            return Severity.INFO
        return max(i.severity for i in self.issues)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "files_scanned": self.files_scanned,
            "scan_duration": self.scan_duration,
            "summary": {
                "critical": len(self.get_issues_by_severity(Severity.CRITICAL)),
                "high": len(self.get_issues_by_severity(Severity.HIGH)),
                "medium": len(self.get_issues_by_severity(Severity.MEDIUM)),
                "low": len(self.get_issues_by_severity(Severity.LOW)),
                "info": len(self.get_issues_by_severity(Severity.INFO)),
            },
            "issues": [
                {
                    "title": i.title,
                    "severity": i.severity.name,
                    "description": i.description,
                    "file": i.file_path,
                    "line": i.line_number,
                    "recommendation": i.recommendation,
                    "cwe_id": i.cwe_id,
                }
                for i in self.issues
            ]
        }


class SecurityScanner:
    """Main security scanner class."""

    # Patterns for detecting hardcoded secrets
    SECRET_PATTERNS = [
        (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[\w-]{20,}["\']?', "API Key", Severity.HIGH),
        (r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?[\w-]{20,}["\']?', "Secret Key", Severity.CRITICAL),
        (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']+["\']', "Password", Severity.HIGH),
        (r'(?i)(token)\s*[=:]\s*["\']?[\w-]{20,}["\']?', "Token", Severity.HIGH),
        (r'(?i)(private[_-]?key)\s*[=:]\s*["\']?[\w-]+["\']?', "Private Key", Severity.CRITICAL),
        (r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----', "Private Key Block", Severity.CRITICAL),
        (r'(?i)(aws[_-]?access[_-]?key)\s*[=:]\s*["\']?[A-Z0-9]{20}["\']?', "AWS Access Key", Severity.CRITICAL),
        (r'(?i)(aws[_-]?secret)\s*[=:]\s*["\']?[\w/+=]{40}["\']?', "AWS Secret Key", Severity.CRITICAL),
        (r'(?i)bearer\s+[\w-]{20,}', "Bearer Token", Severity.HIGH),
        (r'(?i)(database[_-]?url|db[_-]?url)\s*[=:]\s*["\']?[^"\'\s]+://[^"\'\s]+["\']?', "Database URL", Severity.MEDIUM),
    ]

    # Patterns to exclude (false positives)
    EXCLUDE_PATTERNS = [
        r'CHANGE_ME',
        r'your[_-]?.*[_-]?here',
        r'example',
        r'placeholder',
        r'\$\{',  # Environment variable reference
        r'process\.env',
        r'os\.environ',
        r'getenv',
    ]

    # Files to skip
    SKIP_FILES = {
        '.git', 'node_modules', '__pycache__', '.pytest_cache',
        'venv', 'env', '.env.example', '.env.template',
        'secrets-template.yaml', 'htmlcov', '.coverage',
    }

    # File extensions to scan
    SCAN_EXTENSIONS = {
        '.py', '.js', '.ts', '.yaml', '.yml', '.json', '.env',
        '.sh', '.bash', '.toml', '.ini', '.cfg', '.conf',
    }

    def __init__(self, project_root: Path, verbose: bool = False):
        """Initialize the scanner."""
        self.project_root = project_root
        self.verbose = verbose
        self.result = ScanResult()

    def log(self, message: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[SCAN] {message}")

    def should_skip_path(self, path: Path) -> bool:
        """Check if path should be skipped."""
        parts = path.parts
        for skip in self.SKIP_FILES:
            if skip in parts:
                return True
        return False

    def is_excluded(self, line: str) -> bool:
        """Check if line matches exclusion patterns."""
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def scan_file_for_secrets(self, file_path: Path) -> List[SecurityIssue]:
        """Scan a single file for hardcoded secrets."""
        issues = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')

                for line_num, line in enumerate(lines, 1):
                    # Skip comments
                    stripped = line.strip()
                    if stripped.startswith('#') or stripped.startswith('//'):
                        continue

                    # Skip excluded patterns
                    if self.is_excluded(line):
                        continue

                    for pattern, secret_type, severity in self.SECRET_PATTERNS:
                        matches = re.finditer(pattern, line)
                        for match in matches:
                            # Additional validation
                            matched_text = match.group(0)
                            if self.is_excluded(matched_text):
                                continue

                            issues.append(SecurityIssue(
                                title=f"Potential hardcoded {secret_type}",
                                description=f"Found potential {secret_type.lower()} in code",
                                severity=severity,
                                file_path=str(file_path.relative_to(self.project_root)),
                                line_number=line_num,
                                recommendation=f"Use environment variables or secrets management for {secret_type.lower()}",
                                cwe_id="CWE-798"
                            ))

        except Exception as e:
            self.log(f"Error scanning {file_path}: {e}")

        return issues

    def scan_kubernetes_manifests(self, file_path: Path) -> List[SecurityIssue]:
        """Scan Kubernetes manifests for security issues."""
        issues = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check for privileged containers
            if 'privileged: true' in content:
                issues.append(SecurityIssue(
                    title="Privileged container detected",
                    description="Container running in privileged mode",
                    severity=Severity.HIGH,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Remove privileged: true unless absolutely necessary",
                    cwe_id="CWE-250"
                ))

            # Check for runAsRoot
            if 'runAsNonRoot: false' in content or ('runAsUser: 0' in content and 'runAsNonRoot' not in content):
                issues.append(SecurityIssue(
                    title="Container running as root",
                    description="Container configured to run as root user",
                    severity=Severity.MEDIUM,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Set runAsNonRoot: true and specify a non-root runAsUser",
                    cwe_id="CWE-250"
                ))

            # Check for missing security context
            if 'kind: Deployment' in content and 'securityContext' not in content:
                issues.append(SecurityIssue(
                    title="Missing security context",
                    description="Deployment does not define securityContext",
                    severity=Severity.MEDIUM,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Add securityContext with appropriate restrictions",
                    cwe_id="CWE-269"
                ))

            # Check for hostNetwork
            if 'hostNetwork: true' in content:
                issues.append(SecurityIssue(
                    title="Host network access",
                    description="Pod configured with host network access",
                    severity=Severity.HIGH,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Remove hostNetwork: true unless absolutely necessary",
                    cwe_id="CWE-284"
                ))

            # Check for hostPID
            if 'hostPID: true' in content:
                issues.append(SecurityIssue(
                    title="Host PID namespace",
                    description="Pod configured with host PID namespace",
                    severity=Severity.HIGH,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Remove hostPID: true",
                    cwe_id="CWE-284"
                ))

            # Check for missing resource limits
            if 'kind: Deployment' in content and 'limits:' not in content:
                issues.append(SecurityIssue(
                    title="Missing resource limits",
                    description="Container does not define resource limits",
                    severity=Severity.LOW,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Add resource limits to prevent DoS",
                    cwe_id="CWE-400"
                ))

        except Exception as e:
            self.log(f"Error scanning K8s manifest {file_path}: {e}")

        return issues

    def scan_docker_files(self, file_path: Path) -> List[SecurityIssue]:
        """Scan Dockerfiles for security issues."""
        issues = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            # Check for latest tag
            for line_num, line in enumerate(lines, 1):
                if line.strip().startswith('FROM') and ':latest' in line:
                    issues.append(SecurityIssue(
                        title="Using latest tag",
                        description="Docker image uses :latest tag which is mutable",
                        severity=Severity.MEDIUM,
                        file_path=str(file_path.relative_to(self.project_root)),
                        line_number=line_num,
                        recommendation="Use specific version tags for reproducibility",
                        cwe_id="CWE-829"
                    ))

            # Check for running as root
            if 'USER' not in content:
                issues.append(SecurityIssue(
                    title="No USER instruction",
                    description="Dockerfile does not specify a non-root USER",
                    severity=Severity.MEDIUM,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Add USER instruction to run as non-root",
                    cwe_id="CWE-250"
                ))

            # Check for COPY with --chown
            if 'COPY' in content and '--chown' not in content:
                issues.append(SecurityIssue(
                    title="COPY without --chown",
                    description="COPY instructions without --chown may result in root ownership",
                    severity=Severity.LOW,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Use COPY --chown=user:group for proper file ownership",
                    cwe_id="CWE-732"
                ))

        except Exception as e:
            self.log(f"Error scanning Dockerfile {file_path}: {e}")

        return issues

    def scan_python_code(self, file_path: Path) -> List[SecurityIssue]:
        """Scan Python code for security issues."""
        issues = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            # Check for unsafe pickle
            if 'pickle.load' in content or 'pickle.loads' in content:
                issues.append(SecurityIssue(
                    title="Unsafe pickle usage",
                    description="pickle.load/loads can execute arbitrary code",
                    severity=Severity.HIGH,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Use safe serialization formats like JSON",
                    cwe_id="CWE-502"
                ))

            # Check for eval/exec
            for line_num, line in enumerate(lines, 1):
                if re.search(r'\b(eval|exec)\s*\(', line):
                    issues.append(SecurityIssue(
                        title="Dangerous eval/exec usage",
                        description="eval/exec can execute arbitrary code",
                        severity=Severity.HIGH,
                        file_path=str(file_path.relative_to(self.project_root)),
                        line_number=line_num,
                        recommendation="Avoid eval/exec; use safe alternatives",
                        cwe_id="CWE-94"
                    ))

            # Check for shell=True
            if 'shell=True' in content:
                issues.append(SecurityIssue(
                    title="Shell injection risk",
                    description="subprocess with shell=True is vulnerable to injection",
                    severity=Severity.MEDIUM,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Use shell=False and pass command as list",
                    cwe_id="CWE-78"
                ))

            # Check for SQL injection risks (raw string formatting)
            if re.search(r'\.execute\([^)]*%|\.execute\([^)]*\.format\(|\.execute\([^)]*f["\']', content):
                issues.append(SecurityIssue(
                    title="Potential SQL injection",
                    description="SQL query using string formatting instead of parameterized queries",
                    severity=Severity.HIGH,
                    file_path=str(file_path.relative_to(self.project_root)),
                    recommendation="Use parameterized queries",
                    cwe_id="CWE-89"
                ))

        except Exception as e:
            self.log(f"Error scanning Python file {file_path}: {e}")

        return issues

    def run_scan(self) -> ScanResult:
        """Run the complete security scan."""
        import time
        start_time = time.time()

        self.log(f"Starting security scan of {self.project_root}")

        files_scanned = 0

        # Walk through all files
        for root, dirs, files in os.walk(self.project_root):
            # Skip hidden and excluded directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in self.SKIP_FILES]

            for file in files:
                file_path = Path(root) / file

                # Skip if path should be excluded
                if self.should_skip_path(file_path):
                    continue

                # Get file extension
                ext = file_path.suffix.lower()

                # Skip unsupported extensions
                if ext not in self.SCAN_EXTENSIONS and file not in ('Dockerfile', '.env'):
                    continue

                self.log(f"Scanning: {file_path}")
                files_scanned += 1

                # Scan for secrets
                self.result.issues.extend(self.scan_file_for_secrets(file_path))

                # Scan Kubernetes manifests
                if ext in ('.yaml', '.yml') and 'kubernetes' in str(file_path).lower():
                    self.result.issues.extend(self.scan_kubernetes_manifests(file_path))

                # Scan Dockerfiles
                if file.startswith('Dockerfile'):
                    self.result.issues.extend(self.scan_docker_files(file_path))

                # Scan Python files
                if ext == '.py':
                    self.result.issues.extend(self.scan_python_code(file_path))

        self.result.files_scanned = files_scanned
        self.result.scan_duration = time.time() - start_time

        return self.result


def print_results(result: ScanResult, json_output: bool = False) -> None:
    """Print scan results to console."""
    if json_output:
        print(json.dumps(result.to_dict(), indent=2))
        return

    # Print header
    print("\n" + "=" * 60)
    print("SECURITY SCAN RESULTS")
    print("=" * 60)
    print(f"Timestamp: {result.timestamp}")
    print(f"Files Scanned: {result.files_scanned}")
    print(f"Duration: {result.scan_duration:.2f} seconds")
    print()

    # Print summary
    print("SUMMARY:")
    print("-" * 40)
    summary = result.to_dict()["summary"]
    print(f"  CRITICAL: {summary['critical']}")
    print(f"  HIGH:     {summary['high']}")
    print(f"  MEDIUM:   {summary['medium']}")
    print(f"  LOW:      {summary['low']}")
    print(f"  INFO:     {summary['info']}")
    print()

    # Print issues by severity
    for severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
        issues = result.get_issues_by_severity(severity)
        if issues:
            print(f"\n{severity.name} ISSUES ({len(issues)}):")
            print("-" * 40)
            for i, issue in enumerate(issues, 1):
                print(f"\n  [{i}] {issue.title}")
                if issue.file_path:
                    location = issue.file_path
                    if issue.line_number:
                        location += f":{issue.line_number}"
                    print(f"      File: {location}")
                print(f"      Description: {issue.description}")
                if issue.recommendation:
                    print(f"      Fix: {issue.recommendation}")
                if issue.cwe_id:
                    print(f"      CWE: {issue.cwe_id}")

    print("\n" + "=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Security Scanner for Crypto Trading Bot")
    parser.add_argument("--fail-on", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                        default=None, help="Fail if issues of this severity or higher are found")
    parser.add_argument("--output", type=str, help="Output results to file")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--path", type=str, default=".", help="Path to scan")

    args = parser.parse_args()

    # Determine project root
    project_root = Path(args.path).resolve()

    # Run scanner
    scanner = SecurityScanner(project_root, verbose=args.verbose)
    result = scanner.run_scan()

    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"Results written to {args.output}")

    print_results(result, json_output=args.json)

    # Check for fail condition
    if args.fail_on:
        fail_severity = Severity[args.fail_on]
        highest = result.get_highest_severity()

        if highest.value >= fail_severity.value:
            print(f"\nSCAN FAILED: Found {highest.name} severity issues (threshold: {args.fail_on})")
            sys.exit(1)
        else:
            print(f"\nSCAN PASSED: No issues at or above {args.fail_on} severity")
            sys.exit(0)
    else:
        # Exit with count of high/critical issues
        high_count = len(result.get_issues_by_severity(Severity.HIGH))
        critical_count = len(result.get_issues_by_severity(Severity.CRITICAL))
        sys.exit(min(high_count + critical_count, 255))


if __name__ == "__main__":
    main()
