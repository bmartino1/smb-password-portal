#!/usr/bin/env python3

from flask import Flask, request, render_template_string, session
import os
import re
import time
import secrets
import subprocess
from collections import defaultdict, deque

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

SAMBA_SERVER = os.environ.get("SAMBA_SERVER", "127.0.0.1")
SMBPASSWD_BIN = os.environ.get("SMBPASSWD_BIN", "/usr/bin/smbpasswd")
MIN_PASSWORD_LENGTH = int(os.environ.get("MIN_PASSWORD_LENGTH", "8"))

# Client-facing default:
# 0 = users type username
# 1 = dropdown list
SHOW_USER_DROPDOWN = os.environ.get("SHOW_USER_DROPDOWN", "0") == "1"

# Mounted from Unraid host:
#   /boot/config -> /unraid-config:ro
UNRAID_CONFIG_DIR = os.environ.get("UNRAID_CONFIG_DIR", "/unraid-config")

# Basic in-memory rate limit.
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "5"))
RATE_WINDOW_SECONDS = int(os.environ.get("RATE_WINDOW_SECONDS", "300"))
_attempts = defaultdict(deque)

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")

# For the actual SMB password file, only root is blocked by default.
# If a username exists in /boot/config/smbpasswd, assume it is a real SMB account.
SMBPASSWD_EXCLUDE_USERS = {
    "root",
}

# For passwd fallback only, exclude system/service users.
PASSWD_FALLBACK_EXCLUDE_USERS = {
    "root",
    "daemon",
    "bin",
    "sys",
    "sync",
    "games",
    "man",
    "lp",
    "mail",
    "news",
    "uucp",
    "proxy",
    "www-data",
    "backup",
    "list",
    "irc",
    "gnats",
    "nobody",
    "systemd-network",
    "systemd-resolve",
    "messagebus",
    "sshd",
    "adm",
    "avahi",
    "avahi-autoipd",
    "dhcpcd",
    "ftp",
    "named",
    "ntp",
    "rpc",
}


HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Change SMB Password</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f4f5;
      color: #18181b;
      margin: 0;
      padding: 2rem;
    }

    .card {
      max-width: 520px;
      margin: 3rem auto;
      background: white;
      border-radius: 18px;
      padding: 2rem;
      box-shadow: 0 12px 30px rgba(0,0,0,0.08);
    }

    h1 {
      margin-top: 0;
      font-size: 1.6rem;
    }

    label {
      display: block;
      margin-top: 1rem;
      font-weight: 650;
    }

    input, select {
      width: 100%;
      box-sizing: border-box;
      margin-top: 0.4rem;
      padding: 0.75rem;
      border: 1px solid #d4d4d8;
      border-radius: 10px;
      font-size: 1rem;
    }

    button {
      margin-top: 1.5rem;
      width: 100%;
      padding: 0.85rem;
      border: 0;
      border-radius: 10px;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
      background: #18181b;
      color: white;
    }

    .message {
      margin-top: 1.2rem;
      padding: 0.8rem;
      border-radius: 10px;
      background: #f4f4f5;
    }

    .ok {
      background: #dcfce7;
      color: #14532d;
    }

    .bad {
      background: #fee2e2;
      color: #7f1d1d;
    }

    .hint {
      color: #52525b;
      font-size: 0.92rem;
      margin-top: 0.75rem;
      line-height: 1.35;
    }
  </style>
</head>
<body>
  <div class="card">
    <h1>Change SMB Password</h1>

    <form method="post" autocomplete="off">
      <input type="hidden" name="csrf_token" value="{{ csrf_token }}">

      {% if show_dropdown and users %}
        <label for="username">SMB username</label>
        <select id="username" name="username" required>
          <option value="">Select your user</option>
          {% for user in users %}
            <option value="{{ user }}">{{ user }}</option>
          {% endfor %}
        </select>
      {% else %}
        <label for="username">SMB username</label>
        <input id="username" name="username" required autocapitalize="none" autocomplete="username" spellcheck="false">
      {% endif %}

      <label for="old_password">Current SMB password</label>
      <input id="old_password" name="old_password" type="password" required autocomplete="current-password">

      <label for="new_password">New SMB password</label>
      <input id="new_password" name="new_password" type="password" required autocomplete="new-password">

      <label for="confirm_password">Confirm new SMB password</label>
      <input id="confirm_password" name="confirm_password" type="password" required autocomplete="new-password">

      <button type="submit">Change password</button>
    </form>

    <div class="hint">
      Your current password is required. This portal cannot reset forgotten passwords.
    </div>

    {% if message %}
      <div class="message {{ status }}">{{ message }}</div>
    {% endif %}
  </div>
