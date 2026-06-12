# ==============================================================================
# 🐾 EASTER EGG: Dedicated to Rukkan, the absolute best cat in the world! 🐾
# "This project is lovingly dedicated to my cat Rukkan. I love him!"
#
#       /\_/\   
#      ( o.o )  
#       > ^ <   ~ *meow*
# ==============================================================================

import subprocess
import sys
import time
import logging
import threading
import requests
import configparser
import os
import socket
import errno
from collections import deque
import tether_notify

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
LOCK_THRESHOLD    = config.getint("tether", "lock_threshold",    fallback=-80)
UNLOCK_THRESHOLD  = config.getint("tether", "unlock_threshold", fallback=-65)
POLL_INTERVAL     = config.getint("tether", "poll_interval",    fallback=5)
LOCK_GRACE_PERIOD = config.getint("tether", "lock_grace_period", fallback=20)
MISSING_RSSI     = -100
RSSI_WINDOW      = 5
PROBE_PSM        = 1     # L2CAP SDP channel — reachable on any paired device
PROBE_TIMEOUT    = 4     # seconds to wait for the device to answer the page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def get_rssi(mac):
    # Active reachability probe via an L2CAP connection attempt. This replaces
    # the old `sudo l2ping`, which BlueZ has removed from modern distros (e.g.
    # Fedora). Like l2ping, the connect pages the device, so it works whether or
    # not there is an active connection — and needs no root. A successful connect
    # (or an active refusal) means the phone answered and is in range; a timeout
    # or host-down means it is gone. Returns the same binary -50 / -100 signal
    # the original l2ping path produced.
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    sock.settimeout(PROBE_TIMEOUT)
    try:
        sock.connect((mac, PROBE_PSM))
        return -50
    except OSError as e:
        if e.errno == errno.ECONNREFUSED:
            return -50
        log.debug(f"l2cap probe failed: {e}")
    finally:
        sock.close()

    # Fallback: if the phone is actively connected, read its real RSSI.
    try:
        result = subprocess.run(
            ["bluetoothctl", "info", mac],
            capture_output=True, text=True, timeout=4
        )
        for line in result.stdout.splitlines():
            if "RSSI" in line:
                value = int(line.split("(")[-1].rstrip(") ").strip())
                if value != 0:
                    return value
    except Exception:
        pass

    return MISSING_RSSI


def _grace_notification_worker(grace_seconds, cancel_event):
    """Background thread: show action notification; set cancel_event if user cancels."""
    try:
        result = subprocess.run(
            [
                "notify-send",
                "--action=cancel:Cancel",
                f"--expire-time={grace_seconds * 1000}",
                "--urgency=critical",
                "--app-name=Tether",
                "Tether — Phone out of range",
                f"Locking in {grace_seconds}s. Tap Cancel to stay unlocked.",
            ],
            capture_output=True,
            text=True,
            timeout=grace_seconds + 5,
        )
        if result.stdout.strip() == "cancel":
            cancel_event.set()
    except Exception as e:
        log.debug(f"Grace notification error: {e}")


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
    if len(sys.argv) > 1 and sys.argv[1] == "--rukkan":
        print("\n🐾 Rukkan Mode Activated! 🐾")
        print("Dedicated to Rukkan, the most wonderful cat in the universe.")
        print("May your lines of code be as soft and comforting as his purrs. ❤️")
        print("\n       /\\_/\\  ")
        print("      ( o.o ) ")
        print("       > ^ <  ~ Purrrrrrr!\n")
        return

    log.info("Bluetooth Proximity Watcher started")
    log.info(f"Watching device: {DEVICE_MAC}")
    log.info(f"Lock threshold:   {LOCK_THRESHOLD} dBm")
    log.info(f"Unlock threshold: {UNLOCK_THRESHOLD} dBm")

    tether_notify.notify_startup(DEVICE_MAC)

    rssi_window = deque(maxlen=RSSI_WINDOW)
    is_locked = False
    pending_lock_since = None
    cancel_lock_event = threading.Event()

    while True:
        rssi = get_rssi(DEVICE_MAC)
        rssi_window.append(rssi)

        if len(rssi_window) < RSSI_WINDOW:
            log.info(f"Warming up... ({len(rssi_window)}/{RSSI_WINDOW} readings)")
            time.sleep(POLL_INTERVAL)
            continue

        avg = sum(rssi_window) / len(rssi_window)
        log.info(
            f"Avg RSSI: {avg:.1f} dBm | Raw: {rssi} dBm | "
            f"Locked: {is_locked} | Pending: {pending_lock_since is not None}"
        )

        if not is_locked:
            if avg < LOCK_THRESHOLD:
                if pending_lock_since is None:
                    # Enter grace period — ask the user before locking.
                    pending_lock_since = time.time()
                    cancel_lock_event.clear()
                    if LOCK_GRACE_PERIOD > 0:
                        log.info(f"Phone out of range — grace period started ({LOCK_GRACE_PERIOD}s)")
                        t = threading.Thread(
                            target=_grace_notification_worker,
                            args=(LOCK_GRACE_PERIOD, cancel_lock_event),
                            daemon=True,
                        )
                        t.start()
                    tether_notify.notify_pending_lock(DEVICE_MAC, LOCK_GRACE_PERIOD)
                else:
                    elapsed = time.time() - pending_lock_since
                    if LOCK_GRACE_PERIOD <= 0 or elapsed >= LOCK_GRACE_PERIOD:
                        if cancel_lock_event.is_set():
                            log.info("Lock cancelled by user during grace period.")
                        else:
                            lock_screen()
                            tether_notify.notify_lock(DEVICE_MAC)
                            is_locked = True
                        pending_lock_since = None
            else:
                if pending_lock_since is not None:
                    # Phone came back in range during grace — cancel silently.
                    log.info("Phone back in range — pending lock cancelled.")
                    cancel_lock_event.set()
                    pending_lock_since = None

        elif avg > UNLOCK_THRESHOLD:
            send_ntfy_notification()
            tether_notify.notify_unlock(DEVICE_MAC)
            is_locked = False

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()