# Tether 🔗

Tether is a lightweight, privacy-first proximity lock system for Ubuntu that uses your iPhone's Bluetooth signal as an invisible tether to your laptop. Walk away and your screen locks automatically. Come back and your laptop sends a push notification to your iPhone with a one-tap unlock button. No password typing, no manual locking, no third-party surveillance. Just you and your devices, talking to each other privately through an encrypted tunnel.

Built entirely with open-source tools. Runs silently as two background systemd services. All sensitive configuration lives in a file on your machine that never touches the repository.

---

## How It Works

Tether is built around one core idea: **your phone is your key**. As long as your phone is nearby, your laptop stays unlocked. The moment you walk away far enough that Bluetooth can no longer reach your phone, your laptop locks itself. When you return and your phone is detectable again, Tether sends a push notification to your iPhone with an embedded "Unlock Laptop" button. Tap it, and your laptop unlocks without typing a password.

Under the hood, Tether runs two background services. The first is the **proximity watcher** (`tether.py`), a Python daemon that pings your iPhone's Bluetooth MAC address every 5 seconds using `l2ping`. It maintains a rolling average of the last 5 readings to smooth out the natural noise in Bluetooth signals, so a momentary dropout does not trigger a false lock. A hysteresis gap between the lock threshold and the unlock threshold prevents the system from flapping lock-unlock-lock when you are standing right on the edge of range. The second is the **unlock server** (`tether-server.py`), a lightweight Flask HTTPS server that listens for an authenticated HTTP request from your iPhone and calls `loginctl unlock-session` through systemd-logind.

The communication between your iPhone and your laptop happens through **Tailscale**, a WireGuard-based private mesh network that gives both devices stable private IP addresses that can reach each other from anywhere: home Wi-Fi, mobile data, or a coffee shop network. Push notifications are delivered via **ntfy.sh**, a free and open-source pub/sub notification service that relays messages from your laptop to your iPhone in real time, with an action button embedded directly in the notification so you never need to open a separate app.

All sensitive values (your Bluetooth MAC address, secret token, ntfy topic, and Tailscale hostname) live exclusively in a configuration file on your machine at `~/.config/tether/tether.conf`. This file is never committed to the repository. The scripts read from it at startup and work for anyone who fills in their own values.

---

## Architecture

```
+------------------------------------------------------------------+
|                        YOUR HOME / OFFICE                         |
|                                                                   |
|   +--------------+    Bluetooth L2CAP ping    +---------------+  |
|   |   Ubuntu     | <------------------------> |    iPhone     |  |
|   |   Laptop     |                            |               |  |
|   |              |                            |               |  |
|   |  [tether.py] | ---- ntfy.sh (HTTPS) ----> | notification  |  |
|   |  proximity   |                            |   "Unlock?"   |  |
|   |  watcher     |                            |       |       |  |
|   |              | <--- Tailscale WireGuard -- |  tap button   |  |
|   |  [tether-    |         tunnel             |               |  |
|   |   server.py] |                            +---------------+  |
|   |  Flask HTTPS |                                               |
|   +--------------+                                               |
+-------------------------------------------------------------------+
```

The Bluetooth ping is entirely local and requires no internet connection. The ntfy notification and the Tailscale unlock signal both use the internet, but they do not require both devices to be on the same network. Your phone can be on mobile data while your laptop is on home Wi-Fi and everything still works.

---

## Requirements

**Hardware:** An Ubuntu laptop and an iPhone that are Bluetooth-paired with each other.

**Software on your Ubuntu laptop:** Python 3.8 or newer, the `bluez` package (provides `l2ping` and `bluetoothctl`), and the Python packages `flask` and `requests`. You will also need Tailscale installed and running.

**Software on your iPhone:** The Tailscale iOS app and the ntfy iOS app, both available free on the App Store.

**Accounts:** A free Tailscale account at tailscale.com. Both your laptop and iPhone must be signed into the same Tailscale account. You will also need a free ntfy.sh topic, which requires no account at all.

---

## Installation

### Step 1 - Install dependencies on your Ubuntu laptop

```bash
sudo apt update
sudo apt install bluetooth bluez python3-pip -y
pip3 install flask requests --break-system-packages
```

