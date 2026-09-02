#Requires -Version 5.1
<#
.SYNOPSIS
    Enregistre (ou supprime) Odoo comme service Windows, via NSSM.

.DESCRIPTION
    Odoo n'embarque pas de wrapper de service : NSSM (Non-Sucking Service Manager)
    supervise le processus Python, le redemarre en cas d'arret imprevu et redirige
    les sorties vers windows\logs. C'est l'outil qu'utilise l'installeur officiel
    d'Odoo pour Windows.

    Le nom du service reprend odoo.release.nt_service_name, soit
    "odoo-server-saas-19.2" pour cette version.

.EXAMPLE
    .\windows\Install-Service.ps1
    Installe le service et le demarre.

.EXAMPLE
    .\windows\Install-Service.ps1 -StartupType Manual -NoStart
    Installe le service en demarrage manuel, sans le lancer.

.EXAMPLE
    .\windows\Install-Service.ps1 -Remove
    Arrete et supprime le service.
#>
[CmdletBinding()]
param(
    # Supprime le service au lieu de l'installer.
    [switch] $Remove,

    [ValidateSet('Automatic', 'Manual', 'Disabled')]
    [string] $StartupType = 'Automatic',

    # N'demarre pas le service apres installation.
    [switch] $NoStart,

    # Nom du service. Par defaut : odoo.release.nt_service_name.
    [string] $ServiceName
)

$ErrorActionPreference = 'Stop'
# Affiche correctement les accents dans Windows PowerShell 5.1.
# Sans effet sur certains hotes (ISE, console redirigee) : echec sans consequence.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {
    # Encodage de console non modifiable : l'affichage reste lisible.
}

$Root      = Split-Path -Parent $PSScriptRoot
$VenvPy    = Join-Path $Root '.venv-win\Scripts\python.exe'
$OdooBin   = Join-Path $Root 'odoo-bin'
$ConfPath  = Join-Path $Root 'odoo.conf'
$LogDir    = Join-Path $Root 'windows\logs'
$ToolsDir  = Join-Path $Root 'windows\tools'
$NssmDir   = Join-Path $ToolsDir 'nssm'
$NssmUrl   = 'https://nssm.cc/release/nssm-2.24.zip'

function Write-Ok   { param([string] $m) Write-Host "    OK    $m" -ForegroundColor Green }
function Write-Info { param([string] $m) Write-Host "          $m" -ForegroundColor Gray }
function Write-Warn { param([string] $m) Write-Host "    ATTN  $m" -ForegroundColor Yellow }

function Test-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ServiceName {
    if ($ServiceName) { return $ServiceName }
    $releasePy = Join-Path $Root 'odoo\release.py'
    if (Test-Path $VenvPy) {
        # runpy evite d'importer le paquet odoo (et donc ses dependances).
        $name = & $VenvPy -c "import runpy; print(runpy.run_path(r'$releasePy')['nt_service_name'])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $name) { return "$name".Trim() }
    }
    return 'odoo-server-saas-19.2'
}