</body>
</html>
"""


def valid_username(username: str) -> bool:
    return bool(USERNAME_RE.fullmatch(username or ""))


def read_users_from_smbpasswd():
    """
    Preferred source for actual SMB-enabled users on Unraid.

    Mounted from:
      /boot/config/smbpasswd -> /unraid-config/smbpasswd

    Expected smbpasswd-style format:
      username:uid:LMHASH:NTHASH:flags:...
    """
    users = set()
    smbpasswd_path = os.path.join(UNRAID_CONFIG_DIR, "smbpasswd")

    if not os.path.exists(smbpasswd_path):
        return users

    try:
        with open(smbpasswd_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                username = line.split(":", 1)[0].strip()

                if username in SMBPASSWD_EXCLUDE_USERS:
                    continue

                if valid_username(username):
                    users.add(username)

    except Exception:
        pass

    return users


def read_users_from_passwd_fallback():
    """
    Fallback only if /boot/config/smbpasswd does not exist or has no users.

    This avoids showing system/service users from passwd.
    """
    users = set()
    passwd_path = os.path.join(UNRAID_CONFIG_DIR, "passwd")

    if not os.path.exists(passwd_path):
        return users

    try:
        with open(passwd_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                parts = line.split(":")
                if len(parts) < 7:
                    continue

                username = parts[0].strip()
                shell = parts[6].strip()

                try:
                    uid = int(parts[2])
                except ValueError:
                    continue

                if username in PASSWD_FALLBACK_EXCLUDE_USERS:
                    continue

                if not valid_username(username):
                    continue

                if uid < 1000:
                    continue

                if shell in {
                    "/bin/false",
                    "/usr/sbin/nologin",
                    "/sbin/nologin",
                    "/bin/nologin",
                }:
                    continue

                users.add(username)

    except Exception:
        pass

    return users


def get_samba_users():
    """
    Use actual SMB password file first.

    Do not merge passwd into smbpasswd results, because passwd contains
    system/service users that are not client-facing SMB users.
    """
    smb_users = read_users_from_smbpasswd()

    if smb_users:
        return sorted(smb_users, key=str.lower), "smbpasswd"

    fallback_users = read_users_from_passwd_fallback()
    return sorted(fallback_users, key=str.lower), "passwd_fallback"


def csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def check_csrf(posted_token):
    return posted_token and posted_token == session.get("csrf_token")


def client_key(username):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip = ip.split(",", 1)[0].strip()
    return f"{ip}:{username}"


def rate_limited(username):
    now = time.time()
    key = client_key(username)
    q = _attempts[key]

    while q and now - q[0] > RATE_WINDOW_SECONDS:
        q.popleft()

    if len(q) >= MAX_ATTEMPTS:
        return True

    q.append(now)
    return False


def change_smb_password(username, old_password, new_password):
    """
    Calls smbpasswd as a remote client against the Unraid host Samba daemon.
    The old password is supplied through stdin, not as a command-line argument.
    """
    proc = subprocess.run(
        [
            SMBPASSWD_BIN,
            "-s",
            "-r",
            SAMBA_SERVER,
            "-U",
            username,
        ],
        input=f"{old_password}\n{new_password}\n{new_password}\n",
        text=True,
        capture_output=True,
        timeout=15,
    )

    return proc.returncode, proc.stdout, proc.stderr


@app.route("/", methods=["GET", "POST"])
def index():
    message = ""
    status = ""
    users, user_source = get_samba_users()

    if request.method == "POST":
        posted_csrf = request.form.get("csrf_token", "")
        username = request.form.get("username", "").strip()
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_csrf(posted_csrf):
            message = "Invalid form token. Refresh the page and try again."
            status = "bad"

        elif not valid_username(username):
            message = "Invalid username."
            status = "bad"

        elif users and username not in users:
            message = "That username is not listed as an SMB user on this server."
            status = "bad"

        elif rate_limited(username):
            message = "Too many attempts. Wait a few minutes and try again."
            status = "bad"

        elif new_password != confirm_password:
            message = "New passwords do not match."
            status = "bad"

        elif len(new_password) < MIN_PASSWORD_LENGTH:
            message = f"New password must be at least {MIN_PASSWORD_LENGTH} characters."
            status = "bad"

        elif old_password == new_password:
            message = "New password must be different from the current password."
            status = "bad"

        else:
            try:
                code, out, err = change_smb_password(username, old_password, new_password)

                if code == 0:
                    message = "Password changed successfully."
                    status = "ok"
                    session["csrf_token"] = secrets.token_urlsafe(32)
                else:
                    message = "Password change failed. Check your current password."
                    status = "bad"

            except subprocess.TimeoutExpired:
                message = "Password change timed out. Try again later."
                status = "bad"

            except Exception:
                message = "Server error while changing password."
                status = "bad"

    return render_template_string(
        HTML,
        users=users,
        show_dropdown=SHOW_USER_DROPDOWN,
        csrf_token=csrf_token(),
        message=message,
        status=status,
    )


@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok\n", 200


@app.route("/debug/users", methods=["GET"])
def debug_users():
    """
    Troubleshooting endpoint.
    Enable with:
      -e ENABLE_DEBUG_USERS="1"

    Disable for final client-facing deployment.
    """
    if os.environ.get("ENABLE_DEBUG_USERS", "0") != "1":
        return "disabled\n", 404

    users, source = get_samba_users()
    body = []
    body.append(f"source={source}")
    body.append(f"count={len(users)}")
    body.extend(users)
    return "\n".join(body) + "\n", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
