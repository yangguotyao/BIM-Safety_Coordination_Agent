$ErrorActionPreference = 'Stop'
$SourceDir = Split-Path -Parent $PSScriptRoot
$PackageRoot = Split-Path -Parent $SourceDir
$ToolsDir = Join-Path $PackageRoot '.tools'
$UvExe = Join-Path $ToolsDir 'uv\bin\uv.exe'
if (-not (Test-Path -LiteralPath $UvExe)) {
  throw '本交付环境缺少 uv。请从 https://docs.astral.sh/uv/getting-started/installation/ 安装官方 uv，并将 uv.exe 放到 .tools/uv/bin/。'
}
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ToolsDir 'python'
& $UvExe python install 3.11
if ($LASTEXITCODE -ne 0) { throw 'Python 下载失败' }
$VenvDir = Join-Path $SourceDir 'backend\.venv-win311'
if (-not (Test-Path -LiteralPath (Join-Path $VenvDir 'Scripts\python.exe'))) {
  & $UvExe venv $VenvDir --python 3.11
  if ($LASTEXITCODE -ne 0) { throw '创建 Python 环境失败' }
}
& $UvExe pip sync --python (Join-Path $VenvDir 'Scripts\python.exe') (Join-Path $SourceDir 'backend\requirements-lock.txt') --index-url https://pypi.org/simple
if ($LASTEXITCODE -ne 0) { throw '后端依赖安装失败' }
$NodeDir = Join-Path $ToolsDir 'node-v22.23.3-win-x64'
if (-not (Test-Path -LiteralPath (Join-Path $NodeDir 'node.exe'))) {
  throw '缺少项目 Node.js 22，请将官方 node-v22.23.3-win-x64 包解压到 .tools/。'
}
$env:PATH = "$NodeDir;$env:PATH"
Push-Location (Join-Path $SourceDir 'frontend')
try {
  & (Join-Path $NodeDir 'npm.cmd') ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败' }
  & (Join-Path $NodeDir 'npm.cmd') run build
  if ($LASTEXITCODE -ne 0) { throw '前端构建失败' }
} finally { Pop-Location }
Write-Host '环境准备完成，请运行 scripts/start.ps1。'
