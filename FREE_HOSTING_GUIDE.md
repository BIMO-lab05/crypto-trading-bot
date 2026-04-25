# Free Hosting Guide for Crypto Trading Bot
**Date:** 2026-01-14
**Status:** Complete deployment options analysis

---

## 📊 SYSTEM REQUIREMENTS ANALYSIS

### Current Resource Usage:
```
Total Containers: 17 (10 microservices + 4 databases + 3 monitoring/frontend)
Estimated RAM: 2-3 GB
Estimated CPU: 2-4 cores
Estimated Disk: 10-20 GB
Network: Moderate (API calls to Bybit, minimal bandwidth)
Uptime Required: 24/7 for automated trading
```

### Critical Services That Must Run:
1. **Trading Engine** (core logic)
2. **Bybit Connector** (exchange API)
3. **Market Data Service** (price feeds)
4. **Portfolio Manager** (position tracking)
5. **Technical Analysis** (indicators)
6. **TimescaleDB** (time-series data)
7. **PostgreSQL** (application data)
8. **Redis** (caching)

---

## 🆓 FREE HOSTING OPTIONS (Ranked by Suitability)

---

## ⭐ OPTION 1: ORACLE CLOUD FREE TIER (BEST - RECOMMENDED)

### Why Oracle Cloud?
- **FOREVER FREE** (not trial, actually free forever)
- **4 ARM CPUs + 24 GB RAM** (most generous free tier)
- **200 GB storage**
- Perfect for your 17 containers!

### What You Get FREE (Forever):
```
✅ 4 ARM CPUs (Ampere A1)
✅ 24 GB RAM
✅ 200 GB Block Storage
✅ 10 TB/month bandwidth
✅ Public IPv4 address
✅ Load balancer (optional)
```

### Setup Steps:

#### 1. Create Oracle Cloud Account
```bash
# Go to: https://www.oracle.com/cloud/free/
# Sign up (requires credit card for verification, but won't charge)
# You get $300 credits for 30 days PLUS forever free tier
```

#### 2. Create ARM Compute Instance
```bash
# In Oracle Cloud Console:
# 1. Go to: Compute → Instances → Create Instance
# 2. Choose:
#    - Image: Ubuntu 22.04 Minimal (ARM)
#    - Shape: VM.Standard.A1.Flex
#    - CPUs: 4 OCPU
#    - RAM: 24 GB
#    - Storage: 200 GB
# 3. Download SSH keys
# 4. Create instance (takes 2-3 minutes)
```

#### 3. Setup Your VM
```bash
# SSH into your instance
ssh -i your-key.pem ubuntu@<your-instance-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Reboot
sudo reboot
```

#### 4. Deploy Your Trading Bot
```bash
# SSH back in after reboot
ssh -i your-key.pem ubuntu@<your-instance-ip>

# Clone your repo (or upload files)
git clone <your-repo-url>
cd crypto-trading-bot

# Copy your .env file with API keys
nano .env  # Paste your Bybit API keys

# Start all services
docker compose up -d

# Check status
docker compose ps
```

#### 5. Access Your Dashboard
```bash
# Open firewall ports in Oracle Cloud Console:
# Networking → Virtual Cloud Networks → Security Lists → Default
# Add Ingress Rules:
# - Port 3000 (Frontend)
# - Port 8000 (API Gateway)
# - Port 3001 (Grafana)

# Access at:
http://<your-instance-ip>:3000
```

### Cost: **$0/month FOREVER** ✅

---

## ⭐ OPTION 2: GOOGLE CLOUD FREE TIER

### What You Get FREE (Forever):
```
✅ 1 e2-micro instance (2 vCPUs, 1 GB RAM) - US regions only
✅ 30 GB HDD storage
✅ 1 GB network egress/month
✅ $300 credits for 90 days (NEW accounts)
```

### Limitation:
- **1 GB RAM is NOT enough** for full system (need 2-3 GB)
- **Solution:** Use $300 credits for e2-medium (2 CPU, 4 GB RAM) for 90 days
- After credits expire, need to scale down or pay

### Setup:
```bash
# 1. Go to: https://cloud.google.com/free
# 2. Create account ($300 credits + free tier)
# 3. Create Compute Engine instance:
#    - e2-medium (2 vCPU, 4 GB RAM) using credits
#    - Ubuntu 22.04 LTS
#    - 30 GB boot disk
# 4. Follow same Docker setup as Oracle Cloud
```

