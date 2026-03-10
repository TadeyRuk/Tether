import subprocess
import time
import logging
import requests
from collections import deque

# ─── CONFIGURATION — update these values before running ───────────────────────

# Your iPhone's Bluetooth MAC address (from `bluetoothctl devices`)
DEVICE_MAC = "80:54:E3:CA:B2:0B"  # ← REPLACE THIS

# RSSI thresholds in dBm — more negative means weaker/farther signal.
# LOCK_THRESHOLD:   if average RSSI drops below this, you've left → lock.
# UNLOCK_THRESHOLD: if average RSSI rises above this, you're back → notify.
# The gap between them is your hysteresis buffer — prevents flapping.
LOCK_THRESHOLD   = -80
UNLOCK_THRESHOLD = -65

# Value used when the device simply isn't detected at all
MISSING_RSSI = -100

# How many readings to average — higher means slower but more stable decisions
RSSI_WINDOW = 5

# Seconds between each poll — every 5 seconds is a good balance
POLL_INTERVAL = 5

# Your ntfy topic
NTFY_TOPIC = "rukkan_paw_unlock_theLinux_120604"

# Your secret token (must match SECRET_TOKEN in unlock_server.py)
SECRET_TOKEN = "Rukkan_Folded_Paw"  # ← REPLACE THIS

# Your laptop's full Tailscale HTTPS address
LAPTOP_URL = "https://tadey-asus-tuf-gaming-a15-fa507nu-fa507nu.tailb4de09.ts.net:8080"

# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def get_rssi(mac):
    """
    Determine if the device is nearby using two approaches.
    
    Primary: l2ping — sends a Bluetooth ping and waits for a response.
             Returns a strong synthetic RSSI (-50) if reachable,
             or MISSING_RSSI if unreachable. This is the most reliable
             method for iPhones which don't continuously broadcast RSSI.
    
    Fallback: bluetoothctl info — checks for actual RSSI data in case
              the device is connected and broadcasting signal strength.
    """
    # Method 1: l2ping reachability check
    # -c 1 means send 1 ping, -t 3 means wait 3 seconds for a response
    # We run as the current user — note: l2ping may need sudo on some systems
    try:
        result = subprocess.run(
            ["sudo", "l2ping", "-c", "1", "-t", "3", mac],
            capture_output=True, text=True, timeout=6
        )
        if result.returncode == 0:
            # Device responded to ping — it's definitely nearby
            # We return a synthetic "strong signal" value
            log.debug(f"l2ping: {mac} is reachable")
            return -50
        else:
            # Device didn't respond — it's out of range or powered off
            log.debug(f"l2ping: {mac} is unreachable")
            return MISSING_RSSI
    except Exception as e:
        log.debug(f"l2ping failed: {e}")

    # Method 2: bluetoothctl RSSI fallback
    try:
        result = subprocess.run(
            ["bluetoothctl", "info", mac],
            capture_output=True, text=True, timeout=4
        )
        for line in result.stdout.splitlines():
            if "RSSI" in line:
                value = int(line.split(":")[-1].strip())
                if value != 0:  # ignore spurious zero readings
                    return value
    except Exception:
        pass

    return MISSING_RSSI

def lock_screen():
    """Lock the screen using systemd-logind."""
    log.info("🔒 Locking screen — you've left the area.")
    subprocess.run(["loginctl", "lock-session"])


def send_ntfy_notification():
    """
    Push a notification to the iPhone via ntfy.
    The Actions header embeds the unlock button directly in the notification
    so the user can unlock without opening any app.
    """
    log.info("📱 Sending unlock notification to iPhone...")
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            headers={
                # Encode header values as UTF-8 bytes to support emojis
                # latin-1 (requests default) can't handle emoji characters
                "Title": "You're home, Tadey!".encode("utf-8"),
                "Priority": "high",
                "Tags": "key,tada",
                "Actions": f"view, Unlock Laptop, {LAPTOP_URL}/unlock?token={SECRET_TOKEN}",
            },
            data="Your laptop detected you nearby. Tap to unlock.".encode("utf-8"),
            timeout=10
        )
        log.info("✅ Notification sent successfully.")
    except requests.RequestException as e:
        log.warning(f"Failed to send ntfy notification: {e}")

def main():
    log.info("═══════════════════════════════════════════════")
    log.info("   Bluetooth Proximity Watcher started")
    log.info(f"   Watching device: {DEVICE_MAC}")
    log.info(f"   Lock threshold:   {LOCK_THRESHOLD} dBm")
    log.info(f"   Unlock threshold: {UNLOCK_THRESHOLD} dBm")
    log.info("═══════════════════════════════════════════════")

    # A deque is a list with a maximum size — old readings automatically
    # fall off the left end as new ones are added to the right.
    rssi_window = deque(maxlen=RSSI_WINDOW)
    is_locked = False

    while True:
        rssi = get_rssi(DEVICE_MAC)
        rssi_window.append(rssi)

        # Wait until the window is full before making any decisions
        # so we're always averaging a full set of readings
        if len(rssi_window) < RSSI_WINDOW:
            log.info(f"Warming up... ({len(rssi_window)}/{RSSI_WINDOW} readings)")
            time.sleep(POLL_INTERVAL)
            continue

        avg = sum(rssi_window) / len(rssi_window)
        log.info(f"Avg RSSI: {avg:.1f} dBm | Raw: {rssi} dBm | Locked: {is_locked}")

        if not is_locked and avg < LOCK_THRESHOLD:
            # Average signal has dropped below lock threshold — you've left
            lock_screen()
            is_locked = True

        elif is_locked and avg > UNLOCK_THRESHOLD:
            # Average signal has risen above unlock threshold — you're back
            send_ntfy_notification()
            is_locked = False

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
