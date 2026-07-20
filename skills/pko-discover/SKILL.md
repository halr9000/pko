---
name: pko-discover
description: Discover Pinokio instances on localhost, remote hosts, or save known host:port targets for later use. Use when the task is "find Pinokio", "connect to Pinokio", "scan for instances", or "save a host".
metadata:
  author: pko
  version: "0.2.0"
---

# pko-discover: Discover Pinokio Instances

Find local or remote Pinokio instances by scanning well-known ports, or save a host:port for repeated use.

## How It Works

pko scans ports 42000, 42001, 42002, 43000 (the well-known Pinokio ports) on localhost or a specified remote host. It probes each port with `GET /check` — a healthy instance returns `{success: true}`.

## Commands

```bash
# Scan localhost on well-known ports
uvx pko discover

# Scan a remote host
uvx pko discover --host 192.168.1.50

# Scan and save the first found instance as default in one step
uvx pko discover --host 192.168.1.50 --save

# Save a known instance as default
uvx pko connect 192.168.1.50:42000

# List saved hosts
uvx pko hosts
```

## Known Hosts

Known hosts are stored in `~/.config/pko/config.json`, referenced purely by
`host:port` — there is no separate profile-name concept. Each entry stores:
- `host` — the instance hostname/IP
- `port` — the port number

Set a saved host as default:
```bash
uvx pko hosts --default 192.168.1.50:42000
```

Forget a saved host:
```bash
uvx pko hosts --forget 192.168.1.50:42000
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `PKO_HOST` / `PINOKIO_HOST` | Override default host |
| `PKO_PORT` / `PINOKIO_PORT` | Override default port |

## Fallback

If no instances found:
1. Verify Pinokio (pinokiod) is running on the target machine
2. Try `pko discover --host <explicit-ip>` 
3. Check firewall rules for port 42000
4. Connect manually: `pko connect <host>:<port>`

## Installation

```bash
# From this repo (local)
npx skills add path/to/pko --skill pko-discover

# From GitHub (once published)
npx skills add owner/pko --skill pko-discover

# Zero-install usage
uvx pko discover
```