### Cost:
- **First 90 days:** $0 (using $300 credits)
- **After 90 days:** ~$25/month OR scale down to free tier (limited)

---

## ⭐ OPTION 3: AWS FREE TIER

### What You Get FREE (12 Months):
```
✅ t2.micro (1 vCPU, 1 GB RAM) - 750 hours/month
✅ 30 GB EBS storage
✅ 15 GB data transfer out
```

### Limitation:
- **1 GB RAM is NOT enough** for full system
- **Only 12 months free** then you pay
- Need to use t3.medium (2 vCPU, 4 GB RAM) = ~$30/month after free tier

### Better Option:
Use **AWS Lightsail** instead:
```
✅ First 3 months FREE (new customers)
✅ $5/month after (2 GB RAM, 1 vCPU, 60 GB SSD)
```

### Setup:
```bash
# 1. Go to: https://aws.amazon.com/free
# 2. Create account
# 3. Go to: Lightsail
# 4. Create instance:
#    - OS: Ubuntu 22.04
#    - Plan: $5/month (2 GB RAM)
# 5. Follow Docker setup
```

### Cost:
- **First 3 months:** $0
- **After:** $5/month

---

## ⭐ OPTION 4: AZURE FOR STUDENTS (If You're a Student)

### What You Get FREE (12 Months + $100 Credits):
```
✅ B1s instance (1 vCPU, 1 GB RAM) - 750 hours/month
✅ 64 GB storage
✅ $100 Azure credits (no credit card required!)
```

### Best Option for Students:
```
✅ Use $100 credits for B2s (2 vCPU, 4 GB RAM)
✅ Lasts ~3-4 months
✅ NO CREDIT CARD REQUIRED!
```

### Setup:
```bash
# 1. Go to: https://azure.microsoft.com/en-us/free/students/
# 2. Sign up with .edu email
# 3. Get $100 credits + free services
# 4. Create Virtual Machine:
#    - B2s (2 vCPU, 4 GB RAM)
#    - Ubuntu 22.04
# 5. Follow Docker setup
```

