#!/usr/bin/env python3
"""
Crypto Trading Bot - Interactive Setup Wizard
Purpose: Guide user through complete setup and testing
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# Colors
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    BOLD = '\033[1m'
    NC = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.NC}")
    print(f"{Colors.BLUE}{Colors.BOLD}{text}{Colors.NC}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.NC}\n")

def print_step(step, text):
    print(f"\n{Colors.BOLD}Step {step}: {text}{Colors.NC}")
    print("-" * 60)

def print_success(text):
    print(f"{Colors.GREEN}✓{Colors.NC} {text}")

def print_error(text):
    print(f"{Colors.RED}✗{Colors.NC} {text}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠{Colors.NC} {text}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ{Colors.NC} {text}")

def run_command(cmd, cwd=None, check=True):
    """Run a shell command"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr

def check_infrastructure():
    """Check if Docker infrastructure is running"""
    print_step(1, "Checking Docker Infrastructure")
    
    success, stdout, stderr = run_command("docker-compose ps", cwd="infrastructure", check=False)
    
    if not success:
        print_error("Docker Compose is not running or not installed")
        print_info("Please ensure Docker Desktop is running")
        return False
    
    # Check each service
    services = ['postgres', 'timescaledb', 'redis', 'rabbitmq']
    all_healthy = True
    
    for service in services:
        if service in stdout and 'Up' in stdout:
            print_success(f"{service} is running")
        else:
            print_error(f"{service} is not running")
            all_healthy = False
    
    if not all_healthy:
        print_warning("\nSome services are not running. Starting them now...")
        success, _, _ = run_command("docker-compose up -d", cwd="infrastructure")
        if success:
            print_success("Docker services started")
            time.sleep(5)  # Wait for services to initialize
        else:
            print_error("Failed to start Docker services")
            return False
    
    return True

def setup_bybit_connector():
    """Setup Bybit Connector service"""
    print_step(2, "Setting Up Bybit Connector")
    
    connector_dir = Path("services/bybit-connector")
    
    # Check if .env exists
    env_file = connector_dir / ".env"
    if not env_file.exists():
        print_warning(".env file not found. Creating from template...")
        
        # Copy .env.example to .env
        success, _, _ = run_command(
            "cp .env.example .env",
            cwd=str(connector_dir)
        )
        
        if success:
            print_success(".env file created")
            print("\n" + "="*60)
            print_warning("IMPORTANT: You need to add your Bybit testnet API keys!")
            print("\nHow to get Bybit testnet API keys:")
            print("1. Visit: https://testnet.bybit.com/")
            print("2. Sign up for a FREE testnet account")
            print("3. Go to: API Management → Create API")
            print("4. Enable permissions: Read, Trade, Wallet")
            print("5. Copy your API Key and Secret")
            print("\nThen edit the .env file:")
            print(f"  nano {env_file}")
            print("\nSet these values:")
            print("  BYBIT_API_KEY=your_testnet_api_key")
            print("  BYBIT_API_SECRET=your_testnet_api_secret")
            print("  BYBIT_TESTNET=true")
            print("="*60)
            
            response = input("\nHave you added your API keys to .env? (yes/no): ").lower()
            if response != 'yes':
                print_warning("Please add your API keys and run this script again")
                return False
    else:
        print_success(".env file already exists")
    
    # Check if venv exists
    venv_dir = connector_dir / "venv"
    if not venv_dir.exists():
        print_info("Creating virtual environment...")
        success, _, _ = run_command(
            "python3.12 -m venv venv",
            cwd=str(connector_dir)
        )
        if success:
            print_success("Virtual environment created")
        else:
            print_error("Failed to create virtual environment")
            return False
    else:
        print_success("Virtual environment already exists")
    
    # Install dependencies
    print_info("Installing dependencies (this may take a minute)...")
    success, _, stderr = run_command(
        "venv/bin/pip install -q -r requirements.txt",
        cwd=str(connector_dir),
        check=False
    )
    if success:
        print_success("Dependencies installed")
    else:
        print_warning("Some dependencies may have issues, but continuing...")
    
    return True

