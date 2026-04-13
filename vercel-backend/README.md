# Trackpad Cloud Relay - Deployment Guide

This is the Vercel backend that enables share-link-based device discovery for Trackpad.

## Quick Start

### 1. Prerequisites
- Vercel account (free at https://vercel.com)
- Git installed
- Node.js 20+ (for local testing)

### 2. Deploy to Vercel

**Option A: Using Vercel CLI (Recommended)**
```powershell
# Install Vercel CLI globally
npm install -g vercel

# Navigate to vercel-backend folder
cd vercel-backend

# Deploy
vercel --prod
```

**Option B: Using GitHub + Vercel UI**
1. Create a new GitHub repository with the Trackpad folder
2. Go to https://vercel.com/new
3. Import the GitHub repository
4. Select `vercel-backend` as the root directory
5. Click Deploy

### 3. Get Your Vercel URL
After deployment, you'll see something like:
```
✓ Production: https://trackpad-relay-abc123.vercel.app
```

Save this URL—use it in trackpad.html as `RELAY_URI`.

## How It Works

### For You (Phone User)
1. Generate a share link on your phone UI: "Generate Link for Friend"
2. Enter friend's name
3. Get a URL like `https://trackpad-relay.vercel.app/share/abc123xyz`
4. Send this link via WhatsApp, email, etc.

### For Your Friend (Laptop User)
1. Friend opens the link in a browser
2. Sees page with "Download Script" button
3. Downloads PowerShell script
4. Runs script → enters Device ID from page
5. Script starts their Trackpad server and registers with Vercel
6. Server stays active for 30 minutes with automatic registration

### For You (Connect Time)
1. Phone queries Vercel: "Get me friend's IP for this share link"
2. Vercel returns friend's local IP + public IP
3. Phone connects directly to friend's laptop via WebSocket

## Environment Variables

Currently using in-memory storage (fine for dev). For production scaling, add:

```
# .env (optional)
TRACKPAD_DB_TYPE=redis
TRACKPAD_REDIS_URL=redis://...
```

To enable Redis support, update `api/lib.js` and install redis package.

## File Structure

```
vercel-backend/
├── api/
│   ├── index.js              # Root endpoint
│   ├── generate-link.js      # Create share link (POST)
│   ├── register.js           # Register device (POST)
│   ├── device.js             # Get device IP (GET)
│   ├── share.js              # Share link page (GET)
│   └── lib.js                # In-memory device registry
├── package.json
├── vercel.json
└── .gitignore
```

## Testing Locally

```powershell
cd vercel-backend
npm install
vercel dev
```

Then visit `http://localhost:3000/api` in browser.

## API Endpoints

### Generate Share Link
```
POST /api/generate-link
Content-Type: application/json

{
  "friendName": "John's Laptop"
}

Response:
{
  "deviceId": "abc123xyz",
  "shareLinkId": "def456uvw",
  "shareUrl": "https://trackpad-relay.vercel.app/api/share/def456uvw",
  "message": "Share this link with your friend: ..."
}
```

### Register Device (Friend's laptop)
```
POST /api/register
Content-Type: application/json

{
  "deviceId": "abc123xyz",
  "publicIp": "1.2.3.4",
  "localIp": "192.168.1.100",
  "friendName": "John's Laptop"
}

Response:
{
  "success": true,
  "device": { ... }
}
```

### Get Device (Phone queries)
```
GET /api/device?id=abc123xyz&type=device

Response:
{
  "success": true,
  "device": {
    "deviceId": "abc123xyz",
    "publicIp": "1.2.3.4",
    "localIp": "192.168.1.100",
    "friendName": "John's Laptop",
    "expiresAt": 1713024000000
  }
}

# OR by share link
GET /api/device?id=def456uvw&type=sharelink
```

### Share Link Page (Friend opens in browser)
```
GET /api/share/def456uvw

Response: HTML page with:
- Device ID display
- Download Script button
- Instructions
```

## Troubleshooting

**"Device not found"**
- Device registration expired (30-minute timeout)
- Share link was invalid or expired
- Friend hasn't run the registration script yet

**"CORS error"**
- All endpoints have CORS enabled for mobile browsers
- If still failing, check Vercel function logs: `vercel logs`

**"Can't connect to friend's laptop"**
1. Verify friend's Device ID matches
2. Check NAT/firewall—both laptops must be on same Wi-Fi or have public IPs
3. Manual IP fallback: Use "Add by IP" in phone UI instead

## Security Notes

- Device IDs are random (not guessable)
- Share links expire after 24 hours
- Devices deregister after 30 minutes (no active heartbeat needed)
- No authentication required—relies on URL secrecy (share link alone)
- For production: Add optional PIN or signing key

## Next Steps

1. Deploy to Vercel using CLI or GitHub
2. Copy your Vercel URL
3. Update `trackpad.html` to use your Vercel relay URL
4. Update `server.py` to call relay registration endpoint
5. Test: Generate link → Share with friend → Friend runs script → Monitor via phone UI
