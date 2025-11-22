# Frontend Docker Implementation - Complete Code Reference

**Date:** November 21, 2025
**Status:** Ready for Implementation

---

## Overview

This guide contains the exact code for the 3 files needed to containerize the frontend.

**Files to Create:**
1. `frontend/Dockerfile` - Build Node + serve with Nginx
2. `frontend/nginx.conf` - Nginx configuration
3. `frontend/.dockerignore` - Exclude unnecessary files

**Files to Modify:**
1. `docker-compose.yml` - Add frontend service

---

## FILE 1: `frontend/Dockerfile`

**Location:** `/mnt/d/Bimo_max/crypto-trading-bot/frontend/Dockerfile`

**Copy and paste this entire content:**

```dockerfile
# ============================================================================
# Multi-stage Dockerfile for React Frontend with Nginx
# Stage 1: Build React application
# Stage 2: Serve with Nginx
# ============================================================================

# Stage 1: Builder - Build the React application
FROM node:18-alpine AS builder

# Set working directory
WORKDIR /app

# Copy package files (do this first to leverage Docker cache)
COPY package*.json ./

# Install dependencies using npm ci (cleaner install, faster)
RUN npm ci

# Copy source code
COPY . .

# Build the React application (creates dist/ folder)
RUN npm run build

# Stage 2: Runtime - Serve with Nginx
FROM nginx:alpine

# Copy Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built application from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80 (will be mapped to 3000 in docker-compose)
EXPOSE 80

# Health check to ensure Nginx is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1

# Start Nginx in foreground (required for containers)
CMD ["nginx", "-g", "daemon off;"]

# ============================================================================
# Image Size Optimization:
# - Multi-stage build: Only serves stage included in final image (~30MB)
# - Alpine Linux: Minimal base images
# - npm ci: Produces locked dependency tree
#
# Cache Strategy:
# - Dependencies cached separately from code (docker layer caching)
# - Code changes don't rebuild node_modules
#
# Production Ready:
# - Non-root user: Nginx runs as www-data (default in nginx:alpine)
# - Health checks: Automatically restart if Nginx fails
# - Signal handling: Nginx runs in foreground for proper container signals
# ============================================================================
```

---

## FILE 2: `frontend/nginx.conf`

**Location:** `/mnt/d/Bimo_max/crypto-trading-bot/frontend/nginx.conf`

**Copy and paste this entire content:**

