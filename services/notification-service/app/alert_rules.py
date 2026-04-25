"""
Alert Rules Engine
Handles suppression, throttling, quiet hours, and escalation logic
"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
import pytz

from .config import config, AlertSeverity, AlertType
from .models import Alert, SuppressionRule, EscalationRule

logger = logging.getLogger(__name__)


@dataclass
class SuppressionResult:
    """Result of suppression check"""
    suppressed: bool
    reason: Optional[str] = None
    rule_id: Optional[str] = None


@dataclass
class AlertRecord:
    """Record for tracking alerts for suppression"""
    alert_id: str
    dedup_key: str
    alert_type: AlertType
    severity: AlertSeverity
    timestamp: datetime
    acknowledged: bool = False


class AlertRulesEngine:
    """
    Engine for processing alert rules

    Features:
    - Deduplication of identical alerts
    - Throttling repeated alerts
    - Quiet hours enforcement
    - Alert fatigue prevention
    - Escalation for unacknowledged critical alerts
    """

    def __init__(self):
        """Initialize the alert rules engine"""
        # In-memory storage for alert tracking
        self._alert_history: Dict[str, List[AlertRecord]] = defaultdict(list)
        self._dedup_cache: Dict[str, datetime] = {}

        # Suppression rules
        self._suppression_rules: List[SuppressionRule] = self._load_default_suppression_rules()

        # Escalation rules
        self._escalation_rules: List[EscalationRule] = self._load_default_escalation_rules()

        # User preferences (would be loaded from database in production)
        self._user_preferences: Dict[str, Dict[str, Any]] = {}

        logger.info("Alert rules engine initialized")

    def _load_default_suppression_rules(self) -> List[SuppressionRule]:
        """Load default suppression rules from config"""
        return [
            SuppressionRule(
                id="dedup_default",
                name="Deduplicate identical alerts",
                enabled=True,
                rule_type="dedup",
                conditions={
                    "window_seconds": config.dedup_window_seconds
                }
            ),
            SuppressionRule(
                id="throttle_default",
                name="Throttle repeated alerts",
                enabled=True,
                rule_type="throttle",
                conditions={
                    "max_per_hour": config.throttle_max_per_hour
                }
            ),
            SuppressionRule(
                id="quiet_hours",
                name="Quiet hours suppression",
                enabled=config.quiet_hours_enabled,
                rule_type="quiet_hours",
                severities=[AlertSeverity.LOW, AlertSeverity.INFO],
                conditions={
                    "start": config.quiet_hours_start,
                    "end": config.quiet_hours_end,
                    "timezone": config.quiet_hours_timezone
                }
            )
        ]

    def _load_default_escalation_rules(self) -> List[EscalationRule]:
        """Load default escalation rules from config"""
        from .models import NotificationChannel

        return [
            EscalationRule(
                id="critical_ack_timeout",
                name="Escalate unacknowledged critical alerts",
                enabled=config.sms_enabled,
                severity=AlertSeverity.CRITICAL,
                timeout_seconds=config.critical_ack_timeout,
                escalate_to_channel=NotificationChannel.SMS,
                notify_contact=config.emergency_contact
            ),
            EscalationRule(
                id="system_down_escalation",
                name="Escalate prolonged system downtime",
                enabled=config.sms_enabled,
                severity=AlertSeverity.CRITICAL,
                timeout_seconds=config.system_down_escalation,
                escalate_to_channel=NotificationChannel.SMS,
                notify_contact=config.emergency_contact
            )
        ]

    def should_suppress(self, alert: Alert) -> SuppressionResult:
        """
        Check if an alert should be suppressed based on rules

        Args:
            alert: The alert to check

        Returns:
            SuppressionResult with suppression status and reason
        """
        for rule in self._suppression_rules:
            if not rule.enabled:
                continue

            # Check if rule applies to this alert type/severity
            if rule.alert_types and alert.alert_type not in rule.alert_types:
                continue
            if rule.severities and alert.severity not in rule.severities:
                continue

            # Apply rule
            result = self._apply_suppression_rule(alert, rule)
            if result.suppressed:
                logger.info(f"Alert suppressed by rule '{rule.name}': {result.reason}")
                return result

        return SuppressionResult(suppressed=False)

    def _apply_suppression_rule(
        self,
        alert: Alert,
        rule: SuppressionRule
    ) -> SuppressionResult:
        """
        Apply a specific suppression rule

        Args:
            alert: The alert to check
            rule: The rule to apply

        Returns:
            SuppressionResult
        """
        if rule.rule_type == "dedup":
            return self._check_dedup(alert, rule)
        elif rule.rule_type == "throttle":
            return self._check_throttle(alert, rule)
        elif rule.rule_type == "quiet_hours":
            return self._check_quiet_hours(alert, rule)
        elif rule.rule_type == "custom":
            return self._check_custom_rule(alert, rule)

        return SuppressionResult(suppressed=False)

    def _check_dedup(self, alert: Alert, rule: SuppressionRule) -> SuppressionResult:
        """
        Check for duplicate alerts within window

        Args:
            alert: The alert to check
            rule: The dedup rule

        Returns:
            SuppressionResult
        """
        window_seconds = rule.conditions.get("window_seconds", 300)

        # Generate dedup key
        dedup_key = self._generate_dedup_key(alert)
        alert.dedup_key = dedup_key

        # Check cache
        now = datetime.utcnow()
        if dedup_key in self._dedup_cache:
            last_sent = self._dedup_cache[dedup_key]
            if (now - last_sent).total_seconds() < window_seconds:
                return SuppressionResult(
                    suppressed=True,
                    reason=f"Duplicate alert (within {window_seconds}s window)",
                    rule_id=rule.id
                )

        # Update cache
        self._dedup_cache[dedup_key] = now

        # Clean old entries
        self._cleanup_dedup_cache(window_seconds)

        return SuppressionResult(suppressed=False)

    def _check_throttle(self, alert: Alert, rule: SuppressionRule) -> SuppressionResult:
        """
        Check throttle limit for alert type

        Args:
            alert: The alert to check
            rule: The throttle rule

        Returns:
            SuppressionResult
        """
        max_per_hour = rule.conditions.get("max_per_hour", 3)

        # Get recent alerts of same type
        alert_key = f"{alert.alert_type}_{alert.severity}"
        history = self._alert_history[alert_key]

        # Count alerts in last hour
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)
        recent_count = sum(1 for h in history if h.timestamp > one_hour_ago)

        if recent_count >= max_per_hour:
            return SuppressionResult(
                suppressed=True,
                reason=f"Throttled (max {max_per_hour}/hour exceeded)",
                rule_id=rule.id
            )

        # Record this alert
        history.append(AlertRecord(
            alert_id=alert.id,
            dedup_key=alert.dedup_key or "",
            alert_type=alert.alert_type,
            severity=alert.severity,
            timestamp=now
        ))

        # Clean old entries
        self._alert_history[alert_key] = [
            h for h in history if h.timestamp > one_hour_ago
        ]

        return SuppressionResult(suppressed=False)

    def _check_quiet_hours(
        self,
        alert: Alert,
        rule: SuppressionRule
    ) -> SuppressionResult:
        """
        Check if current time is within quiet hours

        Args:
            alert: The alert to check
            rule: The quiet hours rule

        Returns:
            SuppressionResult
        """
        start_str = rule.conditions.get("start", "22:00")
        end_str = rule.conditions.get("end", "08:00")
        tz_str = rule.conditions.get("timezone", "UTC")

        try:
            tz = pytz.timezone(tz_str)
        except Exception:
            tz = pytz.UTC

        now = datetime.now(tz)
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        current_time = now.time()

        # Check if in quiet hours (handles overnight periods)
        in_quiet_hours = False
        if start_time > end_time:
            # Overnight (e.g., 22:00 - 08:00)
            in_quiet_hours = current_time >= start_time or current_time < end_time
        else:
            # Same day (e.g., 01:00 - 06:00)
            in_quiet_hours = start_time <= current_time < end_time

        if in_quiet_hours:
            return SuppressionResult(
                suppressed=True,
                reason=f"Quiet hours ({start_str} - {end_str} {tz_str})",
                rule_id=rule.id
            )

        return SuppressionResult(suppressed=False)

    def _check_custom_rule(
        self,
        alert: Alert,
        rule: SuppressionRule
    ) -> SuppressionResult:
        """
        Check custom suppression rule

        Args:
            alert: The alert to check
            rule: The custom rule

        Returns:
            SuppressionResult
        """
        # Custom rules would be evaluated here
        # For now, just return not suppressed
        return SuppressionResult(suppressed=False)

    def _generate_dedup_key(self, alert: Alert) -> str:
        """
        Generate deduplication key for an alert

        Args:
            alert: The alert

        Returns:
            Hash string for deduplication
        """
        # Combine type, severity, title, and key metadata
        key_parts = [
            alert.alert_type.value,
            alert.severity.value,
            alert.title,
            alert.source
        ]

        # Add relevant metadata
        if alert.metadata:
            for key in ["symbol", "service", "error_type"]:
                if key in alert.metadata:
                    key_parts.append(str(alert.metadata[key]))

        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _cleanup_dedup_cache(self, max_age_seconds: int):
        """Clean old entries from dedup cache"""
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds * 2)
        self._dedup_cache = {
            k: v for k, v in self._dedup_cache.items()
            if v > cutoff
        }

    def check_escalation(self, alert: Alert) -> Optional[EscalationRule]:
        """
        Check if an alert needs escalation

        Args:
            alert: The alert to check

        Returns:
            EscalationRule if escalation needed, None otherwise
        """
        if alert.is_acknowledged:
            return None

        for rule in self._escalation_rules:
            if not rule.enabled:
                continue

            if alert.severity != rule.severity:
                continue

            # Check timeout
            age = (datetime.utcnow() - alert.created_at).total_seconds()
            if age >= rule.timeout_seconds:
                logger.warning(f"Alert {alert.id} needs escalation: {rule.name}")
                return rule

        return None

    def get_combined_alerts(
        self,
        alerts: List[Alert],
        window_seconds: int = 60
    ) -> List[Tuple[str, List[Alert]]]:
        """
        Group related alerts for combined notification

        Args:
            alerts: List of alerts
            window_seconds: Time window for grouping

        Returns:
            List of (group_key, alerts) tuples
        """
        groups: Dict[str, List[Alert]] = defaultdict(list)

        for alert in alerts:
            # Group by type and source
            group_key = f"{alert.alert_type.value}_{alert.source}"
            groups[group_key].append(alert)

        return list(groups.items())

    # ========================================
    # Rule Management
    # ========================================

    def get_suppression_rules(self) -> List[SuppressionRule]:
        """Get all suppression rules"""
        return self._suppression_rules.copy()

    def update_suppression_rules(self, rules: List[SuppressionRule]):
        """Update suppression rules"""
        self._suppression_rules = rules
        logger.info(f"Updated {len(rules)} suppression rules")

    def get_escalation_rules(self) -> List[EscalationRule]:
        """Get all escalation rules"""
        return self._escalation_rules.copy()

    def update_escalation_rules(self, rules: List[EscalationRule]):
        """Update escalation rules"""
        self._escalation_rules = rules
        logger.info(f"Updated {len(rules)} escalation rules")

    def add_suppression_rule(self, rule: SuppressionRule):
        """Add a new suppression rule"""
        self._suppression_rules.append(rule)
        logger.info(f"Added suppression rule: {rule.name}")

    def remove_suppression_rule(self, rule_id: str) -> bool:
        """Remove a suppression rule by ID"""
        original_count = len(self._suppression_rules)
        self._suppression_rules = [
            r for r in self._suppression_rules if r.id != rule_id
        ]
        removed = len(self._suppression_rules) < original_count
        if removed:
            logger.info(f"Removed suppression rule: {rule_id}")
        return removed

    # ========================================
    # User Preferences
    # ========================================

    def set_user_preferences(self, user_id: str, preferences: Dict[str, Any]):
        """Set user-specific alert preferences"""
        self._user_preferences[user_id] = preferences
        logger.info(f"Updated preferences for user: {user_id}")

    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user-specific alert preferences"""
        return self._user_preferences.get(user_id)

    def get_user_channels(
        self,
        user_id: str,
        severity: AlertSeverity
    ) -> Optional[List[str]]:
        """
        Get user's preferred channels for a severity level

        Args:
            user_id: User identifier
            severity: Alert severity

        Returns:
            List of channel names or None to use defaults
        """
        prefs = self._user_preferences.get(user_id)
        if not prefs:
            return None

        channel_prefs = prefs.get("channels", {})
        return channel_prefs.get(severity.value)

    def is_alert_type_muted(self, user_id: str, alert_type: AlertType) -> bool:
        """Check if user has muted an alert type"""
        prefs = self._user_preferences.get(user_id)
        if not prefs:
            return False

        muted_types = prefs.get("muted_types", [])
        return alert_type.value in muted_types

    # ========================================
    # Statistics
    # ========================================

    def get_suppression_stats(self) -> Dict[str, Any]:
        """Get suppression statistics"""
        total_tracked = sum(len(h) for h in self._alert_history.values())
        dedup_entries = len(self._dedup_cache)

        return {
            "total_alerts_tracked": total_tracked,
            "dedup_cache_size": dedup_entries,
            "suppression_rules_count": len(self._suppression_rules),
            "escalation_rules_count": len(self._escalation_rules),
            "user_preferences_count": len(self._user_preferences)
        }

    def clear_history(self):
        """Clear alert history (for testing)"""
        self._alert_history.clear()
        self._dedup_cache.clear()
        logger.info("Cleared alert history")


# Create global rules engine instance
alert_rules_engine = AlertRulesEngine()
