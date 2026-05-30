param(
    [ValidateSet('full', 'backend', 'ops', 'ops-backend', 'monitoring', 'monitoring-backend')]
    [string]$Mode = 'ops',
    [switch]$Build
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$composeYml = Join-Path $projectDir 'docker-compose.yml'
$composeOpsYml = Join-Path $projectDir 'docker-compose.ops.yml'
$composeMonitoringYml = Join-Path $projectDir 'docker-compose.monitoring.yml'

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

function Initialize-ConfigFile {
    param(
        [Parameter(Mandatory = $true)][string]$Target,
        [Parameter(Mandatory = $true)][string]$Example
    )

    if ((Test-Path $Target) -or -not (Test-Path $Example)) {
        return
    }
    Copy-Item -Path $Example -Destination $Target
    Write-Warning "已从示例生成配置：$Target，请按个人环境修改后再用于生产。"
}

Write-Host '========================================='
Write-Host '  Ragent Python Quick Start'
Write-Host '========================================='
Write-Host "Mode: $Mode"
Write-Host "Project: $projectDir"
Write-Host "Build images: $Build"
Write-Host ''

Initialize-ConfigFile -Target (Join-Path $projectDir '.env') -Example (Join-Path $projectDir '.env.example')
Initialize-ConfigFile -Target (Join-Path $projectDir 'config\servers.yml') -Example (Join-Path $projectDir 'config\servers.example.yml')
Initialize-ConfigFile -Target (Join-Path $projectDir 'config\monitoring.yml') -Example (Join-Path $projectDir 'config\monitoring.example.yml')
Write-Host ''

if (-not (Test-CommandExists 'docker')) {
    throw 'Docker is not installed.'
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker is not running.'
}

$frontendEnabled = $false
$monitoringEnabled = $false
$backendHealthUrl = 'http://localhost:8000/api/health'
$activeComposeFiles = @('-f', $composeYml, '-f', $composeOpsYml)
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
        $arguments = $activeComposeFiles + @('--profile', 'full', 'up', '-d')
        if ($Build) {
            $arguments += '--build'
        }
        Invoke-Compose $arguments
    }
    'ops-backend' {
        # 后端模式同样启用 ops override，只是不启动前端。
        $arguments = $activeComposeFiles + @('up', '-d')
        if ($Build) {
            $arguments += '--build'
        }
        $arguments += @('mysql', 'rustfs', 'etcd', 'milvus', 'redis', 'ragent-api', 'ops-test-service')
        Invoke-Compose $arguments
    }
    'monitoring' {
        $frontendEnabled = $true
        $monitoringEnabled = $true
        $activeComposeFiles = @('-f', $composeYml, '-f', $composeOpsYml, '-f', $composeMonitoringYml)
        # 监控模式额外启动 Prometheus、Alertmanager、Grafana 和各类 exporter。
        $arguments = $activeComposeFiles + @('--profile', 'full', 'up', '-d')
        if ($Build) {
            $arguments += '--build'
        }
        Invoke-Compose $arguments
    }
    'monitoring-backend' {
        $monitoringEnabled = $true
        $activeComposeFiles = @('-f', $composeYml, '-f', $composeOpsYml, '-f', $composeMonitoringYml)
        # 后端监控模式不启动正式前端，但保留运维测试服务和监控组件。
        $arguments = $activeComposeFiles + @('up', '-d')
        if ($Build) {
            $arguments += '--build'
        }
        $arguments += @(
            'mysql',
            'rustfs',
            'etcd',
            'milvus',
            'redis',
            'ragent-api',
            'ops-test-service',
            'prometheus',
            'alertmanager',
            'grafana',
            'node-exporter',
            'cadvisor',
            'redis-exporter',
            'mysqld-exporter',
            'blackbox-exporter'
        )
        Invoke-Compose $arguments
    }
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
if ($monitoringEnabled) {
    Write-Host 'Ops test service: http://localhost:18081/'
    Write-Host 'Prometheus: http://localhost:9090/'
    Write-Host 'Alertmanager: http://localhost:9093/'
    Write-Host 'Grafana: http://localhost:3001/  (admin/admin)'
}
Write-Host ''
Write-Host 'Useful commands:'
Write-Host "  Status: docker compose $($activeComposeFiles -join ' ') ps"
Write-Host "  Logs: docker compose $($activeComposeFiles -join ' ') logs -f ragent-api"
Write-Host "  Stop: docker compose $($activeComposeFiles -join ' ') down"
Write-Host "  Rebuild start: `"$scriptDir\start-project.bat`" ops -Build"

