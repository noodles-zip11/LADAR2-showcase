$ErrorActionPreference = 'Stop'

$ToolsDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ToolsDir

# ── Find Python ─────────────────────────────────────────────────────

function Get-PythonCommand {
    try {
        & python --version *> $null
        if ($LASTEXITCODE -eq 0) { return @('python') }
    } catch { }
    return @('py', '-3')
}

$PythonCmd = @(Get-PythonCommand)

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    if ($PythonCmd.Length -gt 1) {
        & $PythonCmd[0] $PythonCmd[1] @Args
    } else {
        & $PythonCmd[0] @Args
    }
}

# ── Find mosquitto tools ────────────────────────────────────────────

function Get-MosquittoPath {
    param([string]$ExeName)
    try {
        $found = Get-Command $ExeName -ErrorAction Stop
        return $found.Source
    } catch { }
    $candidates = @(
        "C:\Program Files\mosquitto\$ExeName"
        "C:\Program Files (x86)\mosquitto\$ExeName"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    return $null
}

# ── Output helpers ──────────────────────────────────────────────────

function Write-Step {
    param([string]$M)
    Write-Host "`n>>> $M" -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$M)
    Write-Host "  PASS  $M" -ForegroundColor Green
}

function Write-Fail {
    param([string]$M)
    Write-Host "  FAIL  $M" -ForegroundColor Red
}

function Write-Info {
    param([string]$M)
    Write-Host "  INFO  $M" -ForegroundColor Yellow
}

# ── Step 0: Check Python + paho-mqtt ────────────────────────────────

Write-Step "Step 0: Check Python environment"

$pyOut = & $PythonCmd[0] --version 2>&1
Write-Info "Python: $pyOut"

$pahoOut = Invoke-Python -c "import paho.mqtt.client; print('paho-mqtt OK')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "paho-mqtt not installed. Run: pip install paho-mqtt"
    exit 1
}
Write-Pass "paho-mqtt installed"

# ── Step 1: Locate Mosquitto tools ──────────────────────────────────

Write-Step "Step 1: Locate Mosquitto tools"

$MosquittoExe = Get-MosquittoPath "mosquitto.exe"
$MosquittoPub  = Get-MosquittoPath "mosquitto_pub.exe"
$MosquittoSub  = Get-MosquittoPath "mosquitto_sub.exe"

if ($MosquittoExe) { Write-Pass "mosquitto: $MosquittoExe" }
else { Write-Info "mosquitto.exe not found" }

if ($MosquittoPub) { Write-Pass "mosquitto_pub: $MosquittoPub" }
else { Write-Info "mosquitto_pub.exe not found" }

if ($MosquittoSub) { Write-Pass "mosquitto_sub: $MosquittoSub" }
else { Write-Info "mosquitto_sub.exe not found" }

if ((-not $MosquittoPub) -or (-not $MosquittoSub)) {
    Write-Host "  Mosquitto tools not fully located. Install from https://mosquitto.org/download/" -ForegroundColor Yellow
    $cont = Read-Host "  Skip and continue? (y/N)"
    if ($cont -ne 'y' -and $cont -ne 'Y') { exit 1 }
}

# ── Step 2: Check broker listening ──────────────────────────────────

Write-Step "Step 2: Check Mosquitto broker"

$brokerRunning = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $task = $tcp.BeginConnect("localhost", 1883, $null, $null)
    if ($task.AsyncWaitHandle.WaitOne(2000)) {
        $tcp.EndConnect($task)
        $brokerRunning = $true
        Write-Pass "Broker listening on localhost:1883"
    }
    $tcp.Close()
} catch {
    Write-Info "localhost:1883 not reachable"
}

if (-not $brokerRunning) {
    Write-Info "Attempting to start Mosquitto broker..."
    if ($MosquittoExe) {
        $si = New-Object System.Diagnostics.ProcessStartInfo
        $si.FileName = $MosquittoExe
        $si.Arguments = "-p 1883"
        $si.UseShellExecute = $false
        [System.Diagnostics.Process]::Start($si) | Out-Null
        Start-Sleep -Seconds 2
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("localhost", 1883)
            $tcp.Close()
            $brokerRunning = $true
            Write-Pass "Broker started"
        } catch {
            Write-Fail "Failed to start broker. Run manually: mosquitto -p 1883"
            exit 1
        }
    } else {
        Write-Fail "Mosquitto not installed. Install and start manually: mosquitto -p 1883"
        exit 1
    }
}

