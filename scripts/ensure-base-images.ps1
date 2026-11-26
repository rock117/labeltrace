# Prefer local base images; if missing, pull via China mirrors and retag to short names.
# Usage: powershell -File scripts/ensure-base-images.ps1
# Optional: $env:DOCKER_MIRRORS = "m.daocloud.io/docker.io/library,dockerproxy.net/library"

$ErrorActionPreference = "Continue"

# Prefer DaoCloud m.daocloud.io/docker.io/... (more reliable than docker.m.daocloud.io alias)
$DefaultMirrors = @(
    "m.daocloud.io/docker.io/library",
    "docker.m.daocloud.io/library",
    "dockerproxy.net/library",
    "docker.1ms.run/library",
    "hub.rat.dev/library",
    "docker.xuanyuan.me/library"
)
if ($env:DOCKER_MIRRORS) {
    $Mirrors = @($env:DOCKER_MIRRORS.Split(",") | ForEach-Object { $_.Trim().TrimEnd("/") } | Where-Object { $_ })
} elseif ($env:DOCKER_MIRROR) {
    $Mirrors = @($env:DOCKER_MIRROR.TrimEnd("/"))
} else {
    $Mirrors = $DefaultMirrors
}

$Images = @(
    "python:3.12-slim",
    "postgres:16-alpine",
    "node:22-bookworm-slim",
    "nginx:1.27-alpine"
)

function Test-LocalImage([string]$Name) {
    docker image inspect $Name 1>$null 2>$null
    return ($LASTEXITCODE -eq 0)
}

Write-Host "Docker mirrors: $($Mirrors -join ', ')"
foreach ($img in $Images) {
    if (Test-LocalImage $img) {
        Write-Host "[local] $img"
        continue
    }

    $ok = $false
    foreach ($mirror in $Mirrors) {
        $remote = "$mirror/$img"
        Write-Host "[pull ] $remote -> $img"
        & docker pull $remote
        if ($LASTEXITCODE -ne 0) { continue }

        & docker tag $remote $img
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[error] tag failed: $remote -> $img"
            continue
        }
        Write-Host "[tag  ] $remote -> $img"
        $ok = $true
        break
    }

    if (-not $ok) {
        Write-Host "[retry] docker.io/$img"
        & docker pull $img
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to pull $img (all mirrors and docker.io)"
        }
    }
}

Write-Host "Base images ready."
