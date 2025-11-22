# Frontend Docker Configuration - Quick Checklist

**Status Date:** November 21, 2025

---

## Current State Summary

| Aspect | Status | Details |
|--------|--------|---------|
| **Frontend Code** | ✅ Complete | React + Vite, fully functional |
| **Development Server** | ✅ Working | npm run dev on port 3000 |
| **Production Build** | ✅ Working | npm run build creates dist/ |
| **API Integration** | ✅ Working | Connects to API Gateway (port 8000) |
| **Docker Image** | ❌ Missing | No Dockerfile for frontend |
| **Nginx Config** | ❌ Missing | No nginx.conf file |
| **Docker Compose** | ❌ Missing | Frontend service not defined |
| **CORS Setup** | ✅ Partial | API Gateway allows localhost:3000 |

---

## What's Missing - 3 Critical Files

### 1. Create: `/frontend/Dockerfile`
**Purpose:** Build React app and serve with Nginx
**Lines of Code:** ~30-40
**Priority:** CRITICAL
**Time:** 5 minutes

**Checklist:**
- [ ] Multi-stage build (builder + nginx stages)
- [ ] Node 18-alpine for build stage
- [ ] Nginx-alpine for serving stage
- [ ] Copy dist/ from builder to nginx
- [ ] Expose port 80
- [ ] Health check configured
- [ ] Production optimizations

---

### 2. Create: `/frontend/nginx.conf`
**Purpose:** Configure Nginx for SPA + API proxy
**Lines of Code:** ~40-50
**Priority:** CRITICAL
**Time:** 5 minutes

