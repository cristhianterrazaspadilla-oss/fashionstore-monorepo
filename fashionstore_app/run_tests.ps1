[CmdletBinding()]
param(
    [ValidateSet('all', 'unit', 'widget')]
    [string]$Suite = 'all',

    # Timeout de seguridad para la fase de ejecucion de pruebas (por defecto 180s).
    [int]$TimeoutSeconds = 180,

    # Timeout de seguridad independiente para el analisis estatico (por defecto 120s).
    # Protege contra la latencia de escaneo de Windows Defender y compiladores en Windows
    # para que una prueba focalizada (ej. -Suite unit -TimeoutSeconds 45) no agote el tiempo
    # prematuramente en la fase previa de analisis estatico.
    [int]$AnalyzeTimeoutSeconds = 120,

    # Opcion para omitir el analisis estatico si solo se requiere verificar la suite de pruebas.
    [switch]$SkipAnalyze
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  FashionStore Movil -- Runner Reproducible de Verificacion" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Directorio base:        $PSScriptRoot"
Write-Host "Fecha y hora:           $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Suite a probar:         $Suite"
Write-Host "Timeout pruebas:        ${TimeoutSeconds}s"
Write-Host "Timeout analisis:       ${AnalyzeTimeoutSeconds}s"
if ($SkipAnalyze) {
    Write-Host "Analisis estatico:      Omitido (-SkipAnalyze activo)" -ForegroundColor DarkGray
}
if ($Suite -eq 'all' -and $TimeoutSeconds -lt 150) {
    Write-Warning "El timeout de pruebas configurado (${TimeoutSeconds}s) es inferior a 150s para la suite completa ('all'). En Windows (arranque en frio con escaneo antivirus y 44 archivos/239 pruebas), la ejecucion total requiere ~130s. Si se interrumpe prematuramente con Exit 124, utilice el comando supervisado (-TimeoutSeconds 180) o suites focalizadas (-Suite unit / -Suite widget)."
}
Write-Host ""

# Helper para ejecucion con timeout real via System.Diagnostics.Process, terminacion limpia del arbol y heartbeat
function Invoke-FlutterWithTimeout {
    param(
        [string[]]$ArgumentList,
        [int]$TimeoutSec,
        [string]$Description
    )

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/c flutter.bat " + ($ArgumentList -join ' ')
    $psi.WorkingDirectory = $PSScriptRoot
    $psi.UseShellExecute = $false

    $p = [System.Diagnostics.Process]::Start($psi)
    Write-Host "  -> Proceso PID $($p.Id) iniciado. Monitoreando (limite: ${TimeoutSec}s)..." -ForegroundColor DarkCyan

    $lastReport = 0
    while (-not $p.HasExited -and $sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        Start-Sleep -Milliseconds 1000
        $currentSec = [int]$sw.Elapsed.TotalSeconds
        if ($currentSec -ge 5 -and ($currentSec - $lastReport) -ge 5 -and -not $p.HasExited) {
            $lastReport = $currentSec
            Write-Host "     [Activo: $Description - ${currentSec}s transcurridos...]" -ForegroundColor DarkGray
        }
    }

    $finished = $p.HasExited
    if ($finished) {
        $p.WaitForExit()
    }
    $sw.Stop()
    $elapsedSec = [Math]::Round($sw.Elapsed.TotalSeconds, 2)

    if (-not $finished) {
        Write-Host ""
        Write-Host "  [TIMEOUT] $Description excedio el limite de seguridad de ${TimeoutSec}s. Terminando arbol de procesos..." -ForegroundColor Red
        try {
            & taskkill.exe /PID $p.Id /T /F 2>$null | Out-Null
        } catch {
            try { $p.Kill() } catch {}
        }
        return @{
            ExitCode = 124
            ElapsedSeconds = $elapsedSec
            TimedOut = $true
        }
    }

    return @{
        ExitCode = $p.ExitCode
        ElapsedSeconds = $elapsedSec
        TimedOut = $false
    }
}

# 1. Verificacion previa del entorno y configuracion de paquetes
Write-Host "[1/3] Verificando entorno Flutter..." -ForegroundColor Yellow

$flutterCmd = Get-Command flutter -ErrorAction SilentlyContinue
if (-not $flutterCmd) {
    Write-Error "No se encontro el comando 'flutter' en el PATH."
    exit 1
}

$pkgConfig = Join-Path $PSScriptRoot ".dart_tool\package_config.json"
if (-not (Test-Path $pkgConfig)) {
    Write-Warning "No se encontro .dart_tool\package_config.json. Ejecutando 'flutter pub get --offline'..."
    & flutter.bat pub get --offline
}

Write-Host "  -> Entorno verificado y listo." -ForegroundColor Green
Write-Host ""

# 2. Analisis estatico
$analyzeExit = 0
$analyzeTime = 0.0

if (-not $SkipAnalyze) {
    Write-Host "[2/3] Ejecutando analisis estatico (flutter analyze --no-pub)..." -ForegroundColor Yellow
    Write-Host "  Nota: Timeout asignado de ${AnalyzeTimeoutSeconds}s para absorber latencia de antivirus en Windows." -ForegroundColor DarkGray

    $resAnalyze = Invoke-FlutterWithTimeout -ArgumentList @('analyze', '--no-pub') -TimeoutSec $AnalyzeTimeoutSeconds -Description "flutter analyze --no-pub"
    $analyzeExit = $resAnalyze.ExitCode
    $analyzeTime = $resAnalyze.ElapsedSeconds

    if ($analyzeExit -ne 0) {
        Write-Host "  [FALLO] flutter analyze reporto errores en ${analyzeTime}s (Exit code: $analyzeExit)" -ForegroundColor Red
        exit $analyzeExit
    } else {
        Write-Host "  -> Analisis completado con 0 errores en ${analyzeTime}s." -ForegroundColor Green
    }
} else {
    Write-Host "[2/3] Analisis estatico omitido (-SkipAnalyze activo)." -ForegroundColor DarkGray
}
Write-Host ""

# 3. Ejecucion de pruebas
Write-Host "[3/3] Ejecutando pruebas Flutter (--no-pub --reporter expanded)..." -ForegroundColor Yellow
Write-Host "  Nota: Se usa --no-pub para evitar consultas bloqueantes de red a pub.dev." -ForegroundColor DarkGray
Write-Host "  Nota: Concurrencia nativa multi-core para rendimiento optimo en Windows." -ForegroundColor DarkGray
Write-Host ""

$testArgs = switch ($Suite) {
    'unit'   { @('test', '--no-pub', '--reporter', 'expanded', 'test/unit/') }
    'widget' { @('test', '--no-pub', '--reporter', 'expanded', 'test/widget/', 'test/widget_test.dart') }
    'all'    { @('test', '--no-pub', '--reporter', 'expanded') }
}

$resTests = Invoke-FlutterWithTimeout -ArgumentList $testArgs -TimeoutSec $TimeoutSeconds -Description "flutter test ($Suite)"
$testExit = $resTests.ExitCode
$testsTime = $resTests.ElapsedSeconds

if ($testExit -ne 0) {
    Write-Host ""
    Write-Host "  [FALLO] Fallaron pruebas en ${testsTime}s (Exit code: $testExit)" -ForegroundColor Red
    exit $testExit
} else {
    Write-Host ""
    Write-Host "  -> Todas las pruebas pasaron exitosamente en ${testsTime}s." -ForegroundColor Green
}
Write-Host ""

# 4. Resumen consolidado
$totalTime = [Math]::Round($analyzeTime + $testsTime, 2)
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Resumen de Verificacion Tecnica FashionStore Movil" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
if (-not $SkipAnalyze) {
    Write-Host "  - Analisis estatico:       0 issues     (${analyzeTime}s) [Timeout limite: ${AnalyzeTimeoutSeconds}s]" -ForegroundColor Green
} else {
    Write-Host "  - Analisis estatico:       OMITIDO      (0.00s)" -ForegroundColor DarkGray
}
Write-Host "  - Pruebas ($Suite):        EXITOSO      (${testsTime}s) [Timeout limite: ${TimeoutSeconds}s]" -ForegroundColor Green
Write-Host "  - Tiempo total invertido:               (${totalTime}s)"
Write-Host "================================================================" -ForegroundColor Cyan
exit 0
