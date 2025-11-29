import logging
import os
from typing import Any, Dict, Optional, Tuple

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil is normally installed
    psutil = None

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None

from ..utils.time import iso_utc
from ..celery_app import celery_app
from ..config import settings

logger = logging.getLogger(__name__)


def _bytes_to_mb(value: float | int) -> float:
    return float(value) / (1024 * 1024)


def _bytes_to_gb(value: float | int) -> float:
    return float(value) / (1024 * 1024 * 1024)


def _get_load_average() -> Tuple[Optional[float], Optional[float], Optional[float]]:
    try:
        load1, load5, load15 = os.getloadavg()  # type: ignore[attr-defined]
        return float(load1), float(load5), float(load15)
    except (OSError, AttributeError):
        return (None, None, None)


def _get_cpu_pct() -> float:
    if not psutil:
        return -1.0
    try:
        return float(psutil.cpu_percent(interval=0.2))
    except Exception:
        return -1.0


def _get_memory_stats() -> Optional[Dict[str, float]]:
    if not psutil:
        return None
    try:
        vm = psutil.virtual_memory()
        return {
            "percent": float(vm.percent),
            "available_mb": _bytes_to_mb(vm.available),
            "total_mb": _bytes_to_mb(vm.total),
        }
    except Exception:
        return None


def _get_disk_stats(path: str) -> Optional[Dict[str, float]]:
    path = path or "/"
    try:
        if psutil:
            usage = psutil.disk_usage(path)
            return {
                "percent": float(usage.percent),
                "free_gb": _bytes_to_gb(usage.free),
                "total_gb": _bytes_to_gb(usage.total),
            }
    except Exception:
        pass

    try:
        stat = os.statvfs(path)
        total = stat.f_frsize * stat.f_blocks
        free = stat.f_frsize * stat.f_bavail
        used = total - free
        percent = (used / total * 100) if total else 0.0
        return {
            "percent": float(percent),
            "free_gb": _bytes_to_gb(free),
            "total_gb": _bytes_to_gb(total),
        }
    except Exception:
        return None


def _evaluate_cpu_metric() -> Dict[str, Any]:
    pct = _get_cpu_pct()
    load1, load5, load15 = _get_load_average()
    cpu_count = psutil.cpu_count(logical=True) if psutil else os.cpu_count()

    metric: Dict[str, Any] = {
        "status": "unknown" if pct < 0 else "ok",
        "value": None if pct < 0 else pct,
        "threshold_pct": settings.health.cpu_warn_pct,
        "load_avg": {"1m": load1, "5m": load5, "15m": load15},
        "cores": cpu_count,
    }

    if pct >= 0 and pct >= settings.health.cpu_warn_pct:
        metric["status"] = "warning"
        metric["message"] = f"CPU usage {pct:.1f}% exceeds threshold {settings.health.cpu_warn_pct}%"

    return metric


def _evaluate_memory_metric() -> Dict[str, Any]:
    stats = _get_memory_stats()
    metric: Dict[str, Any] = {
        "status": "unknown",
        "value": None,
        "threshold_pct": settings.health.mem_warn_pct,
        "min_available_mb": settings.health.mem_min_available_mb,
    }

    if not stats:
        metric["message"] = "Memory metrics unavailable (psutil missing?)"
        return metric

    metric["status"] = "ok"
    metric["value"] = stats["percent"]
    metric["available_mb"] = stats["available_mb"]
    metric["total_mb"] = stats["total_mb"]

    warn_reasons = []
    if stats["percent"] >= settings.health.mem_warn_pct:
        warn_reasons.append(
            f"usage {stats['percent']:.1f}% >= {settings.health.mem_warn_pct}%"
        )
    if stats["available_mb"] <= settings.health.mem_min_available_mb:
        warn_reasons.append(
            f"available {stats['available_mb']:.0f}MB <= {settings.health.mem_min_available_mb}MB"
        )

    if warn_reasons:
        metric["status"] = "warning"
        metric["message"] = " / ".join(warn_reasons)

    return metric


def _evaluate_disk_metric(path: str) -> Dict[str, Any]:
    stats = _get_disk_stats(path)
    metric: Dict[str, Any] = {
        "status": "unknown",
        "value": None,
        "threshold_pct": settings.health.disk_warn_pct,
        "min_free_gb": settings.health.disk_min_free_gb,
        "path": path or "/",
    }

    if not stats:
        metric["message"] = "Disk metrics unavailable"
        return metric

    metric["status"] = "ok"
    metric["value"] = stats["percent"]
    metric["free_gb"] = stats["free_gb"]
    metric["total_gb"] = stats["total_gb"]

    warn_reasons = []
    if stats["percent"] >= settings.health.disk_warn_pct:
        warn_reasons.append(
            f"usage {stats['percent']:.1f}% >= {settings.health.disk_warn_pct}%"
        )
    if stats["free_gb"] <= settings.health.disk_min_free_gb:
        warn_reasons.append(
            f"free {stats['free_gb']:.2f}GB <= {settings.health.disk_min_free_gb}GB"
        )

    if warn_reasons:
        metric["status"] = "warning"
        metric["message"] = " / ".join(warn_reasons)

    return metric


