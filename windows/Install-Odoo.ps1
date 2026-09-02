#Requires -Version 5.1
<#
.SYNOPSIS
    Installe Odoo saas~19.2 sur un PC Windows (Python 3.12, PostgreSQL, wkhtmltopdf).

.DESCRIPTION
    Script d'installation autonome :
      1. verifie les prerequis (Windows 64 bits, winget, droits administrateur) ;
      2. installe Python 3.12 si absent ;
      3. installe PostgreSQL (>= 16, minimum impose par odoo/release.py) ;
      4. installe wkhtmltopdf (rapports PDF) ;
      5. cree l'environnement virtuel .venv-win et installe requirements.txt ;
      6. cree le role PostgreSQL applicatif ;
      7. genere un odoo.conf adapte a Windows a la racine du projet ;
      8. verifie l'installation (odoo-bin --version, imports, connexion SQL).

    Pourquoi Python 3.12 et pas plus recent :
    requirements.txt epingle rl-renderPM==4.0.3 sous Windows. Ce paquet n'expose
    aucune roue cp313+ et n'a aucun repli en pur Python : Python 3.13 imposerait
    l'installation de Visual Studio Build Tools. En 3.12, les trois paquets sans
    roue Windows (ofxparse, vobject, rjsmin) se construisent sans compilateur.

.EXAMPLE
    .\windows\Install-Odoo.ps1
    Installation complete avec les valeurs par defaut.

.EXAMPLE
    .\windows\Install-Odoo.ps1 -CheckOnly
    Diagnostic uniquement : n'installe et ne modifie rien.

.EXAMPLE
    .\windows\Install-Odoo.ps1 -DbName odoo_prod -HttpPort 8080 -DbPassword 'MonMotDePasse'
#>
[CmdletBinding()]
param(
    # Nom de la base creee au premier demarrage (modifiable ensuite dans odoo.conf).
    [string] $DbName = 'odoo_saas19',

    # Role PostgreSQL utilise par Odoo.
    [string] $DbUser = 'odoo',

    # Mot de passe du role Odoo. Genere aleatoirement si omis.
    # Type String et non SecureString : Odoo exige ces mots de passe en clair
    # dans odoo.conf, et psql les recoit via PGPASSWORD. Un SecureString serait
    # dechiffre immediatement : il ajouterait de la ceremonie sans protection
    # reelle. Le fichier genere est protege par une ACL restrictive a la place.
    [string] $DbPassword,

    [string] $DbHost = 'localhost',
    [int]    $DbPort = 5432,

    # Port HTTP du serveur Odoo.
    [int]    $HttpPort = 8069,

    # Mot de passe maitre (gestionnaire de bases). Genere aleatoirement si omis.
    [string] $MasterPassword,

    # Mot de passe du superutilisateur "postgres".
    # Demande interactivement si PostgreSQL est deja installe ; genere sinon.
    [string] $PostgresSuperPassword,

    # Version de PostgreSQL a installer si absente.
    [ValidateSet('16', '17', '18')]
    [string] $PostgresVersion = '17',

    # Rend le serveur accessible depuis le reseau local (par defaut : localhost seul).
    [switch] $ListenOnAllInterfaces,

    [switch] $SkipPostgres,
    [switch] $SkipWkhtmltopdf,

    # Diagnostic seul : aucune installation, aucune modification.
    [switch] $CheckOnly,

    # Recree .venv-win meme s'il existe deja.
    [switch] $Force,

    # N'essaie pas de relancer le script avec elevation des privileges.
    [switch] $NoElevate
)

$ErrorActionPreference = 'Stop'
# Affiche correctement les accents dans Windows PowerShell 5.1.
# Sans effet sur certains hotes (ISE, console redirigee) : echec sans consequence.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {
    # Encodage de console non modifiable : l'affichage reste lisible.
}

# --------------------------------------------------------------------------- #
# Constantes                                                                   #
# --------------------------------------------------------------------------- #

$PythonSeries   = '3.12'
$PythonWingetId = 'Python.Python.3.12'
$MinPgVersion   = 16
$VenvName       = '.venv-win'

$Root      = Split-Path -Parent $PSScriptRoot
$VenvPath  = Join-Path $Root $VenvName
$VenvPy    = Join-Path $VenvPath 'Scripts\python.exe'
$ConfPath  = Join-Path $Root 'odoo.conf'
$DataDir   = Join-Path $Root '.odoo_local_data'
$AddonsDir = Join-Path $Root 'addons'
$OdooBin   = Join-Path $Root 'odoo-bin'
$ReqFile   = Join-Path $Root 'requirements.txt'
$LogDir    = Join-Path $Root 'windows\logs'

$script:Warnings            = @()
$script:StepNo              = 0
$script:IsAdmin             = $false
$script:HasWinget           = $false
$script:PgSuperPassword     = $null
$script:GeneratedPgPassword = $false
$script:NativeExitCode      = 0

# --------------------------------------------------------------------------- #
# Utilitaires                                                                  #
# --------------------------------------------------------------------------- #

