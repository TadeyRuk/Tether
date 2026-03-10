import subprocess
import time
import logging
import requests
import configparser
import os
from collections import deque

config = configparser.ConfigParser()
config_path = os.path.expanduser("~/.config/tether/tether.conf")

if not os.path.exists(config_path):
    raise FileNotFoundError(
        f"Config file not found at {config_path}.\n"
        "Copy tether.conf.example to ~/.config/tether/tether.conf "
        "and fill in your values before running Tether."
    )

config.read(config_path)

DEVICE_MAC       = config.get("tether", "device_mac")
SECRET_TOKEN     = config.get("tether", "secret_token")
NTFY_TOPIC       = config.get("tether", "ntfy_topic")
LAPTOP_URL       = f"https://{config.get('tether', 'tailscale_hostname')}:8080"
LOCK_THRESHOLD   = config.getint("tether", "lock_threshold",   fallback=-80)
UNLOCK_THRESHOLD = config.getint("tether", "unlock_threshold", fallback=-65)
POLL_INTERVAL    = config.getint("tether", "poll_interval",    fallback=5)
MISSING_RSSI     = -100
RSSI_WINDOW      = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def get_rssi(mac):
    try:
        result = subprocess.run(
            ["sudo", "l2ping", "-c", "1", "-t", "3", mac],
            capture_output=True, text=True, timeout=6
        )
        if result.returncode == 0:
            return -50
        else:
            return MISSING_RSSI
    except Exception as e:
        log.debug(f"l2ping failed: {e}")

    try:
        result = subprocess.run(
            ["bluetoothctl", "info", mac],
            capture_output=True, text=True, timeout=4
        )
        for line in result.stdout.splitlines():
            if "RSSI" in line:
                value = int(line.split(":")[-1].strip())
                if value != 0:
                    return value
    except Exception:
        pass

    return MISSING_RSSI


def lock_screen():
    log.info("Locking screen - you have left the area.")
    subprocess.run(["loginctl", "lock-session"])


def send_ntfy_notification():
    log.info("Sending unlock notification to iPhone...")
    try:
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            headers={
                "Title": "You're home!".encode("utf-8"),
                "Priority": "high",
                "Tags": "key,tada",
                "Actions": f"view, Unlock Laptop, {LAPTOP_URL}/unlock?token={SECRET_TOKEN}",
            },
            data="Your laptop detected you nearby. Tap to unlock.".encode("utf-8"),
            timeout=10
        )
        log.info("Notification sent successfully.")
    except requests.RequestException as e:
        log.warning(f"Failed to send ntfy notification: {e}")


def main():
    log.info("Bluetooth Proximity Watcher started")
    log.info(f"Watching device: {DEVICE_MAC}")
    log.info(f"Lock threshold:   {LOCK_THRESHOLD} dBm")
    log.info(f"Unlock threshold: {UNLOCK_THRESHOLD} dBm")

    rssi_window = deque(maxlen=RSSI_WINDOW)
    is_locked = False

    while True:
        rssi = get_rssi(DEVICE_MAC)
        rssi_window.append(rssi)

        if len(rssi_window) < RSSI_WINDOW:
            log.info(f"Warming up... ({len(rssi_window)}/{RSSI_WINDOW} readings)")
            time.sleep(POLL_INTERVAL)
            continue

        avg = sum(rssi_window) / len(rssi_window)
        log.info(f"Avg RSSI: {avg:.1f} dBm | Raw: {rssi} dBm | Locked: {is_locked}")

        if not is_locked and avg < LOCK_THRESHOLD:
            lock_screen()
            is_locked = True

        elif is_locked and avg > UNLOCK_THRESHOLD:
            send_ntfy_notification()
            is_locked = False

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()