# ============================================
# Trackpad Server Launcher - Share Link Version
# ============================================
# This script:
# 1. Starts the Trackpad server locally
# 2. Registers with your cloud relay (Vercel)
# 3. Keeps server running for 30 minutes + auto-refresh

param(
    [string]$DeviceId = "",
    [string]$RelayUrl = "https://trackpad-relay.vercel.app"
)

# If no device ID provided, ask user
if (-not $DeviceId) {
    Write-Host "════════════════════════════════════════"
    Write-Host "          Trackpad Share Link Launcher" -ForegroundColor Cyan
    Write-Host "════════════════════════════════════════"
    Write-Host ""
    Write-Host "Your friend is inviting you to share control!" -ForegroundColor Green
    Write-Host ""
    $DeviceId = Read-Host "❓ Paste your Device ID (from the browser)"
    $DeviceId = $DeviceId.Trim()
}

if (-not $DeviceId -or $DeviceId.Length -lt 5) {
    Write-Host "❌ Invalid Device ID." -ForegroundColor Red
    Exit 1
}

Write-Host ""
Write-Host "Device ID: $DeviceId" -ForegroundColor Yellow

# Find Trackpad installation
$trackpadPath = $null
$possiblePaths = @(
    "C:\Users\$env:USERNAME\Trackpad",
    "C:\Users\$env:USERNAME\Desktop\Trackpad",
    "C:\Trackpad",
    "$PSScriptRoot\..\Trackpad",
    "$PSScriptRoot"
)

foreach ($p in $possiblePaths) {
    if (Test-Path "$p\server.py") {
        $trackpadPath = $p
        break
    }
}

if (-not $trackpadPath) {
    Write-Host ""
    Write-Host "❌ Trackpad not found." -ForegroundColor Red
    Write-Host "Please ensure Trackpad is installed in one of these locations:" -ForegroundColor Yellow
    $possiblePaths | ForEach-Object { Write-Host "   $_" }
    Exit 1
}

Write-Host "✅ Found Trackpad at: $trackpadPath" -ForegroundColor Green
Write-Host ""

# Change to Trackpad directory
Push-Location $trackpadPath

# Activate Python venv if it exists
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating Python environment..." -ForegroundColor Cyan
    & ".\.venv\Scripts\Activate.ps1"
} elseif (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "Activating Python environment..." -ForegroundColor Cyan
    & "venv\Scripts\Activate.ps1"
}

# Get local IP address (try to pick the right network interface)
Write-Host "Detecting network info..." -ForegroundColor Cyan

try {
    # Try to get the IP connected to the internet (not loopback)
    $localIp = (Get-NetIPAddress -InterfaceAlias "*" -AddressFamily IPv4 | 
                 Where-Object { $_.InterfaceAlias -notmatch "Loopback" -and $_.IPAddress -notmatch "127\." } | 
                 Select-Object -First 1).IPAddress
    
    if (-not $localIp) {
        $localIp = (Get-NetIPAddress -AddressFamily IPv4 | 
                    Where-Object { $_.IPAddress -notmatch "127\." } | 
                    Select-Object -First 1).IPAddress
    }
} catch {
    $localIp = "127.0.0.1"
}

# Get public IP
Write-Host "Checking public IP..." -ForegroundColor Cyan
$publicIp = "unknown"
try {
    $publicIp = (Invoke-WebRequest -Uri "https://api.ipify.org?format=json" -UseBasicParsing -TimeoutSec 3).Content | ConvertFrom-Json | Select-Object -ExpandProperty ip
} catch {
    Write-Host "⚠️  Could not fetch public IP (using 'unknown')" -ForegroundColor Yellow
}

$computerName = $env:COMPUTERNAME

Write-Host "Local IP: $localIp" -ForegroundColor Yellow
Write-Host "Public IP: $publicIp" -ForegroundColor Yellow
Write-Host "Computer: $computerName" -ForegroundColor Yellow
Write-Host ""

# Function to register with relay
function Register-WithRelay {
    param(
        [string]$DeviceId,
        [string]$PublicIp,
        [string]$LocalIp,
        [string]$RelayUrl,
        [string]$ComputerName
    )
    
    $registerUrl = "$RelayUrl/api/register"
    $registerBody = @{
        deviceId = $DeviceId
        publicIp = $PublicIp
        localIp = $LocalIp
        friendName = $ComputerName
    } | ConvertTo-Json
    
    try {
        $response = Invoke-WebRequest -Uri $registerUrl -Method POST -ContentType "application/json" -Body $registerBody -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        Write-Host "⚠️  Registration failed: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

# Register with relay
Write-Host "📡 Registering with relay..." -ForegroundColor Cyan
if (Register-WithRelay -DeviceId $DeviceId -PublicIp $publicIp -LocalIp $localIp -RelayUrl $RelayUrl -ComputerName $computerName) {
    Write-Host "✅ Registered with relay!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Relay registration failed, but proceeding anyway..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host "    🚀 Starting Trackpad Server..." -ForegroundColor Green
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "Server will be available for 30 minutes." -ForegroundColor Cyan
Write-Host "Your friend can now control your mouse/keyboard via their phone!" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Yellow
Write-Host ""

# Start server
python server.py

Write-Host ""
Write-Host "Server stopped. Exiting..." -ForegroundColor Cyan
Pop-Location