### Step 2 - Set up Tailscale

Install Tailscale on your Ubuntu laptop following the official instructions at tailscale.com/download/linux. Then install the Tailscale app on your iPhone from the App Store. Sign into the same Tailscale account on both devices. Once both devices appear as "Connected" in your Tailscale admin console at login.tailscale.com/admin/machines, your private tunnel is established.

Enable MagicDNS in your Tailscale admin console under DNS settings. This gives your laptop a stable hostname like `your-machine-name.your-tailnet.ts.net` that you will use in your configuration instead of a raw IP address that could change.

### Step 3 - Provision a TLS certificate

Tether's unlock server needs HTTPS for iOS compatibility. Tailscale can provision a real, trusted TLS certificate for your laptop's MagicDNS hostname:

```bash
sudo tailscale cert your-machine-name.your-tailnet.ts.net
```

This creates two files in your current directory: a `.crt` certificate file and a `.key` private key file. Fix the ownership so your user account can read them:

```bash
sudo chown $USER:$USER your-machine-name.your-tailnet.ts.net.crt
sudo chown $USER:$USER your-machine-name.your-tailnet.ts.net.key
```

Note the full paths to both files as you will need them in Step 5.

### Step 4 - Find your iPhone's Bluetooth MAC address

Pair your iPhone with your Ubuntu laptop through your system Bluetooth settings if you have not already done so. Then run:

```bash
bluetoothctl devices
```

Look for your iPhone in the list. The MAC address looks like `AA:BB:CC:DD:EE:FF`. Copy it as you will need it in the next step.

### Step 5 - Set up ntfy on your iPhone

Install the ntfy app on your iPhone from the App Store. Choose a unique topic name. This is just a random string that acts as your personal notification channel. Something like `yourname-tether-unlock-x7k2` works well. In the ntfy app, tap the "+" button and subscribe to your chosen topic name.

### Step 6 - Install Tether

Clone the repository and copy the scripts to your local bin directory:

```bash
git clone https://github.com/TadeyRuk/Tether.git
cd Tether
mkdir -p ~/.local/bin
cp tether.py ~/.local/bin/
cp tether-server.py ~/.local/bin/
```

### Step 7 - Create your configuration file

Copy the example config and fill in your personal values:

```bash
mkdir -p ~/.config/tether
cp tether.conf.example ~/.config/tether/tether.conf
nano ~/.config/tether/tether.conf
```

The config file looks like this:

```ini
[tether]
# Your iPhone's Bluetooth MAC address from Step 4
device_mac = AA:BB:CC:DD:EE:FF

# A secret token that acts as a password for the unlock endpoint.
# Make this something random and private. Never share it publicly.
secret_token = your-secret-token-here

# Your Tailscale MagicDNS hostname from Step 2
tailscale_hostname = your-machine-name.your-tailnet.ts.net

# Your ntfy topic name from Step 5
ntfy_topic = your-ntfy-topic-here

# Full paths to the TLS certificate files from Step 3
cert_file = /home/yourusername/your-machine-name.your-tailnet.ts.net.crt
key_file = /home/yourusername/your-machine-name.your-tailnet.ts.net.key

# Optional tuning values - these defaults work well for most setups
lock_threshold = -80
unlock_threshold = -65
poll_interval = 5
server_port = 8080
```

This file lives only on your machine and is protected by `.gitignore`. It will never be committed to the repository.

### Step 8 - Grant passwordless sudo for l2ping

Tether's proximity watcher uses `l2ping` to ping your iPhone, which requires root privileges. To allow this without a password prompt (necessary for unattended background operation), add a scoped sudoers rule:

```bash
sudo visudo
```

Add this line at the very bottom, replacing `yourusername` with your actual username:

```
yourusername ALL=(ALL) NOPASSWD: /usr/bin/l2ping
```

This grants passwordless sudo specifically and only for `l2ping`, nothing else.

### Step 9 - Install the systemd services

Copy the service files and enable them so Tether starts automatically every time you log in:

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

You should see `Active: active (running)` in green for both. Tether is now fully installed and will start automatically on every login.

---

## Verifying the Installation

The best way to verify Tether is working is to watch the proximity watcher logs in real time:

```bash
journalctl --user -u tether -f
```

