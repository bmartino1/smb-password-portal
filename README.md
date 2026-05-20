# Unraid SMB Password Portal

A small Flask-based Docker container that provides a simple self-service web page where Unraid SMB users can change their own Samba/SMB password.

This is intended for Unraid systems where non-admin users need a safe way to change their SMB password without being given access to the Unraid web UI.

The user must know their current SMB password. This tool does **not** reset forgotten passwords.

---

## Docker Hub Image

```text
bmmbmm01/unraid-smb-password-portal:latest
```

---

## Features

- Simple web UI for changing an SMB password
- Users enter:
  - SMB username
  - current SMB password
  - new SMB password
  - confirmation password
- Uses Samba's `smbpasswd` client command
- Talks to the Unraid host Samba service
- Reads Unraid SMB users from `/boot/config/smbpasswd`
- Excludes `root` from the client portal by default
- Does not expose plaintext passwords
- Does not require Docker socket access
- Does not need Unraid root credentials
- Auto-generates a persistent Flask secret key on first start
- Optional debug endpoint for testing user detection
- Intended for LAN, VPN, Tailscale, WireGuard, or reverse-proxy-protected use

---

## Important Security Notes

Do **not** expose this container directly to the public internet.

Recommended access methods:

- LAN only
- Tailscale
- WireGuard
- Reverse proxy with HTTPS and access restrictions

This app allows users to change their own SMB password only if they know their current SMB password.

It does not provide admin password resets nor creates new samba users...

The container does not store user passwords. Passwords are submitted to the Flask app and passed to `smbpasswd` through stdin.

---

## How It Works

The container runs a Flask web application.

When a user submits the form, the container runs:

```bash
smbpasswd -s -r 127.0.0.1 -U username
```

The old password and new password are passed through stdin.

The container does not directly edit Unraid's Samba password database.

The container reads the SMB username list from:

```text
/boot/config/smbpasswd
```

mounted read-only into the container as:

```text
/unraid-config/smbpasswd
```

---

## Recommended Docker Run for Unraid

Host networking is recommended on Unraid because the container can talk to the host Samba service at `127.0.0.1`.

```bash
mkdir -p /mnt/user/appdata/smb-password-portal/config

docker rm -f smb-password-portal 2>/dev/null || true

docker run -d \
  --name smb-password-portal \
  --network=host \
  --restart unless-stopped \
  -e SAMBA_SERVER="127.0.0.1" \
  -e MIN_PASSWORD_LENGTH="8" \
  -e SHOW_USER_DROPDOWN="0" \
  -e ENABLE_DEBUG_USERS="0" \
  -v /mnt/user/appdata/smb-password-portal/config:/config \
  -v /boot/config:/unraid-config:ro \
  bmmbmm01/unraid-smb-password-portal:latest
```

Open:

```text
http://UNRAID-IP:8099
```

---

## Bridge Networking Alternative

Host networking is preferred, but bridge networking can also be used.

```bash
mkdir -p /mnt/user/appdata/smb-password-portal/config

docker rm -f smb-password-portal 2>/dev/null || true

docker run -d \
  --name smb-password-portal \
  --restart unless-stopped \
  -p 8099:8099 \
  --add-host=host.docker.internal:host-gateway \
  -e SAMBA_SERVER="host.docker.internal" \
  -e MIN_PASSWORD_LENGTH="8" \
  -e SHOW_USER_DROPDOWN="0" \
  -e ENABLE_DEBUG_USERS="0" \
  -v /mnt/user/appdata/smb-password-portal/config:/config \
  -v /boot/config:/unraid-config:ro \
  bmmbmm01/unraid-smb-password-portal:latest
```

Open:

```text
http://UNRAID-IP:8099
```

### Container Path: `/unraid-config`

Host path:

```text
/boot/config
```

Access mode:

```text
Read Only
```

This allows the app to read Unraid's SMB user list.

---

## Environment Variables

### `SAMBA_SERVER`

Default:

```text
127.0.0.1
```

The Samba server the container should contact.

For Unraid host networking, use:

```text
127.0.0.1
```

For bridge networking, use:

```text
host.docker.internal
```

---

### `MIN_PASSWORD_LENGTH`

Default:

```text
8
```

Minimum allowed new SMB password length.

Example:

```text
12
```

---

### `SHOW_USER_DROPDOWN`

Default:

```text
0
```

Controls whether the web UI shows a username dropdown.

Recommended value:

```text
0
```

With `0`, users type their SMB username.

With `1`, the app shows a dropdown of detected SMB users.

For client-facing use, `0` is recommended so account names are not exposed.

---

### `ENABLE_DEBUG_USERS`

Default:

```text
0
```

