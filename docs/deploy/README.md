# Deploy docs

Three deploy options. Pick by cost + complexity.

| Doc | Target | Cost | Complexity |
|---|---|---|---|
| [QUICKSTART.md](QUICKSTART.md) | Oracle Cloud A1, headless trim, 10 steps | $0 | Low |
| [HEADLESS_FREE_DEPLOY.md](HEADLESS_FREE_DEPLOY.md) | Same as quickstart, full reference + ops | $0 | Low |
| [`../DEPLOYMENT_RUNBOOK.md`](../DEPLOYMENT_RUNBOOK.md) | Kubernetes (Helm + manifests) | Cluster cost varies | High |

Recommend QUICKSTART first. Move to k8s only if outgrowing single VM (multi-region, autoscale, paid managed DBs).

---

## Files referenced

| File | Role |
|---|---|
| `/docker-compose.headless.yml` | Trimmed 8-service stack |
| `/headless.env.example` | Env template |
| `/scripts/oracle-bootstrap.sh` | VM bootstrap |
| `/.github/workflows/ml-retrain.yml` | Weekly cron retrain via SSH |
| `/infrastructure/scripts/init-timescale.sql` | DB init + retention policies |
| `/services/trading-engine/app/main.py` | LIVE_TRADING_ACK gate |
| `/CLAUDE.md` | Project rules, risk caps, flag matrix |