### Cost:
- **$0 for 12 months** (if you're a student)
- After: ~$30-40/month

---

## 💡 OPTION 5: HOME SERVER / OLD LAPTOP (100% FREE)

### Requirements:
```
Any old PC/laptop with:
✅ 4 GB RAM minimum (8 GB recommended)
✅ 2+ CPU cores
✅ 50 GB free disk space
✅ Ubuntu 22.04 installed
✅ Always-on internet connection
```

### Pros:
- ✅ **COMPLETELY FREE** - no monthly costs
- ✅ Full control
- ✅ No bandwidth limits
- ✅ Can run forever

### Cons:
- ❌ Electricity cost (~$5-10/month)
- ❌ Need static IP or dynamic DNS
- ❌ Uptime depends on your home internet
- ❌ No professional support

### Setup:
```bash
# 1. Install Ubuntu Server 22.04 on old PC/laptop
# 2. Setup SSH access
# 3. Install Docker & Docker Compose (same as above)
# 4. Deploy trading bot
# 5. Setup port forwarding on router (optional)
# 6. Use ngrok or Cloudflare Tunnel for remote access (free)
```

### Access from Anywhere (Free):
```bash
# Option A: Cloudflare Tunnel (FREE, recommended)
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Create tunnel
cloudflared tunnel login
cloudflared tunnel create crypto-bot
cloudflared tunnel route dns crypto-bot bot.yourdomain.com

# Access at: https://bot.yourdomain.com

# Option B: ngrok (FREE tier - 1 tunnel)
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
./ngrok authtoken <your-token>
./ngrok http 3000

# Access at: https://xxxx-xxxx-xxxx.ngrok.io
```

### Cost: **$0/month** (except electricity ~$5-10)

---

## 💡 OPTION 6: RASPBERRY PI 4/5 (One-Time Cost)

### Hardware:
```
Raspberry Pi 4/5 (8 GB RAM model)
- Cost: $75-80 one-time
- Power consumption: $1-2/month
- Perfect for 24/7 trading bot
```

### Setup:
```bash
# 1. Buy Raspberry Pi 4/5 (8 GB model)
# 2. Install Raspberry Pi OS (64-bit)
# 3. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 4. Deploy trading bot (same as above)
# 5. Access locally or via Cloudflare Tunnel
```

### Cost:
- **Initial:** $75-80 (one-time)
- **Monthly:** ~$2 (electricity)
- **Total Year 1:** ~$100
- **Year 2+:** ~$24/year

---

## 📊 COMPARISON TABLE

| Option | Free Period | Monthly Cost After | RAM | CPU | Setup Difficulty |
|--------|-------------|-------------------|-----|-----|------------------|
| **Oracle Cloud** | ✅ FOREVER | **$0** | 24 GB | 4 ARM | Medium |
| **Google Cloud** | 90 days | $0 (limited) or $25 | 4 GB | 2 | Medium |
| **AWS Lightsail** | 3 months | $5 | 2 GB | 1 | Easy |
| **Azure Students** | 12 months | $30-40 | 4 GB | 2 | Medium |
| **Home Server** | ✅ FOREVER | **$0** | 4-8 GB | 2-4 | Easy |
| **Raspberry Pi** | ✅ FOREVER | **$2** | 8 GB | 4 ARM | Easy |

---

## 🎯 RECOMMENDATION

### Best Overall: **Oracle Cloud Free Tier** ⭐⭐⭐⭐⭐
**Why?**
- Truly FREE forever (not a trial)
- 4 CPUs + 24 GB RAM = more than enough
- 200 GB storage
- Professional-grade infrastructure
- No credit card charges
- Always-on internet

### Best for Students: **Azure for Students** ⭐⭐⭐⭐
- No credit card required
- $100 free credits
- Good learning experience

### Best DIY: **Home Server/Old Laptop** ⭐⭐⭐⭐
- 100% free (except electricity)
- Full control
- Great for learning
- Use Cloudflare Tunnel for remote access

---

## 🚀 QUICK START (Oracle Cloud - Recommended)

### Step-by-Step Deployment:

```bash
# ============================================
# STEP 1: Create Oracle Cloud Account
# ============================================
# Go to: https://www.oracle.com/cloud/free/
# Sign up (credit card for verification only)
# No charges will occur

# ============================================
# STEP 2: Create VM Instance
# ============================================
# In Oracle Cloud Console:
# Compute → Instances → Create Instance
# - Name: crypto-trading-bot
# - Image: Ubuntu 22.04 Minimal
# - Shape: VM.Standard.A1.Flex (ARM)
# - CPUs: 4 OCPU
# - RAM: 24 GB
# - Boot Volume: 200 GB
# Download SSH keys → Create

# ============================================
# STEP 3: Connect to VM
# ============================================
# Wait 2-3 minutes for VM to boot
# Note the public IP address
ssh -i your-key.pem ubuntu@<PUBLIC_IP>

# ============================================
# STEP 4: Install Docker
# ============================================
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Reboot
sudo reboot

# ============================================
# STEP 5: Deploy Trading Bot
# ============================================
# Reconnect after reboot
ssh -i your-key.pem ubuntu@<PUBLIC_IP>

# Upload your project (choose one method):

# Method A: Git clone
git clone https://github.com/yourusername/crypto-trading-bot.git
cd crypto-trading-bot

# Method B: SCP upload
# On your local machine:
# scp -i your-key.pem -r /path/to/crypto-trading-bot ubuntu@<PUBLIC_IP>:~

# ============================================
# STEP 6: Configure Environment
# ============================================
# Copy and edit .env file
cp .env.example .env
nano .env

# Add your Bybit API keys:
# BYBIT_API_KEY=your_key_here
# BYBIT_API_SECRET=your_secret_here
# BYBIT_TESTNET=true

# ============================================
# STEP 7: Start Services
# ============================================
docker compose up -d

# Wait 2-3 minutes for all services to start
docker compose ps

# Check logs
docker compose logs -f trading-engine

# ============================================
# STEP 8: Open Firewall Ports
# ============================================
# In Oracle Cloud Console:
# Networking → Virtual Cloud Networks →
# Your VCN → Security Lists → Default
# Add Ingress Rules:
# - Source: 0.0.0.0/0
# - Protocol: TCP
# - Destination Port: 3000 (Frontend)
# - Destination Port: 8000 (API)
# - Destination Port: 3001 (Grafana)

# Also open ports on the VM firewall:
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3001 -j ACCEPT
sudo netfilter-persistent save

# ============================================
# STEP 9: Access Your Bot
# ============================================
# Frontend: http://<PUBLIC_IP>:3000
# API: http://<PUBLIC_IP>:8000/docs
# Grafana: http://<PUBLIC_IP>:3001

# ============================================
# STEP 10: Setup Auto-Start on Reboot
# ============================================
# Create systemd service
sudo nano /etc/systemd/system/crypto-bot.service

# Paste this:
[Unit]
Description=Crypto Trading Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/crypto-trading-bot
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=ubuntu

[Install]
WantedBy=multi-user.target

# Enable service
sudo systemctl enable crypto-bot.service
sudo systemctl start crypto-bot.service
```

---

## 🔒 SECURITY CHECKLIST

### Essential Security Steps:

```bash
# 1. Setup firewall (UFW)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 3000/tcp  # Frontend
sudo ufw allow 8000/tcp  # API
sudo ufw allow 3001/tcp  # Grafana
sudo ufw enable

# 2. Change default SSH port
sudo nano /etc/ssh/sshd_config
# Change: Port 22 → Port 2222
sudo systemctl restart sshd

# 3. Disable root login
sudo nano /etc/ssh/sshd_config
# Change: PermitRootLogin yes → PermitRootLogin no
sudo systemctl restart sshd

# 4. Setup fail2ban (prevent brute force)
sudo apt install fail2ban -y
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# 5. Keep secrets in .env file (NEVER commit to git)
echo ".env" >> .gitignore

# 6. Use strong passwords for Grafana/Prometheus
# Edit docker-compose.yml to set GF_SECURITY_ADMIN_PASSWORD
```

---

## 📊 MONITORING YOUR FREE HOSTING

### Check Resource Usage:
```bash
# CPU and RAM usage
docker stats --no-stream

# Disk usage
df -h

# Network usage
sudo iftop

# System load
htop
```

### Setup Alerts (Free):
```bash
# Use UptimeRobot (free tier - 50 monitors)
# Go to: https://uptimerobot.com
# Add monitors for:
# - http://<your-ip>:8000/health
# - http://<your-ip>:8005/health
# Get email alerts if services go down
```

---

## 💰 COST COMPARISON (Annual)

| Option | Year 1 | Year 2 | Year 3 | Year 5 |
|--------|--------|--------|--------|--------|
| **Oracle Cloud** | **$0** | **$0** | **$0** | **$0** |
| Google Cloud | $0-100 | $300 | $300 | $300 |
| AWS Lightsail | $45 | $60 | $60 | $60 |
| Azure | $0-40 | $400 | $400 | $400 |
| **Home Server** | **$60** | **$60** | **$60** | **$60** |
| **Raspberry Pi** | **$100** | **$24** | **$24** | **$24** |

---

## ✅ FINAL RECOMMENDATION

### Go with: **Oracle Cloud Free Tier** ✅

**Why:**
1. ✅ Actually FREE forever (not a trial)
2. ✅ 4 CPUs + 24 GB RAM (plenty for your 17 containers)
3. ✅ 200 GB storage
4. ✅ Professional infrastructure
5. ✅ Always online
6. ✅ No electricity costs
7. ✅ Fast internet
8. ✅ No hardware to maintain

**Setup Time:** 30-60 minutes
**Monthly Cost:** $0
**Difficulty:** Medium (but well worth it)

---

## 📞 SUPPORT & TROUBLESHOOTING

### Common Issues:

**"Oracle Cloud won't let me create ARM instance"**
- Try different regions (some regions have capacity limits)
- Try creating smaller instance first (2 CPU, 12 GB), then resize

**"Services won't start - out of memory"**
- Reduce number of services (disable Grafana/Prometheus for now)
- Increase VM RAM to 24 GB (max free tier)

**"Can't access dashboard from browser"**
- Check Oracle Cloud Security Lists (ingress rules)
- Check VM firewall: `sudo iptables -L`
- Check service status: `docker compose ps`

**"Port 3000 already in use"**
- Change port in docker-compose.yml: `3000:80` → `3001:80`

---

## 📚 ADDITIONAL RESOURCES

- **Oracle Cloud Free Tier:** https://www.oracle.com/cloud/free/
- **Docker Documentation:** https://docs.docker.com/
- **Cloudflare Tunnel:** https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/
- **UptimeRobot Monitoring:** https://uptimerobot.com

---

*Last Updated: 2026-01-14*
*Next Review: Check Oracle Cloud terms for any changes*
