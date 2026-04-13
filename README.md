# Trackpad Pro

Phone-to-desktop remote control with low-latency trackpad, full-screen keyboard, media controls, quick tab shortcuts, and desktop profile switching.

## What is fixed

- Right click, middle click, and double click now call explicit mouse button actions.
- Tap-to-click no longer fires while swiping (movement threshold + tap timing).
- Trackpad movement is faster and smoother with requestAnimationFrame batching.
- WebSocket disconnect noise is handled more safely, reducing hard crashes from temporary network errors.
- `/favicon.ico` endpoint added to remove 404 spam.

## Features

- Trackpad gestures:
  - 1 finger: cursor move
  - 1 finger quick tap: left click
  - 2 fingers: scroll
  - 3 fingers: drag and drop
- Dedicated click buttons:
  - Left, Right, Double, Middle
- Full-screen keyboard panel for easier typing
- Quick combos:
  - copy, paste, undo, find, save, next/prev tab, reopen tab, app switch
- Media and Spotify shortcuts:
  - play/pause, next, previous, volume, open Spotify web/player pages
- Share tools:
  - send files/images from phone to the desktop
  - copy text to the desktop clipboard
  - choose shared folder, Downloads, or Desktop as the target
  - view recent shares and reopen them from the phone
- Quick tabs controls (browser workflow)
- Quick Launch apps:
  - chrome, edge, vscode, explorer, terminal, spotify app (platform-dependent)
- Desktop Profiles:
  - save multiple `ws://.../ws` targets and switch quickly between desktops

## Local run (desktop control)

```bash
pip install fastapi uvicorn websockets pyautogui qrcode pillow
python server.py
```

Windows PowerShell run snippet with PIN:

```powershell
$env:TRACKPAD_PIN="1234"
python server.py
```

## Keep it running after login

If you do not want to start it manually every time:

1. Run [setup_new_laptop.ps1](setup_new_laptop.ps1) once from PowerShell on the laptop you want to use.
2. The script creates a virtual environment, installs dependencies from [requirements.txt](requirements.txt), and enables auto-start.
3. [start_trackpad_hidden.ps1](start_trackpad_hidden.ps1) is launched immediately in the background and also on every sign-in.

If you want to remove it later, delete the `Trackpad Pro.lnk` shortcut from your Startup folder.

Open on phone:

- `http://<desktop-ip>:8000`
- or scan the QR button in the app

Sharing note:

- Open the `Share` tab to send files or images.
- Text entered in the share box is copied to the desktop clipboard.
- Use the target buttons to choose `Shared folder`, `Downloads`, or `Desktop`.
- Turn on `Copy images to clipboard` if you want an uploaded image to be ready for paste on Windows.

If the phone says the address is not accessible:

- Make sure the phone is on the same Wi-Fi network as the laptop.
- Open `http://192.168.10.205:8000` on the phone for this laptop, or use the QR button.
- Run [allow_trackpad_firewall.ps1](allow_trackpad_firewall.ps1) as Administrator to allow inbound TCP port 8000 on the Private network profile.
- Avoid guest Wi-Fi or client-isolation networks, because they block device-to-device access.

Important: phone and desktop must be on the same network for local mode.

## Multiple desktops on same network

Run `python server.py` on each desktop. Then in the app:

1. Open `Shortcuts -> Desktop Profiles`
2. Add profile name and websocket URL for each desktop, for example:
   - `ws://192.168.1.20:8000/ws`
   - `ws://192.168.1.21:8000/ws`
3. Tap `Use` to switch instantly.

## Use with a different laptop

To connect to another laptop, do the same setup on that laptop:

1. Install the Python dependencies on the second laptop.
2. Run [setup_new_laptop.ps1](setup_new_laptop.ps1) once on that laptop (no daily manual `python server.py` needed).
3. Open the phone app and either scan that laptop's QR code or use its IP address, for example `http://192.168.x.x:8000`.
4. If you want to switch between laptops often, add each laptop in `Shortcuts -> Desktop Profiles` using its `ws://<laptop-ip>:8000/ws` address.

Each laptop is a separate target, so the phone must point to the one you want to control.

## Register and switch desktops

- Open the `Desktop Profiles` section on the phone.
- Tap `Scan nearby desktops` to find laptops running Trackpad on the same Wi-Fi.
- The scan checks the local subnet plus nearby private subnets, so office/PG Wi-Fi with multiple ranges has a better chance of showing devices.
- Tap `Register current desktop` while the laptop server is open.
- Tap `Invite` next to a nearby desktop to send a message to that laptop.
- Copy the invite code from that laptop and paste it into another phone session if you want to add it quickly.
- Use the saved profile list to switch between laptops without retyping IP addresses.
- Tap `Use` on any nearby desktop to switch control to that laptop immediately.
- If a laptop still does not show up, use `Add by IP` and enter its address manually.

Each laptop opens a small local invite window at `http://127.0.0.1:8000/invite-center` when it starts. That window shows the invite message with `Accept` and `Reject` buttons.

Invite codes work best on the same Wi-Fi network. If you want to connect from outside the network, use a tunnel like Tailscale or Cloudflare Tunnel and register the tunnel URL instead of the local IP.

## Vercel hosting

This repo includes `vercel.json` for hosting the web UI on Vercel.

```bash
vercel
```

Architecture note:

- Vercel can host the UI.
- Desktop mouse/keyboard control cannot run on Vercel serverless because `pyautogui` must execute on your target desktop OS session.
- Keep one local desktop agent (`server.py`) running per controlled desktop and point profile URLs to those desktop websocket endpoints.

If you want internet-wide access, put each desktop agent behind a secure tunnel (for example Cloudflare Tunnel or Tailscale), then use those `wss://` URLs in Desktop Profiles.

## Open more apps from phone

App launching is handled in `server.py` via a safe app ID map in `get_app_command_map()` and `launch_app()`.

To add a new app:

1. Add a key and command in `get_app_command_map()` for your OS.
2. Add a UI button in `trackpad.html` using `launchApp('your_app_id')`.

Example IDs now supported include `chrome`, `edge`, `vscode`, `explorer`, `terminal`, `spotify` on Windows.

## Security (PIN auth)

- Set `TRACKPAD_PIN` before running the server.
- The phone UI will show an unlock prompt.
- Control commands are blocked until successful auth.

Windows PowerShell:

```powershell
$env:TRACKPAD_PIN="1234"
python server.py
```

## Macros

- Server exposes built-in macros from `get_macro_map()`.
- UI fetches them from `/macros` and renders buttons automatically.
- To add your own macro, add a new item in `get_macro_map()` with `name` and `steps`.
