$ErrorActionPreference = 'Stop'

$ruleName = 'Trackpad Pro TCP 8000'
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
  Write-Host "Firewall rule already exists: $ruleName"
  return
}

New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private | Out-Null
Write-Host "Added firewall rule: $ruleName"
Write-Host "Keep the network profile set to Private for this laptop."
