import subprocess
import logging
import requests

log = logging.getLogger(__name__)


def check_tailscale():
    """Check if Tailscale is running and connected."""
    try:
        result = subprocess.run(
            ["tailscale", "status"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, "Tailscale connected"
        return False, "Tailscale is offline"
    except FileNotFoundError:
        return False, "Tailscale is not installed"
    except Exception as e:
        return False, f"Tailscale check failed: {e}"


def check_bluetooth_adapter():
    """Check if the Bluetooth adapter is powered on."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "show"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "Powered:" in line and "yes" in line.lower():
                return True, "Bluetooth adapter is on"
        return False, "Bluetooth adapter is off"
    except FileNotFoundError:
        return False, "bluetoothctl is not installed"
    except Exception as e:
        return False, f"Bluetooth check failed: {e}"


def check_bluetooth_device(device_mac):
    """Check if the phone is connected or reachable via Bluetooth."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "info", device_mac],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or "not available" in result.stdout.lower():
            return False, "Phone not found via Bluetooth"
        for line in result.stdout.splitlines():
            if "Connected:" in line and "yes" in line.lower():
                return True, "Phone connected via Bluetooth"
        return True, "Phone paired but not connected"
    except Exception as e:
        return False, f"Bluetooth device check failed: {e}"


def check_ntfy():
    """Check if ntfy.sh is reachable."""
    try:
        resp = requests.head("https://ntfy.sh", timeout=5)
        if resp.status_code < 400:
            return True, "ntfy.sh is reachable"
        return False, f"ntfy.sh returned HTTP {resp.status_code}"
    except requests.RequestException as e:
        return False, f"Failed to reach ntfy.sh: {e}"


def run_readiness_checks(device_mac):
    """Run all readiness checks and return structured results."""
    checks = {
        "tailscale": check_tailscale(),
        "bluetooth_adapter": check_bluetooth_adapter(),
        "bluetooth_device": check_bluetooth_device(device_mac),
        "ntfy": check_ntfy(),
    }

    all_ok = all(ok for ok, _ in checks.values())
    failed = [msg for ok, msg in checks.values() if not ok]
    passed = [msg for ok, msg in checks.values() if ok]

    return {
        "all_ok": all_ok,
        "checks": checks,
        "failed": failed,
        "passed": passed,
    }


def _build_detail(readiness):
    """Build a human-readable detail string from readiness results."""
    if readiness["all_ok"]:
        return "All components are optimal"
    return ". ".join(readiness["failed"])


SOUNDS = {
    "critical": "/usr/share/sounds/freedesktop/stereo/dialog-error.oga",
    "normal":   "/usr/share/sounds/freedesktop/stereo/message.oga",
    "lock":     "/usr/share/sounds/freedesktop/stereo/screen-capture.oga",
    "unlock":   "/usr/share/sounds/freedesktop/stereo/service-login.oga",
}


def _play_sound(sound_key):
    """Play a system sound using paplay (non-blocking)."""
    path = SOUNDS.get(sound_key, SOUNDS["normal"])
    try:
        subprocess.Popen(["paplay", path])
    except FileNotFoundError:
        try:
            subprocess.Popen(["aplay", path])
        except Exception:
            pass
    except Exception:
        pass


def notify(summary, body, urgency="normal", sound_key=None):
    """Send a desktop notification via notify-send and play a sound."""
    icon = "lock-screen" if "Lock" in summary or "inactive" in summary.lower() else "security-high"
    cmd = [
        "notify-send",
        "--urgency", urgency,
        "--icon", icon,
        "--app-name", "Tether",
        summary,
        body,
    ]
    try:
        subprocess.run(cmd, timeout=5)
        log.info(f"Desktop notification: {summary} — {body}")
    except FileNotFoundError:
        log.warning("notify-send not found. Install libnotify-bin for desktop notifications.")
    except Exception as e:
        log.warning(f"Failed to send desktop notification: {e}")

    if sound_key is None:
        sound_key = "critical" if urgency == "critical" else "normal"
    _play_sound(sound_key)


def notify_startup(device_mac):
    """Send a startup notification with readiness check results."""
    readiness = run_readiness_checks(device_mac)
    detail = _build_detail(readiness)

    if readiness["all_ok"]:
        notify("Tether active — Monitoring started", detail)
    else:
        failed_count = len(readiness["failed"])
        total = len(readiness["checks"])
        notify(
            f"Tether active — {total - failed_count}/{total} checks passed",
            detail,
            urgency="critical" if failed_count >= 2 else "normal",
        )
    return readiness


def notify_lock(device_mac):
    """Send a notification when the screen is locked."""
    readiness = run_readiness_checks(device_mac)
    detail = _build_detail(readiness)

    if readiness["all_ok"]:
        notify(
            "Tether active — Screen locked",
            f"Phone left proximity. {detail}",
            sound_key="lock",
        )
    else:
        notify(
            "Tether active — Screen locked (degraded)",
            f"Phone left proximity. {detail}",
            urgency="normal",
            sound_key="lock",
        )
    return readiness


def notify_unlock(device_mac):
    """Send a notification when the screen is unlocked."""
    readiness = run_readiness_checks(device_mac)
    detail = _build_detail(readiness)

    if readiness["all_ok"]:
        notify(
            "Tether active — Screen unlocked",
            f"Phone detected nearby. {detail}",
            sound_key="unlock",
        )
    else:
        notify(
            "Tether active — Unlock sent (degraded)",
            f"Phone detected nearby. {detail}",
            urgency="normal",
            sound_key="unlock",
        )
    return readiness


def notify_error(message):
    """Send a notification when Tether encounters a critical error."""
    notify(
        "Tether inactive — System error",
        message,
        urgency="critical",
    )