function Write-Step {
    param([string] $Message)
    $script:StepNo++
    Write-Host ''
    Write-Host ("[{0}] {1}" -f $script:StepNo, $Message) -ForegroundColor Cyan
    Write-Host ('-' * 74) -ForegroundColor DarkGray
}
function Write-Ok   { param([string] $m) Write-Host "    OK    $m" -ForegroundColor Green }
function Write-Info { param([string] $m) Write-Host "          $m" -ForegroundColor Gray }
function Write-Fail { param([string] $m) Write-Host "    ECHEC $m" -ForegroundColor Red }
function Write-Warn {
    param([string] $m)
    Write-Host "    ATTN  $m" -ForegroundColor Yellow
    $script:Warnings += $m
}

function New-RandomPassword {
    param([int] $Length = 24)
    # Alphanumerique strict : evite tout probleme d'echappement en SQL,
    # dans odoo.conf (configparser) et sur la ligne de commande.
    $chars = 'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    -join (1..$Length | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
}

function Test-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Update-SessionPath {
    # winget modifie le PATH machine/utilisateur, pas celui du processus courant.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
}

function Invoke-Native {
    <#  Execute un programme externe, relaie sa sortie vers la console et leve une
        exception si le code de retour n'est pas nul.
        N'ecrit jamais dans le pipeline : le code de sortie est expose via
        $script:NativeExitCode, afin de ne pas polluer la valeur de retour des
        fonctions appelantes. #>
    param(
        [Parameter(Mandatory)] [string]   $FilePath,
        [Parameter(Mandatory)] [string[]] $Arguments,
        [string] $ErrorMessage,
        [switch] $IgnoreExitCode,
        [switch] $Quiet
    )
    # Windows PowerShell 5.1 convertit chaque ligne de stderr d'une commande
    # native en ErrorRecord : avec ErrorActionPreference = 'Stop', un simple
    # avertissement de pip suffirait a interrompre l'installation. On neutralise
    # la preference le temps de l'appel, et on juge sur le code de sortie.
    $previousEap = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($Quiet) {
            & $FilePath @Arguments *> $null
        } else {
            & $FilePath @Arguments 2>&1 |
                ForEach-Object { Write-Host "          $_" -ForegroundColor DarkGray }
        }
        $script:NativeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousEap
    }
    if (-not $IgnoreExitCode -and $script:NativeExitCode -ne 0) {
        $msg = if ($ErrorMessage) { $ErrorMessage } else { "$FilePath a echoue" }
        throw "$msg (code de sortie $script:NativeExitCode)."
    }
}

function Test-WingetPackage {
    param([string] $Id)
    & winget.exe show --id $Id --exact --source winget --disable-interactivity *> $null
    return ($LASTEXITCODE -eq 0)
}

