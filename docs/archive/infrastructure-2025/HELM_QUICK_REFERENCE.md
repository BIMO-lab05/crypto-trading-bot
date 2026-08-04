# Helm Quick Reference Guide
## Crypto Trading Bot Operations

Quick commands for daily operations and troubleshooting.

---

## Installation

```bash
# Development
cd infrastructure/helm/scripts
./install.sh dev crypto-bot crypto-trading-bot

# Staging
./install.sh staging crypto-bot-staging crypto-trading-bot

# Production
./install.sh prod crypto-bot-prod crypto-trading-bot
```

---

## Upgrade

```bash
# Upgrade any environment
./upgrade.sh [dev|staging|prod] [namespace] [release-name]

# Example: Upgrade production
./upgrade.sh prod crypto-bot-prod crypto-trading-bot
```

---

## Rollback

```bash
# Rollback to previous version
helm rollback crypto-trading-bot -n crypto-bot

# Rollback to specific revision
helm rollback crypto-trading-bot 3 -n crypto-bot

# View history
helm history crypto-trading-bot -n crypto-bot
```

---

## Monitoring

```bash
# Check pod status
kubectl get pods -n crypto-bot

# Watch pods
kubectl get pods -n crypto-bot --watch

# Check resource usage
kubectl top pods -n crypto-bot
kubectl top nodes

# View HPA status
kubectl get hpa -n crypto-bot

# Check service status
kubectl get svc -n crypto-bot

# View ingress
kubectl get ingress -n crypto-bot
```

---

## Logs

```bash
# View logs for specific service
kubectl logs -f -n crypto-bot -l app=api-gateway

# View logs for specific pod
kubectl logs -f -n crypto-bot pod-name

# View logs from all containers
kubectl logs -f -n crypto-bot pod-name --all-containers

# View previous container logs
kubectl logs -n crypto-bot pod-name --previous

# Tail last 100 lines
kubectl logs -n crypto-bot pod-name --tail=100
```

---

## Debugging

```bash
# Describe pod
kubectl describe pod pod-name -n crypto-bot

# Get events
kubectl get events -n crypto-bot --sort-by='.lastTimestamp'

# Execute command in pod
kubectl exec -it pod-name -n crypto-bot -- /bin/sh

# Port forward to local
kubectl port-forward -n crypto-bot svc/api-gateway 8000:8000

# Test connectivity
kubectl run test-curl --image=curlimages/curl --rm -i --restart=Never \
  -n crypto-bot \
  -- curl -s http://api-gateway:8000/health
```

---

## Scaling

```bash
# Manual scaling
kubectl scale deployment api-gateway --replicas=5 -n crypto-bot

# View autoscaling status
kubectl get hpa -n crypto-bot

# Edit HPA
kubectl edit hpa api-gateway -n crypto-bot

# Disable autoscaling temporarily
kubectl patch hpa api-gateway -n crypto-bot -p '{"spec":{"minReplicas":1,"maxReplicas":1}}'
```

---

## Configuration

```bash
# View current values
helm get values crypto-trading-bot -n crypto-bot

# View all values (including defaults)
helm get values crypto-trading-bot -n crypto-bot --all

# Update single value
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  --reuse-values \
  --set api-gateway.replicaCount=5

# Update with new values file
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  -f custom-values.yaml
```

---

## Secrets

```bash
# Create secret
kubectl create secret generic my-secret \
  --from-literal=key=value \
  -n crypto-bot

# View secrets (names only)
kubectl get secrets -n crypto-bot

# Decode secret
kubectl get secret postgresql-secret -n crypto-bot -o jsonpath='{.data.password}' | base64 -d

# Edit secret
kubectl edit secret postgresql-secret -n crypto-bot

# Delete secret
kubectl delete secret my-secret -n crypto-bot
```

---

## Database Operations

```bash
# PostgreSQL
kubectl exec -it postgresql-0 -n crypto-bot -- psql -U cryptobot

# TimescaleDB
kubectl exec -it timescaledb-0 -n crypto-bot -- psql -U timescale

# Redis
kubectl exec -it redis-0 -n crypto-bot -- redis-cli

# RabbitMQ Management
kubectl port-forward -n crypto-bot svc/rabbitmq 15672:15672
# Open: http://localhost:15672
```

