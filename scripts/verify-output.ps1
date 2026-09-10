[CmdletBinding()]
param([Parameter(Mandatory)][string]$RunDirectory, [string]$MuseScorePath, [string]$PdfInfoPath, [string]$PythonPath)
. "$PSScriptRoot/common.ps1"
$result = [ordered]@{status='failed'; technicalValidation='failed'; contentValidation=$null; playbackValidation=@(); errors=@(); warnings=@(Get-CorrectionWarnings); files=@(); musicXml=$null; proofPages=$null; reopened=$false}
try {
    $dir = Assert-AbsolutePath $RunDirectory
    $manifest = Get-Content -LiteralPath (Join-Path $dir 'run.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $since = [datetime]::Parse($manifest.startedUtc).ToUniversalTime()
    $required = @($manifest.musicXml, (Join-Path $dir 'score.mscz'), (Join-Path $dir 'score-proof.pdf'))
    if ($manifest.exportMidi) { $required += Join-Path $dir 'score.mid' }
    foreach ($path in $required) {
        $f = Get-Item -LiteralPath $path
        if ($f.Length -eq 0 -or $f.LastWriteTimeUtc -lt $since.AddSeconds(-2)) { throw "Empty or stale output: $path" }
        $result.files += @{path=$f.FullName; bytes=$f.Length; modifiedUtc=$f.LastWriteTimeUtc.ToString('o')}
    }
    $result.musicXml = Get-MusicXmlDetails $manifest.musicXml
    if ($result.musicXml.lyrics -gt 0) { $result.warnings += 'Lyrics detected: check syllables, hyphens, melismas and alignment.' }
    if ($result.musicXml.voices -gt 1 -or $result.musicXml.parts -gt 1) { $result.warnings += 'Multiple voices/parts detected: check voice assignments, rests and synchronization.' }
    $pdf = Find-ScoreTool PdfInfo $PdfInfoPath
    if (-not $pdf) { throw 'pdfinfo is required to verify the proof PDF page count. Set -PdfInfoPath.' }
    $result.proofPages = (Get-PdfDetails (Join-Path $dir 'score-proof.pdf') $pdf).pages
    $m = Find-ScoreTool MuseScore $MuseScorePath
    if (-not $m) { throw 'MuseScore missing; cannot verify reopening MSCZ.' }
    $reopen = Join-Path $dir ('verify-reopen-' + [guid]::NewGuid().ToString('N') + '.musicxml')
    $r = Invoke-ScoreProcess $m @('-o',$reopen,(Join-Path $dir 'score.mscz')) 300 $dir 'verify-reopen'
    if ($r.exitCode -ne 0) { throw "MuseScore reopen failed (exit $($r.exitCode)); see verify-reopen.stderr.log." }
    [void](Get-MusicXmlDetails $reopen)
    $result.reopened = $true
    if ($manifest.exportMidi) {
        $bytes = [IO.File]::ReadAllBytes((Join-Path $dir 'score.mid'))
        if ($bytes.Length -lt 14 -or [Text.Encoding]::ASCII.GetString($bytes,0,4) -ne 'MThd') { throw 'Invalid MIDI header.' }
    }
    $result.technicalValidation = 'passed'
    if (-not $manifest.PSObject.Properties['selection']) { throw 'Legacy run has no reviewed page selection. Technical files are valid, but content validation cannot pass until source pages are reviewed.' }
    $python = Find-ScoreTool Python $PythonPath
    if (-not $python) { throw 'Python missing for mandatory all-page content validation.' }
    $contentDir = Join-Path $dir ('structure-verify-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($contentDir)
    $content = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-structure.py",'check','--xml',$manifest.musicXml,'--selection',$manifest.selection,'--proof',(Join-Path $dir 'score-proof.pdf'),'--out',$contentDir) 300 $dir 'content-proof'
    if ($content.stdout) { $result.contentValidation = $content.stdout | ConvertFrom-Json }
    if ($content.exitCode -ne 0) {
        $result.status = 'failed_content_validation'
        throw "Content validation blocked acceptance: $($content.stdout) $($content.stderr)"
    }
    $result.warnings += @($result.contentValidation.warnings)
    # Validate the final saved score as well as the original recognition output.
    $savedContentDir = Join-Path $dir ('saved-content-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($savedContentDir)
    $savedContent = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-structure.py",'check','--xml',$reopen,'--selection',$manifest.selection,'--out',$savedContentDir) 60 $dir 'content-saved-score'
    if ($savedContent.stdout) { $result['savedContentValidation'] = $savedContent.stdout | ConvertFrom-Json }
    if ($savedContent.exitCode -ne 0) {
        $result.status = 'failed_content_validation'
        throw "Final MSCZ content differs from reviewed expectations: $($savedContent.stdout) $($savedContent.stderr)"
    }
    # Always regenerate MIDI from the final saved MSCZ, even without -ExportMidi.
    $result.status = 'failed_playback_validation'
    $assignment = Join-Path $dir 'playback-assignment.json'
    if (-not (Test-Path -LiteralPath $assignment)) { throw 'Missing playback assignment. Repair a copy of this legacy score and rerun verification.' }
    $midi = Join-Path $dir ('verify-playback-' + [guid]::NewGuid().ToString('N') + '.mid')
    $export = Invoke-ScoreProcess $m @('-o',$midi,(Join-Path $dir 'score.mscz')) 300 $dir 'verify-midi-export'
    if ($export.exitCode -ne 0 -or -not (Test-Path -LiteralPath $midi)) { throw 'Cannot export MIDI from the final MSCZ for playback verification.' }
    $midiFiles = @($midi)
    if ($manifest.exportMidi) { $midiFiles += Join-Path $dir 'score.mid' }
    foreach ($midiFile in $midiFiles) {
        $playbackReport = Join-Path $dir ('playback-verify-' + [guid]::NewGuid().ToString('N') + '.json')
        $playback = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-playback.py",'verify','--score',(Join-Path $dir 'score.mscz'),'--selection',$manifest.selection,'--assignment',$assignment,'--midi',$midiFile,'--report',$playbackReport) 60 $dir 'playback-verify'
        if ($playback.stdout) { $result.playbackValidation += ($playback.stdout | ConvertFrom-Json) }
        if ($playback.exitCode -ne 0) { throw "Playback validation blocked acceptance: $($playback.stdout) $($playback.stderr)" }
    }
    $layoutAssignment = Join-Path $dir 'layout-assignment.json'
    if (Test-Path -LiteralPath $layoutAssignment) {
        $result.status = 'failed_layout_validation'
        $appliedLayout = Get-Content -LiteralPath $layoutAssignment -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.PSObject.Properties['layoutMode'] -and $appliedLayout.mode -ne $manifest.layoutMode) { throw 'Applied layout mode differs from the requested mode.' }
        $layoutReport = Join-Path $dir ('layout-verify-' + [guid]::NewGuid().ToString('N') + '.json')
        $layout = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-layout.py",'verify','--score',(Join-Path $dir 'score.mscz'),'--assignment',$layoutAssignment,'--report',$layoutReport) 60 $dir 'layout-verify'
        if ($layout.stdout) { $result['layoutValidation'] = $layout.stdout | ConvertFrom-Json }
        if ($layout.exitCode -ne 0) { throw "Layout verification failed: $($layout.stdout) $($layout.stderr)" }
    } elseif ($manifest.PSObject.Properties['layoutMode']) {
        $result.status = 'failed_layout_validation'
        throw 'Missing layout-assignment.json for a run with an explicit layout policy.'
    } else { $result.warnings += 'Legacy run: explicit layout break policy has not been verified.' }
    $result.status = 'passed'
} catch { $result.errors += $_.Exception.Message }
$result | ConvertTo-Json -Depth 8
if ($result.status -eq 'failed_content_validation') { exit 3 }
if ($result.status -eq 'failed_playback_validation') { exit 4 }
if ($result.status -eq 'failed_layout_validation') { exit 5 }
if ($result.status -ne 'passed') { exit 1 }