You should see readings arriving every 5 seconds. When your iPhone is nearby the raw RSSI will show `-50`, which represents a successful l2ping response. When you walk away or turn off your phone's Bluetooth, the values will drop toward `-100` and eventually trigger a lock. When you return, the values climb back up and trigger the ntfy notification.

To test the unlock server independently, open Safari on your iPhone and navigate to:

```
https://your-machine-name.your-tailnet.ts.net:8080/status
```

You should see `tether is running`. To test a full unlock cycle, lock your screen manually and then navigate to:

```
https://your-machine-name.your-tailnet.ts.net:8080/unlock?token=your-secret-token
```

Your screen should unlock. If it does, the entire communication chain from iPhone to laptop through the Tailscale tunnel is working correctly.

---

## Setting Up the Apple Shortcut (Optional)

The ntfy notification already includes an embedded "Unlock Laptop" button that fires directly at your unlock server, so a separate Shortcut is optional. However, if you want a standalone one-tap unlock button on your iPhone Home Screen, you can create one in the Shortcuts app.

Open the Shortcuts app on your iPhone and create a new Shortcut. Add a "Get Contents of URL" action and set the URL to:

```
https://your-machine-name.your-tailnet.ts.net:8080/unlock?token=your-secret-token
```

Name it "Unlock Laptop" and add it to your Home Screen from the Shortcut's settings page.

---

## Tuning Tether for Your Environment

The default RSSI thresholds (`lock_threshold = -80`, `unlock_threshold = -65`) are a good starting point, but Bluetooth signal behavior varies depending on your home layout, wall materials, and how you carry your phone. The best way to tune Tether is to watch the live logs while moving around your space.

When you are sitting at your laptop with your phone nearby, the raw RSSI should be consistently `-50`. As you walk away, it will drop through `-60`, `-70`, and eventually reach `-100` when the ping fails entirely. Note the distance at which readings first drop to `-100` and adjust `lock_threshold` in your config file accordingly. A less negative value like `-70` means your laptop locks when you are closer. A more negative value like `-90` means you can walk further before it locks.

After changing any value in `tether.conf`, restart the watcher service for the changes to take effect:

```bash
systemctl --user restart tether
```

---

## How Configuration Works

All sensitive values are stored in `~/.config/tether/tether.conf` on your machine. When either script starts up, it reads this file using Python's built-in `configparser` module and loads your values into memory. If the file does not exist or a required field is missing, the script exits immediately with a clear error message telling you exactly what to fix.

This means the Python scripts themselves contain no sensitive information and are identical on every machine that runs Tether. The only thing that differs between your installation and someone else's is the `tether.conf` file, which never leaves your machine. This is the standard configuration pattern used by professional software: the code is universal, the configuration is personal.

---

## Troubleshooting

**The watcher shows `-100` even when my phone is right next to the laptop.** This usually means your iPhone's Bluetooth is off or the pairing has been lost. Check that Bluetooth is enabled on your iPhone and that your laptop appears as a paired device in iPhone Settings. If it is missing, re-pair the devices. After re-pairing, run `bluetoothctl devices` and confirm the MAC address still matches `device_mac` in your `tether.conf`. Some iPhones randomize their MAC address on re-pairing, in which case you will need to update your config and restart the service.

**The unlock request returns a 403 Forbidden error.** The token in your request does not match `secret_token` in your config. Double-check that your ntfy Actions URL and any Shortcuts you have created contain the exact same token string with no extra spaces or characters.

**Safari says it cannot connect to the unlock server.** Check that the tether-server service is running with `systemctl --user status tether-server`. Also verify that the Tailscale app on your iPhone is connected. If both are running, try the `/status` endpoint first to isolate whether it is a networking issue or a TLS issue.

**The screen locks but the ntfy notification never arrives on my iPhone.** Confirm your ntfy topic name in the config exactly matches the topic you subscribed to in the ntfy app. It is case-sensitive. Check the watcher logs for the line `Notification sent successfully`. If you see it, the issue is on the ntfy or iPhone side. If you see a warning about the request failing, check your laptop's internet connection.

**The services do not start after a reboot.** Tether uses systemd user services, which only start after you log into your desktop session. This is expected behavior. If both services show `active (running)` after login but not before, everything is working correctly. If they fail to start even after login, check `journalctl --user -u tether` for error messages.