# ── Step 3: Start subscriber ────────────────────────────────────────

Write-Step "Step 3: Start subscriber"

$logDir = Join-Path $RepoRoot "docs\mqtt_plugin_refactor"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$subLog   = Join-Path $logDir "phase_b_sub_log.txt"
$smokeLog = Join-Path $logDir "phase_b_smoke_test_log.txt"
$smokeErrLog = "$smokeLog.err"

Remove-Item -LiteralPath $subLog -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $smokeLog -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $smokeErrLog -ErrorAction SilentlyContinue

Write-Info "Sub log:   $subLog"
Write-Info "Smoke log: $smokeLog"

$subProc = Start-Process `
    -FilePath $MosquittoSub `
    -ArgumentList @('-h', 'localhost', '-t', 'lidar/01/#', '-v') `
    -RedirectStandardOutput $subLog `
    -NoNewWindow `
    -PassThru

Start-Sleep -Seconds 1
if ($subProc.HasExited) {
    Write-Fail "Subscriber failed to start"
    exit 1
}

Write-Pass "Subscriber started (PID: $($subProc.Id))"

# ── Step 4: Run mqtt_smoke_test.py ──────────────────────────────────

Write-Step "Step 4: Run mqtt_smoke_test.py (auto-exit in 10s)"

Push-Location $RepoRoot

$pyExe = $PythonCmd[0]
$pyArg = if ($PythonCmd.Length -gt 1) { $PythonCmd[1] } else { "" }

$smokeSi = New-Object System.Diagnostics.ProcessStartInfo
if ($pyArg) {
    $smokeSi.FileName = $pyExe
    $smokeSi.Arguments = "$pyArg mqtt_smoke_test.py --duration 15"
} else {
    $smokeSi.FileName = $pyExe
    $smokeSi.Arguments = "mqtt_smoke_test.py --duration 15"
}
$smokeSi.UseShellExecute = $false
$smokeSi.RedirectStandardOutput = $true
$smokeSi.RedirectStandardError = $true
$smokeProc = [System.Diagnostics.Process]::Start($smokeSi)

Write-Info "Smoke test started (PID: $($smokeProc.Id), duration=15s)"
Write-Info "Waiting for connect+status+telemetry..."

# Poll subscriber log until status online appears (max 10s)
$ready = $false
for ($i = 0; $i -lt 50; $i++) {
    Start-Sleep -Milliseconds 200
    if (Test-Path $subLog) {
        $subCheck = Get-Content $subLog -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($subCheck -and ($subCheck -match 'lidar/01/status.*online')) {
            $ready = $true
            Write-Pass "Status online confirmed in subscriber log"
            break
        }
    }
}
if (-not $ready) {
    Write-Info "Status online not detected — proceeding anyway"
}

# ── Step 5: Send commands via temp file ─────────────────────────────

Write-Step "Step 5: Send ping commands"

function Send-MqttMsg {
    param([string]$PayloadJson)
    $tmp = New-TemporaryFile
    $PayloadJson | Set-Content -Path $tmp.FullName -Encoding ASCII -NoNewline
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $MosquittoPub
    $psi.Arguments = "-h localhost -t lidar/01/cmd -f `"$($tmp.FullName)`" -q 1"
    $psi.UseShellExecute = $false
    $p = [System.Diagnostics.Process]::Start($psi)
    $p.WaitForExit(5000) | Out-Null
    Remove-Item $tmp -ErrorAction SilentlyContinue
}

Send-MqttMsg -PayloadJson '{"cmd":"ping","req_id":"t01"}'
Write-Info "Sent: ping req_id=t01"
Start-Sleep -Milliseconds 500

Send-MqttMsg -PayloadJson '{"cmd":"ping","req_id":"t02"}'
Write-Info "Sent: ping req_id=t02"
Start-Sleep -Milliseconds 500

# ── Step 6: Wait for smoke test to finish ───────────────────────────

Write-Step "Step 6: Wait for smoke test to exit"

$smokeOut = $smokeProc.StandardOutput.ReadToEnd()
$smokeErr = $smokeProc.StandardError.ReadToEnd()
$smokeProc.WaitForExit(15000) | Out-Null

if (-not $smokeProc.HasExited) {
    Write-Info "Smoke test still running — killing"
    $smokeProc.Kill()
}

