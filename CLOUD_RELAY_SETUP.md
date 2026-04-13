# Trackpad Cloud Relay Setup - Complete Guide

## Overview

You now have a **cloud-based share link system** for Trackpad. Instead of manually installing on each friend's laptop, your friends get a personalized link they can click.

**Flow:**
1. You (on your phone): Generate a share link with your friend's name
2. You: Send link to friend (WhatsApp, email, etc.)
3. Friend: Opens link in browser → downloads PowerShell script
4. Friend: Runs script → Trackpad server starts & registers online for 30 min
5. You (on phone): See friend online → send invite → use their desktop

---

##  Part 1: Deploy Vercel Backend (One-Time Setup)

### Prerequisites
- Vercel account (free at https://vercel.com)
- Git installed (or just deploy zip)
- 5 minutes ⏱️

### Option A: Deploy from GitHub (Recommended)

```powershell
# 1. Create a GitHub repository
# - Create repo "Trackpad" on GitHub
# - Clone locally or upload the Trackpad folder

# 2. Go to https://vercel.com/new
# 3. Connect GitHub account
# 4. Select your "Trackpad" repo
# 5. In "Root Directory", select: vercel-backend
# 6. Click Deploy

# After deploy, you'll see: https://trackpad-relay-xxxxx.vercel.app
```

### Option B: Deploy with Vercel CLI

```powershell
# Install Vercel CLI globally (one time)
npm install -g vercel

# Navigate to folder
cd c:\Users\afaqp\Downloads\Trackpad\vercel-backend

# Deploy
vercel --prod

# You'll get a URL like: https://trackpad-relay-xxxxx.vercel.app
```

### Option C: Deploy ZIP (No GitHub/CLI)

1. Go to https://vercel.com/new
2. Under "Other", select "Project from Git"
3. Skip GitHub auth
4. Select "Deploy from Git Clone URL"
5. Paste: `https://github.com/<you>/Trackpad` (your repo)
6. Make sure "Root Directory" = `vercel-backend`
7. Deploy

---

## Part 2: Update Your Phone UI with Relay URL

Once Vercel deployment is complete, you have a URL like:
```
https://trackpad-relay-abc123.vercel.app
```

### Update trackpad.html

Open `c:\Users\afaqp\Downloads\Trackpad\trackpad.html` and find:

```javascript
// Cloud relay configuration
const RELAY_URL = 'https://trackpad-relay.vercel.app'; // UPDATE THIS!
```

Replace with your actual Vercel URL:

```javascript
const RELAY_URL = 'https://trackpad-relay-abc123.vercel.app'; // Your deployed URL
```

**Save the file.**

---

## Part 3: Share Link Generation (On Your Phone)

1. Open Trackpad phone UI: `http://your-laptop-ip:8000`
2. Go to **Shortcuts** tab
3. Scroll to **Share Links** section (new)
4. Enter friend's name: "John's Laptop"
5. Click **Generate Link**
6. Copy the link or click **WhatsApp** to send directly

**Example link you'll get:**
```
https://trackpad-relay-abc123.vercel.app/api/share/def456uvw
```

---

## Part 4: Friend Uses the Share Link

Your friend receives your link and:

1. **Opens link in browser** → Sees beautiful page with:
   - "Trackpad - Share Link" heading
   - Your device ID
   - "Copy ID" button
   - "Download start-trackpad.ps1" button
   - Instructions

2. **Clicks "Download start-trackpad.ps1"** → Saves PowerShell script

3. **Right-clicks script** → "Run with PowerShell"

4. **Pastes Device ID** when prompted

Script automatically:
- ✅ Finds local Trackpad installation
- ✅ Activates Python venv
- ✅ Gets local + public IP
- ✅ **Registers with your relay**
- ✅ **Starts server** (runs 30+ minutes)
- ✅ Shows confirmation message

---

##  Part 5: You Use Friend's Desktop (Back to Your Phone)

Once friend's server is running:

1. Refresh your phone UI
2. Friend's device appears in **Desktop Profiles** as "Online" (via relay query)
3. Send invite to friend's laptop
4. Friend receives invite → sees Accept/Reject button
5. Friend clicks Accept
6. You can now **control their mouse/keyboard**
7. Server auto-registers every 30 min (no need to restart)

---

## Environment Variables

### Your Desktop (server.py)

Optional: Tell server where relay is:

```powershell
# Set environment variable (Windows)
$env:TRACKPAD_RELAY_URL = "https://trackpad-relay-abc123.vercel.app"

# Or in PowerShell script:
python server.py  # Already uses default if not set
```

### Phone (trackpad.html)

Already configured in Step 2. No additional setup needed.

---

## Troubleshooting

### "Link generation failed"

- Check internet connection
- Verify Vercel deployment URL is correct
- Check browser console for errors (F12)
- Try refreshing the page

### "Friend's device shows as offline"

- Friend's script may not have registered successfully
- Check PowerShell output for errors during registration
- Friend's device expires after 30 min of inactivity
- Friend needs to run script again

### "Can't connect after accepting invite"

- Both laptops must be on same Wi-Fi (cloud relay only finds registered IPs)
- If different network, use manual IP fallback: **Add by IP** in phone UI
- Make sure firewall allows port 8000

### "Script can't find Trackpad folder"

- Ensure Trackpad is installed in:
  - `C:\Users\{USERNAME}\Trackpad` (standard location)
  - `C:\Users\{USERNAME}\Desktop\Trackpad`
  - Or same folder as script
- Friend should copy entire Trackpad folder first, or download from your repo

### Relay returns "Device not found"

- Device ID was incorrect (copy exactly from page)
- Device registration expired (30 min timeout)
- Server closed/crashed on friend's laptop
- Ask friend to run script again

---

## Security Notes

- **Share links are secret URLs** (hard to guess)
- **No authentication** (URL itself is the credential)
- **Devices auto-expire** after 30 min
- **For production:** Add optional PIN or HMAC signing in relay/lib.js

---

## File Structure Summary

```
Trackpad/
├── trackpad.html              (Phone UI - updated with RELAY_URL)
├── server.py                  (Backend - updated with relay endpoints)
├── start-trackpad-share-link.ps1  (Friend's setup script)
├── vercel-backend/
│   ├── package.json           (Node.js deps)
│   ├── vercel.json            (Vercel config)
│   ├── api/
│   │   ├── index.js           (API root)
│   │   ├── generate-link.js   (Create share link)
│   │   ├── register.js        (Register device)
│   │   ├── device.js          (Query device IP)
│   │   ├── share.js           (Share link page)
│   │   └── lib.js             (Registry)
│   └── README.md              (Vercel deployment guide)
└── README.md                  (This file)
```

---

## Quick Test Checklist

- [ ] Vercel deployed successfully
- [ ] Copied Vercel URL to trackpad.html `RELAY_URL`
- [ ] Refreshed phone UI
- [ ] Generated test share link
- [ ] Sent link to friend
- [ ] Friend ran PowerShell script
- [ ] Friend's device appears online
- [ ] Can send and accept invite
- [ ] Can control friend's mouse/keyboard

---

## Next Steps (Optional)

- **Desktop Profiles**: Add friend's device manually using IP if relay fails
- **Multiple Friends**: Generate separate links for each
- **Custom Messages**: Include context in share link invites
- **Always-On Alternative**: Use `setup_new_laptop.ps1` if friend wants persistent 24/7 server

---

## Support

If friend's laptop isn't being found:

1. **Same Wi-Fi?** → Cloud relay only works within network
2. **Different network?** → Use "Add by IP" + manual IP entry
3. **Firewall blocking?** → Run `allow_trackpad_firewall.ps1` as Admin
4. **Server crashed?** → Friend re-runs PowerShell script

---

## Advanced: Custom Relay Hosting

To host relay yourself instead of Vercel:

1. Deploy `vercel-backend` to your own Node.js server
2. Update `trackpad.html` RELAY_URL to your server
3. For production, upgrade `lib.js` to use database (Redis/MongoDB) instead of in-memory store

See `vercel-backend/README.md` for details.

---

**You're all set! Start generating share links for your friends. 🚀**
