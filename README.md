# Tether 🔗

> *Your laptop locks when you leave. It notifies you when you return. You confirm. It unlocks. That's it.*

Tether is a lightweight, privacy-first proximity lock system for Ubuntu that uses your iPhone's Bluetooth signal as an invisible tether to your laptop. Walk away: your screen locks automatically. Come back: your laptop sends a push notification to your iPhone with a one-tap unlock button. No password typing, no manual locking, no third-party surveillance. Just you and your devices, talking to each other privately through an encrypted tunnel.

Built entirely with open-source tools and runs silently as a background service.

---

## How It Works

Tether is built around one core idea: **your phone is your key**. As long as your phone is nearby, your laptop stays unlocked. The moment you walk away far enough that Bluetooth can no longer reach your phone, your laptop locks itself. When you return and your phone is detectable again, Tether sends a push notification to your iPhone with an embedded "Unlock Laptop" button. Tap it, and your laptop unlocks: no password required.

Under the hood, Tether runs two background services. The first is the **proximity watcher**: a Python daemon that pings your iPhone's Bluetooth MAC address every 5 seconds using `l2ping`. It maintains a rolling average of the last 5 readings to smooth out the natural noise in Bluetooth signals, so a momentary dropout doesn't trigger a false lock. A hysteresis gap between the lock threshold and the unlock threshold prevents the system from flapping lock-unlock-lock when you're standing right on the edge of range. The second is the **unlock server**: a lightweight Flask HTTPS server that listens for an authenticated HTTP request from your iPhone and calls `loginctl lock-session` or `loginctl unlock-session` through systemd-logind.

