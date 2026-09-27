$ErrorActionPreference = 'Stop'

$ToolsDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ToolsDir

# Force Python UTF-8 mode so Chinese PASS output does not fail on GBK consoles.
$PreviousPythonUtf8 = $env:PYTHONUTF8
$env:PYTHONUTF8 = '1'

function Get-PythonCommand {
    try {
        & python --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @('python')
        }
    }
    catch {
    }
    return @('py', '-3')
}

$PythonCmd = @(Get-PythonCommand)

# Keep this explicit. Assert-SelfcheckInventory fails if a new selfcheck_*.py
# exists but is not wired into this all-in-one entrypoint.
$SelfcheckScripts = @(
    'tools/selfcheck_protocol.py'
    'tools/selfcheck_csv_roundtrip.py'
    'tools/selfcheck_geometry.py'
    'tools/selfcheck_fixtures.py'
    'tools/selfcheck_luna_firmware.py'
    'tools/selfcheck_contract.py'
    'tools/selfcheck_mqtt_contract.py'
    'tools/selfcheck_replay_alarm.py'
    'tools/selfcheck_m8_dataset.py'
    'tools/selfcheck_core.py'
    'tools/selfcheck_input.py'
    'tools/selfcheck_output.py'
    'tools/selfcheck_windows_launcher.py'
    'tools/selfcheck_m8_offline_analysis.py'
    'tools/selfcheck_m9_rule_filter.py'
)

function Invoke-Python {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    if ($PythonCmd.Length -gt 1) {
        & $PythonCmd[0] $PythonCmd[1] @Args
    }
    else {
        & $PythonCmd[0] @Args
    }
}

function Assert-SelfcheckInventory {
    $Actual = @(
        Get-ChildItem -Path (Join-Path $ToolsDir 'selfcheck_*.py') -File |
            ForEach-Object { "tools/$($_.Name)" } |
            Sort-Object
    )
    $Configured = @($SelfcheckScripts | Sort-Object)

    $Missing = @($Actual | Where-Object { $Configured -notcontains $_ })
    $Extra = @($Configured | Where-Object { $Actual -notcontains $_ })

    if ($Missing.Count -gt 0) {
        Write-Host "FAIL: selfcheck_all.ps1 is missing scripts: $($Missing -join ', ')"
        exit 1
    }
    if ($Extra.Count -gt 0) {
        Write-Host "FAIL: selfcheck_all.ps1 references missing scripts: $($Extra -join ', ')"
        exit 1
    }
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ">>> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAIL: $Name exited with code $LASTEXITCODE"
        exit $LASTEXITCODE
    }
}

Push-Location $RepoRoot
try {
    Assert-SelfcheckInventory
    Invoke-Step 'cmake --build --preset Debug' { cmake --build --preset Debug }

    # Compile first so syntax mistakes fail before longer behavioral checks.
    $CompileTargets = @(
        'can_recv4.py'
        'can_parser.py'
        'can_input.py'
        'can_core.py'
        'can_output.py'
        'can_mqtt.py'
        'can_recv4_windows.py'
        'mqtt_smoke_test.py'
    )
    $ToolCompileTargets = @(
        Get-ChildItem -Path $ToolsDir -File -Filter '*.py' |
            ForEach-Object { "tools/$($_.Name)" } |
            Sort-Object
    )
    foreach ($Path in ($CompileTargets + $ToolCompileTargets)) {
        Invoke-Step "python -m py_compile $Path" { Invoke-Python -m py_compile $Path }
    }

    foreach ($Script in $SelfcheckScripts) {
        Invoke-Step $Script { Invoke-Python $Script }
    }

    Write-Host 'PASS: selfcheck_all'
    exit 0
}
finally {
    $env:PYTHONUTF8 = $PreviousPythonUtf8
    Pop-Location
}
