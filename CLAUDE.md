# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Tether is a proximity lock system for Ubuntu/Linux desktops. It uses an iPhone's Bluetooth signal as a presence sensor: when the phone goes out of range the screen locks; when it returns the laptop sends a push notification with a one-tap unlock button. There is no package, build step, or test suite — it is three standalone Python scripts run as systemd user services.

## Architecture

Two independent daemons, plus a shared notification helper module. They do **not** talk to each other directly; they coordinate through the OS (systemd-logind session lock state) and external services.

- **`tether.py`** — the proximity watcher (the "sense + decide" loop). Probes the phone every `poll_interval` seconds via an **L2CAP connection attempt** (`get_rssi()` opens an `AF_BLUETOOTH`/`BTPROTO_L2CAP` socket and connects to `PROBE_PSM` = SDP channel 1). This replaces the old `sudo l2ping` (removed from BlueZ on modern distros like Fedora); like l2ping it pages the device at the link layer, works with or without an active connection, and **needs no root**. The result is binary: a successful connect or `ECONNREFUSED` → `-50` (present), anything else (timeout/host-down) → falls through to a `bluetoothctl info` RSSI read, then `MISSING_RSSI` (`-100`). Keeps a rolling window of the last 5 readings (`RSSI_WINDOW`) and averages them to suppress noise. Lock/unlock use **separate thresholds** (`lock_threshold` < `unlock_threshold`) to create a hysteresis band that prevents lock/unlock flapping at the edge of range. On crossing the lock threshold it calls `loginctl lock-session` locally; on re-entry it does **not** unlock directly — it POSTs an ntfy notification whose action button points at the unlock server, keeping a human tap in the loop.

- **`tether-server.py`** — the unlock server (the "act" half). A minimal Flask HTTPS app exposing `/unlock`, `/lock`, and `/status`. `/unlock` and `/lock` require `?token=<secret_token>` and call `loginctl unlock-session` / `lock-session`; a mismatch returns 403. HTTPS is mandatory (iOS requirement) and is served directly by Flask using the Tailscale-provisioned cert/key from config. Reached from the phone over the Tailscale (WireGuard) tunnel via the MagicDNS hostname, so it works across networks.

- **`tether_notify.py`** — desktop notification + readiness helper, imported by `tether.py`. `run_readiness_checks()` probes Tailscale, the Bluetooth adapter, the paired phone, and ntfy.sh reachability. `notify_startup/lock/unlock/error` fire local `notify-send` desktop notifications (with a `paplay`→`aplay` sound fallback, volume set by the `SOUND_VOLUME` constant — `65536` = 100%) annotated with which checks passed. These are advisory only — failed checks degrade the notification urgency but never block locking/unlocking.

### Trust boundary

The whole security model is the shared `secret_token`: anyone on the Tailscale network who has the token can unlock. Bluetooth proximity is reachability, not identity — the ntfy notification tap is the intended human confirmation step.

## Configuration

All machine-specific and secret values live in `~/.config/tether/tether.conf` (copied from `tether.conf.example`), read via `configparser` at startup. The scripts themselves contain no secrets and are identical across installs. Both daemons raise `FileNotFoundError` immediately if the config is missing. `tether.conf`, `*.crt`, and `*.key` are gitignored — never commit them or hardcode their values.

Keys: `device_mac`, `secret_token`, `tailscale_hostname`, `ntfy_topic`, `cert_file`, `key_file`, and tuning values `lock_threshold` (-80), `unlock_threshold` (-65), `poll_interval` (5), `server_port` (8080). Note `tether.py` hardcodes port `8080` in `LAPTOP_URL` rather than reading `server_port`; keep them in sync if changing the port.

## Running and debugging

These run as **systemd user services** (only after desktop login), not as scripts during normal use:

```bash
systemctl --user restart tether          # after editing tether.conf or tether.py
systemctl --user restart tether-server    # after editing tether-server.py
systemctl --user status tether tether-server
journalctl --user -u tether -f            # watch live RSSI readings / lock decisions
journalctl --user -u tether-server -f
```

The unit files live in `systemd/` and are copied to `~/.config/systemd/user/` during install.

Run a daemon directly for quick iteration (needs a valid config; no root required — the L2CAP probe is unprivileged):

```bash
python3 tether.py
python3 tether-server.py
```

Manual endpoint checks:

```bash
curl -k "https://<tailscale_hostname>:8080/status"
curl -k "https://<tailscale_hostname>:8080/unlock?token=<secret_token>"
```

## Conventions

- Pure standard-library style plus `flask` and `requests` (installed system-wide via `pip3 install --break-system-packages`); there is no virtualenv, lockfile, or dependency manifest.
- Proximity uses the stdlib `socket` module (L2CAP); everything else is shelling out to system tools (`bluetoothctl`, `loginctl`, `notify-send`, `paplay`/`aplay`, `tailscale`) via `subprocess`, each wrapped in timeouts and broad exception handling so one missing tool degrades gracefully rather than crashing the loop.
- Keep it minimal — the project is intentionally small; new behavior should fit the daemon-plus-config pattern rather than introduce frameworks or build tooling.
