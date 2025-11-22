# Dependency Management Guide

## Overview

This document describes the automated dependency management strategy for the Trading Engine service, including tools, workflows, and best practices.

## Tools

### 1. Dependabot (Primary)

**Configuration File:** `.github/dependabot.yml`

**Features:**
- Automated weekly dependency updates (Mondays at 09:00)
- Security vulnerability alerts
- Grouped updates by dependency type
- Automatic PR creation
- Integration with GitHub security advisories

**Dependency Groups:**
- **Framework**: fastapi, uvicorn, pydantic
- **Testing**: pytest, coverage, httpx
- **Database**: sqlalchemy, alembic, psycopg2, redis
- **Monitoring**: prometheus-client, opentelemetry

**Update Schedule:**
```yaml
schedule:
  interval: "weekly"
  day: "monday"
  time: "09:00"
```

### 2. Renovate (Alternative)

**Configuration File:** `renovate.json`

**Features:**
- More advanced configuration options
- Better grouping and auto-merge capabilities
- Dependency dashboard
- Digest pinning for Docker images
- Semantic commit messages

**Advantages over Dependabot:**
- Can auto-merge patch updates for testing dependencies
- More granular control over update strategies
- Better support for monorepos
- Configurable stability periods

## Dependency Update Workflow

### Automated Process

1. **Monday Morning (09:00 UTC)**
   - Dependabot/Renovate checks for updates
   - Creates PRs for available updates
   - Groups related dependencies

2. **PR Creation**
   - Each PR includes:
     - Changelog links
     - Release notes
     - Compatibility information
     - CI test results

3. **CI Pipeline**
   - Runs all tests (pytest)
   - Checks code coverage
   - Runs linters (black, flake8, mypy)
   - Validates security (bandit)

4. **Review & Merge**
   - Review PRs manually
   - Check for breaking changes
   - Merge after tests pass

### Manual Update Process

For urgent security updates or major version upgrades:

```bash
# 1. Check for outdated packages
pip list --outdated

# 2. Update specific package
pip install --upgrade <package-name>

# 3. Update requirements.txt
pip freeze > requirements.txt

# 4. Test changes
pytest tests/ --cov=app

# 5. Commit and push
git add requirements.txt
git commit -m "deps: update <package-name> to <version>"
git push
```

## Security Updates

### Priority Levels

**Critical (CVSS 9.0-10.0):**
- Immediate manual review and merge
- Deploy to production within 24 hours
- Notify team via Slack

**High (CVSS 7.0-8.9):**
- Review and merge within 48 hours
- Deploy in next release cycle

**Medium (CVSS 4.0-6.9):**
- Review and merge within 1 week
- Include in regular maintenance window

**Low (CVSS 0.1-3.9):**
- Review and merge within 2 weeks
- Include with other dependency updates

### Security Vulnerability Response

1. **Alert Received**
   - Dependabot creates security advisory PR
   - Team receives notification

2. **Assessment**
   - Review vulnerability details
   - Check if service is affected
   - Determine impact severity

3. **Remediation**
   - Apply patch/update immediately
   - Run full test suite
   - Deploy hotfix if critical

4. **Documentation**
   - Document in CHANGELOG.md
   - Update security audit log
   - Notify stakeholders

## Version Pinning Strategy

### Production Dependencies (requirements.txt)

**Pin exact versions:**
```txt
fastapi==0.109.0
uvicorn==0.27.0
pydantic==2.5.3
```

**Rationale:**
- Ensures reproducible builds
- Prevents unexpected breaking changes
- Allows controlled upgrade testing

### Development Dependencies

**Use compatible release specifiers:**
```txt
pytest>=7.4.0,<8.0.0
black>=24.0.0,<25.0.0
```

**Rationale:**
- Get latest patches and bug fixes
- Maintain compatibility with major version
- Faster access to development tool improvements

## Dependency Review Guidelines

### Before Merging Updates

**Check:**
- [ ] All tests pass
- [ ] No new deprecation warnings
- [ ] Breaking changes are documented
- [ ] Migration guide provided (for major updates)
- [ ] Performance impact assessed
- [ ] Security implications reviewed
- [ ] Changelog reviewed

### Major Version Updates

**Additional Steps:**
1. Review migration guide from maintainers
2. Check breaking changes list
3. Update code to use new APIs
4. Run extended test suite
5. Test in staging environment
6. Update documentation
7. Plan rollout strategy

### Example: FastAPI Major Update

