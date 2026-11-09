[CmdletBinding()]
param(
    [ValidateSet('benchmark', 'all', 'unit', 'widget')]
    [string]$Suite = 'benchmark',

    # Timeout para pruebas individuales
    [int]$TimeoutSeconds = 180,

    # Timeout para fase de analisis estatico
    [int]$AnalyzeTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  FashionStore Movil -- Diagnostico y Benchmark del Test Runner" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Host OS:                 $($env:OS) ($([System.Environment]::OSVersion.VersionString))"
Write-Host "Procesadores logicos:    $([System.Environment]::ProcessorCount) cores"
Write-Host "Directorio de ejecucion: $PSScriptRoot"
Write-Host "Fecha y hora:            $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Modo solicitado:         $Suite"
Write-Host "Timeout pruebas:         ${TimeoutSeconds}s"
Write-Host "Timeout analisis:        ${AnalyzeTimeoutSeconds}s"
Write-Host ""

$results = @()

function Medir-Paso-Robusto {
    param(
        [string]$Nombre,
        [string[]]$Argumentos,
        [int]$TimeoutSec
    )

    Write-Host "--- Ejecutando: $Nombre ---" -ForegroundColor Yellow
    Write-Host "Comando: flutter.bat $($Argumentos -join ' ')" -ForegroundColor DarkGray

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/c flutter.bat " + ($Argumentos -join ' ')
    $psi.WorkingDirectory = $PSScriptRoot
    $psi.UseShellExecute = $false

    $p = [System.Diagnostics.Process]::Start($psi)
    Write-Host "  -> Proceso PID $($p.Id) iniciado (limite de seguridad: ${TimeoutSec}s)..." -ForegroundColor DarkCyan

    $lastReport = 0
    while (-not $p.HasExited -and $sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        Start-Sleep -Milliseconds 1000
        $currentSec = [int]$sw.Elapsed.TotalSeconds
        if ($currentSec -ge 5 -and ($currentSec - $lastReport) -ge 5 -and -not $p.HasExited) {
            $lastReport = $currentSec
            Write-Host "     [Activo: $Nombre - ${currentSec}s transcurridos...]" -ForegroundColor DarkGray
        }
    }

    $finished = $p.HasExited
    if ($finished) {
        $p.WaitForExit()
    }
    $sw.Stop()
    $duracion = [Math]::Round($sw.Elapsed.TotalSeconds, 2)

    if (-not $finished) {
        Write-Host ""
        Write-Host "  [TIMEOUT] $Nombre excedio el limite de seguridad de ${TimeoutSec}s." -ForegroundColor Red
        try {
            & taskkill.exe /PID $p.Id /T /F 2>$null | Out-Null
        } catch {
            try { $p.Kill() } catch {}
        }
        $estado = "TIMEOUT (124)"
        $exitCode = 124
    } else {
        $exitCode = $p.ExitCode
        $estado = if ($exitCode -eq 0) { "PASO" } else { "FALLO ($exitCode)" }
    }

    Write-Host "Resultado: $estado en ${duracion}s (Exit code: $exitCode)" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
    Write-Host ""

    return [PSCustomObject]@{
        Paso        = $Nombre
        Duracion    = "${duracion}s"
        Estado      = $estado
        ExitCode    = $exitCode
        TimeoutConf = "${TimeoutSec}s"
    }
}

# 1. Analisis Estatico
$results += Medir-Paso-Robusto -Nombre "1. Analisis Estatico (flutter analyze --no-pub)" `
    -Argumentos @("analyze", "--no-pub") `
    -TimeoutSec $AnalyzeTimeoutSeconds

# 2. Suites segun parametro
if ($Suite -eq 'benchmark' -or $Suite -eq 'unit') {
    $results += Medir-Paso-Robusto -Nombre "2. Suite Unitaria (test/unit/)" `
        -Argumentos @("test", "--no-pub", "--reporter", "expanded", "test/unit/") `
        -TimeoutSec $TimeoutSeconds
}

if ($Suite -eq 'benchmark' -or $Suite -eq 'widget') {
    $results += Medir-Paso-Robusto -Nombre "3. Suite Widgets (test/widget/ + test/widget_test.dart)" `
        -Argumentos @("test", "--no-pub", "--reporter", "expanded", "test/widget/", "test/widget_test.dart") `
        -TimeoutSec $TimeoutSeconds
}

if ($Suite -eq 'benchmark' -or $Suite -eq 'all') {
    $results += Medir-Paso-Robusto -Nombre "4. Suite Completa (flutter test --no-pub --reporter expanded)" `
        -Argumentos @("test", "--no-pub", "--reporter", "expanded") `
        -TimeoutSec $TimeoutSeconds
}

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Tabla Consolidada de Resultados de Benchmark" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
$results | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "Causas del Timeout Reportado en Auditoria 33 y Resolucion:" -ForegroundColor Magenta
Write-Host "1. En Windows 11 con Windows Defender activo, 'flutter analyze' tarda entre 3s (en caliente)"
Write-Host "   y ~30-38s (en frio o bajo inspeccion de subprocesos Dart). Un timeout global de 45s para toda"
Write-Host "   la ejecucion estrangulaba la fase de analisis antes de que pudieran ejecutarse las pruebas."
Write-Host "2. Resolucion: Ahora el runner cuenta con temporizador desacoplado e independiente por fase:"
Write-Host "   - Analisis estatico: 120s de presupuesto seguro (evita abortos prematuros en Windows)."
Write-Host "   - Fase de pruebas:   Parametrizable via -TimeoutSeconds (por defecto 180s, o 45s focalizado)."
Write-Host "   - Monitoreo activo:  Heartbeat en consola cada 5s indicando PID y tiempo transcurrido."
Write-Host "3. Flag --no-pub obligatorio: Previene llamadas de red bloqueantes a pub.dev en CI/auditorias."
Write-Host "================================================================" -ForegroundColor Cyan

$hasFailure = $results | Where-Object { $_.ExitCode -ne 0 }
if ($hasFailure) {
    exit 1
}
exit 0