**Checklist:**
- [ ] Listen on port 80
- [ ] Serve static files from /usr/share/nginx/html
- [ ] Route all URLs to index.html (SPA routing)
- [ ] Proxy /api/* to API Gateway
- [ ] Enable gzip compression
- [ ] Set cache headers for static files
- [ ] Add security headers (CSP, X-Frame-Options, etc.)

---

### 3. Modify: `/docker-compose.yml`
**Purpose:** Add frontend service definition
**Lines of Code:** ~20-30 (addition)
**Priority:** CRITICAL
**Time:** 5 minutes

**Checklist:**
- [ ] Add frontend service block
- [ ] Build context: ./frontend
- [ ] Port mapping: 3000:80
- [ ] Network: crypto-bot-network
- [ ] Depends on: api-gateway (service_healthy)
- [ ] Health check configured
- [ ] Environment variables set
- [ ] Restart policy: unless-stopped

---

## Docker Configuration Details

### File 1: Dockerfile
```
Location: /mnt/d/Bimo_max/crypto-trading-bot/frontend/Dockerfile

Key Points:
- Use Node 18-alpine for build (small image)
- Install dependencies with npm ci (faster, locked versions)
- Run npm run build
- Copy dist/ to nginx container
- Use nginx:alpine for serving (lightweight)
- Port 80 inside container, expose to 3000 on host
- Health check: wget for http://localhost/
```

### File 2: nginx.conf
```
Location: /mnt/d/Bimo_max/crypto-trading-bot/frontend/nginx.conf

Key Points:
- Listen on port 80
- Serve static files from /usr/share/nginx/html
- Try files, fall back to index.html (SPA routing)
- Proxy /api to http://api-gateway:8000
- Gzip compression enabled
- Cache static assets for 1 year
- Security headers configured
```

### File 3: docker-compose.yml (addition)
```
Location: /mnt/d/Bimo_max/crypto-trading-bot/docker-compose.yml

Key Points:
- Service name: frontend
- Build: ./frontend (uses Dockerfile above)
- Port: 3000:80 (maps container port 80 to host 3000)
- Network: crypto-bot-network (communicates with other services)
- Depends on: api-gateway healthy
- Health check: wget to http://localhost/
- Restart: unless-stopped (auto-restart if crashes)
```

---

## Why Each File is Needed

### Dockerfile
**Why:** Packages the React app into a container image
- **Without it:** Can't run frontend in Docker
- **What it does:** Builds React bundle, serves it with Nginx
- **Output:** Container image that runs Nginx on port 80

### nginx.conf
**Why:** Configures how Nginx serves the React app
- **Without it:** Nginx won't know how to handle SPA routing
- **What it does:** Serves static files, proxies API calls
- **Key feature:** Redirects all URLs to index.html for React Router

### docker-compose.yml update
**Why:** Registers frontend service with other microservices
- **Without it:** Frontend runs separately, not with the system
- **What it does:** Starts frontend when docker-compose up runs
- **Connection:** Enables frontend to connect to API Gateway

---

## Integration Points

### Frontend ↔ API Gateway
```
Frontend Container     API Gateway Container
Port 80                Port 8000
(serves static files)  (handles /api requests)
        ↓
    Nginx proxies /api to http://api-gateway:8000
    (Docker network name resolution)
```

### Frontend ↔ Backend Services
```
Frontend → API Gateway (Port 8000)
         ↓
    Routes requests to:
    - Bybit Connector (8001)
    - Market Data (8002)
    - Portfolio Manager (8003)
    - Technical Analysis (8004)
    - Trading Engine (8005)
    - etc.
```

---

## Deployment Flow

### Development (Current)
```
1. cd frontend && npm run dev
2. Port 3000 (Vite dev server)
3. Hot reload enabled
4. Proxies /api to localhost:8000
```

### Docker Production (After Setup)
```
1. docker build -f frontend/Dockerfile -t crypto-bot-frontend ./frontend
2. docker-compose up (includes all services)
3. Port 3000 (Nginx serving dist/)
4. Proxies /api to api-gateway container
```

---

## Testing Checklist

After creating the files, test:

### Build Test
- [ ] `docker build -f frontend/Dockerfile -t crypto-bot-frontend ./frontend` succeeds
- [ ] Image size is reasonable (~50-100MB)
- [ ] No build warnings/errors

### Container Test
- [ ] `docker run -p 3000:80 crypto-bot-frontend` starts
- [ ] Access http://localhost:3000 shows dashboard
- [ ] No errors in docker logs

### Docker Compose Test
- [ ] Add service to docker-compose.yml
- [ ] `docker-compose up -d` starts all services
- [ ] Frontend container is healthy: `docker ps | grep frontend`
- [ ] Access http://localhost:3000 works
- [ ] Dashboard loads without errors

### API Integration Test
- [ ] Open http://localhost:3000
- [ ] Portfolio card shows data
- [ ] Price tickers display
- [ ] No console errors
- [ ] API calls work (check Network tab in DevTools)

---

## CORS Configuration

**Current Status (API Gateway):**
```
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
```

**After Containerization:**
Option 1: Keep localhost:3000 (if running docker-compose on localhost)
Option 2: Add http://frontend (internal Docker DNS)
Option 3: Add http://crypto-bot-frontend (full container name)

**Recommended:** Keep localhost:3000 as primary, add others if needed

---

## Port Mapping Summary

| Service | Inside Container | Host Port | Access From |
|---------|------------------|-----------|-------------|
| Frontend | 80 | 3000 | http://localhost:3000 |
| API Gateway | 8000 | 8000 | http://localhost:8000 |
| Other Services | various | 8001-8009 | Internal docker-compose |

---

## Quick Start After Setup

### First Time
```bash
cd /mnt/d/Bimo_max/crypto-trading-bot

# Create the 3 files (Dockerfile, nginx.conf, update docker-compose.yml)
# Then build and run

docker-compose up -d

# Wait for services to be healthy
sleep 30

# Access
open http://localhost:3000  # macOS
xdg-open http://localhost:3000  # Linux
start http://localhost:3000  # Windows
```

### Subsequent Runs
```bash
docker-compose up -d      # Start all services
docker-compose logs -f    # Watch logs
docker-compose down       # Stop all services
```

---

## Troubleshooting Guide

### Issue: Frontend container won't start
```bash
docker logs crypto-bot-frontend
# Check: Is Dockerfile created? Is nginx.conf present?
```

### Issue: API requests fail (404)
```bash
# Check: Is API Gateway running?
docker ps | grep api-gateway
# Check: Is /api proxy configured in nginx.conf?
# Check: Is API Gateway in ALLOWED_ORIGINS?
```

### Issue: Port 3000 already in use
```bash
# Change in docker-compose.yml:
# ports:
#   - "3001:80"  # Use different host port
```

### Issue: Build takes too long
```bash
# Use Docker BuildKit for faster builds:
DOCKER_BUILDKIT=1 docker build -f frontend/Dockerfile -t crypto-bot-frontend ./frontend
```

---

## Success Criteria

✅ All 3 files created and configured
✅ Docker build completes successfully
✅ docker-compose up starts all services
✅ Frontend accessible at http://localhost:3000
✅ Dashboard displays without errors
✅ API calls work (portfolio data loads)
✅ All other microservices accessible
✅ No console errors in browser

---

## Files to Create/Modify

### NEW FILES:
1. `frontend/Dockerfile` (30-40 lines)
2. `frontend/nginx.conf` (40-50 lines)
3. `frontend/.dockerignore` (5-10 lines, optional)

### MODIFY:
1. `docker-compose.yml` (add 20-30 lines for frontend service)

### TOTAL TIME: 15-20 minutes

---

## Next Steps

1. Create `frontend/Dockerfile`
2. Create `frontend/nginx.conf`
3. Update `docker-compose.yml` with frontend service
4. Build Docker image
5. Test with docker-compose up
6. Verify all integrations work

---

**Ready to implement?** All 3 files are simple, straightforward, and well-documented patterns.
