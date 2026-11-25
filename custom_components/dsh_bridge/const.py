"""Constants for the DeepSeek Harness integration."""

from __future__ import annotations

DOMAIN = "dsh_bridge"
NAME = "DeepSeek Harness"
MANUFACTURER = "DeepSeek Harness"
MODEL = "Voice Bridge"

DEFAULT_PORT = 3080
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

CONF_HOST = "host"
CONF_PORT = "port"
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"

STATUS_PATH = "/api/ha-voice/status"

TITLE = "DeepSeek Harness"

STALE_AFTER_MINUTES = 10