---

## Backup and Restore

```bash
# Backup PostgreSQL
kubectl exec -n crypto-bot postgresql-0 -- \
  pg_dump -U cryptobot cryptobot > backup-$(date +%Y%m%d).sql

# Restore PostgreSQL
kubectl exec -i -n crypto-bot postgresql-0 -- \
  psql -U cryptobot cryptobot < backup.sql

# Backup Helm values
helm get values crypto-trading-bot -n crypto-bot > backup-values.yaml

# Backup all Kubernetes resources
kubectl get all,pvc,secrets,configmaps -n crypto-bot -o yaml > backup-k8s.yaml
```

---

## Testing

```bash
# Run Helm tests
helm test crypto-trading-bot -n crypto-bot

# Run automated test suite
cd infrastructure/helm/scripts
./test.sh crypto-bot crypto-trading-bot

# Health check all services
for svc in api-gateway trading-engine portfolio-manager technical-analysis; do
  kubectl run test-$svc --image=curlimages/curl --rm -i --restart=Never \
    -n crypto-bot \
    -- curl -s http://$svc:800x/health && echo "$svc: OK" || echo "$svc: FAIL"
done
```

---

## Restart Services

```bash
# Restart deployment
kubectl rollout restart deployment api-gateway -n crypto-bot

# Restart all deployments
kubectl rollout restart deployment --all -n crypto-bot

# Check rollout status
kubectl rollout status deployment api-gateway -n crypto-bot

# View rollout history
kubectl rollout history deployment api-gateway -n crypto-bot
```

---

## Emergency Operations

```bash
# Stop all trading (scale trading-engine to 0)
kubectl scale deployment trading-engine --replicas=0 -n crypto-bot

# Emergency pod deletion
kubectl delete pod pod-name -n crypto-bot --force --grace-period=0

# Drain node for maintenance
kubectl drain node-name --ignore-daemonsets --delete-emptydir-data

# Uncordon node after maintenance
kubectl uncordon node-name
```

---

## Uninstall

```bash
# Uninstall (keep PVCs)
./uninstall.sh crypto-bot crypto-trading-bot

# Complete uninstall (delete everything)
./uninstall.sh crypto-bot crypto-trading-bot true true

# Manual uninstall
helm uninstall crypto-trading-bot -n crypto-bot
kubectl delete namespace crypto-bot
```

---

## Helm Commands

```bash
# List releases
helm list -n crypto-bot

# Get release info
helm status crypto-trading-bot -n crypto-bot

# Get manifest
helm get manifest crypto-trading-bot -n crypto-bot

# Get notes
helm get notes crypto-trading-bot -n crypto-bot

# Get hooks
helm get hooks crypto-trading-bot -n crypto-bot

# Dry-run upgrade
helm upgrade crypto-trading-bot ./crypto-trading-bot \
  -n crypto-bot \
  -f values-prod.yaml \
  --dry-run --debug
```

---

## Resource Cleanup

```bash
# Delete completed pods
kubectl delete pods -n crypto-bot --field-selector=status.phase==Succeeded

# Delete evicted pods
kubectl delete pods -n crypto-bot --field-selector=status.phase==Failed

# Delete old replica sets
kubectl delete replicaset -n crypto-bot --all

# Cleanup orphaned PVCs
kubectl get pvc -n crypto-bot | grep Released | awk '{print $1}' | xargs kubectl delete pvc -n crypto-bot
```

---

## Performance Tuning

```bash
# View resource requests/limits
kubectl describe nodes | grep -A 5 "Allocated resources"

# Edit resource limits
kubectl edit deployment api-gateway -n crypto-bot

# Update HPA thresholds
kubectl patch hpa api-gateway -n crypto-bot \
  -p '{"spec":{"targetCPUUtilizationPercentage":60}}'
```

---

## Networking

