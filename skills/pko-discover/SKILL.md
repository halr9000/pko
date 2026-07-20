---
name: pko-discover
description: Discover Pinokio instances on localhost, remote hosts, or save connection profiles for later use. Use when the task is "find Pinokio", "connect to Pinokio", "scan for instances", or "save a profile".
metadata:
  author: pko
  version: "0.2.0"
---

# pko-discover: Discover Pinokio Instances

Find local or remote Pinokio instances by scanning well-known ports, or save a connection profile for repeated use.

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

# Save a discovered instance (name is optional, defaults to "default")
uvx pko connect 192.168.1.50:42000

# List saved profiles
uvx pko profile

# View a specific profile
uvx pko profile my-server
```

## Profiles

Connection profiles are stored in `~/.config/pko/config.json`. The profile
name is an internal detail — most users never need to think about it and
can just use `pko connect host:port`, which saves under a profile named
"default". Pass `--name` only if you need multiple saved servers:

```bash
uvx pko connect 10.0.0.5:42000 --name secondary
```

Each profile stores:
- `host` — the instance hostname/IP
- `port` — the port number

Set a profile as default:
```bash
uvx pko profile secondary --default
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
