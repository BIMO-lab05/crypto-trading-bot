# Makefile — minimal ergonomic shortcuts for the crypto-trading-bot stack.
# Phase 2 INFRA-06 / CD-02: scope is intentionally narrow. For full operator workflow,
# see bootstrap.sh, scripts/iter-fix.sh, health_check.sh, and RUNBOOK.md.

.PHONY: build-no-buildkit

# Build a single service with BuildKit off — workaround for WSL2 + Docker Desktop hangs
# (CLAUDE.md § Environment, RUNBOOK.md § BuildKit hang).
# Usage: make build-no-buildkit SVC=<service>
#   e.g. make build-no-buildkit SVC=sentiment-analysis
#
# If SVC is empty, builds all services.
build-no-buildkit:
	DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build $(SVC)
