#Requires -Version 5.1
<#
.SYNOPSIS
    Demarre le serveur Odoo installe par windows\Install-Odoo.ps1.

.DESCRIPTION
    Verifie l'environnement virtuel, s'assure que PostgreSQL tourne, place
    wkhtmltopdf dans le PATH de la session, puis lance odoo-bin avec odoo.conf.
    Tout argument supplementaire est transmis tel quel a odoo-bin.

.EXAMPLE
    .\windows\Start-Odoo.ps1 -Open
    Demarre le serveur et ouvre le navigateur quand le port repond.

.EXAMPLE
    .\windows\Start-Odoo.ps1 -- -u base -d odoo_saas19
    Met a jour le module "base" sur la base odoo_saas19.

.EXAMPLE
    .\windows\Start-Odoo.ps1 -- --dev=xml,reload
    Demarre en mode developpeur avec rechargement automatique.
#>
[CmdletBinding()]
param(
    # Ouvre le navigateur des que le serveur repond.
    [switch] $Open,

    # Fichier de configuration alternatif.
    [string] $ConfigFile,

    # Arguments transmis tels quels a odoo-bin.
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ExtraArgs
)

$ErrorActionPreference = 'Stop'
# Affiche correctement les accents dans Windows PowerShell 5.1.
# Sans effet sur certains hotes (ISE, console redirigee) : echec sans consequence.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {
    # Encodage de console non modifiable : l'affichage reste lisible.
}

$Root     = Split-Path -Parent $PSScriptRoot
$VenvPy   = Join-Path $Root '.venv-win\Scripts\python.exe'
$OdooBin  = Join-Path $Root 'odoo-bin'
$ConfPath = if ($ConfigFile) { $ConfigFile } else { Join-Path $Root 'odoo.conf' }

function Get-ConfValue {
    param([string] $Path, [string] $Key, [string] $Default)
    if (-not (Test-Path $Path)) { return $Default }
    $m = Select-String -Path $Path -Pattern "^\s*$Key\s*=\s*(.+?)\s*$" |
         Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value }
    return $Default
}

# --- Verifications ---------------------------------------------------------

if (-not (Test-Path $VenvPy)) {
    Write-Host ''
    Write-Host "  Environnement virtuel introuvable : $VenvPy" -ForegroundColor Red
    Write-Host '  Lancez d''abord windows\Install-Odoo.ps1 (en administrateur).' -ForegroundColor Yellow
    Write-Host ''
    exit 1
}
if (-not (Test-Path $ConfPath)) {
    Write-Host ''
    Write-Host "  Configuration introuvable : $ConfPath" -ForegroundColor Red
    Write-Host '  Lancez d''abord windows\Install-Odoo.ps1 (en administrateur).' -ForegroundColor Yellow
    Write-Host ''
    exit 1
}

# --- PostgreSQL ------------------------------------------------------------

$svc = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($svc -and $svc.Status -ne 'Running') {
    Write-Host "  Demarrage du service $($svc.Name)..." -ForegroundColor Gray
    try {
        Start-Service $svc.Name
        $svc.WaitForStatus('Running', '00:00:30')
    } catch {
        Write-Host "  Impossible de demarrer $($svc.Name) : $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host '  Un compte administrateur est peut-etre necessaire.' -ForegroundColor Yellow
    }
}

# --- wkhtmltopdf -----------------------------------------------------------

if (-not (Get-Command wkhtmltopdf.exe -ErrorAction SilentlyContinue)) {
    foreach ($p in @("$env:ProgramFiles\wkhtmltopdf\bin",
                     "${env:ProgramFiles(x86)}\wkhtmltopdf\bin")) {
        if (Test-Path (Join-Path $p 'wkhtmltopdf.exe')) {
            $env:Path = "$env:Path;$p"
            break
        }
    }
}

# --- Ouverture du navigateur ----------------------------------------------

$port = [int] (Get-ConfValue -Path $ConfPath -Key 'http_port' -Default '8069')

if ($Open) {
    # Attend que le port accepte les connexions avant d'ouvrir le navigateur :
    # le premier demarrage d'Odoo (chargement du registre) peut etre long.
    Start-Job -ArgumentList $port -ScriptBlock {
        param($Port)
        for ($i = 0; $i -lt 180; $i++) {
            Start-Sleep -Seconds 1
            try {
                $c = New-Object Net.Sockets.TcpClient
                $c.Connect('127.0.0.1', $Port)
                $c.Close()
                Start-Process "http://localhost:$Port/"
                return
            } catch {
                # Port pas encore ouvert : Odoo charge son registre. On reessaie.
            }
        }
    } | Out-Null
}

# --- Lancement -------------------------------------------------------------

Write-Host ''
Write-Host '===========================================================================' -ForegroundColor White
Write-Host '  Odoo saas~19.2' -ForegroundColor White
Write-Host '===========================================================================' -ForegroundColor White
Write-Host "  Configuration : $ConfPath" -ForegroundColor Gray
Write-Host "  Journal       : $(Get-ConfValue -Path $ConfPath -Key 'logfile' -Default '(console)')" -ForegroundColor Gray
Write-Host "  URL           : http://localhost:$port/" -ForegroundColor Gray
Write-Host '  Arret         : Ctrl+C' -ForegroundColor Gray
Write-Host '===========================================================================' -ForegroundColor White
Write-Host ''

# Le repertoire courant devient la racine du projet : les chemins relatifs
# eventuellement presents dans odoo.conf se resolvent correctement.
Push-Location $Root
$previousEap = $ErrorActionPreference
try {
    # Odoo journalise sur stderr : sous Windows PowerShell 5.1, chaque ligne
    # deviendrait une erreur fatale avec ErrorActionPreference = 'Stop'.
    $ErrorActionPreference = 'Continue'
    $arguments = @($OdooBin, '-c', $ConfPath)
    if ($ExtraArgs) {
        # PowerShell laisse passer un "--" isole en tete des arguments restants.
        $arguments += ($ExtraArgs | Where-Object { $_ -ne '--' })
    }
    & $VenvPy @arguments
    $code = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousEap
    Pop-Location
}

if ($code -ne 0) {
    Write-Host ''
    Write-Host "  Odoo s'est arrete avec le code $code." -ForegroundColor Red
    Write-Host '  Consultez le journal ci-dessus, ou la section Depannage de INSTALL-WINDOWS.md.' -ForegroundColor Gray
    Write-Host ''
}
exit $code
