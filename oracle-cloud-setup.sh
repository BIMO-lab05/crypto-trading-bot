#!/bin/bash
###############################################################################
# Oracle Cloud Free Tier - Crypto Trading Bot Deployment Script
# Generated: 2026-01-14
# Purpose: Deploy 17-container trading bot system to Oracle Cloud
###############################################################################

set -e  # Exit on any error

echo "=========================================="
echo "  Crypto Trading Bot - Oracle Cloud Setup"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "ℹ️  $1"
}

###############################################################################
# Step 1: System Update and Basic Setup
###############################################################################
step1_system_update() {
    print_info "Step 1: Updating system packages..."

    # Update package lists
    sudo apt-get update -y

    # Upgrade existing packages
    sudo apt-get upgrade -y

    # Install essential tools
    sudo apt-get install -y \
        curl \
        wget \
        git \
        vim \
        htop \
        net-tools \
        ca-certificates \
        gnupg \
        lsb-release

    print_success "System updated successfully"
}

###############################################################################
# Step 2: Install Docker
###############################################################################
step2_install_docker() {
    print_info "Step 2: Installing Docker..."

    # Remove old Docker versions if any
    sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    # Add Docker's official GPG key
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

    # Set up Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Install Docker Engine
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Add current user to docker group (to run docker without sudo)
    sudo usermod -aG docker $USER

    # Start and enable Docker
    sudo systemctl start docker
    sudo systemctl enable docker

    print_success "Docker installed successfully"
    docker --version
}

###############################################################################
# Step 3: Install Docker Compose
###############################################################################
step3_install_docker_compose() {
    print_info "Step 3: Installing Docker Compose..."

    # Docker Compose v2 is already installed as a plugin
    # Create alias for docker-compose command
    echo 'alias docker-compose="docker compose"' >> ~/.bashrc
    source ~/.bashrc || true

    print_success "Docker Compose ready"
    docker compose version
}

###############################################################################
# Step 4: Configure Firewall
###############################################################################
step4_configure_firewall() {
    print_info "Step 4: Configuring firewall..."

    # Install UFW (Uncomplicated Firewall)
    sudo apt-get install -y ufw

    # Allow SSH (critical - don't lock yourself out!)
    sudo ufw allow 22/tcp comment 'SSH'

    # Allow trading bot ports
    sudo ufw allow 3000/tcp comment 'Frontend Dashboard'
    sudo ufw allow 8000/tcp comment 'API Gateway'
    sudo ufw allow 8001/tcp comment 'Trading Engine'
    sudo ufw allow 8002/tcp comment 'Portfolio Manager'
    sudo ufw allow 8005/tcp comment 'Market Data Service'

    # Enable firewall (with yes confirmation)
    echo "y" | sudo ufw enable

    # Show status
    sudo ufw status

    print_success "Firewall configured"
    print_warning "IMPORTANT: Also configure Oracle Cloud Security List (we'll do this next)"
}

###############################################################################
# Step 5: Clone Trading Bot Repository
###############################################################################
step5_clone_repo() {
    print_info "Step 5: Preparing for trading bot deployment..."

    # Create directory for the project
    mkdir -p ~/crypto-trading-bot
    cd ~/crypto-trading-bot

    print_success "Ready to receive trading bot files"
    print_info "You'll need to transfer files from your local machine"
    print_info "Use: scp -r /mnt/d/Bimo_max/crypto-trading-bot/* ubuntu@<VM_IP>:~/crypto-trading-bot/"
}

###############################################################################
# Step 6: Deploy Trading Bot
###############################################################################
step6_deploy_bot() {
    print_info "Step 6: Deploying trading bot..."

    cd ~/crypto-trading-bot

    # Check if docker-compose.yml exists
    if [ ! -f "docker-compose.yml" ]; then
        print_error "docker-compose.yml not found!"
        print_info "Please transfer your trading bot files first"
        return 1
    fi

    # Check if .env exists
    if [ ! -f ".env" ]; then
        print_warning ".env file not found, creating from example..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_warning "Please edit .env with your API keys and passwords"
        fi
    fi

    # Pull all Docker images (this might take 10-15 minutes)
    print_info "Pulling Docker images (this may take 10-15 minutes)..."
    docker compose pull

    # Start all containers
    print_info "Starting all 17 containers..."
    docker compose up -d

    # Wait for services to start
    sleep 30

    # Check status
    print_info "Checking container status..."
    docker compose ps

    print_success "Trading bot deployed!"
    print_info "Access dashboard at: http://$(curl -s ifconfig.me):3000"
}

