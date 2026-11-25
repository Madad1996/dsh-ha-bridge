# DSH bridge plugin

The Home Assistant integration only reads from this bridge. Without it there is
no status to show.

## What it does

- `GET /api/ha-voice/status` – returns the DSH status snapshot (state, last
  answer, open approvals, presence).
- Answers permission requests by voice through the Assist satellite when the
  user is home, and falls back to the configured channel otherwise.
- Optional: an OpenAI-compatible endpoint for Home Assistant conversation agents.

## Install on the DSH host

1. Copy this folder somewhere permanent, for example `~/dsh-plugins/dsh-bridge`.
2. Copy `config.example.json` to a private location, fill in `haUrl`, the Home
   Assistant long-lived token, and a `bridgeToken` of your choice
   (`openssl rand -hex 24`), then `chmod 600` it.
3. Install the folder as a bundle in the DSH profile (Plugins → Add plugin, or
   the plugin manager with this directory as target).
4. Point `configPath` in `cordis.patch.yml` at your config file.

## Verify

```bash
curl -s -H "Authorization: Bearer $BRIDGE_TOKEN" \
  http://<DSH-HOST>:3080/api/ha-voice/status | python3 -m json.tool
```

Then add the integration in Home Assistant with the same host, port `3080`, and
the same bridge token.