```nginx
# ============================================================================
# Nginx Configuration for React SPA (Single Page Application)
# Serves static files and proxies API requests
# ============================================================================

upstream api_gateway {
    server api-gateway:8000;
}

server {
    # Listen on port 80 (mapped to 3000 in docker-compose)
    listen 80;
    server_name localhost;

    # Enable gzip compression for better performance
    gzip on;
    gzip_types text/plain text/css text/javascript application/json application/javascript;
    gzip_min_length 1000;
    gzip_proxied any;

    # ============================================================================
    # Static File Serving
    # ============================================================================

    # Serve static assets from dist/ folder
    root /usr/share/nginx/html;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # SPA Routing: All requests go to index.html, let React Router handle navigation
    # This allows direct URL navigation and page refreshes to work correctly
    location / {
        # Try to serve the file, if not found try as directory, else serve index.html
        try_files $uri $uri/ /index.html;

        # Cache static assets aggressively
        # Service workers and app shell can be cached for long periods
        add_header Cache-Control "public, max-age=31536000, immutable" always;
    }

    # ============================================================================
    # Static Assets Caching Strategy
    # ============================================================================

    # Cache JS, CSS, SVG, fonts aggressively (they have content hashes)
    location ~* \.(js|css|svg|woff|woff2|ttf|eot)$ {
        add_header Cache-Control "public, max-age=31536000, immutable" always;
        access_log off;
    }

    # Cache images for 30 days
    location ~* \.(jpg|jpeg|png|gif|ico|webp)$ {
        add_header Cache-Control "public, max-age=2592000" always;
        access_log off;
    }

    # index.html should never be cached (it bootstraps the app)
    location = /index.html {
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
    }

    # ============================================================================
    # API Proxy Configuration
    # ============================================================================

    # Forward all /api requests to the API Gateway service
    location /api/ {
        # Proxy configuration
        proxy_pass http://api_gateway;

        # Forward original request details
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;

        # CORS headers (API Gateway handles most CORS)
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, Authorization" always;

        # Timeout configuration (match Vite proxy settings)
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;

        # Buffering configuration for large responses
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;

        # WebSocket support (if needed for future features)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Don't modify the response
        proxy_intercept_errors off;
    }

    # ============================================================================
    # Health Check Endpoint
    # ============================================================================

    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }

    location /ready {
        access_log off;
        return 200 "ready\n";
        add_header Content-Type text/plain;
    }

    # ============================================================================
    # Error Handling for SPA
    # ============================================================================

    # 404 errors should show index.html for SPA routing
    error_page 404 =200 /index.html;

    # Disable access to hidden files and directories
    location ~ /\. {
        access_log off;
        log_not_found off;
        deny all;
    }

    # ============================================================================
    # Performance Optimizations
    # ============================================================================

    # Disable logging for static assets
    location ~* \.(js|css|svg|png|jpg|jpeg|gif|ico|woff|woff2|ttf|eot)$ {
        access_log off;
    }

    # Compress text responses
    gzip_vary on;
    gzip_comp_level 6;

    # ============================================================================
    # Request Logging
    # ============================================================================

    # Log format with request time
    log_format main '$remote_addr - $remote_user [$time_local] '
                    '"$request" $status $body_bytes_sent '
                    '"$http_referer" "$http_user_agent" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';

    access_log /var/log/nginx/access.log main;
    error_log /var/log/nginx/error.log warn;
}

# ============================================================================
# Configuration Notes:
# ============================================================================
# 1. SPA Routing: All requests go to index.html for React Router to handle
# 2. API Proxy: /api/* routes to http://api-gateway:8000 (Docker internal DNS)
# 3. Caching: Static assets cached aggressively, index.html never cached
# 4. Security: Headers set to prevent clickjacking, MIME sniffing, XSS
# 5. Compression: Gzip enabled for text/javascript/json
# 6. Health Checks: /health and /ready endpoints for monitoring
# 7. Error Handling: 404 errors redirect to index.html (SPA requirement)
# ============================================================================
```

---

## FILE 3: `frontend/.dockerignore`

**Location:** `/mnt/d/Bimo_max/crypto-trading-bot/frontend/.dockerignore`

**Copy and paste this entire content:**

```
# ============================================================================
# Docker Build Exclusions - Reduce build context size and build time
# ============================================================================

# Node modules - will be installed during build
node_modules
npm-debug.log
npm-error.log
yarn-error.log
pnpm-debug.log

# Distribution folder - will be recreated
dist

# IDE and Editor files - not needed in production
.vscode
.idea
*.swp
*.swo
*~
.DS_Store
.env.local
.env.*.local

# Version control
.git
.gitignore

# Build and test artifacts
coverage
.nyc_output
.cache

# Documentation
*.md
README.md

# Development files
.env
.env.development

# Other
.prettierrc
.eslintrc
jest.config.js
tsconfig.json
babel.config.js

# ============================================================================
# Why exclude these:
# - node_modules: Will be reinstalled via npm ci in Dockerfile
# - dist: Will be created by npm run build
# - .git: Not needed in production image
# - .env: Secrets shouldn't be in image
# - IDE files: Don't belong in production
# - Documentation: Reduces image size
# ============================================================================
```

---

## FILE 4: Update `docker-compose.yml`

**Location:** `/mnt/d/Bimo_max/crypto-trading-bot/docker-compose.yml`

