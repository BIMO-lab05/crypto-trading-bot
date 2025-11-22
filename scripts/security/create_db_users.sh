#!/bin/bash
# Database User Creation Script
# Creates limited privilege users for PostgreSQL and TimescaleDB
# Run from project root: ./scripts/security/create_db_users.sh

set -e

echo "==================================================================="
echo "   DATABASE USER CREATION - LIMITED PRIVILEGES"
echo "==================================================================="
echo ""
echo "This script will:"
echo "  1. Create cryptobot_app user (read/write for services)"
echo "  2. Create cryptobot_readonly user (analytics/monitoring)"
echo "  3. Grant minimal required privileges"
echo "  4. Generate secure passwords"
echo "  5. Store passwords in .secrets/"
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted by user"
    exit 1
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Ensure .secrets directory exists
mkdir -p .secrets
chmod 700 .secrets

# Generate passwords
echo ""
echo "=== Generating secure passwords ==="
APP_PASSWORD=$(openssl rand -base64 32)
RO_PASSWORD=$(openssl rand -base64 32)

# Save passwords
echo "$APP_PASSWORD" > .secrets/db_app_password
echo "$RO_PASSWORD" > .secrets/db_readonly_password
chmod 600 .secrets/db_*

echo -e "${GREEN}✅ Generated passwords:${NC}"
echo "  - Application user: .secrets/db_app_password"
echo "  - Read-only user: .secrets/db_readonly_password"

# Create SQL script
echo ""
echo "=== Creating SQL script ==="

cat > /tmp/create_db_users.sql << EOF
-- ============================================================
-- Database User Creation - Limited Privileges
-- Created: $(date)
-- ============================================================

-- Application user (read/write access)
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'cryptobot_app') THEN
        CREATE USER cryptobot_app WITH PASSWORD '$APP_PASSWORD';
        RAISE NOTICE 'Created user: cryptobot_app';
    ELSE
        ALTER USER cryptobot_app WITH PASSWORD '$APP_PASSWORD';
        RAISE NOTICE 'Updated password for: cryptobot_app';
    END IF;
END
\$\$;

-- Read-only user (analytics/monitoring)
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'cryptobot_readonly') THEN
        CREATE USER cryptobot_readonly WITH PASSWORD '$RO_PASSWORD';
        RAISE NOTICE 'Created user: cryptobot_readonly';
    ELSE
        ALTER USER cryptobot_readonly WITH PASSWORD '$RO_PASSWORD';
        RAISE NOTICE 'Updated password for: cryptobot_readonly';
    END IF;
END
\$\$;

-- Grant privileges to cryptobot_app
GRANT CONNECT ON DATABASE cryptobot TO cryptobot_app;
GRANT USAGE ON SCHEMA public TO cryptobot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cryptobot_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cryptobot_app;

-- Grant privileges to cryptobot_readonly
GRANT CONNECT ON DATABASE cryptobot TO cryptobot_readonly;
GRANT USAGE ON SCHEMA public TO cryptobot_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO cryptobot_readonly;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cryptobot_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO cryptobot_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO cryptobot_app;

-- Display created users
\echo ''
\echo '=== Created Users ==='
\du cryptobot_app
\du cryptobot_readonly
\echo ''
EOF

echo -e "${GREEN}✅ Created SQL script: /tmp/create_db_users.sql${NC}"

# Execute on PostgreSQL
echo ""
echo "=== Executing on PostgreSQL (cryptobot database) ==="
if docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot < /tmp/create_db_users.sql; then
    echo -e "${GREEN}✅ PostgreSQL users created successfully${NC}"
else
    echo -e "${RED}❌ Failed to create PostgreSQL users${NC}"
    exit 1
fi

# Execute on TimescaleDB (if exists and different from postgres)
echo ""
echo "=== Executing on TimescaleDB (market_data database) ==="