def setup_market_data():
    """Setup Market Data service"""
    print_step(3, "Setting Up Market Data Service")
    
    data_dir = Path("services/market-data-service")
    
    # Check if .env exists
    env_file = data_dir / ".env"
    if not env_file.exists():
        print_info("Creating .env file...")
        success, _, _ = run_command(
            "cp .env.example .env",
            cwd=str(data_dir)
        )
        if success:
            print_success(".env file created")
    else:
        print_success(".env file already exists")
    
    # Check if venv exists
    venv_dir = data_dir / "venv"
    if not venv_dir.exists():
        print_info("Creating virtual environment...")
        success, _, _ = run_command(
            "python3.12 -m venv venv",
            cwd=str(data_dir)
        )
        if success:
            print_success("Virtual environment created")
        else:
            print_error("Failed to create virtual environment")
            return False
    else:
        print_success("Virtual environment already exists")
    
    # Install dependencies
    print_info("Installing dependencies (this may take a minute)...")
    success, _, _ = run_command(
        "venv/bin/pip install -q -r requirements.txt",
        cwd=str(data_dir),
        check=False
    )
    if success:
        print_success("Dependencies installed")
    else:
        print_warning("Some dependencies may have issues, but continuing...")
    
    return True

def print_start_instructions():
    """Print instructions for starting services"""
    print_header("✅ Setup Complete!")
    
    print(f"{Colors.BOLD}Now you need to start the services in separate terminals:{Colors.NC}\n")
    
    print(f"{Colors.YELLOW}Terminal 1 - Bybit Connector:{Colors.NC}")
    print("  cd services/bybit-connector")
    print("  source venv/bin/activate")
    print("  uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload")
    print(f"\n  Then open: {Colors.BLUE}http://localhost:8002/docs{Colors.NC}")
    
    print(f"\n{Colors.YELLOW}Terminal 2 - Market Data Service:{Colors.NC}")
    print("  cd services/market-data-service")
    print("  source venv/bin/activate")
    print("  uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload")
    print(f"\n  Then open: {Colors.BLUE}http://localhost:8003/docs{Colors.NC}")
    
    print(f"\n{Colors.YELLOW}Terminal 3 - Run Tests:{Colors.NC}")
    print("  cd crypto-trading-bot")
    print("  python3 scripts/test_pipeline.py")
    
    print(f"\n{Colors.BOLD}Quick Commands:{Colors.NC}")
    print(f"  • Health check: {Colors.BLUE}bash scripts/check_infrastructure.sh{Colors.NC}")
    print(f"  • View logs: Check services/*/logs/*.log")
    print(f"  • Stop all: {Colors.BLUE}docker-compose down{Colors.NC} (in infrastructure/)")

def main():
    """Main setup wizard"""
    os.chdir(Path(__file__).parent.parent)  # Go to project root
    
    print_header("🤖 Crypto Trading Bot - Setup Wizard")
    print("This wizard will help you set up and test your trading bot.\n")
    
    # Step 1: Check infrastructure
    if not check_infrastructure():
        print_error("\nInfrastructure check failed. Please fix issues and try again.")
        sys.exit(1)
    
    print_success("\nInfrastructure is healthy!")
    
    # Step 2: Setup Bybit Connector
    if not setup_bybit_connector():
        print_error("\nBybit Connector setup incomplete.")
        sys.exit(1)
    
    # Step 3: Setup Market Data
    if not setup_market_data():
        print_error("\nMarket Data Service setup failed.")
        sys.exit(1)
    
    # Print start instructions
    print_start_instructions()
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 Setup wizard complete!{Colors.NC}")
    print(f"{Colors.BOLD}Follow the instructions above to start testing.{Colors.NC}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Setup cancelled by user.{Colors.NC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Error: {str(e)}{Colors.NC}")
        sys.exit(1)