$smokeOut | Out-File -FilePath $smokeLog -Encoding utf8
if ($smokeErr) {
    $smokeErr | Out-File -FilePath $smokeErrLog -Encoding utf8
}

if ($smokeProc.ExitCode -eq 0) {
    Write-Pass "Smoke test finished (exit: 0)"
} else {
    Write-Fail "Smoke test finished (exit: $($smokeProc.ExitCode))"
}

# Stop subscriber
$subProc.Kill()
$subProc.WaitForExit(3000) | Out-Null
$subProc.Dispose()

Pop-Location

# ── Step 7: Check results ───────────────────────────────────────────

Write-Step "Step 7: Check logs"

$allPassed = $true

if ($smokeProc.ExitCode -ne 0) {
    Write-Fail "Smoke test process exited non-zero"
    $allPassed = $false
}

if ($smokeErr) {
    Write-Host "`n  --- Smoke test stderr ---" -ForegroundColor Gray
    Write-Host $smokeErr
    if ($smokeErr -match 'Traceback|RuntimeError|ERROR|FAIL') {
        Write-Fail "Smoke test stderr contains an error"
        $allPassed = $false
    }
}

# -- Smoke test log --
Write-Host "`n  --- Smoke test log ---" -ForegroundColor Gray
if (Test-Path $smokeLog) {
    $sl = Get-Content $smokeLog -Raw -Encoding UTF8
    Write-Host $sl

    if ($sl -match 'MQTT broker')           { Write-Pass "Connected to broker" }
    else { Write-Fail "Connected to broker"; $allPassed = $false }

    if ($sl -match 'status.*online')        { Write-Pass "Status online published" }
    else { Write-Fail "Status online published"; $allPassed = $false }

    if ($sl -match 'telemetry')             { Write-Pass "Telemetry published" }
    else { Write-Fail "Telemetry published"; $allPassed = $false }

    if ($sl -match 'status.*offline')       { Write-Pass "Status offline published" }
    else { Write-Fail "Status offline published"; $allPassed = $false }

    if ($sl -match 't01')                   { Write-Pass "Cmd t01 received" }
    else { Write-Fail "Cmd t01 received"; $allPassed = $false }

    if ($sl -match 't02')                   { Write-Pass "Cmd t02 received" }
    else { Write-Fail "Cmd t02 received"; $allPassed = $false }

    if ($sl -match 'duration reached|exiting|\[OK\]') { Write-Pass "Clean exit" }
    else { Write-Fail "Clean exit"; $allPassed = $false }
} else {
    Write-Fail "Smoke test log not found: $smokeLog"
    $allPassed = $false
}

# -- Subscriber log --
Write-Host "`n  --- Subscriber log (last 30 lines) ---" -ForegroundColor Gray
if (Test-Path $subLog) {
    $subFull = Get-Content $subLog -Raw -Encoding UTF8
    $subTail = Get-Content $subLog -Tail 30 -Encoding UTF8
    Write-Host ($subTail -join "`n")

    if ($subFull -match 'lidar/01/status.*online')  { Write-Pass "Sub: status online" }
    else { Write-Fail "Sub: status online"; $allPassed = $false }

    if ($subFull -match 'lidar/01/telemetry')       { Write-Pass "Sub: telemetry" }
    else { Write-Fail "Sub: telemetry"; $allPassed = $false }

    if ($subFull -match 't01')                       { Write-Pass "Sub: cmd t01" }
    else { Write-Fail "Sub: cmd t01"; $allPassed = $false }

    if ($subFull -match 't02')                       { Write-Pass "Sub: cmd t02" }
    else { Write-Fail "Sub: cmd t02"; $allPassed = $false }

    if ($subFull -match 'lidar/01/status.*offline')  { Write-Pass "Sub: status offline" }
    else { Write-Fail "Sub: status offline"; $allPassed = $false }
} else {
    Write-Fail "Subscriber log not found: $subLog"
    $allPassed = $false
}

# ── Result ──────────────────────────────────────────────────────────

Write-Host ""
if ($allPassed) {
    Write-Host "=== PASS: MQTT closed-loop verified (Phase B) ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Logs: $smokeLog , $subLog" -ForegroundColor Gray
    exit 0
} else {
    Write-Host "=== FAIL: Some checks did not pass ===" -ForegroundColor Red
    exit 1
}
