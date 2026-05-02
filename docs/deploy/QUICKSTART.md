# Quickstart — Headless Free-Tier Deploy

10-step path. Zero cost. ~30 minutes hands-on.

Full doc: `docs/deploy/HEADLESS_FREE_DEPLOY.md`.

---

## 1. Sign up Oracle Cloud
`cloud.oracle.com/free` → credit card hold (no charge).

## 2. Provision A1 VM
Compute → Create Instance → Shape `VM.Standard.A1.Flex` → 4 OCPU / 16-24 GB / 100 GB. Ubuntu 22.04. Paste SSH pubkey. Note public IP.

If "out of capacity": switch to 3-AD region (Ashburn / Phoenix / London).

## 3. Edit bootstrap script
`scripts/oracle-bootstrap.sh:18` — set `REPO_URL` to your fork URL.

## 4. Run bootstrap
```bash
scp scripts/oracle-bootstrap.sh ubuntu@<vm-ip>:~/
ssh ubuntu@<vm-ip> 'bash oracle-bootstrap.sh'
ssh ubuntu@<vm-ip>   # re-login for docker group
```

## 5. Push secrets
```bash
cp headless.env.example .env.deploy
# Fill BYBIT_API_KEY, BYBIT_API_SECRET, *_PASSWORD
chmod 600 .env.deploy
scp .env.deploy ubuntu@<vm-ip>:~/bot/.env
ssh ubuntu@<vm-ip> 'chmod 600 ~/bot/.env'
rm .env.deploy
```

Generate strong passwords: `openssl rand -base64 32`.

## 6. Start stack
```bash
ssh ubuntu@<vm-ip>
cd ~/bot
docker compose -f docker-compose.headless.yml up -d
docker compose -f docker-compose.headless.yml ps
```

All 8 services should reach `Up (healthy)` in ~90s.

## 7. Cloudflare Tunnel
```bash
cloudflared tunnel login
cloudflared tunnel create bot-api
cloudflared tunnel route dns bot-api bot.<your-domain>
# Edit ~/.cloudflared/config.yml — see HEADLESS_FREE_DEPLOY.md §6.4
sudo cloudflared service install <token>
```

In Cloudflare Zero Trust dashboard → add Access policy: One-time PIN, allowed email = yours only.

## 8. Verify
```bash
# T+5 min
docker compose logs --tail=200 trading-engine | grep -iE "decision|signal|cycle"
# Should show ≥1 decision cycle

# From phone hotspot (laptop NOT in loop)
curl https://bot.<your-domain>/api/portfolio/positions
# CF Access prompts for email OTP, then JSON response
```

## 9. Healthchecks ping
Free account at `healthchecks.io`. Add check, copy ping URL.
```bash
ssh ubuntu@<vm-ip>
crontab -e
# Add:
*/10 * * * * curl -fsS http://localhost:8005/health > /dev/null && curl -fsS https://hc-ping.com/<uuid> > /dev/null
```

## 10. GitHub Actions (ml-retrain)
GH repo → Settings → Secrets → Actions:
- `ORACLE_HOST`, `ORACLE_USER=ubuntu`, `ORACLE_SSH_KEY` (dedicated CI key)

Done. Bot trades 24/7. Laptop free.

---

**Daily ops cheatsheet:**
```bash
# Status
ssh ubuntu@<vm-ip> 'cd ~/bot && docker compose -f docker-compose.headless.yml ps'

# Tail logs
ssh ubuntu@<vm-ip> 'cd ~/bot && docker compose -f docker-compose.headless.yml logs -f trading-engine'

# Halt trading
ssh ubuntu@<vm-ip> 'touch ~/bot/EMERGENCY_STOP && cd ~/bot && docker compose -f docker-compose.headless.yml restart trading-engine'

# Resume
ssh ubuntu@<vm-ip> 'rm ~/bot/EMERGENCY_STOP && cd ~/bot && docker compose -f docker-compose.headless.yml restart trading-engine'

# Update bot
ssh ubuntu@<vm-ip> 'cd ~/bot && git pull && docker compose -f docker-compose.headless.yml build && docker compose -f docker-compose.headless.yml up -d'
```
