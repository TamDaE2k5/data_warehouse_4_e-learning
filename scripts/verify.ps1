param([int]$Enrollments = 5000)
$ErrorActionPreference = 'Stop'
# Compatibility entry point; the Python verifier owns isolation and cleanup.
& python (Join-Path $PSScriptRoot 'verify.py') --enrollments $Enrollments
if ($LASTEXITCODE -ne 0) { throw 'Verification failed. Inspect the reported evidence directory.' }
