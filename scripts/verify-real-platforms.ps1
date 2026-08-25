param(
    [string]$CdpUrl = "http://127.0.0.1:9223",
    [string[]]$Platforms = @("boss", "liepin", "51job", "nowcoder")
)

$ErrorActionPreference = "Stop"

function Get-CdpJson {
    param([string]$Path)
    return Invoke-RestMethod -Uri "$($CdpUrl.TrimEnd('/'))/$Path" -TimeoutSec 5
}

Write-Host "Ragent real-platform acceptance"
Write-Host "CDP: $CdpUrl"
Write-Host "Platforms: $($Platforms -join ', ')"
Write-Host ""

try {
    $version = Get-CdpJson -Path "json/version"
    $tabs = @(Get-CdpJson -Path "json/list")
} catch {
    Write-Error "CDP unavailable: $($_.Exception.Message). Start Chrome with --remote-debugging-port=9223 and log in manually."
    exit 2
}

$domains = @{
    boss = "zhipin.com"
    liepin = "liepin.com"
    "51job" = "51job.com"
    nowcoder = "nowcoder.com"
}

$results = foreach ($platform in $Platforms) {
    $domain = $domains[$platform]
    $platformTabs = @($tabs | Where-Object { $_.url -like "*$domain*" })
    [PSCustomObject]@{
        platform = $platform
        cdp_connected = $true
        tabs_detected = $platformTabs.Count
        login_verified = $false
        anti_bot_verified = $false
        detail_verified = $false
        status = if ($platformTabs.Count -gt 0) { "manual_login_and_search_required" } else { "platform_tab_missing" }
        note = "Tab presence is not proof of login. Use the Ragent UI to perform real search and detail checks."
    }
}

$results | ConvertTo-Json -Depth 4
Write-Host ""
Write-Host "Exit code 0 means CDP is reachable only; login, anti-bot, search, and detail fields require manual confirmation in the real browser."