**Add this service BEFORE the `networks:` section (around line 333):**

```yaml
  # Frontend Dashboard - React + Nginx
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: crypto-bot-frontend
    ports:
      - "3000:80"
    environment:
      # Optional: Pass API URL to frontend (can be used in env.js)
      - REACT_APP_API_URL=http://localhost:8000
      - VITE_API_URL=http://localhost:8000
    networks:
      - crypto-bot-network
    depends_on:
      api-gateway:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
    restart: unless-stopped
```

**Where to add it in the file:**
- Find the comment `# Sentiment Analysis Service` (around line 278)
- Scroll down to find the `networks:` section (around line 333)
- Add the frontend service block BEFORE the `networks:` section

**Example structure:**
```yaml
services:
  api-gateway:
    ...
  bybit-connector:
    ...
  market-data:
    ...
  # ... other services ...
  risk-metrics:
    ...

  # ADD FRONTEND SERVICE HERE
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    # ... rest of config ...

networks:
  crypto-bot-network:
    driver: bridge
    name: crypto-bot-network
```

---

## Step-by-Step Implementation

### Step 1: Create frontend/Dockerfile
```bash
# Navigate to frontend directory
cd /mnt/d/Bimo_max/crypto-trading-bot/frontend

# Create the Dockerfile
cat > Dockerfile << 'EOF'
# [PASTE FILE 1 CONTENT HERE]
EOF

# Verify it was created
ls -la Dockerfile
```

### Step 2: Create frontend/nginx.conf
```bash
# In the same frontend directory
cat > nginx.conf << 'EOF'
# [PASTE FILE 2 CONTENT HERE]
EOF

# Verify it was created
ls -la nginx.conf
```

### Step 3: Create frontend/.dockerignore
```bash
# In the same frontend directory
cat > .dockerignore << 'EOF'
# [PASTE FILE 3 CONTENT HERE]
EOF

# Verify it was created
ls -la .dockerignore
```

### Step 4: Update docker-compose.yml
```bash
# Navigate back to project root
cd /mnt/d/Bimo_max/crypto-trading-bot

# Edit docker-compose.yml and add frontend service
# Use your editor to insert the frontend service block before networks:
# OR use sed to insert it programmatically

# Verify the file looks correct
grep -A 10 "# Frontend Dashboard" docker-compose.yml
```

---

## Building and Testing

### Build the Docker Image
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# Build the frontend image
docker build -f frontend/Dockerfile -t crypto-bot-frontend:latest ./frontend

# Verify the image was created
docker images | grep crypto-bot-frontend
```

### Test Individual Container
```bash
# Run just the frontend container (for testing)
docker run -p 3000:80 --name test-frontend crypto-bot-frontend:latest

# In another terminal, test it
curl http://localhost:3000

# Stop and remove
docker stop test-frontend
docker rm test-frontend
```

### Run Full Docker Compose Stack
```bash
# Start all services including frontend
docker-compose up -d

# Check that frontend is running
docker ps | grep frontend

# View logs
docker logs crypto-bot-frontend

# Access in browser
# http://localhost:3000
```

### Verify Health Checks
```bash
# Check frontend health
docker exec crypto-bot-frontend wget -q --spider http://localhost/

# Check API Gateway health
docker exec crypto-bot-api-gateway curl -f http://localhost:8000/health

# View all service status
docker-compose ps
```

---

## Verification Checklist

After implementation, verify:

### File Creation
- [ ] `frontend/Dockerfile` exists and contains 50+ lines
- [ ] `frontend/nginx.conf` exists and contains 200+ lines
- [ ] `frontend/.dockerignore` exists
- [ ] `docker-compose.yml` contains frontend service block

### Build Verification
- [ ] `docker build` completes without errors
- [ ] Image size is ~50-100MB
- [ ] No warnings during build

### Container Verification
- [ ] `docker-compose up` starts all services
- [ ] `docker ps` shows crypto-bot-frontend running
- [ ] Health check shows healthy: `docker ps | grep frontend`

### Functional Verification
- [ ] `http://localhost:3000` loads dashboard
- [ ] Portfolio data displays
- [ ] Price tickers show
- [ ] No console errors in browser DevTools
- [ ] Network tab shows API requests working

