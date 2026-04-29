param(
    [ValidateSet('full', 'backend', 'ops', 'ops-backend')]
    [string]$Mode = 'ops',
    [switch]$Build
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$composeYml = Join-Path $projectDir 'docker-compose.yml'
$composeOpsYml = Join-Path $projectDir 'docker-compose.ops.yml'

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
            # 启动阶段服务可能尚未监听端口，按固定间隔重试即可。
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

Write-Host '========================================='
Write-Host '  Ragent Python Quick Start'
Write-Host '========================================='
Write-Host "Mode: $Mode"
Write-Host "Project: $projectDir"
Write-Host "Build images: $Build"
Write-Host ''

if (-not (Test-CommandExists 'docker')) {
    throw 'Docker is not installed.'
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker is not running.'
}

$frontendEnabled = $false
$backendHealthUrl = 'http://localhost:8000/api/health'
$effectiveMode = switch ($Mode) {
    'full' { 'ops' }
    'backend' { 'ops-backend' }
    default { $Mode }
}

if ($effectiveMode -ne $Mode) {
    Write-Host "Effective mode: $effectiveMode (ops tools enabled by default)"
}

Write-Host '[1/4] Starting containers...'
switch ($effectiveMode) {
    'ops' {
        $frontendEnabled = $true
        # 默认启动即加载 ops override，使运维 Agent 可调用 Docker 白名单工具。
        $arguments = @('-f', $composeYml, '-f', $composeOpsYml, '--profile', 'full', 'up', '-d')
        if ($Build) {
            $arguments += '--build'
        }
        Invoke-Compose $arguments
    }
    'ops-backend' {
        # 后端模式同样启用 ops override，只是不启动前端。
        $arguments = @('-f', $composeYml, '-f', $composeOpsYml, 'up', '-d')
        if ($Build) {
            $arguments += '--build'
        }
        $arguments += @('mysql', 'rustfs', 'etcd', 'milvus', 'redis', 'ragent-api', 'ops-test-service')
        Invoke-Compose $arguments
    }
}

Write-Host ''
Write-Host '[2/4] Waiting for backend health...'
if (-not (Wait-HttpOk -Url $backendHealthUrl -Retries 120 -DelaySeconds 2)) {
    & docker compose -f $composeYml -f $composeOpsYml ps
    throw 'Backend health check timed out. Run docker compose logs ragent-api.'
}
Write-Host "[OK] Backend is ready: $backendHealthUrl"

Write-Host ''
Write-Host '[3/4] Container status...'
& docker compose -f $composeYml -f $composeOpsYml ps

Write-Host ''
if ($frontendEnabled) {
    Write-Host '[4/4] Waiting for frontend...'
    if (Wait-HttpOk -Url 'http://localhost/' -Retries 40 -DelaySeconds 2) {
        Write-Host '[OK] Frontend is ready: http://localhost/'
    } else {
        Write-Warning 'Frontend is not ready yet, but backend started successfully.'
    }
} else {
    Write-Host '[4/4] Frontend check skipped in current mode.'
}

Write-Host ''
Write-Host '========================================='
Write-Host '  Startup Complete'
Write-Host '========================================='
Write-Host "Backend: $backendHealthUrl"
if ($frontendEnabled) {
    Write-Host 'Frontend: http://localhost/'
}
if ($effectiveMode -like 'ops*') {
    Write-Host 'Ops test service: http://localhost:18081/'
}
Write-Host ''
Write-Host 'Useful commands:'
Write-Host "  Status: docker compose -f `"$composeYml`" -f `"$composeOpsYml`" ps"
Write-Host "  Logs: docker compose -f `"$composeYml`" -f `"$composeOpsYml`" logs -f ragent-api"
Write-Host "  Stop: docker compose -f `"$composeYml`" -f `"$composeOpsYml`" down"
Write-Host "  Rebuild start: `"$scriptDir\start-project.bat`" ops -Build"

