# DeepSeek Harness

Shows the status of DeepSeek Harness in Home Assistant: `bereit`, `arbeitet`, or
`wartet auf Freigabe`, open approvals, and the last answer — plus a connectivity
sensor and a device with the bridge version.

The integration polls the local DSH bridge (`GET /api/ha-voice/status`) and does
not change existing agents, pipelines, or automations.