function Test-LongPathSupport {
    <#  Windows limite historiquement un chemin a 260 caracteres (MAX_PATH).
        Le chemin relatif le plus long de ce depot mesure 164 caracteres
        (addons\account_edi_ubl_cii\tests\test_files\...). Une racine de projet
        un peu profonde suffit donc a depasser la limite, et les erreurs qui en
        decoulent (fichiers d'addons introuvables, pip qui echoue a extraire une
        archive) sont particulierement obscures.

        Python 3.6+ est declare "long path aware" : activer le parametre systeme
        LongPathsEnabled suffit a lever la limite pour Odoo comme pour pip. #>
    $longestRelative = 164
    $margin = 260 - $Root.Length - $longestRelative

    $regPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem'
    $enabled = 0
    try {
        $enabled = [int] (Get-ItemProperty -Path $regPath -Name 'LongPathsEnabled' `
                          -ErrorAction Stop).LongPathsEnabled
    } catch {
        # Valeur absente sur les installations plus anciennes : equivaut a 0.
    }

    if ($enabled -eq 1) {
        Write-Ok 'Chemins longs actives (LongPathsEnabled = 1)'
        return
    }
    if ($margin -ge 20) {
        Write-Ok ("Longueur des chemins acceptable (marge de $margin caracteres " +
                  'sous la limite de 260)')
        return
    }

    $message = ("La racine du projet occupe $($Root.Length) caracteres ; le chemin " +
                "le plus long du depot en ajoute $longestRelative, soit " +
                "$($Root.Length + $longestRelative) sur 260 autorises.")
    if ($CheckOnly -or -not $script:IsAdmin) {
        Write-Warn ($message + ' Activez les chemins longs, ou deplacez le projet ' +
                    'vers un dossier plus court comme C:\odoo.')
        return
    }

    Write-Info $message
    Write-Info 'Activation du support des chemins longs de Windows...'
    Set-ItemProperty -Path $regPath -Name 'LongPathsEnabled' -Value 1 -Type DWord
    Write-Ok 'LongPathsEnabled = 1 (parametre systeme)'
    Write-Info ('Pour revenir en arriere : Set-ItemProperty -Path ' +
                "'$regPath' -Name LongPathsEnabled -Value 0")
    Write-Warn ('Les chemins longs ne prennent effet que pour les processus ' +
                'demarres ensuite. Si l''installation echoue sur un fichier ' +
                'introuvable, redemarrez Windows et relancez le script.')
}

function Invoke-SelfElevation {
    <#  Relance ce script dans une console elevee et renvoie $true si une relance
        a eu lieu.

        $BoundParameters doit recevoir le $PSBoundParameters *du script* : a
        l'interieur d'une fonction, $PSBoundParameters designe les parametres de
        la fonction elle-meme, et les options fournies par l'utilisateur seraient
        silencieusement perdues lors de la relance.

        Les elements de -ArgumentList ne sont pas cites par PowerShell : chaque
        valeur est donc entouree de guillemets explicitement, faute de quoi un
        chemin contenant une espace (ici "odoo saas") serait coupe en deux. #>
    param([hashtable] $BoundParameters = @{})

    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit',
                 '-File', """$PSCommandPath""")
    foreach ($kv in $BoundParameters.GetEnumerator()) {
        if ($kv.Key -eq 'NoElevate') { continue }
        if ($kv.Value -is [switch]) {
            if ($kv.Value.IsPresent) { $argList += "-$($kv.Key)" }
        } else {
            $argList += "-$($kv.Key)"
            $argList += """$($kv.Value)"""
        }
    }
    Write-Host ''
    Write-Host '  Privileges administrateur requis : ouverture d''une console elevee.' -ForegroundColor Yellow
    Write-Host '  Acceptez l''invite du controle de compte d''utilisateur (UAC).' -ForegroundColor Yellow
    Write-Host '  L''installation se poursuit dans la nouvelle fenetre.' -ForegroundColor Yellow
    Write-Host ''
    try {
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $argList
        return $true
    } catch {
        Write-Host "  Elevation refusee ou impossible : $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# --------------------------------------------------------------------------- #
# Etape 1 : prerequis systeme                                                  #
# --------------------------------------------------------------------------- #

function Test-Prerequisites {
    Write-Step 'Verification des prerequis systeme'

    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'Odoo requiert un Windows 64 bits. Systeme 32 bits detecte.'
    }
    Write-Ok "Windows 64 bits : $([Environment]::OSVersion.VersionString)"

    if (-not (Test-Path $ReqFile)) {
        throw ("requirements.txt introuvable dans '$Root'. " +
               'Lancez ce script depuis le dossier windows\ du projet Odoo.')
    }
    if (-not (Test-Path $OdooBin)) { throw "odoo-bin introuvable dans '$Root'." }
    Write-Ok "Sources Odoo detectees : $Root"

    if ($Root -match '[^\x20-\x7E]') {
        Write-Warn ('Le chemin du projet contient des caracteres non ASCII. ' +
                    "Certaines dependances Python s'en accommodent mal ; " +
                    'en cas de probleme, deplacez le projet vers C:\odoo.')
    }

    $script:IsAdmin = Test-Administrator
    if ($script:IsAdmin) {
        Write-Ok 'Privileges administrateur presents'
    } elseif ($CheckOnly) {
        Write-Info 'Privileges administrateur absents (sans effet en mode -CheckOnly)'
    } else {
        throw ('Privileges administrateur requis pour installer Python, PostgreSQL ' +
               'et wkhtmltopdf.' + [Environment]::NewLine +
               '  Relancez via windows\install-odoo.bat, ou depuis un PowerShell ' +
               'ouvert en tant qu''administrateur.')
    }

    $script:HasWinget = [bool] (Get-Command winget.exe -ErrorAction SilentlyContinue)
    if ($script:HasWinget) {
        Write-Ok "winget disponible : $((& winget.exe --version) -join '')"
    } else {
        Write-Warn ('winget est absent. Installez "App Installer" depuis le Microsoft ' +
                    'Store, ou installez manuellement Python 3.12, PostgreSQL et ' +
                    'wkhtmltopdf (voir INSTALL-WINDOWS.md).')
    }

    # Apres le controle des privileges : Test-LongPathSupport ne modifie le
    # registre que si $script:IsAdmin est vrai.
    Test-LongPathSupport
}

# --------------------------------------------------------------------------- #
# Etape 2 : Python 3.12                                                        #
# --------------------------------------------------------------------------- #

function Find-Python312 {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $exe = & py.exe "-$PythonSeries" -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return "$exe".Trim() }
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "${env:ProgramFiles(x86)}\Python312\python.exe",
        'C:\Python312\python.exe'
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }

    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        $v = & $cmd.Source -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
        if ($LASTEXITCODE -eq 0 -and "$v".Trim() -eq $PythonSeries) { return $cmd.Source }
    }
    return $null
}

function Install-Python {
    Write-Step "Python $PythonSeries"

    $python = Find-Python312
    if ($python) {
        $full = "$(& $python -c 'import sys; print(sys.version.split()[0])')".Trim()
        $arch = "$(& $python -c 'import struct; print(struct.calcsize(""P"") * 8)')".Trim()
        if ($arch -ne '64') {
            throw "Python trouve en $arch bits ($python). Odoo requiert un Python 64 bits."
        }
        Write-Ok "Python $full (64 bits) : $python"
        return $python
    }

    if ($CheckOnly) { Write-Fail "Python $PythonSeries absent"; return $null }
    if (-not $script:HasWinget) {
        throw ("Python $PythonSeries est absent et winget indisponible. Installez-le " +
               'depuis https://www.python.org/downloads/windows/ (Windows installer ' +
               '64-bit, serie 3.12), puis relancez ce script.')
    }

    Write-Info "Installation de Python $PythonSeries via winget..."
    Invoke-Native -FilePath 'winget.exe' -Arguments @(
        'install', '--id', $PythonWingetId, '--exact', '--source', 'winget',
        '--scope', 'machine', '--silent',
        '--accept-package-agreements', '--accept-source-agreements'
    ) -ErrorMessage "L'installation de Python $PythonSeries a echoue"

    Update-SessionPath
    $python = Find-Python312
    if (-not $python) {
        throw ("Python $PythonSeries a ete installe mais reste introuvable. " +
               'Fermez puis rouvrez PowerShell, et relancez le script.')
    }
    Write-Ok "Python installe : $python"
    return $python
}

# --------------------------------------------------------------------------- #
# Etape 3 : PostgreSQL                                                         #
# --------------------------------------------------------------------------- #

function Find-PgBin {
    $dirs = @()
    foreach ($base in @("$env:ProgramFiles\PostgreSQL", "${env:ProgramFiles(x86)}\PostgreSQL")) {
        if (Test-Path $base) {
            $dirs += Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
                     Sort-Object { [int] ($_.Name -replace '\D', '') } -Descending |
                     ForEach-Object { Join-Path $_.FullName 'bin' }
        }
    }
    $cmd = Get-Command psql.exe -ErrorAction SilentlyContinue
    if ($cmd) { $dirs += Split-Path $cmd.Source }
    foreach ($d in $dirs) { if (Test-Path (Join-Path $d 'psql.exe')) { return $d } }
    return $null
}

function Get-PgMajorVersion {
    param([string] $PgBin)
    $out = "$(& (Join-Path $PgBin 'psql.exe') --version 2>$null)"
    if ($out -match '(\d+)\.') { return [int] $Matches[1] }
    return 0
}

function Install-PostgreSQL {
    Write-Step 'PostgreSQL'

    if ($SkipPostgres) { Write-Info 'Ignore (-SkipPostgres).'; return $null }

    $pgBin = Find-PgBin
    if ($pgBin) {
        $major = Get-PgMajorVersion $pgBin
        if ($major -lt $MinPgVersion) {
            Write-Warn ("PostgreSQL $major detecte, or odoo/release.py exige " +
                        ">= $MinPgVersion. Odoo emettra un avertissement et " +
                        'certaines fonctionnalites peuvent echouer.')
        }
        Write-Ok "PostgreSQL $major : $pgBin"
        return $pgBin
    }

    if ($CheckOnly) { Write-Fail 'PostgreSQL absent'; return $null }
    if (-not $script:HasWinget) {
        throw ('PostgreSQL est absent et winget indisponible. Installez PostgreSQL ' +
               ">= $MinPgVersion depuis https://www.postgresql.org/download/windows/, " +
               'puis relancez avec -PostgresSuperPassword.')
    }

    # L'identifiant winget est versionne : on essaie la version demandee, puis les
    # autres versions supportees, de la plus recente a la plus ancienne.
    $ids = @("PostgreSQL.PostgreSQL.$PostgresVersion") +
           (@('18', '17', '16') | Where-Object { $_ -ne $PostgresVersion } |
            ForEach-Object { "PostgreSQL.PostgreSQL.$_" })

    $chosen = $null
    foreach ($id in $ids) {
        Write-Info "Recherche du paquet $id..."
        if (Test-WingetPackage $id) { $chosen = $id; break }
    }
    if (-not $chosen) {
        throw ('Aucun paquet PostgreSQL trouve dans winget. Installez PostgreSQL ' +
               'manuellement depuis https://www.postgresql.org/download/windows/.')
    }

    Write-Info "Installation de $chosen (plusieurs minutes)..."
    # L'installeur EDB exige --superpassword en mode silencieux : sans lui,
    # l'installation echoue sans message exploitable.
    $custom = "--serverport $DbPort --superpassword `"$($script:PgSuperPassword)`""
    Invoke-Native -FilePath 'winget.exe' -Arguments @(
        'install', '--id', $chosen, '--exact', '--source', 'winget', '--silent',
        '--accept-package-agreements', '--accept-source-agreements',
        '--custom', $custom
    ) -ErrorMessage "L'installation de $chosen a echoue"

    Update-SessionPath
    $pgBin = Find-PgBin
    if (-not $pgBin) {
        throw ('PostgreSQL a ete installe mais psql.exe reste introuvable. ' +
               'Fermez puis rouvrez PowerShell, et relancez le script.')
    }
    Write-Ok "PostgreSQL installe : $pgBin"
    return $pgBin
}

function Start-PostgresService {
    $svc = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $svc) {
        Write-Warn 'Service PostgreSQL introuvable : etat du serveur non verifiable.'
        return
    }
    if ($svc.Status -ne 'Running') {
        Write-Info "Demarrage du service $($svc.Name)..."
        Start-Service $svc.Name
        $svc.WaitForStatus('Running', '00:00:30')
    }
    Write-Ok "Service $($svc.Name) : $((Get-Service $svc.Name).Status)"
}

function Initialize-Database {
    param([string] $PgBin)

    Write-Step "Role PostgreSQL '$DbUser'"

    if (-not $PgBin) { Write-Info 'Ignore : PostgreSQL indisponible.'; return }
    if ($CheckOnly)  { Write-Info 'Ignore (-CheckOnly).'; return }

    Start-PostgresService

    if (-not $script:PgSuperPassword) {
        Write-Host ''
        Write-Host '    PostgreSQL etait deja installe. Le mot de passe du superutilisateur' -ForegroundColor Yellow
        Write-Host '    "postgres" est necessaire pour creer le role applicatif Odoo.' -ForegroundColor Yellow
        $secure = Read-Host '    Mot de passe de postgres' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $script:PgSuperPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }

    # Les mots de passe generes sont alphanumeriques, mais un mot de passe fourni
    # par l'utilisateur peut contenir une apostrophe : on la double pour SQL.
    $escaped = $DbPassword -replace "'", "''"
    $sql = @"
DO
`$do`$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$DbUser') THEN
        ALTER ROLE "$DbUser" WITH LOGIN CREATEDB PASSWORD '$escaped';
    ELSE
        CREATE ROLE "$DbUser" WITH LOGIN CREATEDB PASSWORD '$escaped';
    END IF;
END
`$do`$;
"@

    $sqlFile = Join-Path $env:TEMP ("odoo-role-{0}.sql" -f [guid]::NewGuid().ToString('N'))
    # Sans BOM : psql lit le fichier en UTF-8 et un BOM provoquerait une erreur de syntaxe.
    [IO.File]::WriteAllText($sqlFile, $sql, (New-Object Text.UTF8Encoding($false)))

    $previousPgPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $script:PgSuperPassword
        Invoke-Native -FilePath (Join-Path $PgBin 'psql.exe') -Arguments @(
            '--username', 'postgres', '--host', $DbHost, '--port', "$DbPort",
            '--dbname', 'postgres', '--no-password',
            '--set', 'ON_ERROR_STOP=1', '--file', $sqlFile
        ) -ErrorMessage ("Creation du role '$DbUser' impossible. Verifiez le mot de " +
                         'passe du superutilisateur postgres')
        Write-Ok "Role '$DbUser' pret (LOGIN, CREATEDB)"
        Write-Info "La base '$DbName' sera creee par Odoo au premier demarrage."
    } finally {
        $env:PGPASSWORD = $previousPgPassword
        Remove-Item $sqlFile -Force -ErrorAction SilentlyContinue
    }
}

