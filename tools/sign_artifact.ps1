[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$File,

    [string]$MetadataPath = $(if ($env:ARTIFACT_SIGNING_METADATA) {
        $env:ARTIFACT_SIGNING_METADATA
    } else {
        "C:\CodeSigning\metadata.json"
    }),

    [switch]$VerifyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-SignToolPath {
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $kitsRoot = Join-Path $programFilesX86 "Windows Kits\10\bin"
    if (Test-Path -LiteralPath $kitsRoot) {
        $candidates = foreach ($dir in Get-ChildItem -LiteralPath $kitsRoot -Directory -ErrorAction SilentlyContinue) {
            try {
                $version = [version]$dir.Name
            } catch {
                continue
            }

            $candidate = Join-Path $dir.FullName "x64\signtool.exe"
            if (Test-Path -LiteralPath $candidate) {
                [pscustomobject]@{
                    Version = $version
                    Path    = $candidate
                }
            }
        }

        $best = $candidates | Sort-Object Version -Descending | Select-Object -First 1
        if ($best) {
            return $best.Path
        }
    }

    $fromPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($fromPath) {
        return $fromPath.Source
    }

    throw "signtool.exe was not found. Install the Windows SDK / Artifact Signing client prerequisites."
}

function Test-AuthenticodeFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$SignTool
    )

    & $SignTool verify /pa /v $Path
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool verification failed for: $Path"
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "PowerShell Authenticode verification failed for '$Path': $($signature.Status) - $($signature.StatusMessage)"
    }

    Write-Host "Verified Authenticode signature: $Path" -ForegroundColor Green
}

$resolvedFile = (Resolve-Path -LiteralPath $File).Path
$signTool = Get-SignToolPath

if ($VerifyOnly) {
    Test-AuthenticodeFile -Path $resolvedFile -SignTool $signTool
    exit 0
}

if (-not (Test-Path -LiteralPath $MetadataPath -PathType Leaf)) {
    throw "Artifact Signing metadata file not found: $MetadataPath"
}

$metadata = Get-Content -LiteralPath $MetadataPath -Raw | ConvertFrom-Json
foreach ($required in "Endpoint", "CodeSigningAccountName", "CertificateProfileName") {
    if (-not $metadata.PSObject.Properties.Name.Contains($required) -or
        [string]::IsNullOrWhiteSpace([string]$metadata.$required)) {
        throw "Artifact Signing metadata is missing '$required': $MetadataPath"
    }
}

$dlib = Join-Path $env:LOCALAPPDATA "Microsoft\MicrosoftArtifactSigningClientTools\Azure.CodeSigning.Dlib.dll"
if (-not (Test-Path -LiteralPath $dlib -PathType Leaf)) {
    throw "Azure.CodeSigning.Dlib.dll was not found at '$dlib'. Install Microsoft.Azure.ArtifactSigningClientTools."
}

# Inno spawns this helper in a fresh Windows PowerShell of its own, and a shell
# started before the CLI was installed carries a PATH without it, so fall back
# to where the installer puts it rather than failing mid-compile.
$az = $null
$azCommand = Get-Command az -ErrorAction SilentlyContinue
if ($azCommand) { $az = $azCommand.Source }
if (-not $az) {
    foreach ($candidate in @(
            (Join-Path $env:ProgramFiles "Microsoft SDKs\Azure\CLI2\wbin\az.cmd"),
            (Join-Path ([Environment]::GetEnvironmentVariable("ProgramFiles(x86)")) "Microsoft SDKs\Azure\CLI2\wbin\az.cmd"))) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $az = $candidate
            break
        }
    }
}
if (-not $az) {
    throw "Azure CLI ('az') was not found. Install Microsoft.AzureCLI and run 'az login'."
}

& $az account show --output none
if ($LASTEXITCODE -ne 0) {
    throw "Azure CLI is not authenticated. Run 'az login' with the account that has the Artifact Signing Certificate Profile Signer role."
}

Write-Host "Signing: $resolvedFile" -ForegroundColor Cyan
Write-Host "  Account : $($metadata.CodeSigningAccountName)"
Write-Host "  Profile : $($metadata.CertificateProfileName)"
Write-Host "  Endpoint: $($metadata.Endpoint)"

$signArgs = @(
    "sign",
    "/v",
    "/fd", "SHA256",
    "/tr", "http://timestamp.acs.microsoft.com",
    "/td", "SHA256",
    "/dlib", $dlib,
    "/dmdf", $MetadataPath,
    $resolvedFile
)
& $signTool @signArgs

if ($LASTEXITCODE -ne 0) {
    throw "Artifact Signing failed for: $resolvedFile"
}

Test-AuthenticodeFile -Path $resolvedFile -SignTool $signTool