**Config file not found error on startup.** This means the scripts cannot find `~/.config/tether/tether.conf`. Make sure you created the file by copying `tether.conf.example` and filling in your values. Run `cat ~/.config/tether/tether.conf` to verify the file exists and contains all required fields.

**My iPhone audio keeps routing to my laptop speakers.** This is a Bluetooth A2DP sink profile issue unrelated to Tether. See the section below on disabling Bluetooth audio sink.

---

## Disabling Bluetooth Audio Sink (Optional)

If your Ubuntu laptop is hijacking audio from your iPhone, you can disable the A2DP sink Bluetooth profile without affecting Tether at all. Tether uses L2CAP pings which operate at a much lower level of the Bluetooth stack than audio profiles, so this change is completely safe.

First check which audio session manager you are running:

```bash
systemctl --user status wireplumber
```

If it shows `active (running)`, you are using WirePlumber which is the default on Ubuntu 22.04 and newer. Create this config file:

```bash
mkdir -p ~/.config/wireplumber/bluetooth.lua.d
nano ~/.config/wireplumber/bluetooth.lua.d/50-disable-a2dp-sink.lua
```

Paste this inside:

```lua
bluez_monitor.properties = {
  ["bluez5.roles"] = "[ a2dp_source hfp_ag hsp_ag hfp_hf hsp_hs ]"
}
```

Then restart WirePlumber and re-pair your iPhone:

```bash
systemctl --user restart wireplumber
```

After re-pairing, your laptop will no longer appear as an audio output device to your iPhone. Verify Tether is still working by checking `journalctl --user -u tether -f` for the familiar `-50` readings.

---

## Security Considerations

Tether is designed for personal convenience, not enterprise security. A few things worth understanding before deploying it.

The secret token in your `tether.conf` is the primary protection against unauthorized unlocking. Treat it like a password: make it random, do not share it, and never commit it to a public repository. The `.gitignore` in this repository is configured to exclude `tether.conf` automatically.

Tailscale's WireGuard tunnel means the unlock request is end-to-end encrypted between your iPhone and your laptop and is not visible to anyone on the public internet. However, anyone who has both access to your Tailscale network and your secret token could unlock your laptop. For personal home use this is an acceptable risk.

The proximity detection is based on Bluetooth reachability, not identity verification. If someone physically takes your iPhone and walks near your laptop, Tether will send the unlock notification to your iPhone. The notification tap is the human confirmation step that keeps a person in the loop. Without your tap, the laptop stays locked.

---

## Project Structure

```
Tether/
├── tether.py                # Bluetooth proximity watcher daemon
├── tether-server.py         # Flask HTTPS unlock server
├── tether.conf.example      # Configuration template - copy and fill in your values
├── systemd/
│   ├── tether.service           # systemd user service for the watcher
│   └── tether-server.service    # systemd user service for the server
├── README.md
└── LICENSE
```

---

## Technology Stack

**BlueZ** is the official Linux Bluetooth stack, providing the `l2ping` and `bluetoothctl` tools that Tether uses for proximity detection. **Python 3** runs both background daemons. **Flask** is the micro web framework powering the unlock server. **Tailscale** (free for personal use, source-available) provides the WireGuard-based private mesh network and TLS certificate provisioning. **ntfy.sh** is a free, open-source push notification service with a self-hostable server if you prefer full control. **systemd** manages the background services and automatic startup. **WirePlumber** and **PipeWire** are referenced in the optional Bluetooth audio configuration section.

---

## Contributing

Contributions are welcome. If you find a bug, please open an issue with your Ubuntu version, Python version, and the relevant section of your `journalctl` logs. If you want to add a feature, open an issue first to discuss it. Tether is intentionally minimal and new features should fit within that philosophy.

Some areas that would benefit from improvement: support for Android devices, a setup wizard script that walks new users through installation interactively, and a config validation step that gives clear error messages for every possible misconfiguration.

---

## License

MIT License. See LICENSE for details.

---

*Named Tether because that is exactly what it is: an invisible thread between your phone and your laptop. When the thread snaps, the laptop protects itself. When it reconnects, it welcomes you back.*
