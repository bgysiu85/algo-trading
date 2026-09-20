# TradingView MCP — setup on bens-proart

Installed 2026-09-01. Source: https://github.com/tradesdontlie/tradingview-mcp

Bridges Claude to **TradingView Desktop** over Chrome DevTools Protocol on `127.0.0.1:9222`.
84 tools: chart state, OHLCV, Pine Script (compile/inject/errors), indicators, drawings,
alerts, multi-pane layouts, replay mode, watchlists. No API keys.

## What's where

| Thing | Location |
|---|---|
| Server code | `C:\Users\bens8\tradingview-mcp` |
| Extension manifest | `C:\Users\bens8\tradingview-mcp\manifest.json` |
| Claude Code config | `C:\Users\bens8\.claude\.mcp.json` |
| Launcher (use this) | `...\scripts\launch-tv-debug.ps1` |
| Launcher (repo's, see gotchas) | `...\scripts\launch_tv_debug.bat` |

## How it's registered

Two independent paths, both live:

- **Claude desktop app** — Settings → Extensions → Extension developer → *Install unpacked
  extension*, pointed at `C:\Users\bens8\tradingview-mcp`. The manifest's `${__dirname}`
  references the repo in place, so `git pull` updates apply with no reinstall.
  Tools then reach cloud sessions too, proxied as `TradingView__*`.
- **Claude Code** — `~\.claude\.mcp.json`, standard `mcpServers` entry.

`%APPDATA%\Claude\claude_desktop_config.json` is **legacy** and is not read by current
desktop builds. Writing it does nothing. The extension route is the one that works.

## Daily use

TradingView must be running **with the debug port open** or every tool returns
`cdp_connected: false`. A normally-launched TradingView will not do.

Launch from the "TradingView (debug)" desktop shortcut, which runs:

```
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `
  "$HOME\tradingview-mcp\scripts\launch-tv-debug.ps1"
```

No window appears. It kills any running instance, resolves the MSIX install via
`Get-AppxPackage`, launches detached, polls until CDP answers, then exits.

Verify with the `tv_health_check` tool, or `Invoke-RestMethod 'http://127.0.0.1:9222/json/version'`.

The `tv_launch` tool is the alternative; on builds where launching from `WindowsApps` is
denied it copies the package to `%LOCALAPPDATA%\tradingview-mcp\` (~330 MB, one time,
keeps login and layouts).

## Gotchas hit during install

- **`launch_tv_debug.vbs` does not work.** It sets `ELECTRON_EXTRA_LAUNCH_ARGS` then
  launches via `explorer.exe`; the MSIX app inherits the shell's environment instead, so
  the flag vanishes and TradingView opens looking normal with no port.
- **`launch_tv_debug.bat` works but leaves a live console.** cmd's `start` hands the child
  a copy of the parent console, so TradingView stays attached and the window can never
  close — and **closing that window can take TradingView down with it**, since a console
  close event reaches every attached process. `launch-tv-debug.ps1` avoids this by using
  `Start-Process` (ShellExecute), which detaches with no console at all.
- **PowerShell 5.1 `Set-Content -Encoding UTF8` writes a BOM**, which Node's JSON parser
  rejects. Use `[System.IO.File]::WriteAllText()` for any config file.
- **Execution policy** blocks `npm.ps1`. Use `npm.cmd` to sidestep it without changing
  security settings.
- **Desktop is OneDrive-redirected** (`C:\Users\bens8\OneDrive\Desktop`). Use
  `[Environment]::GetFolderPath('Desktop')`, never `$HOME\Desktop`.
- Settings shows **"Node.js: Not found"** despite Node being installed; harmless, since
  "Use built-in Node.js for MCP" is on and its bundled Node 24.18.1 runs the server.

## Security note

Port 9222 is open for as long as TradingView runs. Bound to `127.0.0.1`, so not exposed
off-machine, but any local process running as this user can drive TradingView through it.
Launching on demand rather than at login keeps that window narrow.

Do **not** set `ELECTRON_EXTRA_LAUNCH_ARGS` as a persistent user environment variable —
every Electron app would open a debug port, Claude Desktop and VS Code included.
