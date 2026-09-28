[CmdletBinding()]
param(
    [string]$MetadataPath = $(if ($env:ARTIFACT_SIGNING_METADATA) {
        $env:ARTIFACT_SIGNING_METADATA
    } else {
        "C:\CodeSigning\metadata.json"
    }),

    [switch]$SkipValidation,

    # Uploads the finished signed Setup.exe and ZIP to the already-existing
    # GitHub release v<version>. It does not create or push a tag.
    [switch]$UploadRelease
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$signScript = Join-Path $PSScriptRoot "sign_artifact.ps1"
$iss = Join-Path $repo "installer\IL2_Korea_Service_Record.iss"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

function Get-InnoCompiler {
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $known = @(
        (Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    foreach ($candidate in $known) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }

    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw "ISCC.exe was not found. Install Inno Setup 6."
}

if (-not (Test-Path -LiteralPath $MetadataPath -PathType Leaf)) {
    throw "Artifact Signing metadata file not found: $MetadataPath"
}
if (-not (Test-Path -LiteralPath $signScript -PathType Leaf)) {
    throw "Signing helper not found: $signScript"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python was not found on PATH."
}
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI ('az') was not found. Install it and run 'az login'."
}

& az account show --output none
Assert-NativeSuccess "Azure authentication check"

$issText = Get-Content -LiteralPath $iss -Raw
if ($issText -notmatch '#define\s+MyAppVersion\s+"([^"]+)"') {
    throw "Could not read MyAppVersion from installer\IL2_Korea_Service_Record.iss."
}
$version = $Matches[1]

$trackerDir = Join-Path $repo "dist\IL2_Korea_Service_Record"
$trackerExe = Join-Path $trackerDir "IL2_Korea_Service_Record.exe"
$helperExe = Join-Path $trackerDir "IL2_Korea_Career_Helper.exe"
$setupExe = Join-Path $repo "installer\Output\IL2_Korea_Service_Record_Setup_v$version.exe"
$zipFile = Join-Path $repo "installer\Output\IL-2 Korea Service Record v$version.zip"
$iscc = Get-InnoCompiler

Push-Location $repo
try {
    Write-Host ""
    Write-Host "IL-2 Korea Service Record v$version - signed release build" -ForegroundColor Cyan
    Write-Host "Artifact Signing metadata: $MetadataPath"

    if (-not $SkipValidation) {
        Write-Host ""
        Write-Host "[1/8] Validate repository" -ForegroundColor Cyan
        & python "tools\validate.py"
        Assert-NativeSuccess "Repository validation"
    } else {
        Write-Host ""
        Write-Host "[1/8] Repository validation skipped" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "[2/8] Build PyInstaller application" -ForegroundColor Cyan
    & python -m PyInstaller "korea_service_record.spec" --noconfirm
    Assert-NativeSuccess "PyInstaller build"

    foreach ($exe in @($trackerExe, $helperExe)) {
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
            throw "Expected PyInstaller executable not found: $exe"
        }
    }

    Write-Host ""
    Write-Host "[3/8] Sign and verify application executables" -ForegroundColor Cyan
    & $signScript -File $trackerExe -MetadataPath $MetadataPath
    & $signScript -File $helperExe -MetadataPath $MetadataPath

    Write-Host ""
    Write-Host "[4/8] Stage installer payload" -ForegroundColor Cyan
    & python "tools\stage_release.py"
    Assert-NativeSuccess "Release staging"

    Write-Host ""
    Write-Host "[5/8] Build and sign Inno Setup installer + uninstaller" -ForegroundColor Cyan

    $innoSignCommand =
        'azureartifacts=powershell.exe -NoProfile -ExecutionPolicy Bypass -File $q' +
        $signScript +
        '$q -MetadataPath $q' +
        $MetadataPath +
        '$q -File $f'

    & $iscc "-dAZURE_SIGNING=1" "-s$innoSignCommand" $iss
    Assert-NativeSuccess "Inno Setup compilation"

    if (-not (Test-Path -LiteralPath $setupExe -PathType Leaf)) {
        throw "Expected signed installer not found: $setupExe"
    }

    Write-Host ""
    Write-Host "[6/8] Verify final installer" -ForegroundColor Cyan
    & $signScript -File $setupExe -VerifyOnly

    Write-Host ""
    Write-Host "[7/8] Build release ZIP" -ForegroundColor Cyan
    & python "tools\make_release_zip.py"
    Assert-NativeSuccess "Release ZIP creation"

    if (-not (Test-Path -LiteralPath $zipFile -PathType Leaf)) {
        throw "Expected release ZIP not found: $zipFile"
    }

    Write-Host ""
    Write-Host "[8/8] Release hashes" -ForegroundColor Cyan
    $setupHash = (Get-FileHash -LiteralPath $setupExe -Algorithm SHA256).Hash.ToLowerInvariant()
    $zipHash = (Get-FileHash -LiteralPath $zipFile -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "  $setupHash  $([IO.Path]::GetFileName($setupExe))"
    Write-Host "  $zipHash  $([IO.Path]::GetFileName($zipFile))"

    if ($UploadRelease) {
        if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
            throw "GitHub CLI ('gh') was not found. Install it or omit -UploadRelease."
        }

        $tag = "v$version"
        & gh release view $tag --repo "1-Arrow-1/IL2-Korea_Service_Record" *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "GitHub release '$tag' does not exist yet. Push the tag first, wait for build.yml to create the release, then rerun with -UploadRelease."
        }

        Write-Host ""
        Write-Host "Uploading signed release assets to GitHub release $tag..." -ForegroundColor Cyan
        & gh release upload $tag $setupExe $zipFile --clobber --repo "1-Arrow-1/IL2-Korea_Service_Record"
        Assert-NativeSuccess "GitHub release upload"
    }

    Write-Host ""
    Write-Host "Signed release build completed successfully." -ForegroundColor Green
    Write-Host "  Setup: $setupExe"
    Write-Host "  ZIP  : $zipFile"
} finally {
    Pop-Location
}