def _check_redis_replication() -> Dict[str, Any]:
    if not redis:
        return {"status": "unknown", "message": "redis library not installed"}

    client = None
    try:
        client = redis.Redis.from_url(
            settings.celery.broker_url,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        info = client.info("replication")
    except Exception as exc:
        logger.error("Failed to check Redis replication status: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        if client is not None:
            try:
                client.close()  # type: ignore[has-type]
            except Exception:
                pass

    role = info.get("role", "unknown")
    master_link_status = info.get("master_link_status", "N/A")
    connected_slaves = info.get("connected_slaves", 0)

    metric: Dict[str, Any] = {
        "status": "ok",
        "role": role,
        "master_link_status": master_link_status,
        "connected_slaves": connected_slaves,
    }

    if role == "slave":
        metric["status"] = "error"
        metric["message"] = "Redis is in replica mode; write operations may fail"
        logger.critical(
            "CRITICAL: Redis broker is a replica! Fix by running 'redis-cli REPLICAOF NO ONE'. Info: %s",
            metric,
        )

    return metric


def _summary_line(metrics: Dict[str, Dict[str, Any]]) -> str:
    """Build short human-readable line even when some stats are unavailable."""
    parts = []

    cpu_metric = metrics["cpu"]
    cpu_value = cpu_metric.get("value")
    if isinstance(cpu_value, (int, float)):
        part = f"cpu={cpu_value:.1f}%"
        load1 = cpu_metric.get("load_avg", {}).get("1m")
        if isinstance(load1, (int, float)):
            part += f" (load1={load1:.2f})"
        parts.append(part)
    else:
        parts.append("cpu=unknown")

    mem_metric = metrics["memory"]
    mem_value = mem_metric.get("value")
    if isinstance(mem_value, (int, float)):
        available = mem_metric.get("available_mb")
        if isinstance(available, (int, float)):
            parts.append(f"mem={mem_value:.1f}% (avail={available:.0f}MB)")
        else:
            parts.append(f"mem={mem_value:.1f}%")
    else:
        parts.append("mem=unknown")

    disk_metric = metrics["disk"]
    disk_value = disk_metric.get("value")
    if isinstance(disk_value, (int, float)):
        free = disk_metric.get("free_gb")
        if isinstance(free, (int, float)):
            parts.append(f"disk={disk_value:.1f}% (free={free:.2f}GB)")
        else:
            parts.append(f"disk={disk_value:.1f}%")
    else:
        parts.append("disk=unknown")

    redis_metric = metrics["redis"]
    redis_status = redis_metric.get("status") or "unknown"
    parts.append(f"redis={redis_status}")

    return " | ".join(parts)


def _issues_text(metrics: Dict[str, Dict[str, Any]]) -> str:
    issues = []
    for component, metric in metrics.items():
        status = metric.get("status")
        if status in {"warning", "error"}:
            message = metric.get("message") or status
            issues.append(f"{component}: {message}")
    return "; ".join(issues)


@celery_app.task
def check_system_health_task():
    """
    Periodic task to check CPU, memory, disk, and Redis replication status.

    Returns a structured payload with per-metric statuses so dashboards
    or alerting hooks can reason about system health.
    """
    metrics = {
        "cpu": _evaluate_cpu_metric(),
        "memory": _evaluate_memory_metric(),
        "disk": _evaluate_disk_metric(settings.health.disk_path),
        "redis": _check_redis_replication(),
    }

    overall_status = "ok"
    summary = _summary_line(metrics)
    issues = _issues_text(metrics)

    for metric in metrics.values():
        status = metric.get("status")
        if status == "error":
            overall_status = "error"
            break
        if status == "warning" and overall_status != "error":
            overall_status = "warning"

    if overall_status == "ok":
        logger.info("System health OK | %s", summary or metrics)
    elif overall_status == "warning":
        logger.warning("System health warning | %s | %s", summary or "n/a", issues or "unspecified")
    else:
        logger.error("System health ERROR | %s | %s", summary or "n/a", issues or "unknown issue")

    return {
        "time": iso_utc(),
        "status": overall_status,
        "metrics": metrics,
    }
