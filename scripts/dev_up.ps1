<#
.SYNOPSIS
  ProLine CAD one-click dev stack: PostGIS + Alembic head + (optional) FastAPI.

.DESCRIPTION
  Brings up the lite Postgres+PostGIS container, waits for healthcheck,
  exports POSTGRES_DSN for the current PowerShell session, runs
  `alembic upgrade head`, then optionally starts uvicorn for the
  Dashboard backend.

  Idempotent: re-running detects the existing container and skips up.

.PARAMETER Full
  Use the full TimescaleDB image (db/docker-compose.db.yml, port 5433)
  instead of the lite PostGIS image (port 5434). Required for revision
  0003 (TimescaleDB hypertable) to actually run instead of being stamped.

.PARAMETER ServeApi
  After migrations, start uvicorn for app.main:app on :8000 in this
  shell (foreground). Use Ctrl+C to stop; container keeps running.

.PARAMETER Down
  Tear down the stack (containers + volumes) and exit. Mutually
  exclusive with -ServeApi.

.EXAMPLE
  .\scripts\dev_up.ps1
  # Lite stack, migrations to head, no API.

.EXAMPLE
  .\scripts\dev_up.ps1 -Full -ServeApi
  # Full Timescale stack + migrations + uvicorn foreground.

.EXAMPLE
  .\scripts\dev_up.ps1 -Down
  # Stop and wipe. Warning: -v drops the volume.
#>
[CmdletBinding()]
param(
    [switch]$Full,
    [switch]$ServeApi,
    [switch]$Down
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --- Resolve repo root (script lives in <repo>/scripts/) -----------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir '..')
Push-Location $RepoRoot
try {
    if ($Full) {
        $ComposeFile = 'db/docker-compose.db.yml'
        $Port        = 5433
        $Container   = 'proline-postgres-spatial'
    } else {
        $ComposeFile = 'db/docker-compose.db-lite.yml'
        $Port        = 5434
        $Container   = 'proline-postgres-postgis'
    }
    $Dsn = "postgresql+psycopg2://proline:proline_dev@localhost:$Port/proline_cad"

    # --- Down path: tear down and exit -----------------------------------
    if ($Down) {
        Write-Host "[dev_up] Tearing down $ComposeFile (volumes included)..." -ForegroundColor Yellow
        docker compose -f $ComposeFile down -v
        return
    }

    # --- Preflight: docker reachable? ------------------------------------
    try {
        docker version --format '{{.Server.Version}}' | Out-Null
    } catch {
        throw "[dev_up] Docker daemon not reachable. Is Docker Desktop running?"
    }

    # --- Step 1: container up -------------------------------------------
    $existing = docker ps --filter "name=^/$Container$" --format '{{.Names}}'
    if ($existing -eq $Container) {
        Write-Host "[dev_up] Container $Container already running on :$Port" -ForegroundColor Green
    } else {
        Write-Host "[dev_up] Starting $Container via $ComposeFile..." -ForegroundColor Cyan
        docker compose -f $ComposeFile up -d
    }

    # --- Step 2: wait for healthcheck (max 60s) --------------------------
    Write-Host "[dev_up] Waiting for $Container healthcheck..." -NoNewline
    $deadline = (Get-Date).AddSeconds(60)
    do {
        $health = docker inspect --format '{{.State.Health.Status}}' $Container 2>$null
        if ($health -eq 'healthy') { break }
        Write-Host '.' -NoNewline
        Start-Sleep -Milliseconds 1000
    } while ((Get-Date) -lt $deadline)
    if ($health -ne 'healthy') {
        throw "[dev_up] $Container did not become healthy within 60s (last status: $health)"
    }
    Write-Host " healthy" -ForegroundColor Green

    # --- Step 3: export DSN for this shell -------------------------------
    $env:POSTGRES_DSN = $Dsn
    Write-Host "[dev_up] POSTGRES_DSN exported for this session" -ForegroundColor Green

    # --- Step 4: alembic upgrade head ------------------------------------
    # Locate venv python; fall back to system python if no venv.
    $VenvPy = Join-Path $RepoRoot '..\.venv\Scripts\python.exe'
    if (Test-Path $VenvPy) {
        $Py = (Resolve-Path $VenvPy).Path
    } else {
        $Py = 'python'
        Write-Warning "[dev_up] No .venv detected at $VenvPy; falling back to system 'python'"
    }

    Write-Host "[dev_up] Running alembic upgrade head..." -ForegroundColor Cyan
    if ($Full) {
        & $Py -m alembic -c db/alembic.ini upgrade head
    } else {
        # Lite path: PostGIS-only image cannot run 0003 (Timescale) or 0006
        # (pgvector). Stamp them so alembic skips, but only do the bootstrap
        # stamp on a FRESH database -- on an already-stamped DB just upgrade.
        # Alembic writes INFO to stderr; with $ErrorActionPreference=Stop that
        # gets treated as a failure. Capture into a string via cmd redirection.
        $current = & cmd /c "`"$Py`" -m alembic -c db/alembic.ini current 2>&1"
        $current = ($current | Out-String)
        if ($current -notmatch '\b[0-9a-f]{4,}_') {
            Write-Host "[dev_up] Fresh DB detected; stamping baseline..." -ForegroundColor Cyan
            & $Py -m alembic -c db/alembic.ini stamp 0001_baseline
        }
        & $Py -m alembic -c db/alembic.ini upgrade 0002_postgis_spatial
        # Only stamp Timescale if we haven't already passed it.
        if ($current -notmatch '0003_timescale_mcp|0004|0005|0006') {
            & $Py -m alembic -c db/alembic.ini stamp 0003_timescale_mcp
        }
        & $Py -m alembic -c db/alembic.ini upgrade 0005_audit_log_actions
        if ($current -notmatch '0006_pgvector_reserve') {
            & $Py -m alembic -c db/alembic.ini stamp 0006_pgvector_reserve
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "[dev_up] alembic upgrade failed (exit $LASTEXITCODE)"
    }
    Write-Host "[dev_up] Migrations applied." -ForegroundColor Green

    # --- Step 5 (optional): uvicorn --------------------------------------
    if ($ServeApi) {
        $AppModule = 'app.main:app'
        Write-Host "[dev_up] Starting uvicorn $AppModule on :8000 (Ctrl+C to stop)..." -ForegroundColor Cyan
        & $Py -m uvicorn $AppModule --reload --host 127.0.0.1 --port 8000
    } else {
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Yellow
        Write-Host "  - DSN ready in this shell:  `$env:POSTGRES_DSN" -ForegroundColor Gray
        Write-Host "  - Run tests:                pytest tests/db -v" -ForegroundColor Gray
        Write-Host "  - Start API:                .\scripts\dev_up.ps1 -ServeApi" -ForegroundColor Gray
        Write-Host "  - Tear down:                .\scripts\dev_up.ps1 -Down" -ForegroundColor Gray
    }
}
finally {
    Pop-Location
}
