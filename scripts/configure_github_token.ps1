[CmdletBinding()]
param(
    [ValidateSet('Publish', 'Read')]
    [string]$Purpose = 'Publish'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ConvertFrom-SecureString without a key uses the current Windows user's DPAPI.
# Only that user on this machine can decrypt the saved token for scheduled runs.
if ($env:OS -ne 'Windows_NT') {
    throw 'This credential setup script requires Windows.'
}

$catalogRoot = Split-Path -Parent $PSScriptRoot
$credentialDirectory = Join-Path $catalogRoot 'data\credentials'
$credentialName = if ($Purpose -eq 'Publish') { 'github-publish.dpapi' } else { 'github-read.dpapi' }
$credentialPath = Join-Path $credentialDirectory $credentialName
$catalogToken = Read-Host "Paste GitHub $Purpose token (input hidden)" -AsSecureString
$catalogPlainToken = $null
$normalizedToken = $null

try {
    if ($catalogToken.Length -eq 0) {
        throw 'Token cannot be empty. Nothing was saved.'
    }
    $catalogPlainToken = [System.Net.NetworkCredential]::new('', $catalogToken).Password.Trim()
    if ($catalogPlainToken -cnotmatch '^(github_pat_[A-Za-z0-9_]{40,}|ghp_[A-Za-z0-9]{30,})$') {
        Write-Host 'TOKEN_FORMAT_INVALID - nothing was saved; the existing credential file is unchanged.'
        Write-Host 'Paste the full secret from the GitHub generation result page, without quotes.'
        exit 1
    }
    $normalizedToken = ConvertTo-SecureString -String $catalogPlainToken -AsPlainText -Force
    $encryptedToken = ConvertFrom-SecureString -SecureString $normalizedToken
    New-Item -ItemType Directory -Path $credentialDirectory -Force | Out-Null
    Set-Content -LiteralPath $credentialPath -Value $encryptedToken -Encoding UTF8
    Write-Host "Saved encrypted $Purpose token: $credentialPath"
    Write-Host 'The token has not been validated against GitHub yet.'
}
finally {
    $catalogPlainToken = $null
    if ($null -ne $normalizedToken) { $normalizedToken.Dispose() }
    $catalogToken.Dispose()
    Remove-Variable encryptedToken -ErrorAction SilentlyContinue
}
