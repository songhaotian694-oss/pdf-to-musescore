[CmdletBinding()]
param([Parameter(Mandatory)][string]$FixtureDirectory, [Parameter(Mandatory)][string]$ResultsDirectory, [string]$MuseScorePath, [string]$PdfInfoPath, [string[]]$TestName)
. "$PSScriptRoot/../scripts/common.ps1"
$psExe = (Get-Process -Id $PID).Path
$converter = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../scripts/convert-score.ps1'))
[void][IO.Directory]::CreateDirectory($ResultsDirectory)
$sentinel = Join-Path $ResultsDirectory 'score.mscz'
if (-not (Test-Path -LiteralPath $sentinel)) { [IO.File]::WriteAllText($sentinel,'PREEXISTING OUTPUT - MUST NOT CHANGE') }
$sentinelHash = (Get-FileHash -LiteralPath $sentinel).Hash
$cases = @(
    @{name='single-chinese-path-midi'; file='single-melody.pdf'; extra=@('-ExportMidi'); success=$true},
    @{name='two-page-piano'; file='two-page-piano.pdf'; extra=@(); success=$true},
    @{name='lyrics'; file='lyrics-melody.pdf'; extra=@(); success=$true},
    @{name='existing-output'; file='single-melody.pdf'; extra=@('-Force'); success=$true},
    @{name='missing-audiveris'; file='single-melody.pdf'; extra=@('-AudiverisPath',(Join-Path $ResultsDirectory 'missing-audiveris.exe')); success=$false},
    @{name='missing-musescore'; file='single-melody.pdf'; extra=@('-MuseScorePath',(Join-Path $ResultsDirectory 'missing-musescore.exe')); success=$false},
    @{name='invalid-pdf'; file='invalid.pdf'; extra=@(); success=$false},
    @{name='text-only'; file='text-only.pdf'; extra=@(); success=$false}
)
$records = @()
if ($TestName) {
    foreach ($name in $TestName) { if ($name -notin $cases.name) { throw "Unknown test name: $name" } }
    $cases = @($cases | Where-Object { $_.name -in $TestName })
}
foreach ($case in $cases) {
    $params = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$converter,'-InputPdf',(Join-Path $FixtureDirectory $case.file),'-OutputDirectory',$ResultsDirectory) + $case.extra
    # Expectations are from our original fixture generator, not from OMR output.
    if ($case.file -notin @('invalid.pdf','text-only.pdf')) {
        $pages = @(if ($case.file -eq 'two-page-piano.pdf') { 1; 2 } else { 1 })
        $measures = if ($case.file -eq 'two-page-piano.pdf') { 16 } else { 8 }
        $clefs = @(if ($case.file -eq 'two-page-piano.pdf') { 'G'; 'F' } else { 'G' })
        $planPath = Join-Path $ResultsDirectory ($case.name + '-plan-' + [guid]::NewGuid().ToString('N') + '.json')
        @{schemaVersion=2; sourceSha256=(Get-FileHash -LiteralPath (Join-Path $FixtureDirectory $case.file)).Hash.ToLowerInvariant(); reviewed=$true; reviewedPages=$pages; selectionBasis='unambiguous_visual_review'; groups=@(@{id='fixture';pages=$pages;expectedParts=1;playbackInstruments=@('piano');lyricsExpected=($case.file -eq 'lyrics-melody.pdf');expectedMeasuresPerPart=@($measures);allowedClefsPerPart=@(,$clefs)})} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
        $params += @('-SelectionPlan',$planPath,'-GroupId','fixture')
    }
    if ($MuseScorePath -and $case.name -ne 'missing-musescore') { $params += @('-MuseScorePath',$MuseScorePath) }
    if ($PdfInfoPath) { $params += @('-PdfInfoPath',$PdfInfoPath) }
    $r = Invoke-ScoreProcess $psExe $params 2100 $ResultsDirectory $case.name
    $report = $null
    try { $report = $r.stdout | ConvertFrom-Json } catch {}
    $ok = if ($case.success) { $r.exitCode -eq 0 -and $report -and $report.status -eq 'completed_needs_manual_review' -and $report.verification.reopened } else { $r.exitCode -eq 1 -and $report -and $report.status -eq 'failed' -and $report.error }
    if ($case.name -eq 'missing-audiveris') { $ok = $ok -and $report.error -match 'Audiveris is missing' }
    if ($case.name -eq 'missing-musescore') { $ok = $ok -and $report.error -match 'MuseScore is missing' -and $report.candidates.Count -ge 1 }
    if ($case.name -eq 'lyrics') { $ok = $ok -and ($report.warnings -join ' ') -match 'Lyrics detected' }
    if ($case.name -eq 'two-page-piano') { $ok = $ok -and ($report.warnings -join ' ') -match 'Multiple voices/parts' }
    if ($case.name -eq 'text-only') { $ok = $r.exitCode -eq 2 -and $report.status -eq 'needs_selection' -and -not (Test-Path -LiteralPath (Join-Path $report.outputDirectory 'audiveris')) }
    $ok = $ok -and ((Get-FileHash -LiteralPath $sentinel).Hash -eq $sentinelHash)
    $files = @()
    if ($report -and $report.outputDirectory) { $files = @(Get-ChildItem -LiteralPath $report.outputDirectory -Recurse -File | Select-Object FullName,Length) }
    $records += [pscustomobject]@{test=$case.name; passed=[bool]$ok; exitCode=$r.exitCode; command=@($psExe)+$params; seconds=$r.seconds; report=$report; files=$files; stderr=$r.stderr}
    $records | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $ResultsDirectory 'test-results.json') -Encoding UTF8
    Write-Output "$($case.name): passed=$ok exit=$($r.exitCode) seconds=$($r.seconds)"
}
$records | Select-Object test,passed,exitCode,seconds | Format-Table
if (@($records | Where-Object { -not $_.passed }).Count) { exit 1 }
