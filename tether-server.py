from flask import Flask, request, abort
import subprocess
import logging
import configparser
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
PORT         = config.getint("tether", "server_port", fallback=8080)

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


@app.route("/unlock", methods=["GET"])
def unlock():
    # Check that the request includes the correct secret token
    # Any request with a missing or wrong token gets a 403 Forbidden response
    token = request.args.get("token")

    if token != SECRET_TOKEN:
        log.warning(f"Rejected unlock attempt with token: {token}")
        abort(403)

    log.info("Correct token received - unlocking screen...")
    subprocess.run(["loginctl", "unlock-session"])
    return "unlocked", 200

@app.route("/lock", methods=["GET"])
def lock():
    token = request.args.get("token")

    if token != SECRET_TOKEN:
        log.warning(f"Rejected lock attempt with token: {token}")
        abort(403)

    log.info("Correct token received - locking screen...")
    subprocess.run(["loginctl", "lock-session"])
    return "locked", 200


@app.route("/status", methods=["GET"])
def status():
    # A simple health check endpoint
    # Visit /status to confirm the server is running and reachable
    return "tether is running", 200


if __name__ == "__main__":
    log.info("Tether unlock server starting...")
    app.run(
        host="0.0.0.0",
        port=PORT,
        ssl_context=(CERT_FILE, KEY_FILE)
    )
