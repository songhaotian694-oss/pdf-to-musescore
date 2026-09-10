[CmdletBinding()]
param([string]$InputPdf, [string]$OutputDirectory, [string]$AudiverisPath, [string]$MuseScorePath, [string]$PdfInfoPath, [string]$PythonPath)
. "$PSScriptRoot/common.ps1"
$a = Find-ScoreTool Audiveris $AudiverisPath
$m = Find-ScoreTool MuseScore $MuseScorePath
$pdf = Find-ScoreTool PdfInfo $PdfInfoPath
$python = Find-ScoreTool Python $PythonPath
$result = [ordered]@{ Audiveris=@{exists=[bool]$a; path=$a; version=$null}; MuseScore=@{exists=[bool]$m; path=$m; version=$null}; Java=@{required=$null; bundled=$false; version=$null}; PdfInfo=@{exists=[bool]$pdf; path=$pdf}; inputPdf=$null; output=@{path=$OutputDirectory; writable=$null}; errors=@() }
$result.Python = @{exists=[bool]$python; path=$python; structurePackagesReady=$false}
if ($python) {
    try {
        $check = Invoke-ScoreProcess $python @('-c','import pypdf, pypdfium2, numpy, PIL') 30
        $result.Python.structurePackagesReady = $check.exitCode -eq 0
        if ($check.exitCode -ne 0) { $result.errors += 'Python needs pypdf, pypdfium2, numpy and Pillow for required structural preflight.' }
    } catch { $result.errors += $_.Exception.Message }
} else { $result.errors += 'Python missing for required structural preflight.' }
if ($a) {
    $release = Join-Path (Split-Path $a) 'runtime/release'
    $result.Java.bundled = Test-Path -LiteralPath $release
    $result.Java.required = -not $result.Java.bundled
    if ($result.Java.bundled) { $result.Java.version = (Get-Content -LiteralPath $release | Select-String '^JAVA_VERSION=') -replace '^JAVA_VERSION="?|"$','' }
    $result.Audiveris.version = (Get-Item -LiteralPath $a).VersionInfo.ProductVersion
    if (-not $result.Audiveris.version) {
        try { $version = Invoke-ScoreProcess $a @('-version') 30; if (($version.stdout + $version.stderr) -match 'Version:\s+(\S+)') { $result.Audiveris.version = $Matches[1] } } catch { $result.errors += $_.Exception.Message }
    }
}
if ($m) { try { $version = Invoke-ScoreProcess $m @('--version') 30; $result.MuseScore.version = ($version.stdout + $version.stderr).Trim() } catch { $result.errors += $_.Exception.Message } }
if ($InputPdf) {
    $result.inputPdf = @{path=$InputPdf; exists=(Test-Path -LiteralPath $InputPdf -PathType Leaf); bytes=$null; pages=$null; pageCountVerified=$false}
    try { $result.inputPdf = Get-PdfDetails $InputPdf $pdf } catch { $result.errors += $_.Exception.Message }
}
if ($OutputDirectory) {
    try {
        $dir = Assert-AbsolutePath $OutputDirectory
        # Check nearest existing ancestor without creating the requested output.
        while (-not (Test-Path -LiteralPath $dir -PathType Container)) { $dir = Split-Path $dir -Parent; if (-not $dir) { throw 'No existing output ancestor.' } }
        $probe = Join-Path $dir ('.pdf-to-musescore-probe-' + [guid]::NewGuid().ToString('N'))
        $f = [IO.File]::Open($probe, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None); $f.Dispose()
        Remove-Item -LiteralPath $probe
        $result.output.writable = $true
    } catch { $result.output.writable = $false; $result.errors += $_.Exception.Message }
}
$result | ConvertTo-Json -Depth 6
if ($result.errors.Count) { exit 1 }
