<#
.SYNOPSIS
    Sélectionne les fichiers Docker Compose et le fichier d'environnement
    selon le mode (local / prod), puis transmet le reste des arguments
    tel quel à `docker compose`. Ne réimplémente rien d'autre.

.EXAMPLE
    .\docker.ps1 local up -d
    .\docker.ps1 local down -v
    .\docker.ps1 local ps
    .\docker.ps1 local logs -f backend
    .\docker.ps1 prod up -d
    .\docker.ps1 prod config
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("local", "prod")]
    [string]$Mode,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not $Rest -or $Rest.Count -eq 0) {
    Write-Error "Usage: .\docker.ps1 <local|prod> <commande docker compose...>  (ex: up -d, down -v, ps, logs -f backend)"
    exit 1
}

if ($Mode -eq "local") {
    if (-not (Test-Path ".env.local")) {
        Write-Error ".env.local introuvable. Creez-le d'abord : Copy-Item .env.local.example .env.local"
        exit 1
    }

    $ComposeArgs = @(
        "--env-file", ".env.local",
        "-f", "docker-compose.yaml",
        "-f", "docker-compose-postgres.yaml",
        "-f", "docker-compose-keycloak.yaml",
        "-f", "docker-compose-traefik.yml",
        "-f", "docker-compose.local.yml"
    )
}
else {
    if (-not (Test-Path ".env")) {
        Write-Error ".env introuvable. Creez-le d'abord : Copy-Item .env.production.example .env"
        exit 1
    }

    $ComposeArgs = @()
}

& docker compose @ComposeArgs @Rest
exit $LASTEXITCODE