# Create script for TimescaleDB (different database name)
cat > /tmp/create_db_users_timescale.sql << EOF
-- TimescaleDB User Creation
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'cryptobot_app') THEN
        CREATE USER cryptobot_app WITH PASSWORD '$APP_PASSWORD';
    ELSE
        ALTER USER cryptobot_app WITH PASSWORD '$APP_PASSWORD';
    END IF;
END
\$\$;

DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'cryptobot_readonly') THEN
        CREATE USER cryptobot_readonly WITH PASSWORD '$RO_PASSWORD';
    ELSE
        ALTER USER cryptobot_readonly WITH PASSWORD '$RO_PASSWORD';
    END IF;
END
\$\$;

GRANT CONNECT ON DATABASE market_data TO cryptobot_app;
GRANT USAGE ON SCHEMA public TO cryptobot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cryptobot_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cryptobot_app;

GRANT CONNECT ON DATABASE market_data TO cryptobot_readonly;
GRANT USAGE ON SCHEMA public TO cryptobot_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO cryptobot_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cryptobot_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO cryptobot_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO cryptobot_app;
EOF

if docker exec -i crypto-bot-timescaledb psql -U cryptobot -d market_data < /tmp/create_db_users_timescale.sql 2>/dev/null; then
    echo -e "${GREEN}✅ TimescaleDB users created successfully${NC}"
else
    echo -e "${YELLOW}⚠️  TimescaleDB not available or already configured${NC}"
fi

# Cleanup
rm /tmp/create_db_users.sql /tmp/create_db_users_timescale.sql 2>/dev/null || true

# Verify users were created
echo ""
echo "=== Verifying user creation ==="

echo "PostgreSQL users:"
docker exec crypto-bot-postgres psql -U cryptobot -d cryptobot -c "SELECT usename, usesuper, usecreatedb FROM pg_user WHERE usename LIKE 'cryptobot%';" 2>/dev/null || true

echo ""
echo "TimescaleDB users:"
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c "SELECT usename, usesuper, usecreatedb FROM pg_user WHERE usename LIKE 'cryptobot%';" 2>/dev/null || true

# Summary and next steps
echo ""
echo "==================================================================="
echo "   USER CREATION COMPLETE"
echo "==================================================================="
echo ""
echo -e "${GREEN}✅ Created users:${NC}"
echo "  - cryptobot_app (read/write for services)"
echo "  - cryptobot_readonly (read-only for analytics)"
echo ""
echo -e "${GREEN}✅ Passwords stored in:${NC}"
echo "  - .secrets/db_app_password"
echo "  - .secrets/db_readonly_password"
echo ""
echo -e "${YELLOW}⚠️  NEXT STEPS:${NC}"
echo ""
echo "1. Update service .env files to use new user:"
echo "   DB_USER=cryptobot_app"
echo "   DB_PASSWORD=\$(cat .secrets/db_app_password)"
echo ""
echo "2. Update these service .env files:"
echo "   - services/portfolio-manager/.env"
echo "   - services/trading-engine/.env"
echo "   - services/market-data-service/.env"
echo "   - services/risk-metrics-service/.env"
echo ""
echo "3. For analytics/monitoring tools, use:"
echo "   DB_USER=cryptobot_readonly"
echo "   DB_PASSWORD=\$(cat .secrets/db_readonly_password)"
echo ""
echo "4. Test database connections:"
echo "   docker exec -it crypto-bot-postgres psql -U cryptobot_app -d cryptobot"
echo ""
echo "5. After testing, consider removing SUPERUSER from cryptobot:"
echo "   ALTER USER cryptobot WITH NOSUPERUSER;"
echo "   (Keep cryptobot for admin tasks only)"
echo ""
echo "6. Restart services to apply new credentials:"
echo "   docker-compose restart portfolio-manager trading-engine market-data"
echo ""
echo -e "${YELLOW}⚠️  Security Note:${NC}"
echo "   - Keep .secrets/ directory secure (chmod 700)"
echo "   - Never commit .secrets/ to git"
echo "   - Rotate passwords regularly (quarterly recommended)"
echo "   - Use different passwords for production"
echo ""
echo "==================================================================="