The communication between your iPhone and your laptop happens through **Tailscale**, a WireGuard-based private mesh network that gives both devices stable private IP addresses that can reach each other from anywhere: home Wi-Fi, mobile data, or a coffee shop. Push notifications are delivered via **ntfy.sh**, a free and open-source pub/sub notification service that relays messages from your laptop to your iPhone in real time, with an action button embedded directly in the notification so you never need to open a separate app.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR HOME / OFFICE                        │
│                                                                  │
│   ┌──────────────┐    Bluetooth L2CAP ping    ┌──────────────┐  │
│   │   Ubuntu     │ ◄────────────────────────► │   iPhone     │  │
│   │   Laptop     │                            │              │  │
│   │              │                            │              │  │
│   │  [tether.py] │ ──── ntfy.sh (HTTPS) ───► │ notification │  │
│   │  proximity   │                            │  "Unlock?"   │  │
│   │  watcher     │                            │      │       │  │
│   │              │ ◄── Tailscale WireGuard ── │   tap button │  │
│   │  [tether-    │       tunnel               │              │  │
│   │   server.py] │                            └──────────────┘  │
│   │  Flask HTTPS │                                              │
│   └──────────────┘                                              │
└─────────────────────────────────────────────────────────────────┘
```

The Bluetooth ping is entirely local: no internet required for detection. The ntfy notification and the Tailscale unlock signal both use the internet, but they don't need to be on the same network. Your phone could be on mobile data while your laptop is on Wi-Fi and everything still works.

---

## Requirements

**Hardware:** An Ubuntu laptop and an iPhone that are Bluetooth-paired with each other.

**Software on your Ubuntu laptop:** Python 3.8 or newer, the `bluez` package (provides `l2ping` and `bluetoothctl`), and the Python packages `flask` and `requests`. You'll also need Tailscale installed and running.

**Software on your iPhone:** The Tailscale iOS app and the ntfy iOS app, both available free on the App Store.

**Accounts:** A free Tailscale account (tailscale.com): both your laptop and iPhone must be signed into the same Tailscale account.

---

## Installation

### Step 1 - Install dependencies on your Ubuntu laptop

Start by installing the system-level Bluetooth tools and then the Python packages:

```bash
sudo apt update
sudo apt install bluetooth bluez python3-pip -y
pip3 install flask requests --break-system-packages
```

### Step 2 - Set up Tailscale

Install Tailscale on your Ubuntu laptop by following the official instructions at tailscale.com/download/linux. Then install the Tailscale app on your iPhone from the App Store. Sign into the same Tailscale account on both devices. Once both devices appear as "Connected" in the Tailscale admin console at login.tailscale.com/admin/machines, your private tunnel is established.

Enable MagicDNS in your Tailscale admin console under DNS settings. This gives your laptop a stable hostname like `your-machine-name.your-tailnet.ts.net` that you'll use instead of a raw IP address.

### Step 3 - Provision a TLS certificate

Tether's unlock server needs HTTPS for iOS compatibility. Tailscale can provision a real, trusted TLS certificate for your laptop's MagicDNS hostname. Run:

```bash
sudo tailscale cert your-machine-name.your-tailnet.ts.net
```

This creates two files in your current directory: a `.crt` certificate file and a `.key` private key file. Move them somewhere permanent and fix the ownership so your user account can read them:

```bash
mkdir -p ~/.config/tether
mv your-machine-name.your-tailnet.ts.net.* ~/.config/tether/
sudo chown $USER:$USER ~/.config/tether/*.crt ~/.config/tether/*.key
```

### Step 4 - Find your iPhone's Bluetooth MAC address

Pair your iPhone with your Ubuntu laptop through the system Bluetooth settings if you haven't already. Then run:

```bash
bluetoothctl devices
```

Look for your iPhone in the list. The MAC address looks like `AA:BB:CC:DD:EE:FF`. Copy it: you'll need it in the next step.

### Step 5 - Set up ntfy on your iPhone

Install the ntfy app on your iPhone from the App Store. Choose a unique topic name: this is just a random string that acts as your personal notification channel. Something like `yourname-tether-unlock-x7k2` is obscure enough that strangers won't stumble upon it. In the ntfy app, tap "+" and subscribe to your chosen topic name.

### Step 6 - Install Tether

Clone the repository and copy the scripts to your local bin:

```bash
git clone https://github.com/yourusername/tether.git
cd tether
mkdir -p ~/.local/bin
cp src/tether.py ~/.local/bin/
cp src/tether-server.py ~/.local/bin/
```

### Step 7 - Configure Tether

Copy the example config file and fill in your values:

```bash
mkdir -p ~/.config/tether
cp config/tether.conf.example ~/.config/tether/tether.conf
nano ~/.config/tether/tether.conf
```

The config file looks like this: every value marked REQUIRED must be filled in:

```ini
[tether]
# REQUIRED: Your iPhone's Bluetooth MAC address (from Step 4)
device_mac = AA:BB:CC:DD:EE:FF

# REQUIRED: A secret token: make this something random and private.
# Your iPhone will need to include this in the unlock request.
# Treat it like a password. Example: Rf9kX2mQpL
secret_token = your-secret-token-here

# REQUIRED: Your Tailscale MagicDNS hostname (the full domain, not just the machine name)
tailscale_hostname = your-machine-name.your-tailnet.ts.net

# REQUIRED: Your ntfy topic name (the one you subscribed to in the ntfy app)
ntfy_topic = your-ntfy-topic-name

# REQUIRED: Full path to your Tailscale TLS certificate file
cert_file = /home/yourusername/.config/tether/your-machine-name.your-tailnet.ts.net.crt

# REQUIRED: Full path to your Tailscale TLS private key file
key_file = /home/yourusername/.config/tether/your-machine-name.your-tailnet.ts.net.key

# OPTIONAL: RSSI threshold below which the screen locks (default: -80)
# More negative = you have to walk further away before it locks.
# Tune this based on your home environment by watching the watcher logs.
lock_threshold = -80

# OPTIONAL: RSSI threshold above which the unlock notification fires (default: -65)
# Must be higher (less negative) than lock_threshold to create a hysteresis gap.
unlock_threshold = -65

# OPTIONAL: Seconds between each Bluetooth poll (default: 5)
# Increasing this reduces battery impact but slows response time.
poll_interval = 5

# OPTIONAL: Port for the Flask unlock server (default: 8080)
server_port = 8080
```

### Step 8 - Grant passwordless sudo for l2ping

Tether's proximity watcher uses `l2ping` to ping your iPhone, which requires root privileges. To allow this without a password prompt (necessary for unattended background operation), add a scoped sudoers rule:

```bash
sudo visudo
```

Add this line at the very bottom: it grants passwordless sudo specifically and only for `l2ping`, nothing else:

```
yourusername ALL=(ALL) NOPASSWD: /usr/bin/l2ping
```

### Step 9 - Install the systemd services

Copy the service files to your systemd user directory and enable them:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/tether.service ~/.config/systemd/user/
cp systemd/tether-server.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tether tether-server
```

Verify both services are running:

```bash
systemctl --user status tether tether-server
```

You should see `Active: active (running)` in green for both. From this point forward, Tether starts automatically every time you log into your desktop session and restarts itself if it ever crashes.

---

## Verifying the Installation

The best way to verify Tether is working is to watch the proximity watcher logs in real time:

```bash
journalctl --user -u tether -f
```

You should see readings coming in every 5 seconds. When your iPhone is nearby, the Raw RSSI will show `-50` (a synthetic value indicating a successful ping). When you walk away or turn off your phone's Bluetooth, the values will drop toward `-100` and eventually trigger a lock. When you return, the values climb back up and trigger the ntfy notification.

To test the unlock server independently, open Safari on your iPhone and navigate to:

```
https://your-machine-name.your-tailnet.ts.net:8080/status
```

You should see `tether is running`. To test a full unlock, lock your screen manually and then navigate to:

```
https://your-machine-name.your-tailnet.ts.net:8080/unlock?token=your-secret-token
```

Your screen should unlock.

---

## Setting Up the Apple Shortcut (Optional)

The ntfy notification already includes an embedded "Unlock Laptop" button that fires directly at your unlock server, so the Shortcut is optional. However, if you want a standalone one-tap unlock button on your iPhone Home Screen, you can create one in the Shortcuts app.

Open the Shortcuts app on your iPhone and create a new Shortcut. Add a "Get Contents of URL" action and set the URL to:

```
https://your-machine-name.your-tailnet.ts.net:8080/unlock?token=your-secret-token
```

Name it "Unlock Laptop" and add it to your Home Screen from the Shortcut's settings page. You now have a dedicated unlock button that works from anywhere your iPhone has internet access.

---

## Tuning Tether for Your Environment

The default RSSI thresholds (`lock_threshold = -80`, `unlock_threshold = -65`) are a reasonable starting point, but Bluetooth signal behavior varies significantly depending on your home's layout, wall materials, and how you carry your phone. The best way to tune Tether is to watch the live logs while moving around your space.

When you're sitting at your laptop with your phone on the desk, the raw RSSI should be consistently `-50` (successful ping). As you walk away, it will drop through `-50`, `-60`, `-70`, and eventually reach `-100` when the ping fails. Note the distance at which the reading first drops to `-100`: if that distance feels too close or too far for your preference, adjust `lock_threshold` accordingly. A less negative value (like `-70`) means you have to walk closer before it locks. A more negative value (like `-90`) means you can walk further before it locks.

The `poll_interval` setting is worth thinking about if you use Tether on battery frequently. Each l2ping briefly wakes your Bluetooth chip, and at the default 5-second interval that's 12 pings per minute. Increasing to 10 or 15 seconds halves or thirds that activity with only a modest impact on response time.

---

## Troubleshooting

**The watcher shows `-100` even when my phone is right next to the laptop.** This usually means your iPhone's Bluetooth is either off or the pairing has been lost. Check that Bluetooth is enabled on your iPhone and that your laptop appears as a paired device in iPhone Settings → Bluetooth. If it doesn't appear, you'll need to re-pair. After re-pairing, verify the MAC address hasn't changed by running `bluetoothctl devices` and checking that it matches `device_mac` in your config.

**The unlock request from my iPhone returns a 403 Forbidden error.** This means the token in your request doesn't match `secret_token` in your config. Double-check that your ntfy Actions URL and any Shortcuts you've created contain the exact same token string, with no extra spaces or characters.

**Safari says it can't connect to the unlock server.** Check that the tether-server service is running with `systemctl --user status tether-server`. Also verify your iPhone has Tailscale connected: the Tailscale app on iOS has its own connection toggle that must be enabled. If both are fine, try the `/status` endpoint first to isolate whether it's a network issue or a TLS issue.

**The screen locks but the ntfy notification never arrives on my iPhone.** First confirm your ntfy topic name in the config matches the topic you subscribed to in the ntfy app exactly: it's case-sensitive. Then check the watcher logs for the line `✅ Notification sent successfully`: if you see it, the issue is on the ntfy/iPhone side. If you see a warning about the request failing, check your laptop's internet connection.

**The services don't start after a reboot.** Tether uses systemd *user* services, which only start after you log into your desktop session: they won't run at the login screen. If both services show `active (running)` after you log in but not before, that's expected behavior. If they fail to start even after login, check `journalctl --user -u tether` for error messages.

**My iPhone's Bluetooth audio keeps routing to my laptop speakers.** This is a Bluetooth A2DP sink profile issue. Your laptop is advertising itself as an audio receiver, which iOS picks up and uses opportunistically. See the section below on disabling Bluetooth audio sink.

---

## Disabling Bluetooth Audio Sink (Optional)

If your Ubuntu laptop is hijacking audio from your iPhone, you can disable the A2DP sink Bluetooth profile without affecting Tether's proximity detection at all. Tether uses L2CAP pings which operate at a lower level of the Bluetooth stack than audio profiles.

If you're running WirePlumber as your PipeWire session manager (default on Ubuntu 22.04+), create this config file:

```bash
mkdir -p ~/.config/wireplumber/bluetooth.lua.d
nano ~/.config/wireplumber/bluetooth.lua.d/50-disable-a2dp-sink.lua
```

And add:

```lua
bluez_monitor.properties = {
  ["bluez5.roles"] = "[ a2dp_source hfp_ag hsp_ag hfp_hf hsp_hs ]"
}
```

Then restart WirePlumber and re-pair your iPhone:

```bash
systemctl --user restart wireplumber
```

After re-pairing, your laptop will no longer appear as an audio output device to your iPhone.

---

## Security Considerations

Tether is designed for personal convenience, not enterprise security. A few things worth understanding before you deploy it.

The secret token in your config file is the only thing preventing an unauthorized device on your Tailscale network from unlocking your laptop. Treat it like a password: make it random, don't share it, and don't commit it to a public repository. If you ever suspect it's been compromised, change it in your config and restart the tether-server service.

Tailscale's WireGuard tunnel means the unlock request is end-to-end encrypted between your iPhone and your laptop, and is not visible to anyone on the public internet. However, anyone who has both access to your Tailscale network and your secret token could unlock your laptop. For most personal use cases this is an acceptable risk.

The proximity detection is based on Bluetooth reachability, not identity. If someone physically takes your iPhone and walks near your laptop, Tether will send the unlock notification to your iPhone. This is intentional: the notification is the confirmation step that puts a human in the loop. Without your tap, the laptop stays locked.

---

## Project Structure

```
tether/
├── src/
│   ├── tether.py          # Bluetooth proximity watcher daemon
│   └── tether-server.py   # Flask HTTPS unlock server
├── systemd/
│   ├── tether.service         # systemd user service for the watcher
│   └── tether-server.service  # systemd user service for the server
├── config/
│   └── tether.conf.example    # Example configuration file
├── README.md
└── LICENSE
```

---

## Technology Stack

Tether is built on top of these technologies, all of which are free and open source except where noted.

**BlueZ** is the official Linux Bluetooth stack, providing the `l2ping` and `bluetoothctl` tools that Tether uses for proximity detection. **Python 3** runs both background daemons. **Flask** is the micro web framework that powers the unlock server. **Tailscale** (free for personal use, source-available) provides the WireGuard-based private mesh network and TLS certificate provisioning. **ntfy.sh** is a free, open-source push notification service with a self-hostable server if you prefer full control. **systemd** manages the background services and automatic startup. **WirePlumber** and **PipeWire** are the modern Linux audio stack, referenced in the optional Bluetooth audio configuration section.

---

## Contributing

Contributions are welcome. If you find a bug, please open an issue with your Ubuntu version, Python version, and the relevant section of your `journalctl` logs. If you want to add a feature, open an issue first to discuss it: Tether is intentionally minimal, and new features should fit within that philosophy.

Some areas that could use improvement: support for Android devices (which behave differently from iPhones regarding Bluetooth advertisement), a proper config validation step that runs on startup and gives clear errors for misconfiguration, and a setup wizard script that walks new users through the installation interactively.

---

## License

MIT License. See LICENSE for details.

---

## Acknowledgments

Built in one afternoon as a personal experiment, driven entirely by curiosity about how Linux Bluetooth tooling, Tailscale's private networking, and Apple's Shortcuts automation could be wired together into something genuinely useful. The fact that it works is a testament to how far open tooling has come.

*Named Tether because that's exactly what it is: an invisible thread between your phone and your laptop. When the thread snaps, the laptop protects itself. When it reconnects, it welcomes you back.*