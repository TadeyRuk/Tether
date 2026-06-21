# ==============================================================================
# 🐾 EASTER EGG: Dedicated to Rukkan, the absolute best cat in the world! 🐾
# "This project is lovingly dedicated to my cat Rukkan. I love him!"
#
#       /\_/\   
#      ( o.o )  
#       > ^ <   ~ *meow*
# ==============================================================================

from flask import Flask, request, abort
import subprocess
import logging
import configparser
import time
import os

# Load sensitive configuration from ~/.config/tether/tether.conf
# This file lives only on your machine and is never committed to Git.
config = configparser.ConfigParser()
config_path = os.path.expanduser("~/.config/tether/tether.conf")

if not os.path.exists(config_path):
    raise FileNotFoundError(
        f"Config file not found at {config_path}.\n"
        "Copy tether.conf.example to ~/.config/tether/tether.conf "
        "and fill in your values before running Tether."
    )

config.read(config_path)

SECRET_TOKEN = config.get("tether", "secret_token")
CERT_FILE    = config.get("tether", "cert_file")
KEY_FILE     = config.get("tether", "key_file")
PORT           = config.getint("tether", "server_port", fallback=8080)
RETRY_ATTEMPTS = 3
RETRY_DELAY    = 1  # seconds between retries

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def run_with_retry(cmd):
    """Run a shell command with retries. Returns (success, error_message)."""
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True, None
            last_error = result.stderr.strip() or f"exit code {result.returncode}"
            log.warning(f"Attempt {attempt}/{RETRY_ATTEMPTS} failed: {last_error}")
        except Exception as e:
            last_error = str(e)
            log.warning(f"Attempt {attempt}/{RETRY_ATTEMPTS} raised exception: {last_error}")
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_DELAY)
    return False, last_error


@app.route("/unlock", methods=["GET"])
def unlock():
    token = request.args.get("token")

    if token != SECRET_TOKEN:
        log.warning(f"Rejected unlock attempt with token: {token}")
        return "Invalid token", 403

    log.info("Correct token received - attempting to unlock screen...")
    ok, error = run_with_retry(["loginctl", "unlock-session"])

    if ok:
        log.info("Screen unlocked successfully.")
        return "Screen unlocked successfully", 200
    else:
        log.error(f"Failed to unlock screen after {RETRY_ATTEMPTS} attempts: {error}")
        return f"Failed after {RETRY_ATTEMPTS} attempts: {error}", 500


@app.route("/lock", methods=["GET"])
def lock():
    token = request.args.get("token")

    if token != SECRET_TOKEN:
        log.warning(f"Rejected lock attempt with token: {token}")
        return "Invalid token", 403

    log.info("Correct token received - attempting to lock screen...")
    ok, error = run_with_retry(["loginctl", "lock-session"])

    if ok:
        log.info("Screen locked successfully.")
        return "Screen locked successfully", 200
    else:
        log.error(f"Failed to lock screen after {RETRY_ATTEMPTS} attempts: {error}")
        return f"Failed after {RETRY_ATTEMPTS} attempts: {error}", 500


@app.route("/status", methods=["GET"])
def status():
    return "Tether is running", 200


@app.route("/rukkan", methods=["GET"])
def rukkan():
    return (
        """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🐾 Rukkan 🐾</title>
<style>
  body { background:#1a1a2e; color:#e0e0e0; font-family:monospace;
         display:flex; flex-direction:column; align-items:center;
         justify-content:center; min-height:100vh; margin:0; }
  pre  { color:#f0a500; font-size:1.2rem; line-height:1.4; }
  h1   { color:#f0a500; font-size:2rem; margin-bottom:0.2em; }
  p    { color:#aaa; font-size:1rem; margin:0.3em 0; }
  .heart { color:#e05c97; }
</style>
</head>
<body>
<h1>🐾 Rukkan 🐾</h1>
<pre>
    /\\_/\\
   ( o.o )
    > ^ <
   /|   |\\
  (_|   |_)
</pre>
<p>This project is lovingly dedicated to</p>
<p><strong>Rukkan</strong> — the absolute best cat in the world.</p>
<p class="heart">❤️ I love him! ❤️</p>
</body>
</html>""",
        200,
        {"Content-Type": "text/html"},
    )


if __name__ == "__main__":
    log.info("Tether unlock server starting...")
    app.run(
        host="0.0.0.0",
        port=PORT,
        ssl_context=(CERT_FILE, KEY_FILE)
    )
