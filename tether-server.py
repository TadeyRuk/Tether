from flask import Flask, request, abort
import subprocess
import logging

app = Flask(__name__)

# Your secret token — change this to something only you know
SECRET_TOKEN = "Rukkan_Folded_Paw"

# Simple logging so you can see activity in the terminal
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@app.route("/unlock", methods=["GET"])
def unlock():
    token = request.args.get("token")

    if token != SECRET_TOKEN:
        log.warning(f"Rejected unlock attempt with token: {token}")
        abort(403)

    log.info("✅ Correct token received — unlocking screen...")
    subprocess.run(["loginctl", "unlock-session"])
    return "unlocked", 200


@app.route("/status", methods=["GET"])
def status():
    return "bt-proximity-lock is running", 200


if __name__ == "__main__":
    log.info("🚀 Unlock server starting on port 8080...")
    app.run(
        host="0.0.0.0",
        port=8080,
	ssl_context=(
    		"/home/tadey/tadey-asus-tuf-gaming-a15-fa507nu-fa507nu.tailb4de09.ts.net.crt",
    		"/home/tadey/tadey-asus-tuf-gaming-a15-fa507nu-fa507nu.tailb4de09.ts.net.key"
        )
    )
