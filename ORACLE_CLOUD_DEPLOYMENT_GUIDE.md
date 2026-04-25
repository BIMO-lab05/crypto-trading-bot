# Oracle Cloud Free Tier Deployment Guide
**Crypto Trading Bot - Complete Setup Instructions**
**Date:** 2026-01-14
**Estimated Time:** 45-60 minutes

---

## 🎯 What You'll Get

- **4 ARM CPUs** (2.4 GHz each)
- **24 GB RAM** (10x more than needed!)
- **200 GB storage**
- **10 TB/month bandwidth**
- **Cost:** $0/month FOREVER

---

## 📋 Prerequisites Checklist

Before starting, have ready:
- [ ] Email address (for account signup)
- [ ] Credit/debit card (verification only - no charges)
- [ ] Phone number (SMS verification)
- [ ] Your current trading bot directory: `/mnt/d/Bimo_max/crypto-trading-bot`

---

## Part 1: Create Oracle Cloud Account (10 minutes)

### Step 1.1: Start Signup
1. Go to: https://www.oracle.com/cloud/free/
2. Click **"Start for free"** button
3. Select your **country/region** (IMPORTANT: Can't change later!)

### Step 1.2: Account Information
Fill in the form:
```
Email: your-email@example.com
Password: (Create a strong password - save it!)
Cloud Account Name: crypto-bot-[yourname]  (Example: crypto-bot-john)
Home Region: (Choose closest to you - USA, EU, Asia, etc.)
```

**CRITICAL:** The "Home Region" affects latency. Choose:
- US East (Ashburn) - if you're in Americas
- EU Frankfurt - if you're in Europe
- Japan Central (Tokyo) - if you're in Asia
- UK South (London) - if you're in UK

### Step 1.3: Account Type
- Select: **"Individual"** (not Company/Government)
- Enter your full name
- Enter home address
- Enter phone number

### Step 1.4: Payment Verification
- Enter credit/debit card details
- Oracle will do a $1 pre-authorization (refunded immediately)
- This is ONLY for identity verification
- You will NOT be charged unless you manually upgrade to paid

### Step 1.5: Verify Email
- Check your inbox for verification email
- Click the verification link
- Wait for account activation (usually instant, max 30 min)

### Step 1.6: Complete Setup
- Once activated, you'll see the Oracle Cloud Dashboard
- You're now on the **Always Free** tier

---

## Part 2: Create VM Instance (15 minutes)

### Step 2.1: Navigate to Compute
1. Log into Oracle Cloud: https://cloud.oracle.com/
2. Click **"Create a VM instance"** on the main dashboard
3. Or go to: **Menu** → **Compute** → **Instances** → **Create Instance**

### Step 2.2: Configure Instance - Basic Information

**Name your instance:**
```
Name: crypto-trading-bot
Compartment: (root) - leave default
Availability Domain: (Any) - leave default
```

### Step 2.3: Configure Instance - Image and Shape

**Image (Operating System):**
1. Click **"Change Image"**
2. Select: **Ubuntu** (20.04 or 22.04 LTS)
3. Image version: Latest
4. Click **"Select Image"**

**Shape (Resources):**
1. Click **"Change Shape"**
2. Select **"Ampere"** (ARM-based)
3. Click **"VM.Standard.A1.Flex"**
4. Configure OCPU and memory:
   ```
   OCPU count: 4
   Memory (GB): 24
   ```
   These are the MAXIMUM free tier limits - use them all!
5. Click **"Select Shape"**

### Step 2.4: Configure Networking

**Primary VNIC Information:**
```
Network: (Default VCN)
Subnet: (Public subnet)
```

**Public IP Address:**
- ☑️ **Assign a public IPv4 address** (MUST be checked!)

### Step 2.5: Add SSH Keys

**IMPORTANT:** You need SSH keys to connect to your VM.

**Option A: Generate new SSH key pair (Recommended)**
1. Select: **"Generate a key pair for me"**
2. Click **"Save Private Key"** → Save as `oracle-cloud-key.pem`
3. Click **"Save Public Key"** → Save as `oracle-cloud-key.pub`
4. **CRITICAL:** Keep these files safe! You can't download them again.

**Option B: Use existing SSH key**
1. Select: **"Upload public key files (.pub)"**
2. Upload your existing `id_rsa.pub` or `id_ed25519.pub`

### Step 2.6: Boot Volume

Leave defaults:
```
Boot volume size: 50 GB (minimum)
☐ Use in-transit encryption (not needed)
☐ Encrypt this volume (not needed for public data)
```

### Step 2.7: Create the Instance

1. Review all settings
2. Click **"Create"** button at bottom
3. Wait 2-3 minutes for instance to provision
4. Status will change: Provisioning → Running (orange → green)

### Step 2.8: Note Your VM Details

Once running, note these details:
```
Instance Name: crypto-trading-bot
Public IP Address: xxx.xxx.xxx.xxx (write this down!)
Username: ubuntu (default for Ubuntu images)
Private Key Location: /path/to/oracle-cloud-key.pem
```

---

## Part 3: Configure Oracle Cloud Network Security (10 minutes)

By default, Oracle Cloud blocks ALL ports except SSH (22). We need to open ports for the trading bot.

### Step 3.1: Navigate to Security List
1. On your instance page, under **"Primary VNIC"** section
2. Click on your **Subnet** name (will be something like "subnet-...")
3. Click on your **Security List** (will be "Default Security List for ...")

### Step 3.2: Add Ingress Rules

Click **"Add Ingress Rules"** button and add EACH of these:

**Rule 1: Frontend Dashboard**
```
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Source Port Range: (leave blank)
Destination Port Range: 3000
Description: Trading Bot Frontend
```
Click **"Add Ingress Rule"**

**Rule 2: API Gateway**
```
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 8000
Description: API Gateway
```
Click **"Add Ingress Rule"**

**Rule 3: Trading Engine**
```
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 8001
Description: Trading Engine
```
Click **"Add Ingress Rule"**

**Rule 4: Portfolio Manager**
```
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 8002
Description: Portfolio Manager
```
Click **"Add Ingress Rule"**

**Rule 5: Market Data Service**
```
Source Type: CIDR
Source CIDR: 0.0.0.0/0
IP Protocol: TCP
Destination Port Range: 8005
Description: Market Data Service
```
Click **"Add Ingress Rule"**

### Step 3.3: Verify Rules
You should now have 6 ingress rules total:
- Port 22 (SSH) - was already there
- Port 3000 (Frontend)
- Port 8000 (API Gateway)
- Port 8001 (Trading Engine)
- Port 8002 (Portfolio Manager)
- Port 8005 (Market Data)

---

## Part 4: Connect to Your VM (5 minutes)

### Step 4.1: Prepare SSH Key (Windows WSL)

From your WSL terminal:
```bash
# Move the key to your SSH directory
mkdir -p ~/.ssh
cp /mnt/c/Users/YourName/Downloads/oracle-cloud-key.pem ~/.ssh/

# Set correct permissions (CRITICAL!)
chmod 600 ~/.ssh/oracle-cloud-key.pem

# Test the key
ls -la ~/.ssh/oracle-cloud-key.pem
# Should show: -rw------- (only you can read)
```

### Step 4.2: Connect via SSH

Replace `xxx.xxx.xxx.xxx` with your VM's public IP:

```bash
ssh -i ~/.ssh/oracle-cloud-key.pem ubuntu@xxx.xxx.xxx.xxx
```

**First time connecting:**
- You'll see: "The authenticity of host... can't be established"
- Type: `yes` and press Enter
- You should now be logged into your Oracle Cloud VM!

You'll see a prompt like:
```
ubuntu@crypto-trading-bot:~$
```

---

## Part 5: Setup VM Environment (15 minutes)

### Step 5.1: Run Automated Setup Script

On your **Oracle Cloud VM** (via SSH):

```bash
# Download the setup script
wget https://raw.githubusercontent.com/your-repo/crypto-trading-bot/main/oracle-cloud-setup.sh

# Or create it manually:
nano oracle-cloud-setup.sh
# Paste the script content from the file we created
# Press Ctrl+X, then Y, then Enter to save

# Make it executable
chmod +x oracle-cloud-setup.sh

# Run the installation
bash oracle-cloud-setup.sh install
```

**What this does:**
- Updates Ubuntu system packages
- Installs Docker and Docker Compose
- Configures firewall (UFW)
- Sets up monitoring tools
- Prepares directory for trading bot

This will take **10-15 minutes**. Go grab a coffee! ☕

### Step 5.2: Verify Installation

After script completes:
```bash
# Check Docker
docker --version
# Should show: Docker version 24.x.x or higher

# Check Docker Compose
docker compose version
# Should show: Docker Compose version v2.x.x or higher

# Check firewall
sudo ufw status
# Should show: Status: active

# Check directory
ls -la ~/crypto-trading-bot
# Should exist but be empty (ready for your files)
```

---

## Part 6: Transfer Trading Bot Files (10 minutes)

### Step 6.1: From Your Local Machine (WSL)

Open a **NEW** terminal on your **LOCAL** machine (keep SSH connection open in other terminal):

```bash
# Navigate to your trading bot directory
cd /mnt/d/Bimo_max/crypto-trading-bot

# Transfer all files to Oracle Cloud
# Replace xxx.xxx.xxx.xxx with your VM's IP
scp -i ~/.ssh/oracle-cloud-key.pem -r ./* ubuntu@xxx.xxx.xxx.xxx:~/crypto-trading-bot/

# This will transfer all files (may take 5-10 minutes)
```

**What gets transferred:**
- All service directories
- docker-compose.yml
- .env file (with your API keys)
- Configuration files
- Database initialization scripts

### Step 6.2: Verify Transfer

Back on your **Oracle Cloud VM** (SSH terminal):

```bash
cd ~/crypto-trading-bot

# Check files are there
ls -la

# Should see:
# - services/
# - docker-compose.yml
# - .env
# - progress.md
# - etc.
```

---

## Part 7: Deploy Trading Bot (15 minutes)

### Step 7.1: Configure Environment

On **Oracle Cloud VM**:

```bash
cd ~/crypto-trading-bot

# Edit .env file if needed
nano .env

# Make sure these are set:
# - BYBIT_API_KEY=your_key
# - BYBIT_SECRET=your_secret
# - POSTGRES_PASSWORD=cryptobot_secure_2024
# etc.

# Save: Ctrl+X, Y, Enter
```

### Step 7.2: Run Deployment Script

```bash
# Run the deployment
bash oracle-cloud-setup.sh deploy
```

**What this does:**
- Pulls all 17 Docker images (takes 10-15 minutes!)
- Starts all containers
- Waits for services to initialize
- Runs health checks
- Sets up monitoring

You'll see output like:
```
ℹ️  Step 6: Deploying trading bot...
ℹ️  Pulling Docker images (this may take 10-15 minutes)...
[+] Running 17/17
 ✔ timescaledb Pulled
 ✔ postgres Pulled
 ✔ redis Pulled
 ... (all services)
ℹ️  Starting all 17 containers...
✅ Trading bot deployed!
```

### Step 7.3: Verify Deployment

Check container status:
```bash
docker compose ps
```

You should see 17 containers, all with status **"Up"**:
```
NAME                          STATUS
crypto-bot-api-gateway        Up 2 minutes
crypto-bot-bybit              Up 2 minutes
crypto-bot-frontend           Up 2 minutes
crypto-bot-market-data        Up 2 minutes
crypto-bot-ml-prediction      Up 2 minutes
crypto-bot-notification       Up 2 minutes
crypto-bot-portfolio          Up 2 minutes
crypto-bot-postgres           Up 2 minutes
crypto-bot-rabbitmq           Up 2 minutes
crypto-bot-redis              Up 2 minutes
crypto-bot-risk-metrics       Up 2 minutes
crypto-bot-sentiment          Up 2 minutes
crypto-bot-signal-aggregator  Up 2 minutes
crypto-bot-technical-analysis Up 2 minutes
crypto-bot-timescaledb        Up 2 minutes
crypto-bot-trading            Up 2 minutes
crypto-bot-visual-analysis    Up 2 minutes
```

### Step 7.4: Run Health Check

```bash
bash ~/check-bot-health.sh
```

Should show:
```
=== Container Status ===
(17 containers running)

=== Service Health ===
✅ Port 8000: Healthy
✅ Port 8001: Healthy
✅ Port 8002: Healthy
✅ Port 8005: Healthy
✅ Port 3000: Healthy

=== Resource Usage ===
(Memory and CPU stats)
```

---

## Part 8: Access Your Trading Bot (2 minutes)

### Step 8.1: Get Your Public IP

```bash
curl ifconfig.me
```

This will show your Oracle Cloud VM's public IP: `xxx.xxx.xxx.xxx`

### Step 8.2: Access Dashboard

Open your web browser and go to:
```
http://xxx.xxx.xxx.xxx:3000
```

You should see your trading bot dashboard! 🎉

### Step 8.3: Test API Endpoints

```bash
# API Gateway health
curl http://xxx.xxx.xxx.xxx:8000/health

# Trading Engine health
curl http://xxx.xxx.xxx.xxx:8001/health

# Portfolio Manager health
curl http://xxx.xxx.xxx.xxx:8002/health
```

All should return: `{"status":"healthy"}`

---

## Part 9: Monitoring & Maintenance

### Daily Health Check

Run this from SSH:
```bash
bash ~/check-bot-health.sh
```

### View Logs

```bash
cd ~/crypto-trading-bot

# View all logs
docker compose logs -f

# View specific service
docker compose logs -f trading-engine
docker compose logs -f market-data-service

# Last 100 lines
docker compose logs --tail=100 trading-engine
```

### Restart Service

```bash
cd ~/crypto-trading-bot

# Restart specific service
docker compose restart trading-engine

# Restart all services
docker compose restart

# Stop all
docker compose down

# Start all
docker compose up -d
```

### Resource Monitoring

```bash
# CPU and memory usage
docker stats

# Disk usage
df -h

# System resources
htop
```

### Auto-Restart (Already Configured)

The setup script added a cron job that checks every 5 minutes and restarts any stopped containers automatically.

Check it:
```bash
crontab -l
```

---

## Part 10: Security Hardening (Optional but Recommended)

### Step 10.1: Change SSH Port (Optional)

```bash
sudo nano /etc/ssh/sshd_config

# Change this line:
# Port 22
# To:
# Port 2222

# Save and restart SSH
sudo systemctl restart sshd

# Remember to update Oracle Cloud Security List to allow port 2222!
```

### Step 10.2: Setup Fail2Ban (Brute Force Protection)

```bash
sudo apt-get install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Step 10.3: Enable Automatic Security Updates

```bash
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
# Select "Yes" when prompted
```

### Step 10.4: Setup SSL/HTTPS (Advanced)

For production with custom domain:
```bash
# Install Certbot
sudo apt-get install -y certbot

# Get free SSL certificate (requires domain name)
sudo certbot certonly --standalone -d your-domain.com

# Configure nginx reverse proxy with SSL
# (Instructions in separate guide if needed)
```

---

## Troubleshooting

### Problem: Can't SSH to VM

**Solution 1:** Check SSH key permissions
```bash
chmod 600 ~/.ssh/oracle-cloud-key.pem
```

**Solution 2:** Verify you're using correct username
- Ubuntu images: username is `ubuntu`
- Oracle Linux: username is `opc`

**Solution 3:** Check Security List
- Ensure port 22 is allowed in Oracle Cloud Security List
- Source CIDR should be 0.0.0.0/0 or your IP

### Problem: Can't Access Dashboard (Port 3000)

**Solution 1:** Check Oracle Cloud Security List
- Ensure port 3000 is allowed
- Ingress rule must be added (see Part 3)

**Solution 2:** Check UFW firewall on VM
```bash
sudo ufw status
sudo ufw allow 3000/tcp
```

**Solution 3:** Check if frontend container is running
```bash
docker compose ps | grep frontend
docker compose logs frontend
```

### Problem: Containers Keep Stopping

**Solution 1:** Check logs
```bash
docker compose logs --tail=100 [service-name]
```

**Solution 2:** Check resources
```bash
docker stats
free -h
df -h
```

**Solution 3:** Restart with clean state
```bash
docker compose down
docker system prune -f
docker compose up -d
```

### Problem: Out of Disk Space

**Solution:** Clean Docker resources
```bash
# Remove unused images
docker image prune -a -f

# Remove unused volumes
docker volume prune -f

# Remove build cache
docker builder prune -a -f

# Check disk usage
df -h
docker system df
```

### Problem: Database Connection Errors

**Solution:** Check database containers
```bash
# Check PostgreSQL
docker compose logs postgres | tail -50

# Check TimescaleDB
docker compose logs timescaledb | tail -50

# Restart databases
docker compose restart postgres timescaledb

# Wait 30 seconds, then restart dependent services
sleep 30
docker compose restart trading-engine technical-analysis
```

---

## Maintenance Schedule

### Daily (Automated via Cron)
- ✅ Container health check
- ✅ Auto-restart stopped containers

### Weekly (Manual)
- [ ] Check logs for errors: `docker compose logs --tail=500`
- [ ] Verify disk space: `df -h`
- [ ] Check system resources: `htop`
- [ ] Review trading performance in dashboard

### Monthly (Manual)
- [ ] Update system packages: `sudo apt-get update && sudo apt-get upgrade`
- [ ] Clean Docker resources: `docker system prune -af`
- [ ] Backup database: `docker compose exec postgres pg_dump -U cryptobot cryptobot > backup.sql`
- [ ] Review and rotate logs

---

## Backup Strategy

### Database Backup

```bash
# Create backup directory
mkdir -p ~/backups

# Backup PostgreSQL (trading data)
docker compose exec postgres pg_dump -U cryptobot cryptobot > ~/backups/postgres-$(date +%Y%m%d).sql

# Backup TimescaleDB (market data)
docker compose exec timescaledb pg_dump -U cryptobot market_data > ~/backups/timescale-$(date +%Y%m%d).sql

# Compress backups
gzip ~/backups/*.sql
```

### Automated Daily Backup

Add to crontab:
```bash
crontab -e

# Add this line:
0 2 * * * cd ~/crypto-trading-bot && docker compose exec postgres pg_dump -U cryptobot cryptobot | gzip > ~/backups/postgres-$(date +\%Y\%m\%d).sql.gz
```

### Download Backups to Local Machine

From your local machine:
```bash
scp -i ~/.ssh/oracle-cloud-key.pem ubuntu@xxx.xxx.xxx.xxx:~/backups/*.sql.gz ./backups/
```

---

## Cost Monitoring

### Verify You're on Always Free Tier

1. Log into Oracle Cloud Console
2. Go to **Account Management** → **Usage and Cost Reports**
3. Check that usage shows: **"Always Free resources"**
4. Verify no charges appear

**What's included in Always Free:**
- VM.Standard.A1.Flex: Up to 4 OCPUs, 24 GB RAM
- Block storage: 200 GB total
- Bandwidth: 10 TB/month outbound
- **No time limit** - Free forever

**What's NOT free:**
- Additional VMs beyond free limits
- Upgraded shapes (x86 instances)
- Load balancers (beyond free tier)
- Additional block storage (beyond 200 GB)

---

## Performance Optimization

### Enable Swap (If Running Low on RAM)

```bash
# Create 4 GB swap file
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Optimize Docker

```bash
# Add to /etc/docker/daemon.json
sudo nano /etc/docker/daemon.json

{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}

# Restart Docker
sudo systemctl restart docker
```

---

## Next Steps

After successful deployment:

1. **Monitor for 24 hours**
   - Check dashboard regularly
   - Review logs for errors
   - Verify trading operations

2. **Configure alerts**
   - Setup email notifications
   - Configure Telegram bot (if using)

3. **Optimize performance**
   - Review resource usage
   - Adjust container limits if needed

4. **Setup domain name** (Optional)
   - Point domain to VM IP
   - Setup SSL certificate
   - Configure nginx reverse proxy

5. **Review trading performance**
   - Check wins/losses
   - Verify stop losses working
   - Monitor position hold times

---

## Support Resources

### Oracle Cloud Documentation
- Free Tier: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm
- Compute: https://docs.oracle.com/en-us/iaas/Content/Compute/home.htm

### Trading Bot Documentation
- Main README: `/mnt/d/Bimo_max/crypto-trading-bot/README.md`
- API Docs: `/mnt/d/Bimo_max/crypto-trading-bot/docs/`
- Progress: `/mnt/d/Bimo_max/crypto-trading-bot/progress.md`

### Your Deployment Details
```
VM Public IP: _____._____._____._____ (write this down!)
SSH Key Location: ~/.ssh/oracle-cloud-key.pem
Username: ubuntu
Dashboard URL: http://_____._____._____.____:3000
API Gateway: http://_____._____._____.____:8000
Trading Engine: http://_____._____._____.____:8001
```

---

## Success Checklist

After completing this guide, you should have:

- [x] Oracle Cloud Free Tier account created
- [x] ARM VM instance running (4 CPU, 24 GB RAM)
- [x] Security List configured (ports 22, 3000, 8000, 8001, 8002, 8005)
- [x] SSH access to VM working
- [x] Docker and Docker Compose installed
- [x] UFW firewall configured
- [x] All 17 containers running and healthy
- [x] Dashboard accessible at http://VM_IP:3000
- [x] API endpoints responding
- [x] Monitoring script setup
- [x] Auto-restart cron job active
- [x] Backup strategy implemented

---

## 🎉 Congratulations!

Your crypto trading bot is now running on professional cloud infrastructure - **completely free!**

Total cost: **$0/month forever** 💰

You now have:
- ✅ 24/7 uptime
- ✅ Professional infrastructure
- ✅ 10x more resources than needed
- ✅ Automatic monitoring and restarts
- ✅ Secure, isolated environment
- ✅ All critical fixes applied (2% SL, LONG only, 48h max hold)

**Your bot is actively trading with improved risk management!** 📈

---

*Last Updated: 2026-01-14*
*Next Review: Check dashboard in 24 hours*
*Status: 🟢 DEPLOYED - MONITORING ACTIVE*
