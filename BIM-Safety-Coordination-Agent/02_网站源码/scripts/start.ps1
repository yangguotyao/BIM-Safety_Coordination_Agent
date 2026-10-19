param([int]$Port = 8003, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceDir = Split-Path -Parent $ScriptDir
$PackageRoot = Split-Path -Parent $SourceDir
$BackendDir = Join-Path $SourceDir "backend"
$FrontendDir = Join-Path $SourceDir "frontend"
$DataRoot = if ($env:DATA_ROOT) { $env:DATA_ROOT } else { Join-Path $PackageRoot "01_资料与依据" }
$RuntimeDir = if ($env:RUNTIME_DIR) { $env:RUNTIME_DIR } else { Join-Path $BackendDir "runtime" }
if ($env:PORT) { $Port = [int]$env:PORT }
$HostName = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }

$env:DATA_ROOT = $DataRoot
$env:RUNTIME_DIR = $RuntimeDir
$env:PORT = $Port
$env:HOST = $HostName

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
if (-not (Test-Path $DataRoot)) {
  Write-Host "资料目录不存在：$DataRoot" -ForegroundColor Red
  exit 1
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
  try {
    $ExistingHealth = Invoke-RestMethod -Uri "http://${HostName}:${Port}/api/health" -TimeoutSec 3
    if ($ExistingHealth.ok -and $ExistingHealth.package_root -eq $PackageRoot) {
      Write-Host "平台已在运行：http://${HostName}:${Port}"
      if (-not $NoBrowser) { Start-Process "http://${HostName}:${Port}" }
      exit 0
    }
  } catch { }
  Write-Host "端口 $Port 已被其他服务占用；可使用 -Port 8004 后重试。" -ForegroundColor Red
  exit 1
}

Set-Location $BackendDir
$PythonExe = Join-Path $BackendDir '.venv-win311\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) {
  throw '缺少本项目 Python 3.11 环境，请先运行 scripts/setup.ps1。'
}
& $PythonExe -c "import sys, importlib.metadata as m; from langgraph.checkpoint.sqlite import SqliteSaver; assert sys.version_info[:2] == (3,11); assert m.version('fastapi') == '0.141.1'; assert m.version('uvicorn') == '0.52.4'; assert m.version('pydantic-settings') == '2.15.0'; assert m.version('langgraph-checkpoint-sqlite') == '3.0.3'"
if ($LASTEXITCODE -ne 0) { throw '运行版本不匹配，请运行 scripts/setup.ps1。' }

if (-not (Test-Path (Join-Path $FrontendDir "dist\index.html"))) {
  Set-Location $FrontendDir
  $NodeDir = Join-Path $PackageRoot '.tools\node-v22.23.3-win-x64'
  $env:PATH = "$NodeDir;$env:PATH"
  & (Join-Path $NodeDir 'npm.cmd') ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
  & (Join-Path $NodeDir 'npm.cmd') run build
  if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
  Set-Location $BackendDir
}

Write-Host ""
Write-Host "BIM 施工安全协同平台"
Write-Host "地址      http://${HostName}:${Port}"
Write-Host "API 文档  http://${HostName}:${Port}/api/docs"
Write-Host "资料根目录 $DataRoot"
Write-Host "运行目录   $RuntimeDir"
Write-Host ""

if (-not $NoBrowser) {
  $BrowserJob = Start-Job -ArgumentList "http://${HostName}:${Port}" -ScriptBlock {
    param($Url)
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
      try {
        Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 1 | Out-Null
        Start-Process $Url
        return
      } catch { Start-Sleep -Seconds 1 }
    }
  }
}
& $PythonExe -m uvicorn app.main:app --host $HostName --port $Port
