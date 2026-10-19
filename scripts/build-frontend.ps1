param([string]$NodePath)
$ErrorActionPreference = 'Stop'
$rfRoot = Split-Path -Parent $PSScriptRoot
$rfFrontend = Join-Path $rfRoot 'frontend'
$rfTsc = Join-Path $rfFrontend 'node_modules\typescript\bin\tsc'
$rfVite = Join-Path $rfFrontend 'node_modules\vite\bin\vite.js'

if ($NodePath) {
    $rfNode = $NodePath
} else {
    $rfCommand = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $rfCandidates = @()
    if ($rfCommand) { $rfCandidates += $rfCommand.Source }
    if ($env:ProgramFiles) { $rfCandidates += Join-Path $env:ProgramFiles 'nodejs\node.exe' }
    if ($env:LOCALAPPDATA) { $rfCandidates += Join-Path $env:LOCALAPPDATA 'Programs\nodejs\node.exe' }
    # Match start-frontend.ps1: reuse an existing runtime without changing PATH.
    if ($env:USERPROFILE) {
        $rfCandidates += Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    }
    $rfNode = $rfCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $rfNode -or -not (Test-Path -LiteralPath $rfNode -PathType Leaf)) {
    throw 'Node.js was not found. Install Node 20.19+ or 22.12+, or pass -NodePath with the path to node.exe.'
}
$rfNode = (Resolve-Path -LiteralPath $rfNode).Path
if (-not (Test-Path -LiteralPath $rfTsc -PathType Leaf) -or -not (Test-Path -LiteralPath $rfVite -PathType Leaf)) {
    throw 'Frontend dependencies are missing. Install them with pnpm --dir frontend install --frozen-lockfile. See README.md.'
}
Write-Host "Node executable: $rfNode"
& $rfNode -e "const [major,minor]=process.versions.node.split('.').map(Number); if (!((major===20 && minor>=19)||(major===22 && minor>=12)||major>22)) { console.error('Unsupported Node version: '+process.versions.node); process.exit(1); } console.log('Node '+process.versions.node);"
if ($LASTEXITCODE -ne 0) { throw 'A compatible Node version is required. Use -NodePath to select another node.exe.' }

# Keep these two steps equivalent to frontend/package.json's build script.
Push-Location $rfFrontend
try {
    & $rfNode $rfTsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw "TypeScript check failed with code $LASTEXITCODE." }
    & $rfNode $rfVite build
    if ($LASTEXITCODE -ne 0) { throw "Vite build failed with code $LASTEXITCODE." }
    Write-Host "Frontend build complete: $rfFrontend\dist"
} finally {
    Pop-Location
}
