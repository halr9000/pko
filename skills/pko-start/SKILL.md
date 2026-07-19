---
name: pko-start
description: Start and stop Pinokio apps, check app status, and manage the server lifecycle via WebSocket protocol. Use when the task is "start an app", "stop an app", "check status", "restart server", or "run a Pinokio script".
metadata:
  author: pko
  version: "0.1.0"
---

# pko-start: Start and Stop Pinokio Apps

Manage the lifecycle of Pinokio applications — start, stop, check status, and restart the server.

## How It Works

Pinokio apps are controlled through a WebSocket connection to pinokiod. The protocol uses JSON messages:

- **Run**: Send `{uri, mode: "run", input, client}` to execute an app's pinokio.js script
- **Stop**: Send `{method: "kernel.api.stop", params: {uri}}` to kill a running script
- **Status**: Send `{uri, status: true}` to check if a script is running

## Commands

```bash
# Check if an app is running
uvx pko status comfyui

# Restart the whole Pinokio server
uvx pko restart

# Remote instance
uvx pko --host 192.168.1.50 status comfyui
```

## WebSocket Protocol Reference

### Streamed Packets (Server → Client)

| Type | Meaning |
|------|---------|
| `start` | Script execution begun `{description, current, total}` |
| `stream` | Terminal output `{data: {raw: "..."}}` |
| `result` | Step completed `{data: result_value}` |
| `error` | Error occurred |
| `event` | System event (e.g., stop) |
| `disconnect` | Script finished |

### Client Requests

**Run a script:**
```json
{
  "uri": "/api/myapp/index.json",
  "mode": "run",
  "input": {},
  "client": {"cols": 80, "rows": 24}
}
```

**Stop a script:**
```json
{
  "method": "kernel.api.stop",
  "params": {"uri": "/api/myapp/index.json"}
}
```

## Interactive Prompts

Some scripts pause for user input. The server sends an `input` packet:
```json
{
  "type": "input",
  "data": {
    "title": "Configuration",
    "description": "Enter settings",
    "form": [...]
  }
}
```
Response is sent via the `kernel.api.respond` method over WebSocket.

## Installation

```bash
# From this repo (local)
npx skills add path/to/pko --skill pko-start

# From GitHub (once published)
npx skills add owner/pko --skill pko-start
```