### Service Communication
- [ ] Frontend can reach API Gateway
- [ ] API responses appear in Network tab
- [ ] CORS not blocking requests
- [ ] All dashboard features functional

---

## Common Issues and Solutions

### Issue: Docker build fails
```bash
# Check Dockerfile syntax
docker build --no-cache -f frontend/Dockerfile -t crypto-bot-frontend:test ./frontend

# View detailed error
docker build -f frontend/Dockerfile -t crypto-bot-frontend:test ./frontend 2>&1 | tail -20
```

### Issue: Container starts but shows error
```bash
# Check Nginx logs
docker logs crypto-bot-frontend

# Check if Nginx is running
docker exec crypto-bot-frontend ps aux | grep nginx

# Verify nginx.conf syntax
docker exec crypto-bot-frontend nginx -t
```

### Issue: API requests return 502 Bad Gateway
```bash
# Verify API Gateway is running
docker ps | grep api-gateway

# Check DNS resolution in container
docker exec crypto-bot-frontend nslookup api-gateway

# Check proxy configuration
docker exec crypto-bot-frontend cat /etc/nginx/conf.d/default.conf | grep -A 5 "api/"
```

### Issue: Port 3000 already in use
```bash
# Check what's using port 3000
lsof -i :3000  # macOS/Linux
netstat -ano | findstr :3000  # Windows

# Either kill it or change port in docker-compose.yml
# From: "3000:80"
# To:   "3001:80"
```

---

## Performance Tips

### Reduce Build Time
```bash
# Enable Docker BuildKit for faster parallel builds
DOCKER_BUILDKIT=1 docker build -f frontend/Dockerfile -t crypto-bot-frontend ./frontend
```

### Check Image Size
```bash
# View image layers and sizes
docker history crypto-bot-frontend:latest

# Keep image small by excluding unnecessary files in .dockerignore
```

### Monitor Container Performance
```bash
# Check container resource usage
docker stats crypto-bot-frontend

# View container logs in real-time
docker logs -f crypto-bot-frontend
```

---

## Integration with Other Services

### Frontend Network Communication
```
Frontend (port 3000)
    ↓
Nginx proxies /api/*
    ↓
http://api-gateway:8000 (internal Docker DNS)
    ↓
API Gateway routes to microservices
    ↓
Various services (8001-8009)
```

### Service Dependencies
```
frontend → api-gateway (MUST be healthy)
         ↓
       Services:
       - bybit-connector
       - market-data-service
       - technical-analysis
       - portfolio-manager
       - trading-engine
       - etc.
```

---

## Post-Implementation Checklist

- [ ] All 4 files created/modified
- [ ] Docker image builds successfully
- [ ] docker-compose.yml valid YAML
- [ ] All services start: `docker-compose up -d`
- [ ] Frontend accessible at http://localhost:3000
- [ ] Dashboard displays without errors
- [ ] Portfolio data loads
- [ ] API proxy works (check Network tab)
- [ ] Health checks pass
- [ ] No console errors in browser

---

## Next Steps

1. Create the 3 files (Dockerfile, nginx.conf, .dockerignore)
2. Update docker-compose.yml with frontend service
3. Build Docker image: `docker build -f frontend/Dockerfile -t crypto-bot-frontend ./frontend`
4. Test container: `docker run -p 3000:80 crypto-bot-frontend`
5. Run full stack: `docker-compose up -d`
6. Access dashboard: http://localhost:3000

---

**Implementation Time:** 15-20 minutes
**Difficulty:** Low (copy-paste code)
**Result:** Fully containerized production-ready frontend
