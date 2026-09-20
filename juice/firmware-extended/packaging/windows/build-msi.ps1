# Builds radioberry-juice-x64.exe (via windows-Makefile) and packages it
# as an MSI with the WiX Toolset v3 (candle.exe/light.exe), same tool
# hpsdr-rs itself uses via cargo-wix. Run from the repository root
# (juice/firmware-extended), or anywhere -- this script cd's there
# itself.
#
# Deliberately does NOT bundle the FTDI CDM driver -- see
# packaging/windows/DRIVER-README.txt and main.wxs's own top-of-file
# comment for why (FTDI's driver license only permits redistributing it
# "with the Device", i.e. by a hardware seller, which this project isn't).
param(
    [string]$Version = "1.0.0"
)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
Set-Location $repoRoot

$mingwBin = "C:\ProgramData\mingw64\mingw64\bin"
if (Test-Path $mingwBin) { $env:Path = "$mingwBin;$env:Path" }

Write-Host "== Building radioberry-juice-x64.exe ==" -ForegroundColor Cyan
mingw32-make -f windows-Makefile ARCH=x64
if ($LASTEXITCODE -ne 0) { throw "windows-Makefile build failed" }

$sourceDir = Join-Path $repoRoot "dist\windows-x64"
foreach ($required in @("radioberry-juice-x64.exe", "radioberry.props", "gateware\CL016\radioberry.rbf", "gateware\CL025\radioberry.rbf")) {
    if (-not (Test-Path (Join-Path $sourceDir $required))) {
        throw "Missing expected build output: $sourceDir\$required"
    }
}

$wixDir = Join-Path $scriptDir ""
$outDir = Join-Path $repoRoot "dist"
$wixobj = Join-Path $outDir "radioberry-juice.wixobj"
$outMsi = Join-Path $outDir "radioberry-juice-$Version-x64.msi"

Write-Host "== Compiling MSI (WiX) ==" -ForegroundColor Cyan
& candle.exe -nologo `
    -dVersion="$Version" `
    -dSourceDir="$sourceDir" `
    -dPkgDir="$scriptDir" `
    -arch x64 `
    -out $wixobj `
    (Join-Path $scriptDir "main.wxs")
if ($LASTEXITCODE -ne 0) { throw "candle.exe failed" }

& light.exe -nologo `
    -ext WixUIExtension `
    -out $outMsi `
    $wixobj `
    -b $repoRoot
if ($LASTEXITCODE -ne 0) { throw "light.exe failed" }

Write-Host ""
Write-Host "Built: $outMsi" -ForegroundColor Green