```bash
# 1. Create feature branch
git checkout -b deps/fastapi-major-update

# 2. Update requirements.txt
sed -i 's/fastapi==0.109.0/fastapi==1.0.0/' requirements.txt

# 3. Install new version
pip install -r requirements.txt

# 4. Check deprecation warnings
python -Werror::DeprecationWarning -m pytest tests/

# 5. Update code for breaking changes
# (Review FastAPI 1.0 migration guide)

# 6. Run full test suite
pytest tests/ --cov=app --cov-fail-under=80

# 7. Update documentation
# Update API docs, README, etc.

# 8. Create PR
git add .
git commit -m "deps: update FastAPI to 1.0.0"
git push origin deps/fastapi-major-update
```

## Monitoring Dependency Health

### Metrics to Track

1. **Update Frequency**
   - Weekly update rate
   - Time to merge dependency PRs
   - Number of pending updates

2. **Security**
   - Known vulnerabilities count
   - Time to patch vulnerabilities
   - Security advisory response time

3. **Stability**
   - Failed builds due to dependencies
   - Rollback frequency
   - Post-update bug reports

### Tools

**GitHub Insights:**
- Dependabot alerts dashboard
- Security advisories
- PR merge time statistics

**Python Security Tools:**
```bash
# Check for known vulnerabilities
pip install safety
safety check --json > security-report.json

# Audit dependencies
pip-audit

# Check license compliance
pip-licenses --format=markdown > licenses.md
```

## Best Practices

### DO ✅

- **Review changelogs** before merging updates
- **Test thoroughly** after major updates
- **Keep dependencies up-to-date** (weekly reviews)
- **Monitor security advisories** daily
- **Pin production dependencies** to exact versions
- **Document breaking changes** in CHANGELOG.md
- **Use virtual environments** for isolated testing
- **Run full test suite** before merging
- **Check for deprecation warnings** regularly
- **Update dependencies incrementally** (one at a time for major versions)

### DON'T ❌

- **Auto-merge major version updates** without review
- **Ignore security advisories**
- **Skip testing** after dependency updates
- **Update all dependencies at once** (for major versions)
- **Use outdated dependencies** in production
- **Commit lockfiles** without verifying changes
- **Ignore breaking changes** in changelogs
- **Deploy untested dependency updates** to production
- **Mix dependency updates** with feature changes
- **Use wildcards** (`*`) in production requirements

## Troubleshooting

### Issue: Dependency Conflict

**Symptoms:**
```bash
ERROR: pip's dependency resolver does not currently take into account all the packages that are installed.
```

**Solution:**
```bash
# 1. Check conflict details
pip install pip-tools
pip-compile --verbose requirements.in

# 2. Identify conflicting packages
pipdeptree --warn conflict

# 3. Resolve manually or use compatible versions
pip install <package-a>==<version-a> <package-b>==<version-b>
```

### Issue: Breaking Changes After Update

**Symptoms:**
- Tests fail after dependency update
- Deprecation warnings in logs
- Runtime errors in production

**Solution:**
```bash
# 1. Rollback immediately
git revert <commit-hash>
git push

# 2. Create fix branch
git checkout -b fix/dependency-breaking-change

# 3. Review migration guide
# Check package docs for breaking changes

# 4. Update code
# Fix deprecated API usage

# 5. Test thoroughly
pytest tests/ -v

# 6. Re-apply update
git add .
git commit -m "fix: handle breaking changes from <package> update"
git push
```

### Issue: Security Vulnerability with No Patch

**Symptoms:**
- Security advisory with no fixed version available
- Dependabot can't create PR

**Solution:**
1. **Assess Risk**: Determine if vulnerability affects your usage
2. **Workarounds**: Implement temporary mitigations
3. **Monitor**: Watch for patch release
4. **Consider Alternatives**: Evaluate switching to maintained package
5. **Document**: Add to security risk register

## Related Documentation

- [Testing Guide](../TESTING.md)
- [Security Guidelines](../SECURITY.md)
- [CI/CD Pipeline](../CI_CD.md)
- [Deployment Process](../DEPLOYMENT.md)

## Appendix: Useful Commands

```bash
# Check outdated packages
pip list --outdated

# Show dependency tree
pipdeptree

# Security audit
safety check
pip-audit

# Update all development dependencies
pip install -U pip setuptools wheel
pip install -U -r requirements-dev.txt

# Generate requirements from installed packages
pip freeze > requirements.txt

# Check for unused dependencies
pip-autoremove --list

# Verify requirements.txt integrity
pip check

# Show package information
pip show <package-name>

# List vulnerabilities
safety check --json --output vulnerabilities.json
```

## Version History

| Version | Date       | Changes                              |
|---------|------------|--------------------------------------|
| 1.0     | 2025-11-11 | Initial dependency management guide  |