# --------------------------------------------------------------------------- #
# Etape 4 : wkhtmltopdf                                                        #
# --------------------------------------------------------------------------- #

function Find-Wkhtmltopdf {
    $cmd = Get-Command wkhtmltopdf.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @("$env:ProgramFiles\wkhtmltopdf\bin\wkhtmltopdf.exe",
                     "${env:ProgramFiles(x86)}\wkhtmltopdf\bin\wkhtmltopdf.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Install-Wkhtmltopdf {
    Write-Step 'wkhtmltopdf (rapports PDF)'

    if ($SkipWkhtmltopdf) { Write-Info 'Ignore (-SkipWkhtmltopdf).'; return }

    $exe = Find-Wkhtmltopdf
    if (-not $exe -and -not $CheckOnly -and $script:HasWinget) {
        Write-Info 'Installation de wkhtmltopdf via winget...'
        # Non bloquant : Odoo demarre sans wkhtmltopdf, seuls les PDF sont degrades.
        Invoke-Native -FilePath 'winget.exe' -Arguments @(
            'install', '--id', 'wkhtmltopdf.wkhtmltopdf', '--exact', '--source', 'winget',
            '--silent', '--accept-package-agreements', '--accept-source-agreements'
        ) -IgnoreExitCode
        if ($script:NativeExitCode -ne 0) {
            Write-Warn ('Installation de wkhtmltopdf echouee. Les rapports PDF seront ' +
                        'rendus en HTML. Installez la version 0.12.6 depuis ' +
                        'https://wkhtmltopdf.org/downloads.html.')
            return
        }
        Update-SessionPath
        $exe = Find-Wkhtmltopdf
    }

    if (-not $exe) {
        Write-Warn ('wkhtmltopdf absent : Odoo fonctionnera, mais les rapports PDF ' +
                    'seront degrades en HTML.')
        return
    }

    $version = "$(& $exe --version 2>$null)".Trim()
    Write-Ok "wkhtmltopdf : $exe"
    if ($version) { Write-Info $version }
    if ($version -and $version -notmatch '0\.12\.6') {
        Write-Warn ('Odoo recommande wkhtmltopdf 0.12.6 (build avec Qt patche). ' +
                    'Les autres versions rendent mal les en-tetes et pieds de page.')
    }

    # Odoo localise wkhtmltopdf via le PATH.
    $binDir = Split-Path $exe
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    if (($machinePath -split ';') -notcontains $binDir) {
        if ($CheckOnly -or -not $script:IsAdmin) {
            Write-Warn "$binDir n'est pas dans le PATH machine."
        } else {
            [Environment]::SetEnvironmentVariable(
                'Path', ($machinePath.TrimEnd(';') + ';' + $binDir), 'Machine')
            Update-SessionPath
            Write-Ok "$binDir ajoute au PATH machine"
        }
    }
}

# --------------------------------------------------------------------------- #
# Etape 5 : environnement virtuel et dependances                               #
# --------------------------------------------------------------------------- #

function Install-VirtualEnv {
    param([string] $Python)

    Write-Step "Environnement virtuel $VenvName"

    if ($CheckOnly) {
        if (Test-Path $VenvPy) { Write-Ok "Present : $VenvPath" }
        else { Write-Fail "Absent : $VenvPath" }
        return
    }
    if (-not $Python) { throw 'Python introuvable : creation du venv impossible.' }

    if ((Test-Path $VenvPath) -and $Force) {
        Write-Info 'Suppression du venv existant (-Force)...'
        Remove-Item $VenvPath -Recurse -Force
    }

    if (Test-Path $VenvPy) {
        Write-Ok "Venv deja present : $VenvPath"
    } else {
        if (Test-Path $VenvPath) {
            # Dossier present sans Scripts\python.exe : venv corrompu, ou copie
            # depuis macOS/Linux. Un venv est reconstructible : suppression sure.
            Write-Warn "'$VenvPath' existe sans Scripts\python.exe ; recreation."
            Remove-Item $VenvPath -Recurse -Force
        }
        Write-Info 'Creation du venv...'
        Invoke-Native -FilePath $Python -Arguments @('-m', 'venv', $VenvPath) `
            -ErrorMessage 'Creation du venv impossible' -Quiet
        Write-Ok "Venv cree : $VenvPath"
    }

    Write-Info 'Mise a jour de pip, setuptools et wheel...'
    # setuptools est indispensable : sous Windows, ofxparse, vobject et rjsmin
    # ne sont distribues qu'en sdist et sont construits localement.
    Invoke-Native -FilePath $VenvPy -Arguments @(
        '-m', 'pip', 'install', '--upgrade', '--quiet', 'pip', 'setuptools', 'wheel'
    ) -ErrorMessage 'Mise a jour de pip impossible'
    Write-Ok "pip : $("$(& $VenvPy -m pip --version)".Trim())"

    Write-Info 'Installation des dependances de requirements.txt (plusieurs minutes)...'
    Write-Info 'Les marqueurs sys_platform du fichier excluent automatiquement gevent,'
    Write-Info 'greenlet, python-ldap et python-magic, indisponibles sous Windows.'
    Invoke-Native -FilePath $VenvPy -Arguments @(
        '-m', 'pip', 'install', '--requirement', $ReqFile
    ) -ErrorMessage ('Installation des dependances echouee. Consultez la section ' +
                     'Depannage de INSTALL-WINDOWS.md')
    Write-Ok 'Dependances installees'

    Repair-PyWin32
}

function Repair-PyWin32 {
    <#  odoo/service/server.py execute "import win32api" quand os.name == 'nt'.
        Les DLL de pywin32 ne sont pas toujours visibles dans un venv :
        pywin32_postinstall.py les enregistre. #>
    & $VenvPy -c 'import win32api' *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok 'win32api importable (requis par Odoo sous Windows)'
        return
    }
    Write-Info 'Reparation de pywin32 (enregistrement des DLL)...'
    $postInstall = Join-Path $VenvPath 'Scripts\pywin32_postinstall.py'
    if (Test-Path $postInstall) {
        Invoke-Native -FilePath $VenvPy -Arguments @($postInstall, '-install', '-silent') `
            -IgnoreExitCode -Quiet
    }
    & $VenvPy -c 'import win32api' *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok 'win32api importable apres reparation'
    } else {
        Write-Warn ('win32api reste inimportable : Odoo refusera de demarrer. ' +
                    "Essayez : `"$VenvPy`" -m pip install --force-reinstall pywin32")
    }
}

# --------------------------------------------------------------------------- #
# Etape 6 : odoo.conf                                                          #
# --------------------------------------------------------------------------- #

function Write-OdooConf {
    Write-Step 'Fichier de configuration odoo.conf'

    if ($CheckOnly) {
        if (Test-Path $ConfPath) { Write-Ok "Present : $ConfPath" }
        else { Write-Fail "Absent : $ConfPath" }
        return
    }

    if (Test-Path $ConfPath) {
        $backup = '{0}.bak-{1:yyyyMMdd-HHmmss}' -f $ConfPath, (Get-Date)
        Copy-Item $ConfPath $backup
        Write-Info "Configuration existante sauvegardee : $(Split-Path -Leaf $backup)"
    }

    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    New-Item -ItemType Directory -Force -Path $LogDir  | Out-Null

    $interface = if ($ListenOnAllInterfaces) { '0.0.0.0' } else { '127.0.0.1' }
    $logFile   = Join-Path $LogDir 'odoo.log'
    $stamp     = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    # Options volontairement absentes : workers, gevent_workers, limit_time_cpu,
    # limit_memory_soft, limit_memory_hard, limit_request. Ce sont des
    # PosixOnlyOption (odoo/tools/config.py) : sous Windows, Odoo les ignore
    # silencieusement. Le serveur tourne donc en mode multi-thread, sans prefork.
    $conf = @"
[options]
; Genere par windows\Install-Odoo.ps1 le $stamp
; Ne pas versionner : ce fichier contient des mots de passe en clair.

; --- Chemins ---------------------------------------------------------------
; Absolus : un service Windows ne partage pas le repertoire courant.
addons_path = $AddonsDir
data_dir = $DataDir

; --- Base de donnees -------------------------------------------------------
db_host = $DbHost
db_port = $DbPort
db_user = $DbUser
db_password = $DbPassword
db_name = $DbName

; --- Serveur HTTP ----------------------------------------------------------
http_port = $HttpPort
http_interface = $interface

; --- Gestionnaire de bases de donnees --------------------------------------
; admin_passwd protege la creation, la duplication et la suppression de bases.
admin_passwd = $MasterPassword
; Passer a False en production pour masquer /web/database/manager.
list_db = True

; --- Journalisation --------------------------------------------------------
logfile = $logFile
log_level = info

; --- Limites ---------------------------------------------------------------
; limit_time_cpu et limit_memory_* sont des options POSIX, ignorees par Odoo
; sous Windows. Seul limit_time_real s'applique ici.
limit_time_real = 1200
"@

    [IO.File]::WriteAllText($ConfPath, $conf, (New-Object Text.UTF8Encoding($false)))
    Write-Ok "Ecrit : $ConfPath"

    # Le fichier contient le mot de passe de la base et le mot de passe maitre.
    try {
        $acl = Get-Acl $ConfPath
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($rule in @($acl.Access)) { $acl.RemoveAccessRule($rule) | Out-Null }
        foreach ($who in @([Security.Principal.WindowsIdentity]::GetCurrent().Name,
                           'BUILTIN\Administrators', 'NT AUTHORITY\SYSTEM')) {
            $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
                $who, 'FullControl', 'Allow')))
        }
        Set-Acl -Path $ConfPath -AclObject $acl
        Write-Ok 'Permissions restreintes (mots de passe en clair dans le fichier)'
    } catch {
        Write-Warn "Restriction des permissions de odoo.conf impossible : $($_.Exception.Message)"
    }
}

# --------------------------------------------------------------------------- #
# Etape 7 : verification                                                       #
# --------------------------------------------------------------------------- #

function Test-Installation {
    Write-Step 'Verification de l''installation'

    if (-not (Test-Path $VenvPy)) {
        Write-Fail 'Venv absent : verification impossible.'
        return $false
    }

    $ok = $true

    # odoo-bin et la sonde psycopg2 ecrivent sur stderr. Sous Windows PowerShell
    # 5.1, "2>&1" transformerait ces lignes en erreurs fatales tant que
    # ErrorActionPreference vaut 'Stop' : on juge sur le code de sortie.
    $previousEap = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'

        $version = & $VenvPy $OdooBin --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "odoo-bin --version : $(($version -join ' ').Trim())"
        } else {
            Write-Fail "odoo-bin --version a echoue : $(($version -join ' ').Trim())"
            $ok = $false
        }

        # sass = libsass, PIL = Pillow, win32api = pywin32 (requis sous Windows).
        # vobject, ofxparse et rjsmin sont les trois paquets construits depuis une
        # archive source : on verifie explicitement qu'ils sont utilisables.
        foreach ($mod in @('psycopg2', 'lxml', 'PIL', 'reportlab', 'sass',
                           'rjsmin', 'vobject', 'ofxparse', 'win32api')) {
            # *> et non 2> : stdout doit aussi etre ecarte, sans quoi la
            # sortie d'un module polluerait la valeur de retour booleenne.
            & $VenvPy -c "import $mod" *> $null
            if ($LASTEXITCODE -eq 0) { Write-Ok "import $mod" }
            else { Write-Fail "import $mod"; $ok = $false }
        }

        if (-not $CheckOnly -and -not $SkipPostgres) {
            # Connexion reelle avec les identifiants ecrits dans odoo.conf : c'est
            # le seul moyen de valider role, mot de passe et pg_hba.conf.
            $probe = @"
import sys, psycopg2
try:
    c = psycopg2.connect(host=r'''$DbHost''', port=$DbPort,
                         user=r'''$DbUser''', password=r'''$DbPassword''',
                         dbname='postgres', connect_timeout=10)
    print(c.get_parameter_status('server_version'))
    c.close()
except Exception as exc:
    print('ERREUR: %s' % exc, file=sys.stderr)
    sys.exit(1)
"@
            $out = $probe | & $VenvPy - 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Ok ("Connexion PostgreSQL reussie en tant que '$DbUser' " +
                          "(serveur $(($out -join '').Trim()))")
            } else {
                Write-Fail "Connexion PostgreSQL echouee : $(($out -join ' ').Trim())"
                $ok = $false
            }
        }
    } finally {
        $ErrorActionPreference = $previousEap
    }

    return $ok
}

# --------------------------------------------------------------------------- #
# Programme principal                                                          #
# --------------------------------------------------------------------------- #

Write-Host ''
Write-Host '===========================================================================' -ForegroundColor White
Write-Host "  Installation d'Odoo saas~19.2 sur Windows" -ForegroundColor White
Write-Host '===========================================================================' -ForegroundColor White
if ($CheckOnly) {
    Write-Host '  Mode diagnostic : aucune modification ne sera effectuee.' -ForegroundColor Yellow
}

# L'installation de Python, PostgreSQL et wkhtmltopdf requiert une elevation.
# Le mode diagnostic, lui, fonctionne sans privileges particuliers.
if (-not $CheckOnly -and -not $NoElevate -and -not (Test-Administrator)) {
    if (Invoke-SelfElevation -BoundParameters $PSBoundParameters) { exit 0 }
}

$generatedDbPassword   = -not $DbPassword
$generatedMasterPasswd = -not $MasterPassword
if ($generatedDbPassword)   { $DbPassword     = New-RandomPassword }
if ($generatedMasterPasswd) { $MasterPassword = New-RandomPassword }
$script:PgSuperPassword = $PostgresSuperPassword

try {
    Test-Prerequisites

    # PostgreSQL absent : l'installeur EDB exige un mot de passe superutilisateur.
    if (-not $SkipPostgres -and -not $CheckOnly -and
        -not (Find-PgBin) -and -not $script:PgSuperPassword) {
        $script:PgSuperPassword = New-RandomPassword
        $script:GeneratedPgPassword = $true
    }

    $python = Install-Python
    $pgBin  = Install-PostgreSQL
    Install-Wkhtmltopdf
    Install-VirtualEnv -Python $python
    Initialize-Database -PgBin $pgBin
    Write-OdooConf
    $verified = Test-Installation

    Write-Host ''
    Write-Host '===========================================================================' -ForegroundColor White
    if ($CheckOnly) {
        Write-Host '  Diagnostic termine' -ForegroundColor White
    } elseif ($verified) {
        Write-Host '  Installation terminee avec succes' -ForegroundColor Green
    } else {
        Write-Host '  Installation terminee avec des erreurs (voir ci-dessus)' -ForegroundColor Red
    }
    Write-Host '===========================================================================' -ForegroundColor White

    if (-not $CheckOnly) {
        Write-Host ''
        Write-Host '  Identifiants - conservez-les :' -ForegroundColor Yellow
        Write-Host ''
        if ($script:GeneratedPgPassword) {
            Write-Host "    Superutilisateur PostgreSQL   postgres / $($script:PgSuperPassword)"
        }
        Write-Host ("    Role Odoo                     {0} / {1}{2}" -f `
                    $DbUser, $DbPassword, $(if ($generatedDbPassword) { '' } else { '   (fourni)' }))
        Write-Host ("    Mot de passe maitre Odoo      {0}{1}" -f `
                    $MasterPassword, $(if ($generatedMasterPasswd) { '' } else { '   (fourni)' }))
        Write-Host ''
        Write-Host "    Ces valeurs figurent egalement dans $ConfPath" -ForegroundColor Gray
        Write-Host ''
        Write-Host '  Etape suivante :' -ForegroundColor Yellow
        Write-Host ''
        Write-Host '    .\windows\Start-Odoo.ps1 -Open'
        Write-Host '      ou double-cliquez sur windows\start-odoo.bat'
        Write-Host ''
        Write-Host "    Puis ouvrez http://localhost:$HttpPort et creez la base '$DbName'"
        Write-Host '    avec le mot de passe maitre ci-dessus.'
        Write-Host ''
        Write-Host '  Pour executer Odoo en tant que service Windows :' -ForegroundColor Yellow
        Write-Host '    .\windows\Install-Service.ps1'
    }

    if ($script:Warnings.Count) {
        Write-Host ''
        Write-Host "  $($script:Warnings.Count) avertissement(s) :" -ForegroundColor Yellow
        foreach ($w in $script:Warnings) { Write-Host "    - $w" -ForegroundColor Yellow }
    }
    Write-Host ''

    if (-not $CheckOnly -and -not $verified) { exit 1 }
    exit 0

} catch {
    Write-Host ''
    Write-Host '===========================================================================' -ForegroundColor Red
    Write-Host '  Installation interrompue' -ForegroundColor Red
    Write-Host '===========================================================================' -ForegroundColor Red
    Write-Host ''
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ''
    Write-Host '  Consultez la section Depannage de INSTALL-WINDOWS.md.' -ForegroundColor Gray
    Write-Host ''
    exit 1
}
