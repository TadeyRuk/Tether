# Tether 🔗

**Your phone is your key.** Tether is a lightweight, privacy-first proximity lock for Linux that uses your phone's Bluetooth signal as an invisible tether to your laptop. Walk away and your screen locks automatically. Come back and your laptop sends a push notification to your phone with a one-tap unlock button. No password typing, no manual locking, no third-party surveillance — just your devices talking to each other privately through an encrypted tunnel.

Built entirely with open-source tools. Runs silently as two background `systemd` services. All sensitive configuration lives in a single file on your machine that never touches the repository.

> **Works on any modern Linux desktop** — Fedora, Ubuntu, Debian, Arch, and more — under both **KDE Plasma** and **GNOME**, on **Wayland or X11**. No root privileges required at runtime.

---

## Table of Contents

- [Features](#features)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration Reference](#configuration-reference)
- [Desktop Notifications & Health Checks](#desktop-notifications--health-checks)
- [Verifying the Installation](#verifying-the-installation)
- [The iOS Unlock Shortcut](#the-ios-unlock-shortcut)
- [Tuning Tether for Your Environment](#tuning-tether-for-your-environment)
- [Disabling Bluetooth Audio Routing](#disabling-bluetooth-audio-routing)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)
- [Uninstalling](#uninstalling)
- [Project Structure](#project-structure)
- [Technology Stack](#technology-stack)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- 🔒 **Automatic lock** — screen locks the moment your phone leaves Bluetooth range.
- 🔔 **One-tap unlock** — a push notification with an embedded "Unlock Laptop" button appears on your phone when you return.
- 📡 **Rootless proximity detection** — uses a pure-Python L2CAP reachability probe; no `l2ping`, no `sudo`, no special capabilities.
- 🧠 **Noise-resistant** — a rolling average plus a hysteresis gap between the lock and unlock thresholds prevents lock/unlock flapping at the edge of range.
- 🔐 **End-to-end encrypted** — all phone↔laptop traffic rides a Tailscale (WireGuard) tunnel; works across any network.
- 🖥️ **Desktop notifications** — local toast notifications on lock/unlock with a built-in readiness self-check (Bluetooth, Tailscale, ntfy).
- 🗂️ **Secrets stay local** — every personal value lives in `~/.config/tether/tether.conf`, which is git-ignored and never leaves your machine.
- 🪶 **Tiny footprint** — two small daemons, negligible CPU and battery impact.

---

## How It Works

Tether is built around one idea: **as long as your phone is nearby, your laptop stays unlocked.** The moment you walk far enough that Bluetooth can no longer reach your phone, your laptop locks itself. When you return, Tether sends a push notification to your phone with an "Unlock Laptop" button. Tap it, and your laptop unlocks — no password.

Under the hood, two background services do the work:

### 1. The proximity watcher — `tether.py`

A Python daemon that probes your phone every few seconds (default: 5) and decides when to lock or unlock.

- **Reachability probe.** Instead of the deprecated `l2ping` tool (which BlueZ has removed from modern distros like Fedora), Tether opens an **L2CAP socket and attempts a connection** to the phone's SDP channel. Like `l2ping`, this *pages* the device at the link layer, so it works whether or not there's an active Bluetooth connection — and crucially, **it needs no root privileges.** A successful connect (or an active refusal) means the phone answered and is in range; a timeout or host-down means it's gone. This produces a clean binary signal: `-50` (present) or `-100` (away).
- **Smoothing.** The last 5 readings are kept in a rolling window and averaged, so a momentary Bluetooth dropout doesn't trigger a false lock.
- **Hysteresis.** Locking and unlocking use *separate* thresholds (`lock_threshold` < `unlock_threshold`). The gap between them stops the system from flapping lock→unlock→lock when you're standing right on the edge of range.
- **Acting.** On crossing the lock threshold it calls `loginctl lock-session` locally. On re-entry it does **not** unlock directly — it sends an ntfy push notification whose action button points at the unlock server, keeping a human tap in the loop.

### 2. The unlock server — `tether-server.py`

A minimal Flask HTTPS server exposing three endpoints:

| Endpoint | Method | Auth | Action |
|----------|--------|------|--------|
| `/unlock` | GET | `?token=...` | `loginctl unlock-session` |
| `/lock`   | GET | `?token=...` | `loginctl lock-session` |
| `/status` | GET | none | health check → `tether is running` |

`/unlock` and `/lock` require your secret token; a mismatch returns `403 Forbidden`. HTTPS is mandatory (iOS requires it) and is served directly by Flask using the TLS certificate Tailscale provisions for your machine's hostname.

### The transport

Communication between your phone and laptop happens over **Tailscale**, a WireGuard-based private mesh network that gives both devices stable private IPs reachable from anywhere — home Wi-Fi, mobile data, or a coffee-shop network. Push notifications are delivered via **[ntfy.sh](https://ntfy.sh)**, a free, open-source pub/sub service, with the unlock action embedded directly in the notification.

---

## Architecture

```
+--------------------------------------------------------------------+
|                         YOUR HOME / OFFICE                          |
|                                                                     |
|   +---------------+   L2CAP reachability probe   +--------------+   |
|   |    Laptop     | <--------------------------> |    Phone     |   |
|   |   (Linux)     |       (local Bluetooth)      |              |   |
|   |               |                              |              |   |
|   | [tether.py]   | ---- ntfy.sh (HTTPS) ------>  | notification |   |
|   |  watcher      |                              |  "Unlock?"   |   |
|   |               |                              |      |       |   |
|   | [tether-      | <--- Tailscale WireGuard ---  |  tap button  |   |
|   |  server.py]   |          tunnel              |              |   |
|   |  Flask HTTPS  |                              +--------------+   |
|   +---------------+                                                 |
+--------------------------------------------------------------------+
```

The Bluetooth probe is entirely local and needs no internet. The ntfy notification and the Tailscale unlock signal use the internet but **do not require both devices to be on the same network** — your phone can be on mobile data while your laptop is on Wi-Fi and everything still works.

---

## Requirements

**Hardware:** A Linux laptop and a phone that are Bluetooth-paired with each other.

**On your laptop:**
- Python 3.8+
- `bluez` (provides `bluetoothctl`)
- Python packages `flask` and `requests`
- `libnotify` (`notify-send`) and `pipewire`/`pulseaudio` (`paplay`) for desktop notifications — optional but recommended
- Tailscale, installed and connected

**On your phone (iPhone shown; Android works too with equivalent apps):**
- The **Tailscale** app
- The **ntfy** app

**Accounts:** A free [Tailscale](https://tailscale.com) account (both devices signed into the *same* account). ntfy needs no account at all.

---

## Installation

### Step 1 — Install dependencies

<details open>
<summary><strong>Fedora / RHEL / Nobara</strong></summary>

```bash
sudo dnf install bluez python3-flask python3-requests libnotify
```
</details>

<details>
<summary><strong>Ubuntu / Debian / Pop!_OS</strong></summary>

```bash
sudo apt update
sudo apt install bluez python3-flask python3-requests libnotify-bin -y
```

If your distro ships Flask/requests only via pip, you can instead run:
```bash
pip3 install flask requests --break-system-packages
```
</details>

<details>
<summary><strong>Arch / Manjaro</strong></summary>

```bash
sudo pacman -S bluez bluez-utils python-flask python-requests libnotify
```
</details>

Make sure Bluetooth is enabled:

```bash
sudo systemctl enable --now bluetooth
```

> **Note:** Tether does **not** require `l2ping` (the old BlueZ tool many guides reference). It uses a rootless L2CAP probe instead, so you don't need `bluez-deprecated` or any passwordless-sudo rule.

### Step 2 — Set up Tailscale

Install Tailscale ([tailscale.com/download/linux](https://tailscale.com/download/linux)), then install the Tailscale app on your phone. Sign into the **same account** on both devices and bring the laptop online:

```bash
sudo systemctl enable --now tailscaled
sudo tailscale up
```

In the [admin console](https://login.tailscale.com/admin/dns), **enable MagicDNS** and **enable HTTPS Certificates** (both under the DNS tab). This gives your laptop a stable hostname like `your-machine.your-tailnet.ts.net` and allows it to be issued a real TLS certificate.

Find your hostname:

```bash
tailscale status --json | python3 -c "import sys,json;print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))"
```

### Step 3 — Provision a TLS certificate

iOS requires HTTPS. Tailscale issues a real, trusted certificate for your MagicDNS hostname. Generate it straight into the config directory:

```bash
mkdir -p ~/.config/tether
cd ~/.config/tether
sudo tailscale cert your-machine.your-tailnet.ts.net
sudo chown $USER:$USER your-machine.your-tailnet.ts.net.crt your-machine.your-tailnet.ts.net.key
```

The `chown` is important: the unlock server runs as your user and must be able to read the key. Note the two file paths for Step 6.

> If `tailscale cert` fails with `500 ... failed to create DNS record`, see [Troubleshooting](#tailscale-cert-fails-with-500-failed-to-create-dns-record).

### Step 4 — Find your phone's Bluetooth MAC address

Pair your phone through your desktop's Bluetooth settings if you haven't already, then:

```bash
bluetoothctl devices
```

Copy your phone's MAC (looks like `AA:BB:CC:DD:EE:FF`). In your phone's Bluetooth device settings, it also helps to enable **Trusted** so the link auto-reconnects reliably.

### Step 5 — Set up ntfy on your phone

Install the **ntfy** app. Pick a unique, hard-to-guess topic name (e.g. `yourname-tether-x7k2`) — this is effectively a private channel, so treat it like a secret. Subscribe to it in the app.

### Step 6 — Install the scripts and configuration

```bash
git clone https://github.com/TadeyRuk/Tether.git
cd Tether

# Copy ALL THREE scripts — tether.py imports tether_notify.py
mkdir -p ~/.local/bin
cp tether.py tether-server.py tether_notify.py ~/.local/bin/

# Create your config from the template
cp tether.conf.example ~/.config/tether/tether.conf
nano ~/.config/tether/tether.conf
```

Fill in your values (see the [Configuration Reference](#configuration-reference) below). A handy way to generate a strong token:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 7 — Install the systemd user services

```bash
mkdir -p ~/.config/systemd/user
cp systemd/tether.service systemd/tether-server.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tether tether-server
systemctl --user status tether tether-server
```

You should see `Active: active (running)` for both. Tether now starts automatically every time you log in.

> **Why user services?** They run while you're logged in and stop when you log out — exactly the lifetime during which there's a session worth protecting. They keep running while your screen is locked, which is what makes the come-back-and-unlock flow work. You do **not** need `loginctl enable-linger`.

---

## Configuration Reference

All values live in `~/.config/tether/tether.conf`, read at startup via Python's `configparser`. If the file is missing or a required field is absent, the scripts exit immediately with a clear error. This file is git-ignored and never leaves your machine — the scripts themselves contain no secrets and are identical on every install.

```ini
[tether]
device_mac          = AA:BB:CC:DD:EE:FF
secret_token        = a-long-random-string
tailscale_hostname  = your-machine.your-tailnet.ts.net
ntfy_topic          = your-ntfy-topic
cert_file           = /home/youruser/.config/tether/your-machine.your-tailnet.ts.net.crt
key_file            = /home/youruser/.config/tether/your-machine.your-tailnet.ts.net.key
lock_threshold      = -80
unlock_threshold    = -65
poll_interval       = 5
server_port         = 8080
```

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `device_mac` | ✅ | — | Your phone's Bluetooth MAC address. |
| `secret_token` | ✅ | — | Password for the unlock endpoint. Make it long and random. |
| `tailscale_hostname` | ✅ | — | Your laptop's MagicDNS hostname. |
| `ntfy_topic` | ✅ | — | The ntfy topic you subscribed to. Treat as a secret. |
| `cert_file` | ✅ | — | Path to the Tailscale-issued `.crt`. |
| `key_file` | ✅ | — | Path to the Tailscale-issued `.key`. |
| `lock_threshold` | | `-80` | Lock when the smoothed signal drops below this. |
| `unlock_threshold` | | `-65` | Notify-to-unlock when it climbs above this. Must be **greater** than `lock_threshold`. |
| `poll_interval` | | `5` | Seconds between probes. |
| `server_port` | | `8080` | Port the unlock server listens on. |

> ⚠️ **Known caveat:** the proximity watcher hardcodes port `8080` in the notification's unlock URL, while the server reads `server_port`. If you change `server_port`, also update the port in `tether.py`'s `LAPTOP_URL`, or simply leave it at `8080`.

---

## Desktop Notifications & Health Checks

`tether_notify.py` (imported by the watcher) sends local desktop toast notifications on startup, lock, and unlock, each annotated with a quick **readiness self-check**:

- **Tailscale** is running and connected
- the **Bluetooth adapter** is powered on
- your **phone** is paired/reachable
- **ntfy.sh** is reachable

Notifications are sent via `notify-send` and accompanied by a short sound (`paplay`, falling back to `aplay`). If a check fails, the notification's urgency is raised but locking/unlocking is never blocked — the checks are advisory.

**Adjusting the sound volume.** Edit `SOUND_VOLUME` near the top of `tether_notify.py` (PipeWire/PulseAudio scale: `65536` = 100%):

```python
SOUND_VOLUME = 32768   # 50%   →   16384 = 25%, 0 = silent
```

Then redeploy and restart: `cp tether_notify.py ~/.local/bin/ && systemctl --user restart tether`.

---

## Verifying the Installation

Watch the proximity watcher live:

```bash
journalctl --user -u tether -f
```

You'll see a reading every few seconds. With your phone nearby it shows `-50`; walk away (or turn off the phone's Bluetooth) and the smoothed average climbs toward `-100` and triggers a lock.

Test the unlock server independently — open the `/status` URL in your phone's browser (Tailscale connected):

```
https://your-machine.your-tailnet.ts.net:8080/status      →  "tether is running"
```

Test a full unlock — lock the screen, then visit:

```
https://your-machine.your-tailnet.ts.net:8080/unlock?token=your-secret-token
```

Your screen should unlock. From the command line you can verify the lock/unlock primitives directly:

```bash
loginctl lock-session     # screen should lock
loginctl unlock-session   # screen should unlock
```

---

## The iOS Unlock Shortcut

The ntfy notification already includes an "Unlock Laptop" button, so a separate Shortcut is optional — but a Home-Screen / Back-Tap shortcut is handy for unlocking on demand.

1. Open the **Shortcuts** app → **+** (new shortcut).
2. Add the **"Get Contents of URL"** action.
3. Set the URL to:
   ```
   https://your-machine.your-tailnet.ts.net:8080/unlock?token=your-secret-token
   ```
   Leave the method as **GET**.
4. Rename it **Unlock Laptop**, tap **Done**.
5. Make it one-tap: the shortcut's ⋯ → **Add to Home Screen**, or bind it under **Settings → Accessibility → Touch → Back Tap**.

Because the certificate is a real, trusted Tailscale/Let's Encrypt cert, iOS connects without warnings.

---

## Tuning Tether for Your Environment

The default thresholds (`lock_threshold = -80`, `unlock_threshold = -65`) suit most setups, but Bluetooth behavior varies with your walls and how you carry your phone. The L2CAP probe reports a binary `-50` (in range) / `-100` (out of range), and the watcher averages the last 5 readings — so locking is governed by **how many of the recent probes failed**, not a continuous RSSI curve.

To make Tether lock sooner after you leave, move `lock_threshold` closer to `-50` (e.g. `-65`); to let you wander further first, move it closer to `-100` (e.g. `-90`). Lengthening `poll_interval` lowers overhead but slows the response and widens the smoothing window.

After any change, restart the watcher:

```bash
systemctl --user restart tether
```

---

## Disabling Bluetooth Audio Routing

A paired phone often makes your laptop advertise itself as a Bluetooth **speaker** (the A2DP *sink* role), so your phone's audio may start playing through your laptop's speakers. Tether probes at the L2CAP link layer, completely independent of audio profiles, so disabling this is **100% safe** for Tether.

<details open>
<summary><strong>WirePlumber 0.5+ (Fedora 40+, recent Ubuntu/Arch) — the modern config</strong></summary>

Check your version with `wireplumber --version`. For 0.5 and newer, create a drop-in:

```bash
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cat > ~/.config/wireplumber/wireplumber.conf.d/51-bluez-no-sink.conf <<'EOF'
# Keep A2DP source + HFP/HSP gateway; drop the sink/head-unit roles that let
# the phone play through the laptop.
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_source hfp_ag hsp_ag ]
}
EOF
systemctl --user restart wireplumber
```
</details>

<details>
<summary><strong>WirePlumber &lt; 0.5 (older Ubuntu) — legacy Lua config</strong></summary>

```bash
mkdir -p ~/.config/wireplumber/bluetooth.lua.d
cat > ~/.config/wireplumber/bluetooth.lua.d/50-disable-a2dp-sink.lua <<'EOF'
bluez_monitor.properties = {
  ["bluez5.roles"] = "[ a2dp_source hfp_ag hsp_ag ]"
}
EOF
systemctl --user restart wireplumber
```
</details>

After restarting, your laptop no longer appears as an audio output to your phone. Verify Tether still works with `journalctl --user -u tether -f` (you should still see `-50` readings). To revert, delete the file and restart WirePlumber.

---

## Troubleshooting

### `tailscale cert` fails with `500 ... failed to create DNS record`

First confirm **HTTPS Certificates** is enabled in the [admin DNS settings](https://login.tailscale.com/admin/dns). If it's already on and the error persists with the *same* challenge value on every retry, the usual cause is a stale `_acme-challenge` record tied to the node's name. The most reliable fix is to **rename the machine**:

1. Admin console → **Machines** → your machine → **⋯** → **Edit machine name** → give it a new name.
2. Confirm the new hostname: `tailscale status --json | python3 -c "import sys,json;print(json.load(sys.stdin)['Self']['DNSName'])"`
3. Provision against the new name: `sudo tailscale cert new-name.your-tailnet.ts.net`

Use the new hostname everywhere in your config afterward. (A `systemctl restart tailscaled` and toggling HTTPS off/on are lighter-weight things to try first.)

### The watcher always shows `-100` even with the phone nearby

- The phone's Bluetooth is off, or the pairing was lost. Confirm it's paired in your desktop's Bluetooth settings and that the MAC matches `device_mac`.
- Some phones randomize their MAC on re-pairing — run `bluetoothctl devices` and update the config if it changed.
- Verify the probe directly:
  ```bash
  python3 - <<'PY'
  import socket
  s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
  s.settimeout(4)
  try: s.connect(("AA:BB:CC:DD:EE:FF", 1)); print("present")
  except OSError as e: print("away:", e)
  PY
  ```

### `loginctl unlock-session` doesn't release the lock screen

This depends on your screen locker honoring logind's Unlock signal. KDE Plasma's `kscreenlocker` and GNOME both support it. If your `loginctl lock-session` works but `unlock-session` doesn't, your locker may not implement remote unlock — test the primitives directly (see [Verifying](#verifying-the-installation)) to isolate this from any networking issue.

### The unlock request returns `403 Forbidden`

The `token` in your request doesn't match `secret_token`. Check for stray spaces or characters in the ntfy Actions URL and any Shortcut you created — the token must match exactly.

### The browser/Shortcut can't connect to the server

- Confirm the server is up: `systemctl --user status tether-server` and `curl -s https://your-host:8080/status`.
- Confirm Tailscale is connected on **both** devices.
- Confirm the cert files are readable by your user (the `chown` from Step 3) — if the key is root-owned, the server fails to start. Check `journalctl --user -u tether-server`.

### The screen locks but no ntfy notification arrives

- The `ntfy_topic` must exactly match (case-sensitive) the topic you subscribed to.
- Look for `Notification sent successfully` in the watcher logs. If it's there, the issue is phone-side (check the ntfy app's notification permissions); if you see a failure warning, check the laptop's internet connection.

### Services don't start after a reboot

User services start after you log into your desktop session — this is expected. If they're `active (running)` after login but not before, all is well. If they fail even after login, check `journalctl --user -u tether`.

### `Config file not found` on startup

The scripts can't find `~/.config/tether/tether.conf`. Make sure you copied `tether.conf.example` there and filled in all required fields.

### Phone audio is playing through my laptop speakers

See [Disabling Bluetooth Audio Routing](#disabling-bluetooth-audio-routing).

---

## Security Considerations

Tether is designed for personal convenience, not enterprise security.

- **The secret token is the primary protection.** Treat it like a password — long, random, never committed or shared. `.gitignore` excludes `tether.conf`, `*.crt`, and `*.key` automatically.
- **Traffic is end-to-end encrypted** by Tailscale's WireGuard tunnel and is not visible on the public internet. However, anyone with access to your tailnet *and* your token could unlock your laptop. For personal use this is an acceptable risk.
- **Treat your ntfy topic as a secret too** — anyone who knows it could read your notifications (which contain the tokenized unlock link). Use a long, random topic name, or self-host ntfy for full control.
- **Proximity is reachability, not identity.** If someone takes your phone near the laptop, Tether sends the unlock notification *to your phone* — the tap is the human-in-the-loop confirmation. Without your tap, the laptop stays locked.

---

## Uninstalling

```bash
systemctl --user disable --now tether tether-server
rm ~/.config/systemd/user/tether.service ~/.config/systemd/user/tether-server.service
rm ~/.local/bin/tether.py ~/.local/bin/tether-server.py ~/.local/bin/tether_notify.py
systemctl --user daemon-reload
# Optional — removes your secrets and certificate:
rm -rf ~/.config/tether
```

---

## Project Structure

```
Tether/
├── tether.py                     # Bluetooth proximity watcher daemon
├── tether-server.py              # Flask HTTPS unlock server
├── tether_notify.py              # Desktop notifications + readiness checks
├── tether.conf.example           # Configuration template
├── systemd/
│   ├── tether.service            # systemd user service for the watcher
│   └── tether-server.service     # systemd user service for the server
├── README.md
└── LICENSE
```

---

## Technology Stack

**BlueZ** provides `bluetoothctl` and the kernel L2CAP sockets Tether probes over. **Python 3** runs both daemons (proximity probing uses only the standard library's `socket` module — no `l2ping` binary required). **Flask** powers the unlock server. **Tailscale** (free for personal use) provides the WireGuard mesh and TLS certificate provisioning. **[ntfy.sh](https://ntfy.sh)** delivers push notifications (self-hostable if you prefer). **systemd** manages the background services. **WirePlumber / PipeWire** are referenced only in the optional audio-routing section.

---

## Contributing

Contributions are welcome. For bugs, please open an issue with your distro and version, Python version, desktop environment (KDE/GNOME), and the relevant `journalctl --user -u tether` output. For features, open an issue first to discuss — Tether is intentionally minimal and new features should fit that philosophy.

Areas that would benefit from improvement: Android-side helper/shortcut documentation, an interactive setup wizard, and richer config validation.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

*Named Tether because that's exactly what it is: an invisible thread between your phone and your laptop. When the thread snaps, the laptop protects itself. When it reconnects, it welcomes you back.*
