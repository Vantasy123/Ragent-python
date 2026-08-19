param(
    [ValidateSet('full', 'backend')]
    [string]$Mode = 'full',
    [switch]$Build
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$composeYml = Join-Path $projectDir 'docker-compose.yml'

function Test-CommandExists {
    param([string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$Retries = 60,
        [int]$DelaySeconds = 2
    )

    for ($i = 1; $i -le $Retries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
            # wait for service
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    return $false
}

function Invoke-Compose {
    param([string[]]$Arguments)

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed: $($Arguments -join ' ')"
    }
}

function Initialize-ConfigFile {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Example
    )

    if ((Test-Path $Target) -or -not (Test-Path $Example)) {
        return
    }
    Copy-Item -Path $Example -Destination $Target
    Write-Warning "Auto initialized config: $Target"
}

Write-Host '========================================='
Write-Host '  Ragent Job Agent Quick Start'
Write-Host '========================================='
Write-Host "Mode: $Mode"
Write-Host "Project: $projectDir"
Write-Host "Build images: $Build"
Write-Host ''

Initialize-ConfigFile -Target (Join-Path $projectDir '.env') -Example (Join-Path $projectDir '.env.example')
Initialize-ConfigFile -Target (Join-Path $projectDir 'config\servers.yml') -Example (Join-Path $projectDir 'config\servers.example.yml')
Write-Host ''

if (-not (Test-CommandExists 'docker')) {
    throw 'Docker is not installed.'
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker is not running.'
}

$frontendEnabled = ($Mode -eq 'full')
$backendHealthUrl = 'http://localhost:8000/api/health'
$activeComposeFiles = @('-f', $composeYml)

Write-Host '[1/4] Starting containers...'
if ($Mode -eq 'full') {
    $arguments = $activeComposeFiles + @('--profile', 'full', 'up', '-d')
    if ($Build) {
        $arguments += '--build'
    }
    Invoke-Compose $arguments
} else {
    $arguments = $activeComposeFiles + @('up', '-d')
    if ($Build) {
        $arguments += '--build'
    }
    $arguments += @('mysql', 'rustfs', 'etcd', 'milvus', 'redis', 'ragent-api')
    Invoke-Compose $arguments
}

Write-Host ''
Write-Host '[2/4] Waiting for backend health...'
if (-not (Wait-HttpOk -Url $backendHealthUrl -Retries 120 -DelaySeconds 2)) {
    & docker compose @activeComposeFiles ps
    throw 'Backend health check timed out. Run docker compose logs ragent-api.'
}
Write-Host "[OK] Backend is ready: $backendHealthUrl"

Write-Host ''
Write-Host '[3/4] Container status...'
& docker compose @activeComposeFiles ps

Write-Host ''
if ($frontendEnabled) {
    Write-Host '[4/4] Waiting for frontend...'
    if (Wait-HttpOk -Url 'http://localhost/' -Retries 40 -DelaySeconds 2) {
        Write-Host '[OK] Frontend is ready: http://localhost/'
    } else {
        Write-Warning 'Frontend is not ready yet, but backend started successfully.'
    }
} else {
    Write-Host '[4/4] Frontend check skipped in backend mode.'
}

Write-Host ''
Write-Host '========================================='
Write-Host '  Startup Complete'
Write-Host '========================================='
Write-Host "Backend API: $backendHealthUrl"
Write-Host 'API Docs: http://localhost:8000/docs'
if ($frontendEnabled) {
    Write-Host 'Frontend UI: http://localhost/'
    Write-Host 'Job Dashboard: http://localhost/admin/job-dashboard'
    Write-Host 'Chat Assistant: http://localhost/chat'
    Write-Host 'Agent Evaluations: http://localhost/admin/evaluations'
}
Write-Host ''
Write-Host 'Useful commands:'
Write-Host "  Status: docker compose -f $composeYml ps"
Write-Host "  Logs: docker compose -f $composeYml logs -f ragent-api"
Write-Host "  Stop: docker compose -f $composeYml down"
Write-Host "  Rebuild: .\scripts\start-project.bat -Build"