```bash
# View services
kubectl get svc -n crypto-bot

# View endpoints
kubectl get endpoints -n crypto-bot

# View network policies
kubectl get networkpolicies -n crypto-bot

# Test DNS
kubectl run test-dns --image=busybox --rm -i --restart=Never \
  -n crypto-bot \
  -- nslookup api-gateway
```

---

## Troubleshooting Common Issues

### Pod CrashLoopBackOff

```bash
# View logs
kubectl logs pod-name -n crypto-bot

# View previous logs
kubectl logs pod-name -n crypto-bot --previous

# Describe pod
kubectl describe pod pod-name -n crypto-bot

# Check events
kubectl get events -n crypto-bot | grep pod-name
```

### ImagePullBackOff

```bash
# Check image name
kubectl describe pod pod-name -n crypto-bot | grep Image

# Verify image pull secrets
kubectl get secrets -n crypto-bot

# Test image pull
docker pull registry/image:tag
```

### Pending Pods

```bash
# Check node resources
kubectl top nodes

# Describe pod to see reason
kubectl describe pod pod-name -n crypto-bot

# Check PVC status
kubectl get pvc -n crypto-bot
```

### Service Not Reachable

```bash
# Check service endpoints
kubectl get endpoints service-name -n crypto-bot

# Check if pods are ready
kubectl get pods -n crypto-bot -l app=service-name

# Test from another pod
kubectl run test-svc --image=curlimages/curl --rm -i --restart=Never \
  -n crypto-bot \
  -- curl -v http://service-name:port/health
```

---

## Grafana Access

```bash
# Port forward
kubectl port-forward -n crypto-bot svc/grafana 3000:3000

# Get admin password
kubectl get secret grafana-secret -n crypto-bot -o jsonpath='{.data.password}' | base64 -d

# Open browser
http://localhost:3000
```

---

## Prometheus Access

```bash
# Port forward
kubectl port-forward -n crypto-bot svc/prometheus 9090:9090

# Open browser
http://localhost:9090
```

---

## Quick Health Check

```bash
#!/bin/bash
# Save as health-check.sh

NAMESPACE="crypto-bot"

echo "=== Pod Status ==="
kubectl get pods -n $NAMESPACE

echo -e "\n=== Unhealthy Pods ==="
kubectl get pods -n $NAMESPACE --field-selector=status.phase!=Running,status.phase!=Succeeded

echo -e "\n=== HPA Status ==="
kubectl get hpa -n $NAMESPACE

echo -e "\n=== Resource Usage ==="
kubectl top pods -n $NAMESPACE 2>/dev/null || echo "Metrics server not available"

echo -e "\n=== Recent Events ==="
kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -10
```

---

## Environment Variables

Common environment variables to set:

```bash
export KUBECONFIG=~/.kube/config
export NAMESPACE=crypto-bot
export RELEASE_NAME=crypto-trading-bot
export HELM_CHART_PATH=./infrastructure/helm/crypto-trading-bot

# Then use
kubectl get pods -n $NAMESPACE
helm status $RELEASE_NAME -n $NAMESPACE
```

---

## Aliases

Add to ~/.bashrc or ~/.zshrc:

```bash
# Kubernetes aliases
alias k='kubectl'
alias kgp='kubectl get pods'
alias kgs='kubectl get svc'
alias kd='kubectl describe'
alias kl='kubectl logs'
alias ke='kubectl exec -it'

# Namespace-specific
alias kcb='kubectl -n crypto-bot'
alias kcbp='kubectl get pods -n crypto-bot'
alias kcbl='kubectl logs -n crypto-bot'

# Helm aliases
alias h='helm'
alias hls='helm list'
alias hst='helm status'
alias hup='helm upgrade'
```

---

## Important Files

```
Main Chart: infrastructure/helm/crypto-trading-bot/
Values:     infrastructure/helm/crypto-trading-bot/values-[env].yaml
Scripts:    infrastructure/helm/scripts/
Docs:       infrastructure/helm/README.md
```

---

## Support

- **Documentation**: /infrastructure/helm/README.md
- **Summary**: /infrastructure/helm/HELM_DEPLOYMENT_SUMMARY.md
- **This Guide**: /infrastructure/helm/QUICK_REFERENCE.md

---

**Last Updated**: 2025-11-23
