param(
    [string]$SdkPath = "",
    [string]$JdkPath = ""
)

$ErrorActionPreference = "Stop"

function Get-SandSJdk {
    param([string]$Candidate)
    if ([string]::IsNullOrWhiteSpace($Candidate)) { return $null }
    $Candidate = $Candidate.Trim().Trim('"')
    if (-not (Test-Path -LiteralPath (Join-Path $Candidate "bin\javac.exe") -PathType Leaf)) { return $null }
    if (-not (Test-Path -LiteralPath (Join-Path $Candidate "bin\java.exe") -PathType Leaf)) { return $null }
    $release = Join-Path $Candidate "release"
    if (-not (Test-Path -LiteralPath $release -PathType Leaf)) { return $null }
    $version = [regex]::Match((Get-Content -LiteralPath $release -Raw), '(?m)^JAVA_VERSION="(?<major>\d+)')
    if (-not $version.Success) { return $null }
    return [pscustomobject]@{
        Path = (Get-Item -LiteralPath $Candidate).FullName
        Major = [int]$version.Groups['major'].Value
    }
}

if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    throw "Run BUILD_PILOT.ps1 as a file, or use RUN_ANDROID_BUILD.cmd from the extracted update folder."
}
if (-not $SdkPath) {
    if ($env:ANDROID_HOME) { $SdkPath = $env:ANDROID_HOME }
    else { $SdkPath = Join-Path $env:LOCALAPPDATA "Android\Sdk" }
}
if ($JdkPath) {
    $selectedJdk = Get-SandSJdk -Candidate $JdkPath
    if ($null -eq $selectedJdk -or $selectedJdk.Major -notin @(17, 21)) {
        throw "The selected path must contain JDK 17 or 21. This Gradle 8.13 build cannot run on Java 25."
    }
} else {
    $candidates = @($env:JAVA_HOME)
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "Programs\Android Studio\jbr"
    }
    $jdkFolders = @()
    if ($env:ProgramFiles) {
        foreach ($folder in @("Eclipse Adoptium", "Java", "Microsoft", "Amazon Corretto", "Zulu")) {
            $jdkFolders += Join-Path $env:ProgramFiles $folder
        }
    }
    if ($env:USERPROFILE) { $jdkFolders += Join-Path $env:USERPROFILE ".jdks" }
    foreach ($folder in $jdkFolders) {
        if (Test-Path -LiteralPath $folder -PathType Container) {
            $candidates += @(Get-ChildItem -LiteralPath $folder -Directory | Sort-Object Name -Descending | ForEach-Object { $_.FullName })
        }
    }
    $selectedJdk = $null
    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        $info = Get-SandSJdk -Candidate $candidate
        if ($null -eq $info) { continue }
        if ($info.Major -in @(17, 21)) { $selectedJdk = $info; break }
        Write-Host "Skipping Java $($info.Major): $($info.Path)"
    }
    if ($null -eq $selectedJdk) {
        throw "No compatible JDK found. Run: winget install --id EclipseAdoptium.Temurin.17.JDK -e ; then run this build again. Or pass -JdkPath for an existing JDK 17 or 21."
    }
}
$JdkPath = $selectedJdk.Path
if (-not (Test-Path (Join-Path $SdkPath "platforms\android-36\android.jar"))) {
    throw "Android SDK platform 36 is missing. Install it using Android Studio's SDK Manager, or pass the correct -SdkPath."
}

$configPath = Join-Path $PSScriptRoot "app\google-services.json"
if (-not (Test-Path $configPath)) { throw "Missing app\google-services.json." }
$firebaseConfig = Get-Content -Raw $configPath | ConvertFrom-Json
$packages = @($firebaseConfig.client | ForEach-Object { $_.client_info.android_client_info.package_name })
if ($firebaseConfig.private_key -or $firebaseConfig.project_info.project_id -ne "sands-workforce" -or $packages -notcontains "in.sandssoftware.workforce.pilot") {
    throw "The Firebase Android client configuration must match sands-workforce / in.sandssoftware.workforce.pilot."
}

$previousJava = $env:JAVA_HOME
$previousSdk = $env:ANDROID_HOME
$previousPath = $env:PATH
Push-Location $PSScriptRoot
try {
    $env:JAVA_HOME = $JdkPath
    $env:ANDROID_HOME = $SdkPath
    $env:PATH = (Join-Path $JdkPath "bin") + ";" + $previousPath
    Write-Host "Using JDK $($selectedJdk.Major): $JdkPath"
    Write-Host "Building and checking the configured Android pilot..."
    # Pin the build JVM as well as JAVA_HOME so a user-level Gradle property
    # cannot silently select a different JDK for the single-use daemon.
    & .\gradlew.bat "-Dorg.gradle.java.home=$JdkPath" --no-daemon testDebugUnitTest lintDebug assembleDebug
    if ($LASTEXITCODE -ne 0) { throw "Android build failed. Keep the first error shown above; no new APK is confirmed." }
    $apkPath = Join-Path $PSScriptRoot "app\build\outputs\apk\debug\app-debug.apk"
    if (-not (Test-Path $apkPath)) { throw "Build completed but the expected APK was not found." }
    Write-Host "APK created: $apkPath"
    Get-FileHash -Algorithm SHA256 $apkPath
    Write-Host "This is a debug-signed pilot. An in-place update requires the previous APK's signing key."
}
finally {
    Pop-Location
    $env:JAVA_HOME = $previousJava
    $env:ANDROID_HOME = $previousSdk
    $env:PATH = $previousPath
}
