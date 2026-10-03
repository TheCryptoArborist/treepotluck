# Local validation only; no publication, wallet setup or transaction submission.
param([switch]$InstallToolchain)
$ErrorActionPreference = 'Stop'
$Runner = Join-Path $PSScriptRoot 'verify_move.py'
$Options = @()
if ($InstallToolchain) { $Options += '--install-toolchain' }
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Runner @Options
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $Runner @Options
} else {
    throw 'Python 3.10+ is required.'
}
if ($LASTEXITCODE -ne 0) {
    throw 'Validation did not pass. Read the result.json path above; do not deploy.'
}
