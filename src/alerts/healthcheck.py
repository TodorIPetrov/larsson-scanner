"""
Dead Man's Switch / Heartbeat Monitoring (Healthchecks.io).
Pings an external monitoring service after each successful scan to prevent silent failures.
"""

import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)


def send_heartbeat_ping(healthcheck_url: Optional[str] = None) -> bool:
    """
    Sends a heartbeat ping to Healthchecks.io (or any HTTP monitoring service).
    If URL is not configured, silently skips.
    """
    if not healthcheck_url:
        return True

    try:
        resp = requests.get(healthcheck_url, timeout=10)
        if resp.status_code == 200:
            logger.info("Heartbeat ping sent successfully to Healthchecks.io.")
            return True
        else:
            logger.warning(f"Heartbeat ping returned status {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send heartbeat ping: {e}")
        return False