Enables or disables the debug user-list endpoint.

When enabled:

```text
http://UNRAID-IP:8099/debug/users
```

Example output:

```text
source=smbpasswd
count=2
apple
samba
```

Recommended final value:

```text
0
```

Use `1` only during testing.

---

### `SECRET_KEY`

Optional.

Normally you do not need to set this.

If no `SECRET_KEY` is provided, the container auto-generates one and stores it at:

```text
/config/secret_key
```

This keeps Flask browser sessions stable across container restarts.

---

### `UNRAID_CONFIG_DIR`

Default:

```text
/unraid-config
```

Path inside the container where Unraid's `/boot/config` is mounted.

Most users should not change this.

---

### `SMBPASSWD_BIN`

Default:

```text
/usr/bin/smbpasswd
```

Path to the `smbpasswd` binary inside the container.

Most users should not change this.

---

## Verify the Container

Check logs:

```bash
docker logs -n 100 smb-password-portal
```

Expected startup output:

```text
Starting smb-password-portal
SAMBA_SERVER=127.0.0.1
UNRAID_CONFIG_DIR=/unraid-config
MIN_PASSWORD_LENGTH=8
SHOW_USER_DROPDOWN=0
```

Health check:

```bash
curl -v http://127.0.0.1:8099/healthz
```

Expected response:

```text
ok
```

---

## Debug SMB User Detection

Start with debug enabled:

```bash
docker rm -f smb-password-portal 2>/dev/null || true

docker run -d \
  --name smb-password-portal \
  --network=host \
  --restart unless-stopped \
  -e SAMBA_SERVER="127.0.0.1" \
  -e MIN_PASSWORD_LENGTH="8" \
  -e SHOW_USER_DROPDOWN="0" \
  -e ENABLE_DEBUG_USERS="1" \
  -v /mnt/user/appdata/smb-password-portal/config:/config \
  -v /boot/config:/unraid-config:ro \
  bmmbmm01/unraid-smb-password-portal:latest
```

Then run:

```bash
curl http://127.0.0.1:8099/debug/users
```

Expected style of output:

```text
source=smbpasswd
count=2
user1
user2
```

Disable debug mode for normal use:

```text
ENABLE_DEBUG_USERS=0
```

---

## Confirm a Password Change Worked

You cannot list plaintext SMB passwords.

To test a changed password from the Unraid host:

```bash
USERNAME='username'
NEWPASS='your_new_password'

smbclient -L //127.0.0.1 -U "${USERNAME}%${NEWPASS}"
```

If the login works, Samba should return a share list.

Example successful output:

```text
Sharename       Type      Comment
---------       ----      -------
IPC$            IPC       IPC Service
```

---

## Notes About Password Storage

The container does not store user passwords.

The web form sends the old and new password to the Flask app. The app passes them to `smbpasswd` through stdin.

Samba stores password hashes. Plaintext passwords cannot be recovered from `/boot/config/smbpasswd`.

---

## Troubleshooting

### `Invalid form token. Refresh the page and try again.`

Refresh the page and submit again. 
Hard Refresh ctrl + f5

This can happen if the container was rebuilt or restarted while the browser still had an old form open.
If it persists, clear the browser cookie for the local site or test with a private/incognito window.

---

### `/debug/users` is empty

Check that `/boot/config` is mounted correctly:

```bash
docker exec -it smb-password-portal bash
ls -lah /unraid-config
cat /unraid-config/smbpasswd
```

On the Unraid host, check:

```bash
cut -d: -f1 /boot/config/smbpasswd
```

---

### Password change says success but login does not work

Test manually from the Unraid host:

```bash
smbclient -L //127.0.0.1 -U "USERNAME%PASSWORD"
```

Also confirm the container is talking to the correct Samba host:

```bash
docker logs -n 100 smb-password-portal
```

For host networking, `SAMBA_SERVER` should usually be:

```text
127.0.0.1
```

---

### Cannot connect to the web page

Check the container is running:

```bash
docker ps | grep smb-password-portal
```

Check logs:

```bash
docker logs -n 100 smb-password-portal
```

Check health endpoint:

```bash
curl -v http://127.0.0.1:8099/healthz
```

---

## Recommended Final Production Settings

```text
Network Type: Host
SAMBA_SERVER=127.0.0.1
MIN_PASSWORD_LENGTH=8
SHOW_USER_DROPDOWN=0
ENABLE_DEBUG_USERS=0
/config -> /mnt/user/appdata/smb-password-portal/config
/unraid-config -> /boot/config read-only
```

Place access behind LAN, VPN, Tailscale, WireGuard, or a protected reverse proxy.

---

## License

MIT License recommended. Per Samba License
