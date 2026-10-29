# Unraid SMB Password Portal

[![Docker Hub](https://img.shields.io/badge/Docker%20Hub-bmmbmm01%2Funraid--smb--password--portal-blue?logo=docker)](https://hub.docker.com/r/bmmbmm01/unraid-smb-password-portal)
[![GitHub](https://img.shields.io/badge/Source-bmartino1%2Fsmb--password--portal-181717?logo=github)](https://github.com/bmartino1/smb-password-portal)
[![Unraid](https://img.shields.io/badge/Platform-Unraid-F15A2C?logo=unraid)](https://unraid.net/)

<img width="1313" height="835" alt="Unraid SMB Password Portal" src="https://github.com/user-attachments/assets/6f5a0219-2bfb-41b1-92a3-af96b75de21b" />

A small self-service web portal for **Unraid SMB users to change their own Samba password** without needing access to the Unraid administration interface.

This container is designed specifically for Unraid. It provides a simple browser-based front end and uses Samba's standard `smbpasswd` client to send the password change to the Samba service running on the Unraid host.

The user must know their **current SMB password** before it can be changed. This is a password-change portal, not an administrator password-reset tool.

> **Unraid only:** this image expects the Unraid SMB configuration layout and is intended to run alongside the Samba service provided by Unraid.

## Links

- **Docker image:** [bmmbmm01/unraid-smb-password-portal](https://hub.docker.com/r/bmmbmm01/unraid-smb-password-portal)
- **Source:** [bmartino1/smb-password-portal](https://github.com/bmartino1/smb-password-portal)
- **Unraid support:** [Support - Samba Web Portal](https://forums.unraid.net/topic/198949-support-samba-web-portal/)
- **Unraid template repository:** [bmartino1/unraid-docker-templates](https://github.com/bmartino1/unraid-docker-templates)

## What It Does

The portal gives an existing Unraid SMB user a simple page where they can enter:

- their SMB username
- their current SMB password
- a new SMB password
- confirmation of the new password

After the form is validated, the application runs Samba's `smbpasswd` client against the Unraid host. The old and new passwords are supplied to `smbpasswd` through standard input rather than being placed on the command line.

The application does **not** directly edit Unraid's Samba password database and does not require the Docker socket or Unraid root credentials.

## Features

- Browser-based SMB password changes for non-admin users
- Uses the existing Unraid Samba service
- Requires the user's current SMB password
- Reads the Unraid SMB user list from `/boot/config/smbpasswd`
- Excludes the `root` account from the SMB user portal
- Optional typed username or detected-user dropdown
- Configurable minimum password length
- CSRF protection for the password-change form
- Basic per-user/IP in-memory rate limiting
- Persistent Flask session secret stored in appdata
- Health-check endpoint
- Optional SMB user-detection debug endpoint
- No Docker socket access required
- No Unraid administrator credentials required

## Recommended Unraid Installation

The easiest installation is through the Unraid Community Applications template.

The normal configuration uses **Host** networking so the container can contact the Unraid Samba service at `127.0.0.1`.

Typical settings:

```text
Network Type: Host
WebUI: http://UNRAID-IP:8099

SAMBA_SERVER=127.0.0.1
MIN_PASSWORD_LENGTH=8
SHOW_USER_DROPDOWN=0
ENABLE_DEBUG_USERS=0

/config        -> /mnt/user/appdata/smb-password-portal/config
/unraid-config -> /boot/config (read-only)
```

The `/boot/config` mount is read-only. It is used to identify the SMB users configured on the Unraid server.

### Manual Docker Run

If you prefer to create the container manually:

```bash
mkdir -p /mnt/user/appdata/smb-password-portal/config

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

Then open:

```text
http://UNRAID-IP:8099
```

## How the Password Change Works

For a submitted username, the application calls:

```bash
smbpasswd -s -r 127.0.0.1 -U username
```

The user's current password and new password are passed to that process through stdin.

The portal first reads the available SMB usernames from:

```text
/boot/config/smbpasswd
```

which is normally mounted inside the container as:

```text
/unraid-config/smbpasswd
```

If the SMB password file is unavailable or contains no usable users, the application can fall back to the Unraid `passwd` file while filtering system/service accounts.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `SAMBA_SERVER` | `127.0.0.1` | Samba server contacted by `smbpasswd`. Host networking on Unraid should normally use `127.0.0.1`. |
| `MIN_PASSWORD_LENGTH` | `8` | Minimum length accepted for a new SMB password. |
| `SHOW_USER_DROPDOWN` | `0` | `0` lets the user type their username. `1` displays detected SMB usernames in a dropdown. |
| `ENABLE_DEBUG_USERS` | `0` | Enables `/debug/users` for troubleshooting user detection. Leave disabled for normal use. |
| `MAX_ATTEMPTS` | `5` | Number of password-change attempts allowed within the rate-limit window for a user/IP combination. |
| `RATE_WINDOW_SECONDS` | `300` | In-memory rate-limit window in seconds. |
| `SECRET_KEY` | generated | Optional Flask session secret. Normally generated automatically and persisted under `/config`. |
| `UNRAID_CONFIG_DIR` | `/unraid-config` | Container path for the read-only Unraid configuration mount. |
| `SMBPASSWD_BIN` | `/usr/bin/smbpasswd` | Path to the Samba `smbpasswd` client inside the container. |

### Username Entry vs. Dropdown

The recommended setting is:

```text
SHOW_USER_DROPDOWN=0
```

Users type their existing SMB username instead of being shown a list of accounts configured on the server.

Set it to `1` if you prefer a dropdown populated from the detected Unraid SMB users.

## Security and Scope

This application is intentionally limited: it gives an existing SMB user a way to change **their own password** using their current credentials.

It does not:

- create Samba users
- reset a forgotten password
- provide Unraid administrator access
- require the Unraid root password
- mount the Docker socket
- directly write to `/boot/config/smbpasswd`

Passwords submitted through the form are passed to the Samba client for the password-change operation. The application does not maintain its own password database.

Because this is an account-management page, keep the WebUI available only to people who should be able to reach your Unraid services. If you make the page available outside your local network, use an appropriately secured access method and HTTPS.

## Persistent Session Key

You normally do not need to configure `SECRET_KEY`.

On first start, the entrypoint generates a random Flask secret and saves it to:

```text
/config/secret_key
```

With the normal Unraid appdata mapping, that file survives container updates and restarts so browser sessions and form tokens remain consistent.

## Health Check

Check the application locally from the Unraid host:

```bash
curl http://127.0.0.1:8099/healthz
```

Expected response:

```text
ok
```

Container logs can be viewed with:

```bash
docker logs -n 100 smb-password-portal
```

## Troubleshooting SMB User Detection

The debug endpoint is disabled by default.

Temporarily set:

```text
ENABLE_DEBUG_USERS=1
```

Then check:

```bash
curl http://127.0.0.1:8099/debug/users
```

Example:

```text
source=smbpasswd
count=2
user1
user2
```

Return `ENABLE_DEBUG_USERS` to `0` after troubleshooting.

You can also verify the read-only Unraid configuration mount:

```bash
docker exec -it smb-password-portal sh
ls -lah /unraid-config
cut -d: -f1 /unraid-config/smbpasswd
```

## Testing a Password Change

A successful portal message means `smbpasswd` returned successfully. You can independently test the new SMB credentials from the Unraid host with `smbclient`:

```bash
USERNAME='username'
NEWPASS='your_new_password'

smbclient -L //127.0.0.1 -U "${USERNAME}%${NEWPASS}"
```

If authentication succeeds, Samba should return the shares visible to that account.

## Bridge Networking

Host networking is the intended Unraid setup, but bridge networking can be used if needed.

One approach is to map port `8099`, add the Docker host gateway, and point `SAMBA_SERVER` at it:

```bash
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

For the standard Unraid Community Applications installation, use the Host network configuration supplied by the template.

## Common Problems

### Invalid form token

If you see:

```text
Invalid form token. Refresh the page and try again.
```

Refresh the page and submit the form again. This can happen when an older form remains open across a container restart or session-key change.

If it continues, clear the browser data for the portal or try a private/incognito window.

### Username is not listed as an SMB user

Confirm that the user exists in Unraid's SMB password file:

```bash
cut -d: -f1 /boot/config/smbpasswd
```

Also verify that `/boot/config` is mounted read-only to `/unraid-config` inside the container.

### Password change fails

Confirm the user is entering the current **SMB password**, not an unrelated Unraid web login password.

Check the container logs:

```bash
docker logs -n 100 smb-password-portal
```

For the normal Host network setup, `SAMBA_SERVER` should be:

```text
127.0.0.1
```

### Web page does not open

Check that the container is running:

```bash
docker ps | grep smb-password-portal
```

Then check the health endpoint:

```bash
curl http://127.0.0.1:8099/healthz
```

## License

This project is released under the [MIT License](LICENSE).

The container includes Samba client utilities provided by the Samba project; those components remain subject to their respective upstream licenses.
