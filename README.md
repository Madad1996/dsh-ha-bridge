# DeepSeek Harness — Home Assistant integration

A custom integration (`custom_components/dsh_bridge`) that shows the status of
DeepSeek Harness (DSH) in Home Assistant. It polls the DSH bridge endpoint
`GET /api/ha-voice/status` with a bearer token.

**Documentation: the [Wiki](../../wiki).**

## What it provides

- Config flow (host, port, bridge token), options flow for the polling interval.
- One device **DeepSeek Harness** with model, bridge version, and a link.
- Sensors: `status` (`bereit` / `arbeitet` / `wartet auf Freigabe`),
  `pending_approvals`, `last_answer` (disabled by default).
- `binary_sensor` *Connected* from the coordinator state.
- Reauthentication and reconfiguration without deleting the entry.
- Diagnostics download with the token redacted.
- No changes to conversation agents, pipelines, automations, or scripts.

## Requirements

- Home Assistant 2025.1 or newer
- The DSH bridge reachable from Home Assistant
- The bridge token from the DSH configuration

## Install

HACS → Integrations → ⋮ → Custom repositories → this repository, category
**Integration** → install → restart Home Assistant → add the integration.


## Verify without HA

```bash
python3 -m py_compile custom_components/dsh_bridge/*.py
curl -s -H "Authorization: Bearer $TOKEN" "http://$DSH_HOST:3080/api/ha-voice/status"
```
