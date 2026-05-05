---
type: decision
status: accepted
date: 2026-05-03
context: "bcrypt 5.0 + libpass 1.9.3 incompatibility on >72-byte passwords"
deciders: []
tags: [decision, adr, security, auth]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-003: switch to bcrypt_sha256 prehash for password hashing

## Context

PR #77 (`fix/api-gateway-py314-deps`) bumps `bcrypt` to 5.0 + `libpass` to 1.9.3. New stack raises `ValueError` on inputs >72 bytes (bcrypt's hard limit), so `/auth/login` would return 500 instead of 401 once the cp314 migration lands.

main currently uses `passlib 1.7.4 + bcrypt 4.1.2` which silently truncates >72-byte input — not affected, but the silent truncation is also bad behavior.

## Decision

Switch `CryptContext` scheme to `bcrypt_sha256`:
- SHA-256 prehash sidesteps the 72-byte limit
- `verify_password` wrapped in `try/except ValueError → False` (preserves constant-time auth contract)
- `UserLogin.password` bounded `max_length=200` (was unbounded)

## Commits

`6cd9bf6` (on PR branch — only matters once py3.14 PR rebases and merges)

## Tests

Cover >72-byte roundtrip + malformed-hash path.

## Consequences

- Stronger guarantee: long passwords don't 500 OR get silently truncated
- Migration: existing bcrypt hashes need re-hash on next login (passlib handles transparently)

## Related

- [[../modules/api-gateway]]
