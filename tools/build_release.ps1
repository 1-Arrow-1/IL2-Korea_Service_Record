#
# One command to make and publish a release.
#
#     .\tools\build_release.ps1 -Version 1.8.2 -Publish
#
# Everything a release needs, in the order it needs doing, with the steps
# that have gone wrong before enforced rather than remembered:
#
#   * both version strings move together, so the zip and the installer can
#     never disagree
#   * the tag is created at the commit the binaries were built from, not
#     wherever main happens to be by the time someone remembers to tag
#   * the published bytes are downloaded back and compared against the local
#     build before anything is called finished
#   * the checksums written into the forum post are the ones GitHub serves,
#     because a signature carries a timestamp and no two builds are alike
#   * a release whose assets people have already downloaded is not replaced
#
# What it deliberately does not do: post to the forum, and choose the
# version number. Neither has an API, and the second is a judgement.
#
[CmdletBinding()]
param(
    # Bump MyAppVersion and VERSION to this and commit, before building.
    # Omit to build whatever the .iss already says.
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    # Push main, tag at the built commit, open the release, upload, verify
    # what GitHub serves, and write those checksums into the forum post.
    [switch]$Publish,

    # Everything except the irreversible parts: no push, no tag, no release,
    # no upload. Prints what it would have done.
    [switch]$DryRun,

    # Replace assets that already have downloads. Without this the script
    # refuses, because someone is holding a file whose checksum you published.
    [switch]$Force,

    [string]$MetadataPath = $(if ($env:ARTIFACT_SIGNING_METADATA) {
        $env:ARTIFACT_SIGNING_METADATA
    } else {
        "C:\CodeSigning\metadata.json"
    }),

    # tools/validate.py does read the live installation, and its career
    # fixtures do depend on which careers exist - but most of what it checks
    # is the source tree, and its locale checks are the project's only guard
    # against shipping a key that reaches the user as "KEY!LOCALIZE!". It
    # exits non-zero on failure, so it gates the release by default.
    [switch]$SkipValidation
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# This script probes exit codes itself - "gh release view" on a release that
# does not exist yet is a question, not a failure. Left at the PowerShell 7.4+
# default of $true, that probe would throw instead of answering.
$PSNativeCommandUseErrorActionPreference = $false

$repo = Split-Path -Parent $PSScriptRoot
$signScript = Join-Path $PSScriptRoot "sign_artifact.ps1"
$iss = Join-Path $repo "installer\IL2_Korea_Service_Record.iss"
$zipPy = Join-Path $repo "tools\make_release_zip.py"
$slug = "1-Arrow-1/IL2-Korea_Service_Record"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

function Step {
    param([string]$Text)
    Write-Host ""
    Write-Host $Text -ForegroundColor Cyan
}

function Would {
    param([string]$Text)
    Write-Host "  would $Text" -ForegroundColor DarkGray
}

function Get-InnoCompiler {
    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    foreach ($candidate in @(
            (Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"))) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw "ISCC.exe was not found. Install Inno Setup 6."
}

# -- preconditions ---------------------------------------------------------

if (-not (Test-Path -LiteralPath $MetadataPath -PathType Leaf)) {
    throw "Artifact Signing metadata file not found: $MetadataPath"
}
if (-not (Test-Path -LiteralPath $signScript -PathType Leaf)) {
    throw "Signing helper not found: $signScript"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "'python' was not found on PATH."
}

# A shell started before one of these was installed carries a stale PATH and
# loses the release run at the last step, so look where the installer puts it
# before giving up.
function Resolve-Tool {
    param([string]$Name, [string[]]$Fallbacks)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in $Fallbacks) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            # Put it on PATH rather than only returning it: sign_artifact.ps1
            # looks 'az' up for itself, and Inno spawns that helper in a fresh
            # PowerShell of its own. Both inherit this.
            $env:PATH = (Split-Path -Parent $candidate) + ";" + $env:PATH
            Write-Host "  using $candidate (was not on this shell's PATH)" -ForegroundColor DarkGray
            return $candidate
        }
    }
    return $null
}

$programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
$az = Resolve-Tool "az" @(
    (Join-Path $env:ProgramFiles "Microsoft SDKs\Azure\CLI2\wbin\az.cmd"),
    (Join-Path $programFilesX86 "Microsoft SDKs\Azure\CLI2\wbin\az.cmd"))
if (-not $az) { throw "The Azure CLI ('az') was not found." }

$gh = $null
if ($Publish) {
    $gh = Resolve-Tool "gh" @((Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"))
    if (-not $gh) { throw "GitHub CLI ('gh') was not found. Install it or omit -Publish." }
}

& $az account show --output none
Assert-NativeSuccess "Azure authentication check"

Push-Location $repo
try {
    # A release is cut from a known commit. PyInstaller builds the working
    # tree, but the tag can only point at a commit - so uncommitted work means
    # a tag that does not describe the binaries under it. -Version is no
    # exception: its commit carries the two version lines and nothing else.
    if ($Publish) {
        $dirty = & git status --porcelain
        if ($dirty) {
            throw "The working tree has uncommitted changes, so the tag would not match the binaries. Commit or stash them first:`n$($dirty -join "`n")"
        }
    }

    # -- version ----------------------------------------------------------
    Step "[1/11] Version"
    if ($Version) {
        $issText = Get-Content -LiteralPath $iss -Raw
        $zipText = Get-Content -LiteralPath $zipPy -Raw
        $issText = [regex]::Replace($issText, '(#define\s+MyAppVersion\s+")[^"]+(")', "`${1}$Version`${2}")
        $zipText = [regex]::Replace($zipText, '(?m)^(VERSION\s*=\s*")[^"]+(")', "`${1}$Version`${2}")
        Set-Content -LiteralPath $iss -Value $issText -NoNewline
        Set-Content -LiteralPath $zipPy -Value $zipText -NoNewline
        Write-Host "  bumped the .iss and make_release_zip.py to $Version"
        if ($DryRun) {
            Would "commit the version bump"
        } else {
            & git add -- $iss $zipPy
            # Nothing staged means the tree already carried this version -
            # a rerun after a failed publish, not a problem.
            $staged = & git diff --cached --name-only
            if ($staged) {
                & git commit -q -m "Version $Version"
                Assert-NativeSuccess "Version commit"
            } else {
                Write-Host "  already at $Version, nothing to commit" -ForegroundColor DarkGray
            }
            Write-Host "  committed"
        }
    }
    $issText = Get-Content -LiteralPath $iss -Raw
    if ($issText -notmatch '#define\s+MyAppVersion\s+"([^"]+)"') {
        throw "Could not read MyAppVersion from $iss."
    }
    $version = $Matches[1]
    # The two must agree, or the zip is named for one release and built from
    # another - which shipped a 1.3.0 tracker inside 1.4.0 once.
    $zipText = Get-Content -LiteralPath $zipPy -Raw
    if ($zipText -notmatch '(?m)^VERSION\s*=\s*"([^"]+)"' -or $Matches[1] -ne $version) {
        throw "Version mismatch: the .iss says $version, make_release_zip.py says $($Matches[1]). Pass -Version to set both."
    }
    Write-Host "  building $version"

    $trackerDir = Join-Path $repo "dist\IL2_Korea_Service_Record"
    $trackerExe = Join-Path $trackerDir "IL2_Korea_Service_Record.exe"
    $helperExe = Join-Path $trackerDir "IL2_Korea_Career_Helper.exe"
    $setupExe = Join-Path $repo "installer\Output\IL2_Korea_Service_Record_Setup_v$version.exe"
    $zipFile = Join-Path $repo "installer\Output\IL-2 Korea Service Record v$version.zip"
    $iscc = Get-InnoCompiler
    $tag = "v$version"

    # -- checks -----------------------------------------------------------
    Step "[2/11] Validate locales, awards and career data"
    if ($SkipValidation) {
        Write-Host "  skipped at your request" -ForegroundColor Yellow
    } else {
        & python "tools\validate.py"
        Assert-NativeSuccess "Validation"
    }

    # -- build ------------------------------------------------------------
    Step "[3/11] Build PyInstaller application"
    & python -m PyInstaller "korea_service_record.spec" --noconfirm
    Assert-NativeSuccess "PyInstaller build"
    foreach ($exe in @($trackerExe, $helperExe)) {
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
            throw "Expected PyInstaller executable not found: $exe"
        }
    }

    Step "[4/11] Sign and verify application executables"
    & $signScript -File $trackerExe -MetadataPath $MetadataPath
    & $signScript -File $helperExe -MetadataPath $MetadataPath

    Step "[5/11] Stage installer payload"
    & python "tools\stage_release.py"
    Assert-NativeSuccess "Release staging"

    Step "[6/11] Build and sign Inno Setup installer + uninstaller"
    # Spawn the same PowerShell this script is running under, not a bare
    # "powershell.exe". Under pwsh 7 that would start Windows PowerShell 5.1,
    # which inherits 7's PSModulePath, tries to load 7's copy of
    # Microsoft.PowerShell.Security and cannot - so the helper signs the
    # uninstaller and then dies verifying it, three retries deep into a compile.
    $psExe = (Get-Process -Id $PID).Path
    $innoSignCommand =
        'azureartifacts=$q' + $psExe + '$q -NoProfile -ExecutionPolicy Bypass -File $q' +
        $signScript + '$q -MetadataPath $q' + $MetadataPath + '$q -File $f'
    & $iscc "-dAZURE_SIGNING=1" "-s$innoSignCommand" $iss
    Assert-NativeSuccess "Inno Setup compilation"
    if (-not (Test-Path -LiteralPath $setupExe -PathType Leaf)) {
        throw "Expected signed installer not found: $setupExe"
    }

    Step "[7/11] Verify final installer"
    & $signScript -File $setupExe -VerifyOnly

    Step "[8/11] Build release ZIP"
    & python "tools\make_release_zip.py"
    Assert-NativeSuccess "Release ZIP creation"
    if (-not (Test-Path -LiteralPath $zipFile -PathType Leaf)) {
        throw "Expected release ZIP not found: $zipFile"
    }

    Step "[9/11] Scan the release artifacts with Microsoft Defender"
    $mpCmdRun = Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"
    if (Test-Path -LiteralPath $mpCmdRun -PathType Leaf) {
        foreach ($artifact in @($setupExe, $zipFile)) {
            # -DisableRemediation so a detection is reported rather than the
            # file being quarantined out from under the release.
            & $mpCmdRun -Scan -ScanType 3 -File $artifact -DisableRemediation |
                Select-Object -Last 1
            if ($LASTEXITCODE -ne 0) { throw "Defender reported a detection in: $artifact" }
        }
    } else {
        Write-Host "  MpCmdRun.exe not found - scan before uploading." -ForegroundColor Yellow
    }

    $setupHash = (Get-FileHash -LiteralPath $setupExe -Algorithm SHA256).Hash.ToLowerInvariant()
    $zipHash = (Get-FileHash -LiteralPath $zipFile -Algorithm SHA256).Hash.ToLowerInvariant()
    Step "[10/11] Local build"
    Write-Host "  $setupHash  $([IO.Path]::GetFileName($setupExe))"
    Write-Host "  $zipHash  $([IO.Path]::GetFileName($zipFile))"

    if (-not $Publish) {
        Step "Built, signed and scanned. Not published."
        Write-Host "  add -Publish to tag, upload and verify." -ForegroundColor DarkGray
        return
    }

    # -- publish ------------------------------------------------------------
    Step "[11/11] Publish $tag"

    # Refuse to take away a file someone already has. The checksum they were
    # given is in a forum post; replacing the bytes makes it a lie.
    # "release not found" on stderr is the answer to a question, not a
    # failure - but under $ErrorActionPreference = "Stop" PowerShell turns a
    # native command's stderr into a terminating error regardless of its exit
    # code, so the probe has to be made with that relaxed.
    $ErrorActionPreference = "Continue"
    $existingJson = & $gh release view $tag --repo $slug --json assets 2>&1
    $probe = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($probe -eq 0) {
        $existing = ($existingJson -join "" | ConvertFrom-Json).assets
        $taken = ($existing | Measure-Object -Property downloadCount -Sum).Sum
        if (-not $taken) { $taken = 0 }
        if ($taken -gt 0 -and -not $Force) {
            throw ("Release $tag already has $taken download(s). Replacing those assets " +
                   "invalidates the checksums people were given - ship a new version " +
                   "instead.`n" +
                   "  If you have not posted $tag anywhere, this is safe to override: the " +
                   "verification step below downloads both assets, so every completed " +
                   "publish leaves one download against each. Rerun with -Force.")
        }
        Write-Host "  release exists, $taken download(s) so far"
    }

    $head = (& git rev-parse --short HEAD).Trim()
    if ($DryRun) {
        Would "push main"
        Would "tag $tag at $head and push it"
        Would "create the release and upload both assets"
        Would "download them back and verify"
        Step "Dry run complete - nothing was pushed."
        return
    }

    & git push origin main
    Assert-NativeSuccess "git push main"

    # The tag goes on the commit that was built, not on whatever main is by
    # the time somebody remembers. -f because a rebuild of an unposted
    # release legitimately moves it.
    & git tag -f $tag $head
    & git push -f origin $tag
    Assert-NativeSuccess "git push tag"
    Write-Host "  tagged $tag at $head"

    $ErrorActionPreference = "Continue"
    & $gh release view $tag --repo $slug *> $null
    $probe = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($probe -ne 0) {
        & $gh release create $tag --repo $slug --title $tag --generate-notes
        Assert-NativeSuccess "GitHub release create"
        Write-Host "  release created"
    }

    & $gh release upload $tag $setupExe $zipFile --clobber --repo $slug
    Assert-NativeSuccess "GitHub release upload"
    Write-Host "  uploaded"

    # What GitHub serves is the only thing that matters. Every build signs
    # afresh and a signature carries a timestamp, so bytes from an earlier
    # run are never the bytes on the release.
    $check = Join-Path ([IO.Path]::GetTempPath()) ("relcheck_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $check | Out-Null
    try {
        & $gh release download $tag --repo $slug --dir $check --clobber
        Assert-NativeSuccess "GitHub release download"
        $servedSetup = (Get-ChildItem $check -Filter "*.exe" | Select-Object -First 1)
        $servedZip = (Get-ChildItem $check -Filter "*.zip" | Select-Object -First 1)
        $sHash = (Get-FileHash $servedSetup.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $zHash = (Get-FileHash $servedZip.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sHash -ne $setupHash -or $zHash -ne $zipHash) {
            throw "What GitHub serves does not match the local build.`n  setup local $setupHash served $sHash`n  zip   local $zipHash served $zHash"
        }
        Write-Host "  verified: the served bytes match the local build"
    } finally {
        Remove-Item $check -Recurse -Force -ErrorAction SilentlyContinue
    }

    # -- the forum text -----------------------------------------------------
    $post = Join-Path $repo "docs\forum-post-$version.txt"
    if (Test-Path -LiteralPath $post -PathType Leaf) {
        $text = Get-Content -LiteralPath $post -Raw
        $hashes = [regex]::Matches($text, 'SHA-256\s+([0-9a-f]{64})')
        if ($hashes.Count -eq 2) {
            # Splice by position, not by value. Replace() rewrites every
            # occurrence, so two identical placeholders - a file written
            # with 64 zeros twice, say - would both take the first hash and
            # the second substitution would find nothing left to do. That
            # shipped a forum post for 2.0.0 quoting the installer's
            # checksum against the zip.
            foreach ($i in 1, 0) {
                $g = $hashes[$i].Groups[1]
                $with = if ($i -eq 0) { $setupHash } else { $zipHash }
                $text = $text.Remove($g.Index, $g.Length).Insert($g.Index, $with)
            }
            Set-Content -LiteralPath $post -Value $text -NoNewline
            & git add -- $post
            & git commit -q -m "Forum post: checksums for $tag"
            & git push -q origin main
            Write-Host "  wrote the verified checksums into $([IO.Path]::GetFileName($post))"
        } else {
            Write-Host "  $([IO.Path]::GetFileName($post)) does not carry two SHA-256 lines - left alone." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  no docs\forum-post-$version.txt yet - checksums not written." -ForegroundColor Yellow
    }

    Step "Released."
    Write-Host "  https://github.com/$slug/releases/tag/$tag"
    Write-Host "  Setup  $setupHash"
    Write-Host "  Zip    $zipHash"
    Write-Host ""
    Write-Host "  Left to do by hand: post the forum text. There is no API for it." -ForegroundColor DarkGray
} finally {
    Pop-Location
}
