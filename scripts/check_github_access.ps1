[CmdletBinding()]
param(
    [string]$Repository = 'JstFrG0/game-release-data',
    [ValidateSet('Publish', 'Read')]
    [string]$Purpose = 'Publish',
    [string]$Proxy,
    [switch]$LocalOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$catalogToken = $null
$catalogPlainToken = $null
$catalogHeaders = @{}
$catalogStage = 'local credential'

try {
    if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' -or
        ($Repository.Split('/') | Where-Object { $_ -in '.', '..' })) {
        throw 'Invalid repository format.'
    }
    $catalogRoot = Split-Path -Parent $PSScriptRoot
    $credentialName = if ($Purpose -eq 'Publish') { 'github-publish.dpapi' } else { 'github-read.dpapi' }
    $credentialPath = Join-Path $catalogRoot "data\credentials\$credentialName"
    if (-not (Test-Path -LiteralPath $credentialPath -PathType Leaf)) {
        Write-Host "Credential file missing. Run configure_github_token.ps1 -Purpose $Purpose first."
        exit 1
    }

    $catalogToken = ConvertTo-SecureString -String (Get-Content -LiteralPath $credentialPath -Raw).Trim()
    Write-Host 'CREDENTIAL_DECRYPT_OK'
    $catalogPlainToken = [System.Net.NetworkCredential]::new('', $catalogToken).Password.Trim()
    if ($catalogPlainToken -cnotmatch '^(github_pat_[A-Za-z0-9_]{40,}|ghp_[A-Za-z0-9]{30,})$') {
        Write-Host 'TOKEN_FORMAT_INVALID - saved content does not look like a complete GitHub personal access token.'
        Write-Host 'Copy the full secret from the generation result page; do not copy the token name, URL, or quotes.'
        exit 1
    }
    Write-Host 'TOKEN_FORMAT_OK - format only; validity is not yet verified.'
    if ($LocalOnly) { return }
    $catalogHeaders = @{
        Authorization = 'Bearer ' + $catalogPlainToken
        Accept = 'application/vnd.github+json'
        'User-Agent' = 'game-platform-credential-check'
    }
    $requestOptions = @{
        Headers = $catalogHeaders
        Method = 'Get'
        TimeoutSec = 30
        MaximumRedirection = 0
        ErrorAction = 'Stop'
    }
    if ($Proxy) { $requestOptions['Proxy'] = $Proxy }
    $catalogStage = 'GitHub authentication'
    $catalogUser = Invoke-RestMethod @requestOptions -Uri 'https://api.github.com/user'
    Write-Host "AUTH_OK - GitHub account: $($catalogUser.login)"
    $catalogStage = 'repository access'
    $catalogRepo = Invoke-RestMethod @requestOptions -Uri "https://api.github.com/repos/$Repository"
    if ($catalogRepo.full_name -ine $Repository) {
        throw 'Repository identity does not match.'
    }
    $catalogBranch = [Uri]::EscapeDataString([string]$catalogRepo.default_branch)
    $catalogStage = 'initial commit access'
    $catalogCommit = Invoke-RestMethod @requestOptions -Uri "https://api.github.com/repos/$Repository/commits/$catalogBranch"
    Write-Host "Repository: $($catalogRepo.full_name)"
    Write-Host "Private: $($catalogRepo.private)"
    Write-Host "Default branch: $($catalogRepo.default_branch)"
    Write-Host "Latest commit: $($catalogCommit.sha.Substring(0, 7))"
    Write-Host 'ACCESS_OK - repository and initial commit are readable.'
    Write-Host 'Upload permission has not been tested; first publish will verify it.'
}
catch {
    # Do not print exception text, request headers, responses, or credential values.
    $catalogStatus = $null
    if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) {
        if ($_.Exception.Response.PSObject.Properties['StatusCode']) {
            $catalogStatus = [int]$_.Exception.Response.StatusCode
        }
    }
    if ($catalogStatus) {
        Write-Host "ACCESS_FAILED - HTTP $catalogStatus ($catalogStage)."
    }
    else {
        Write-Host 'ACCESS_FAILED - credential decryption, repository validation, or network error.'
        Write-Host 'Run as the Windows user who saved the token; check connectivity and proxy settings.'
    }
    exit 1
}
finally {
    $catalogHeaders.Clear()
    $catalogPlainToken = $null
    if ($null -ne $catalogToken) { $catalogToken.Dispose() }
}
