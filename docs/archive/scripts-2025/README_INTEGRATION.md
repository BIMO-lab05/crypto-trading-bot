# Infrastructure Integration Scripts

## Quick Start

### Integrate All Services (Recommended)
```bash
# Preview changes first (dry run)
python scripts/integrate_infrastructure.py --all --dry-run

# Apply changes to all services
python scripts/integrate_infrastructure.py --all
```

### Integrate Single Service
```bash
# Integrate specific service
python scripts/integrate_infrastructure.py --service trading-engine

# Available services:
# - api-gateway (already integrated ✅)
# - trading-engine
# - market-data-service
# - technical-analysis
# - portfolio-manager
# - bybit-connector
# - risk-metrics-service
# - ml-prediction-service
# - sentiment-analysis-service
# - notification-service
```

## What This Script Does

The integration script automatically:

1. **Adds Structured Logging**
   - Replaces basic `logging.basicConfig()` with `StructuredLogger`
   - Adds JSON formatting for production logs
   - Implements request ID tracking

2. **Integrates Graceful Shutdown**
   - Adds `GracefulShutdownHandler`
   - Sets up SIGTERM/SIGINT signal handlers
   - Implements ordered cleanup (LIFO)

3. **Creates Backups**
   - Backs up original files as `.bak` before modification
   - Allows easy rollback if needed

## Before Running

### Check Dependencies
```bash
# Ensure shared utilities are installed
pip install -r shared/requirements-base.txt

# Required packages:
# - python-json-logger==2.0.7
# - structlog==23.2.0
```

### Verify Service Structure
The script expects this structure:
```
services/
└── [service-name]/
    └── app/
        └── main.py
```

## After Integration

### 1. Review Changes
```bash
# Check what changed
diff services/[service-name]/app/main.py.bak services/[service-name]/app/main.py
```

### 2. Test Service
```bash
# Start service
cd services/[service-name]
uvicorn app.main:app --reload

# Check health endpoint
curl http://localhost:8000/health

# Check logs (should be JSON format)
tail -f logs/service.log
```

### 3. Update Log Statements (Manual)
The script updates the logging setup, but individual log statements need manual migration:

```python
# Before
logger.info(f"Processing {symbol} with interval {interval}")

# After (structured format)
logger.info("Processing symbol", symbol=symbol, interval=interval)
```

### 4. Test Graceful Shutdown
```bash
# Start service
uvicorn app.main:app

# Press Ctrl+C and verify:
# - "Initiating graceful shutdown" message appears
# - Resources are cleaned up
# - Database connections are closed
# - Process exits within 30 seconds
```

## Rollback

If you need to rollback changes:

```bash
# Restore backup for specific service
cd services/[service-name]/app
cp main.py.bak main.py

# Restart service
docker-compose restart [service-name]
```

## Troubleshooting

### Error: "Module not found: utils"
**Cause:** Python can't find shared utilities
**Fix:** Check that sys.path is set correctly in main.py:
```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
```

### Error: "python-json-logger not installed"
**Cause:** Missing dependency
**Fix:**
```bash
pip install python-json-logger==2.0.7
# or
pip install -r shared/requirements-base.txt
```

### Error: Service won't start after integration
**Cause:** Syntax error or missing import
**Fix:**
1. Check service logs for errors
2. Review the changes with `diff`
3. Restore backup if needed
4. Report issue for manual review

## What's NOT Automated

These tasks require manual attention:

1. **Updating log statements** - Convert f-strings to structured format
2. **Adding circuit breakers** - Wrap external API calls
3. **Database pool configuration** - Service-specific settings
4. **Custom cleanup handlers** - Service-specific resources

## Next Steps After Integration

1. Update individual log statements to structured format
2. Add circuit breakers for external API calls
3. Configure database connection pools
4. Test in staging environment
5. Deploy to production

## Getting Help

- **Documentation:** `/docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md`
- **Status Tracker:** `/docs/INFRASTRUCTURE_STATUS.md`
- **Reference Implementation:** `services/api-gateway/app/main.py`

## Script Options

```bash
--service NAME    Integrate specific service
--all            Integrate all services
--dry-run        Preview changes without modifying files
--help           Show help message
```

## Examples

```bash
# Preview all changes
python scripts/integrate_infrastructure.py --all --dry-run

# Integrate trading engine
python scripts/integrate_infrastructure.py --service trading-engine

# Integrate all except api-gateway (already done)
python scripts/integrate_infrastructure.py --all

# Check specific service
python scripts/integrate_infrastructure.py --service portfolio-manager --dry-run
```
