---
name: pko-install
description: Install Pinokio apps from GitHub repositories, understand the pinokio.js launcher format, and manage app lifecycle. Use when the task is "install an app", "add a Pinokio app", "list apps", "clone a Pinokio launcher", or "delete an app".
metadata:
  author: pko
  version: "0.1.0"
---

# pko-install: Install and Manage Pinokio Apps

Install applications from GitHub repositories into a Pinokio instance, list installed apps, and understand the pinokio.js launcher format.

## How It Works

Pinokio installs apps by cloning GitHub repositories into `~/pinokio/api/<name>/`. The repository must contain a `pinokio.js` (or `index.json`) launcher file that defines the install, run, and menu scripts.

## Commands

```bash
# List installed apps
uvx pko list

# Delete an app or its cache
uvx pko delete my-app

# Delete with specific type
uvx pko delete my-app --type cache
```

## Pinokio.js Launcher Format

The launcher file (`pinokio.js` or `index.json`) defines the app's lifecycle:

```json
{
  "title": "My App",
  "description": "What it does",
  "icon": "icon.png",
  "run": [
    {
      "method": "shell.run",
      "params": {
        "message": "uv pip install -r requirements.txt",
        "path": ".",
        "venv": "venv"
      }
    }
  ]
}
```

### Script Methods

| Method | Purpose |
|--------|---------|
| `shell.run` | Execute shell command |
| `fs.write` | Write file |
| `fs.read` | Read file |
| `fs.copy` | Copy file |
| `fs.download` | Download file from URL |
| `json.set/get/rm` | JSON file operations |
| `local.set` | Set script-local variable |
| `net` | Network request |
| `git` | Git operations |
| `hf.download` | Hugging Face model download |
| `script.stop` | Stop current script |
| `gradio.predict` | Call Gradio API |
| `log` | Print message to terminal |
| `notify` | Desktop notification |
| `web.open` | Open URL in browser |

### Template Variables

| Variable | Description |
|----------|-------------|
| `{{cwd}}` | Current working directory |
| `{{platform}}` | OS: darwin, win32, linux |
| `{{arch}}` | System architecture |
| `{{port}}` | Next available port |
| `{{gpus}}` | GPU information |
| `{{path}}` | Resolved path utility |
| `{{os}}` | Node.js os module |
| `{{envs}}` | Environment variables |
| `{{which(command)}}` | Check if command exists |
| `{{exists(path)}}` | Check if file exists |
| `{{running(script)}}` | Check if script is running |

## App Lifecycle Notes

- Apps install to `~/pinokio/api/<name>/`
- Each app gets its own virtual environment
- All scripts must be from public Git repositories
- The `run` array executes steps sequentially
- `shell.run` with `path` and `venv` attributes ensures isolation

## Installation

```bash
# From this repo (local)
npx skills add path/to/pko --skill pko-install

# From GitHub (once published)
npx skills add owner/pko --skill pko-install
```