function Get-Nssm {
    <# Renvoie le chemin de nssm.exe : celui du PATH, sinon celui deja telecharge,
       sinon telecharge nssm 2.24 (meme version que l'installeur officiel Odoo). #>
    $cmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $local = Join-Path $NssmDir 'win64\nssm.exe'
    if (Test-Path $local) { return $local }

    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        Write-Info 'Installation de NSSM via winget...'
        & winget.exe install --id NSSM.NSSM --exact --source winget --silent `
            --accept-package-agreements --accept-source-agreements *> $null
        if ($LASTEXITCODE -eq 0) {
            $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
            $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
            $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
            $cmd = Get-Command nssm.exe -ErrorAction SilentlyContinue
            if ($cmd) { return $cmd.Source }
        }
        Write-Info 'winget indisponible pour NSSM ; telechargement direct.'
    }

    Write-Info "Telechargement de NSSM depuis $NssmUrl ..."
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
    $zip = Join-Path $ToolsDir 'nssm.zip'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $NssmUrl -OutFile $zip -UseBasicParsing

    if (Test-Path $NssmDir) { Remove-Item $NssmDir -Recurse -Force }
    $extract = Join-Path $ToolsDir '_nssm_extract'
    if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $extract -Force
    # L'archive contient un dossier nssm-2.24\ que l'on aplatit en tools\nssm\.
    $inner = Get-ChildItem $extract -Directory | Select-Object -First 1
    Move-Item $inner.FullName $NssmDir
    Remove-Item $extract -Recurse -Force
    Remove-Item $zip -Force

    $local = Join-Path $NssmDir 'win64\nssm.exe'
    if (-not (Test-Path $local)) { throw "nssm.exe introuvable apres extraction dans $NssmDir." }
    Write-Ok "NSSM : $local"
    return $local
}

function Invoke-Nssm {
    param([string] $Nssm, [string[]] $Arguments, [switch] $IgnoreExitCode)
    # nssm ecrit ses messages sur stderr : sous Windows PowerShell 5.1, avec
    # ErrorActionPreference = 'Stop', 2>&1 les transformerait en erreur fatale.
    $previousEap = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Nssm @Arguments 2>&1 |
            ForEach-Object { Write-Host "          $_" -ForegroundColor DarkGray }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousEap
    }
    if (-not $IgnoreExitCode -and $code -ne 0) {
        throw "nssm $($Arguments -join ' ') a echoue (code $code)."
    }
}

# --------------------------------------------------------------------------- #

Write-Host ''
if (-not (Test-Administrator)) {
    Write-Host '  Privileges administrateur requis pour gerer un service Windows.' -ForegroundColor Red
    Write-Host '  Ouvrez PowerShell en tant qu''administrateur et relancez ce script.' -ForegroundColor Yellow
    Write-Host ''
    exit 1
}

$name = Get-ServiceName
$existing = Get-Service -Name $name -ErrorAction SilentlyContinue

try {
    if ($Remove) {
        Write-Host "  Suppression du service '$name'" -ForegroundColor Cyan
        Write-Host ('-' * 74) -ForegroundColor DarkGray
        if (-not $existing) {
            Write-Warn "Le service '$name' n'existe pas."
            exit 0
        }
        $nssm = Get-Nssm
        if ($existing.Status -ne 'Stopped') {
            Write-Info 'Arret du service...'
            Invoke-Nssm -Nssm $nssm -Arguments @('stop', $name) -IgnoreExitCode
        }
        Invoke-Nssm -Nssm $nssm -Arguments @('remove', $name, 'confirm')
        Write-Ok "Service '$name' supprime"
        Write-Host ''
        exit 0
    }

    Write-Host "  Installation du service '$name'" -ForegroundColor Cyan
    Write-Host ('-' * 74) -ForegroundColor DarkGray

    foreach ($p in @($VenvPy, $OdooBin, $ConfPath)) {
        if (-not (Test-Path $p)) {
            throw ("Fichier requis introuvable : $p" + [Environment]::NewLine +
                   '  Lancez d''abord windows\Install-Odoo.ps1.')
        }
    }
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

    $nssm = Get-Nssm

    if ($existing) {
        Write-Info "Le service '$name' existe deja : reconfiguration."
        if ($existing.Status -ne 'Stopped') {
            Invoke-Nssm -Nssm $nssm -Arguments @('stop', $name) -IgnoreExitCode
        }
        Invoke-Nssm -Nssm $nssm -Arguments @('remove', $name, 'confirm')
        Start-Sleep -Seconds 2
    }

    Invoke-Nssm -Nssm $nssm -Arguments @('install', $name, $VenvPy, $OdooBin, '-c', $ConfPath)

    $startMode = switch ($StartupType) {
        'Automatic' { 'SERVICE_AUTO_START' }
        'Manual'    { 'SERVICE_DEMAND_START' }
        'Disabled'  { 'SERVICE_DISABLED' }
    }

    $settings = @(
        @('set', $name, 'AppDirectory',   $Root),
        @('set', $name, 'DisplayName',    'Odoo Server saas~19.2'),
        @('set', $name, 'Description',    'Serveur Odoo saas~19.2 (ERP/CRM open source).'),
        @('set', $name, 'Start',          $startMode),
        @('set', $name, 'AppStdout',      (Join-Path $LogDir 'service-stdout.log')),
        @('set', $name, 'AppStderr',      (Join-Path $LogDir 'service-stderr.log')),
        # Rotation des journaux du service a 16 Mio.
        @('set', $name, 'AppRotateFiles', '1'),
        @('set', $name, 'AppRotateOnline','1'),
        @('set', $name, 'AppRotateBytes', '16777216'),
        # Laisse a Odoo le temps de fermer proprement ses connexions SQL.
        @('set', $name, 'AppStopMethodConsole', '30000'),
        # Redemarrage automatique, avec une temporisation contre les boucles d'echec.
        @('set', $name, 'AppExit',        'Default', 'Restart'),
        @('set', $name, 'AppRestartDelay','10000')
    )
    foreach ($s in $settings) { Invoke-Nssm -Nssm $nssm -Arguments $s }

    # Odoo ne peut pas demarrer avant PostgreSQL : on declare la dependance.
    $pgSvc = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pgSvc) {
        Invoke-Nssm -Nssm $nssm -Arguments @('set', $name, 'DependOnService', $pgSvc.Name)
        Write-Ok "Dependance declaree : $($pgSvc.Name)"
    } else {
        Write-Warn 'Service PostgreSQL introuvable : aucune dependance declaree.'
    }

    Write-Ok "Service '$name' installe ($StartupType)"
    Write-Info "Executable  : $VenvPy"
    Write-Info "Arguments   : $OdooBin -c $ConfPath"
    Write-Info "Repertoire  : $Root"
    Write-Info "Journaux    : $LogDir"

    if ($NoStart -or $StartupType -eq 'Disabled') {
        Write-Info "Demarrage manuel : Start-Service '$name'"
    } else {
        Write-Info 'Demarrage du service...'
        Start-Service $name
        (Get-Service $name).WaitForStatus('Running', '00:01:00')
        Write-Ok "Service demarre : $((Get-Service $name).Status)"
    }

    Write-Host ''
    Write-Host '  Commandes utiles :' -ForegroundColor Yellow
    Write-Host "    Get-Service '$name'"
    Write-Host "    Restart-Service '$name'"
    Write-Host "    Stop-Service '$name'"
    Write-Host "    .\windows\Install-Service.ps1 -Remove"
    Write-Host ''
    exit 0

} catch {
    Write-Host ''
    Write-Host "  Echec : $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    exit 1
}
