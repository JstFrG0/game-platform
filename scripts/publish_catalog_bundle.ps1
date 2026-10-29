[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BundleDirectory,
    [string]$Repository = 'JstFrG0/game-release-data'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$catalogRoot = Split-Path -Parent $PSScriptRoot
$catalogToken = $null
$catalogPreviousToken = $env:GITHUB_TOKEN
$catalogPreviousLocation = Get-Location
$catalogExitCode = 1
try {
    $catalogCredential = Join-Path $catalogRoot 'data\credentials\github-publish.dpapi'
    $catalogToken = ConvertTo-SecureString -String (Get-Content -LiteralPath $catalogCredential -Raw).Trim()
    $env:GITHUB_TOKEN = [System.Net.NetworkCredential]::new('', $catalogToken).Password.Trim()
    Set-Location -LiteralPath $catalogRoot
    & (Join-Path $catalogRoot '.venv\Scripts\python.exe') -u -m game_platform.data_updates publish --repository $Repository --bundle-dir $BundleDirectory
    $catalogExitCode = $LASTEXITCODE
}
catch {
    Write-Host 'PUBLISH_FAILED - unable to decrypt credentials or start publisher; secret hidden.'
}
finally {
    $env:GITHUB_TOKEN = $catalogPreviousToken
    $catalogPreviousToken = $null
    if ($null -ne $catalogToken) { $catalogToken.Dispose() }
    Set-Location -LiteralPath $catalogPreviousLocation.Path
}
exit $catalogExitCode
