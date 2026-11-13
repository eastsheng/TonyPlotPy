param([string]$IsccPath)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

if (-not $IsccPath) {
    $IsccPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}
if (-not $IsccPath) {
    $IsccPath = @(${env:ProgramFiles(x86)}, $env:ProgramFiles, (Join-Path $env:LOCALAPPDATA 'Programs')) |
        Where-Object { $_ } |
        ForEach-Object { Join-Path $_ 'Inno Setup 6\ISCC.exe' } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}
if (-not $IsccPath) { throw 'Install Inno Setup 6 or pass -IsccPath.' }
$IsccPath = (Resolve-Path -LiteralPath $IsccPath).Path

Push-Location $project
try {
    $version = py -c 'from src.version import APP_VERSION; print(APP_VERSION)'
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Cannot read APP_VERSION.' }
    py -c 'import sys; assert sys.maxsize > 2**32'
    if ($LASTEXITCODE -ne 0) { throw 'Use 64-bit Windows Python.' }

    $build = Join-Path $project '.installer-build'
    $output = Join-Path $project 'installer-output'
    New-Item -ItemType Directory -Force -Path $build | Out-Null
    $assets = (Join-Path $project 'imgs') + [IO.Path]::PathSeparator + 'imgs'
    $icon = Join-Path $project 'imgs\tonyplotpy.ico'
    py -m PyInstaller --noconfirm --windowed --onedir --noupx --name TonyPlotPy `
        --icon $icon --add-data $assets `
        --specpath $build --workpath "$build\work" --distpath "$build\dist" `
        'tonyplotpy.py'
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }

    & $IsccPath "/DAppVersion=$version" "/DProjectDir=$project" "/DBundleDir=$build\dist\TonyPlotPy" `
        "/O$output" (Join-Path $PSScriptRoot 'TonyPlotPy.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup build failed.' }
    Get-Item -LiteralPath (Join-Path $output "TonyPlotPy-Setup-$version-x64.exe")
} finally {
    Pop-Location
}
