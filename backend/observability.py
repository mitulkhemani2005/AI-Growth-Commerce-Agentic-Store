"""
Observability & Telemetry — Metrics, Audit Tracing & Alert Aggregation
=======================================================================
Tracks tool execution metrics, agent latencies, error reports, and provides
executive alert aggregation to prevent notification spam to the CEO.
"""

import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


METRICS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_metrics.json"))
ALERTS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "agent_alerts.json"))
_obs_lock = threading.RLock()


class ObservabilityManager:
    """Manages structured telemetry, execution logs, and executive alert grouping."""

    def __init__(self):
        self._tool_executions: List[Dict[str, Any]] = []
        self._alerts: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        with _obs_lock:
            if os.path.exists(ALERTS_FILE):
                try:
                    with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                        self._alerts = json.load(f)
                except Exception:
                    self._alerts = []

    def _save_alerts(self):
        try:
            tmp_file = f"{ALERTS_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._alerts[:500], f, indent=2)
            os.replace(tmp_file, ALERTS_FILE)
        except Exception:
            try:
                with open(ALERTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._alerts[:500], f, indent=2)
            except Exception:
                pass

    def log_tool_execution(
        self,
        agent_name: str,
        tool_name: str,
        duration_ms: float,
        policy_result: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error: Optional[str] = None,
        operation_id: Optional[str] = None,
        event_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        confidence: Optional[float] = None,
        details: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records a structured tool execution telemetry event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ts": time.time(),
            "agent": agent_name,
            "tool": tool_name,
            "duration_ms": round(duration_ms, 2),
            "policy": policy_result.get("policy", "passed") if policy_result else "passed",
            "policy_allowed": policy_result.get("allowed", True) if policy_result else True,
            "success": success,
            "error": error,
            "operation_id": operation_id,
            "event_id": event_id,
            "correlation_id": correlation_id,
            "confidence": confidence,
            "details": (details or "")[:300]
        }
        with _obs_lock:
            self._tool_executions.append(entry)
            if len(self._tool_executions) > 1000:
                self._tool_executions = self._tool_executions[-1000:]
        return entry

    def create_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        source_agent: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Creates an alert entry."""
        alert = {
            "id": f"alt_{int(time.time()*1000)}",
            "alert_type": alert_type,
            "severity": severity,  # info, warning, high, critical
            "title": title,
            "message": message,
            "source_agent": source_agent,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ts": time.time(),
            "acknowledged": False
        }
        with _obs_lock:
            self._alerts.insert(0, alert)
            self._alerts = self._alerts[:500]
            self._save_alerts()
        return alert

    def aggregate_alerts(self, timeframe_seconds: float = 3600.0) -> List[Dict[str, Any]]:
        """
        Groups repetitive alerts within the timeframe into summarized executive insights.
        Prevents flooding CEO with raw message spam.
        """
        now_ts = time.time()
        with _obs_lock:
            recent_alerts = [a for a in self._alerts if (now_ts - a.get("timestamp_ts", 0.0)) <= timeframe_seconds]

        # Group by alert_type
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for a in recent_alerts:
            grouped[a.get("alert_type", "GENERAL")].append(a)

        summaries = []
        for a_type, items in grouped.items():
            count = len(items)
            severities = [i.get("severity") for i in items]
            max_severity = "critical" if "critical" in severities else ("high" if "high" in severities else ("warning" if "warning" in severities else "info"))

            if a_type == "PRODUCT_LOW_STOCK":
                skus = list({i.get("data", {}).get("product_name") or i.get("data", {}).get("product_id") for i in items if i.get("data")})
                summaries.append({
                    "type": a_type,
                    "title": f"📦 Inventory Risk: {len(skus)} SKUs below safety stock",
                    "count": count,
                    "severity": max_severity,
                    "summary": f"{len(skus)} products reached low stock thresholds ({', '.join(skus[:4])}{'...' if len(skus) > 4 else ''}). Restock evaluated.",
                    "latest_timestamp": items[0].get("timestamp")
                })
            elif a_type == "LOW_RATING_ALERT":
                summaries.append({
                    "type": a_type,
                    "title": f"⭐ Product Sentiment Risk: {count} low rating incidents",
                    "count": count,
                    "severity": max_severity,
                    "summary": f"Detected {count} low-rated review alerts. Review Manager investigating defect clusters.",
                    "latest_timestamp": items[0].get("timestamp")
                })
            elif a_type == "SLA_BREACH_ALERT":
                summaries.append({
                    "type": a_type,
                    "title": f"⏱️ Order SLA Alert: {count} orders pending confirmation > 1 hour",
                    "count": count,
                    "severity": max_severity,
                    "summary": f"{count} pending orders breached standard confirmation SLA threshold.",
                    "latest_timestamp": items[0].get("timestamp")
                })
            else:
                summaries.append({
                    "type": a_type,
                    "title": f"⚠️ {a_type}: {count} event(s)",
                    "count": count,
                    "severity": max_severity,
                    "summary": items[0].get("message", "Operational alert"),
                    "latest_timestamp": items[0].get("timestamp")
                })

        return summaries

    def get_tool_metrics(self) -> Dict[str, Any]:
        """Calculates call count, success rate, and average latency per tool."""
        with _obs_lock:
            logs = list(self._tool_executions)

        metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"calls": 0, "successes": 0, "failures": 0, "total_duration_ms": 0.0})
        for l in logs:
            t = l.get("tool", "unknown")
            metrics[t]["calls"] += 1
            if l.get("success"):
                metrics[t]["successes"] += 1
            else:
                metrics[t]["failures"] += 1
            metrics[t]["total_duration_ms"] += l.get("duration_ms", 0.0)

        result = {}
        for t, data in metrics.items():
            calls = data["calls"]
            result[t] = {
                "total_calls": calls,
                "success_rate_pct": round((data["successes"] / calls * 100), 1) if calls > 0 else 100.0,
                "failure_count": data["failures"],
                "avg_latency_ms": round((data["total_duration_ms"] / calls), 1) if calls > 0 else 0.0
            }
        return result

    def get_agent_activity(self, limit: int = 50, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        with _obs_lock:
            logs = list(self._tool_executions)
        if agent_name:
            logs = [l for l in logs if agent_name.lower() in l.get("agent", "").lower()]
        return logs[-limit:]

    def get_agent_error_report(self, limit: int = 50) -> List[Dict[str, Any]]:
        with _obs_lock:
            errors = [l for l in self._tool_executions if not l.get("success") or l.get("error")]
        return errors[-limit:]


# Singleton
observability_manager = ObservabilityManager()
