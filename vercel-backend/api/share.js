const { shareLinks } = require('./lib');

export default function handler(req, res) {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  
  const { id } = req.query;
  
  if (!id || !shareLinks[id]) {
    return res.status(404).send(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Trackpad - Link Invalid</title>
        <style>
          body { font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
          .card { background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; max-width: 400px; }
          h1 { color: #333; margin-top: 0; }
          p { color: #666; }
        </style>
      </head>
      <body>
        <div class="card">
          <h1>❌ Link Expired</h1>
          <p>This share link is no longer valid. Please ask your friend to generate a new one.</p>
        </div>
      </body>
      </html>
    `);
  }
  
  const link = shareLinks[id];
  
  res.status(200).send(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Trackpad - Share Link</title>
      <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
          display: flex;
          justify-content: center;
          align-items: center;
          height: 100vh;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
          background: white;
          padding: 50px 40px;
          border-radius: 16px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
          text-align: center;
          max-width: 450px;
          width: 90%;
        }
        .logo {
          font-size: 48px;
          margin-bottom: 20px;
        }
        h1 {
          color: #333;
          margin: 20px 0;
          font-size: 28px;
        }
        .friend-name {
          color: #667eea;
          font-weight: bold;
          font-size: 18px;
          margin: 10px 0 30px;
        }
        p {
          color: #666;
          line-height: 1.6;
          margin: 15px 0;
          font-size: 15px;
        }
        .btn {
          display: inline-block;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          padding: 14px 32px;
          border-radius: 8px;
          text-decoration: none;
          font-weight: bold;
          font-size: 16px;
          margin: 20px 0;
          cursor: pointer;
          border: none;
          transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        .code-block {
          background: #f5f5f5;
          padding: 8px 12px;
          border-radius: 6px;
          font-family: monospace;
          font-size: 13px;
          color: #333;
          margin: 10px 0;
          word-break: break-all;
        }
        .step {
          margin: 25px 0;
          padding: 15px;
          background: #f0f7ff;
          border-left: 4px solid #667eea;
          text-align: left;
          border-radius: 4px;
        }
        .step-number {
          font-weight: bold;
          color: #667eea;
          font-size: 18px;
        }
        .step p {
          margin: 8px 0;
          text-align: left;
        }
        .status {
          color: #666;
          font-size: 13px;
          margin-top: 20px;
        }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="logo">🖥️</div>
        <h1>Trackpad Remote Control</h1>
        <div class="friend-name">${link.friendName} is inviting you to share control</div>
        
        <p>Your laptop will become available for remote control via their phone.</p>
        
        <div class="step">
          <div class="step-number">Step 1: Copy Device ID</div>
          <p>Save this ID—you'll need it to start the server:</p>
          <div class="code-block" id="deviceId">${link.deviceId}</div>
          <button class="btn" onclick="copyDeviceId()">📋 Copy ID</button>
        </div>
        
        <div class="step">
          <div class="step-number">Step 2: Download Script</div>
          <p>Download the script that will start your Trackpad server:</p>
          <button class="btn" onclick="downloadScript()">⬇️ Download start-trackpad.ps1</button>
        </div>
        
        <div class="step">
          <div class="step-number">Step 3: Run Script</div>
          <p>On your Windows laptop, right-click the downloaded script and select "Run with PowerShell". Paste your Device ID when prompted.</p>
        </div>
        
        <p style="color: #999; font-size: 13px; margin-top: 30px;">
          ✅ Server will run for 30 minutes after startup<br>
          ✅ Your friend will see you online and can send an invite<br>
          ✅ Close the PowerShell window to stop sharing
        </p>
        
        <div class="status">⏱️ This link expires in 24 hours</div>
      </div>
      
      <script>
        function copyDeviceId() {
          const deviceId = document.getElementById('deviceId').textContent;
          navigator.clipboard.writeText(deviceId).then(() => {
            alert('Device ID copied to clipboard!');
          });
        }
        
        function downloadScript() {
          const script = \`# Trackpad Server Launcher - Register & Start
# This script will start the Trackpad server on your laptop

$deviceId = Read-Host "Paste your Device ID (from the browser)"

# If you don't have Trackpad installed, download it first
if (-not (Test-Path "C:\\\\Users\\\\$env:USERNAME\\\\Trackpad")) {
  Write-Host "Downloading Trackpad..."
  # TODO: Add download URL here
}

cd "C:\\\\Users\\\\$env:USERNAME\\\\Trackpad"

# Activate Python venv
.venv\\\\Scripts\\\\Activate.ps1

# Get local IP
$localIp = (Get-NetIPAddress -InterfaceAlias "Ethernet" -AddressFamily IPv4).IPAddress
$publicIp = (Invoke-WebRequest -Uri "https://api.ipify.org?format=json" -UseBasicParsing).Content | ConvertFrom-Json | Select-Object -ExpandProperty ip

Write-Host "Local IP: $localIp" -ForegroundColor Green
Write-Host "Public IP: $publicIp" -ForegroundColor Green
Write-Host "Device ID: $deviceId" -ForegroundColor Green

# Register with cloud relay
$relayUrl = "https://trackpad-relay.vercel.app/api/register"
$registerBody = @{
  deviceId = $deviceId
  publicIp = $publicIp
  localIp = $localIp
  friendName = $env:COMPUTERNAME
} | ConvertTo-Json

Write-Host "Registering with relay..."
Invoke-WebRequest -Uri $relayUrl -Method POST -ContentType "application/json" -Body $registerBody

# Start server
Write-Host "Starting Trackpad server..."
python server.py
\`;

          const element = document.createElement('a');
          element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(script));
          element.setAttribute('download', 'start-trackpad.ps1');
          element.style.display = 'none';
          document.body.appendChild(element);
          element.click();
          document.body.removeChild(element);
        }
      </script>
    </body>
    </html>
  `);
}