###############################################################################
# Step 7: Health Check
###############################################################################
step7_health_check() {
    print_info "Step 7: Running health checks..."

    cd ~/crypto-trading-bot

    # Count running containers
    running=$(docker compose ps | grep -c "Up" || echo "0")
    total=$(docker compose ps | grep -c "crypto-bot" || echo "0")

    print_info "Containers running: $running/$total"

    # Check key services
    services=("trading-engine:8001" "api-gateway:8000" "frontend:3000")

    for service in "${services[@]}"; do
        service_name="${service%%:*}"
        port="${service##*:}"

        if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1; then
            print_success "$service_name is healthy"
        else
            print_warning "$service_name is not responding on port $port"
        fi
    done

    print_success "Health check complete"
}

###############################################################################
# Step 8: Setup Monitoring
###############################################################################
step8_setup_monitoring() {
    print_info "Step 8: Setting up monitoring..."

    # Create monitoring script
    cat > ~/check-bot-health.sh << 'EOF'
#!/bin/bash
# Quick health check script

cd ~/crypto-trading-bot

echo "=== Container Status ==="
docker compose ps

echo ""
echo "=== Service Health ==="
services=("8000" "8001" "8002" "8005" "3000")
for port in "${services[@]}"; do
    if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1; then
        echo "✅ Port $port: Healthy"
    else
        echo "❌ Port $port: Down"
    fi
done

echo ""
echo "=== Resource Usage ==="
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
EOF

    chmod +x ~/check-bot-health.sh

    # Create auto-restart cron job
    (crontab -l 2>/dev/null; echo "*/5 * * * * cd ~/crypto-trading-bot && docker compose up -d >> /tmp/bot-restart.log 2>&1") | crontab -

    print_success "Monitoring setup complete"
    print_info "Run: ~/check-bot-health.sh to check system health"
}

###############################################################################
# Main Installation Flow
###############################################################################
main() {
    print_info "Starting Oracle Cloud setup for crypto trading bot..."
    print_warning "This script will install Docker, configure firewall, and deploy the bot"
    print_info ""

    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        print_error "Please run as regular user (not root)"
        exit 1
    fi

    # Run all steps
    step1_system_update
    sleep 2

    step2_install_docker
    sleep 2

    step3_install_docker_compose
    sleep 2

    step4_configure_firewall
    sleep 2

    step5_clone_repo

    print_success ""
    print_success "=========================================="
    print_success "  Initial Setup Complete!"
    print_success "=========================================="
    print_info ""
    print_info "Next steps:"
    print_info "1. Transfer your trading bot files from local machine:"
    print_info "   scp -r /mnt/d/Bimo_max/crypto-trading-bot/* ubuntu@<VM_IP>:~/crypto-trading-bot/"
    print_info ""
    print_info "2. After files are transferred, run:"
    print_info "   cd ~/crypto-trading-bot"
    print_info "   bash oracle-cloud-setup.sh deploy"
    print_info ""
    print_info "3. Configure Oracle Cloud Security List to allow ports 3000, 8000, 8001"
    print_info ""
}

###############################################################################
# Command Router
###############################################################################
case "${1:-install}" in
    install)
        main
        ;;
    deploy)
        step6_deploy_bot
        step7_health_check
        step8_setup_monitoring
        ;;
    health)
        step7_health_check
        ;;
    *)
        print_error "Unknown command: $1"
        print_info "Usage: $0 [install|deploy|health]"
        exit 1
        ;;
esac

print_success "Done!"
