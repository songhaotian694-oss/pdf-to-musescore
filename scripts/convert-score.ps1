[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InputPdf,
    [string]$OutputDirectory,
    [switch]$ExportMidi,
    [switch]$OpenInMuseScore,
    [bool]$KeepIntermediate = $false,
    [switch]$Force,
    [string]$AudiverisPath,
    [string]$MuseScorePath,
    [string]$PdfInfoPath,
    [string]$TessdataDirectory,
    [string]$SelectionPlan,
    [string]$GroupId,
    [string]$ReferenceMscz,
    [string]$PythonPath,
    [ValidateSet('draft','validated')][string]$OutputMode = 'draft',
    [ValidateSet('auto','original')][string]$RecognitionProfile = 'auto',
    [ValidateSet('reflow','source')][string]$LayoutMode = 'reflow',
    [ValidateRange(30,7200)][int]$TimeoutSeconds = 1800
)
. "$PSScriptRoot/common.ps1"
$dir = $null
$report = [ordered]@{schemaVersion=6; status='failed'; outputMode=$OutputMode; recognitionProfile=$RecognitionProfile; selectedRecognitionProfile=$null; recognitionAttempts=@(); referenceMscz=$null; referenceBaseline=$null; measureNumberValidation=$null; correctionWorklist=$null; acceptancePassed=$false; draftUsable=$false; inputPdf=$InputPdf; outputDirectory=$null; startedUtc=[datetime]::UtcNow.ToString('o'); finishedUtc=$null; error=''; warnings=@(Get-CorrectionWarnings); candidates=@(); dependencies=@{}; preflight=$null; selection=$null; contentValidation=$null; playbackAssignment=$null; layoutAssignment=$null; verification=$null; cleanup=[ordered]@{requested=(-not $KeepIntermediate); performed=$false; reason='pending'; removed=@(); retained=@()}}
try {
    $InputPdf = Assert-AbsolutePath $InputPdf
    $parent = if ($OutputDirectory) { Assert-AbsolutePath $OutputDirectory } else { Split-Path $InputPdf -Parent }
    [void][IO.Directory]::CreateDirectory($parent)
    $name = [IO.Path]::GetFileNameWithoutExtension($InputPdf) + '-musescore-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
    $dir = Join-Path $parent $name
    New-Item -ItemType Directory -Path $dir -ErrorAction Stop | Out-Null
    $report.outputDirectory = $dir
    if ($Force) { $report.warnings += '-Force does not enable overwriting; a new run directory was created.' }
    $pdf = Find-ScoreTool PdfInfo $PdfInfoPath
    $inputInfo = Get-PdfDetails $InputPdf $pdf
    if (-not $pdf) { throw 'Missing pdfinfo: install Poppler or pass -PdfInfoPath before conversion.' }
    $python = Find-ScoreTool Python $PythonPath
    if (-not $python) { throw 'Missing Python for mandatory page preflight. Configure Python in config.local.json with pypdf, pypdfium2, numpy and Pillow installed.' }
    $prepareArgs = @('-X','utf8',"$PSScriptRoot/score-structure.py",'prepare','--input',$InputPdf,'--out',$dir)
    if ($SelectionPlan) { $prepareArgs += @('--plan',(Assert-AbsolutePath $SelectionPlan)) }
    if ($GroupId) { $prepareArgs += @('--group',$GroupId) }
    $prepared = Invoke-ScoreProcess $python $prepareArgs 300 $dir 'preflight'
    if (Test-Path -LiteralPath (Join-Path $dir 'preflight.json')) { $report.preflight = Join-Path $dir 'preflight.json' }
    if ($prepared.exitCode -eq 2) {
        $report.status = 'needs_selection'
        throw 'OMR has NOT run. Inspect ALL source thumbnails and preflight.json, create a reviewed selection plan, then convert one page group at a time. Mixed score/parts require user selection.'
    }
    if ($prepared.exitCode -ne 0) { throw "Page preflight/selection failed: $($prepared.stdout) $($prepared.stderr)" }
    $selection = $prepared.stdout | ConvertFrom-Json
    $report.selection = $selection
    $omrInput = $selection.selectedPdf
    $a = Find-ScoreTool Audiveris $AudiverisPath
    $m = Find-ScoreTool MuseScore $MuseScorePath
    $report.dependencies = @{audiveris=$a; musescore=$m; pdfinfo=$pdf; python=$python}
    if (-not $a) { throw 'Audiveris is missing. Install it from https://github.com/Audiveris/audiveris/releases and run detect-dependencies.ps1, or pass -AudiverisPath.' }
    $omr = Join-Path $dir 'audiveris'
    [void][IO.Directory]::CreateDirectory($omr)
    # Keep application cache/logs within this run; change child environment only.
    $appData = Join-Path $dir 'runtime-data'
    [void][IO.Directory]::CreateDirectory($appData)
    $childEnv = @{APPDATA=$appData; LOCALAPPDATA=$appData; TEMP=$appData; TMP=$appData}
    if (-not $TessdataDirectory) {
        $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../config.local.json') -Raw -Encoding UTF8 -ErrorAction SilentlyContinue | ConvertFrom-Json
        if ($config -and $config.PSObject.Properties['Tessdata']) { $TessdataDirectory = $config.Tessdata }
    }
    if ($TessdataDirectory) {
        $TessdataDirectory = Assert-AbsolutePath $TessdataDirectory
        if (-not (Test-Path -LiteralPath (Join-Path $TessdataDirectory 'eng.traineddata'))) { throw 'Configured Tesseract data directory has no eng.traineddata.' }
        $childEnv.TESSDATA_PREFIX = $TessdataDirectory
    }
    $referenceBaseline = $null
    if ($ReferenceMscz) {
        $ReferenceMscz = Assert-AbsolutePath $ReferenceMscz
        if ([IO.Path]::GetExtension($ReferenceMscz) -ine '.mscz') { throw '-ReferenceMscz must point to an MSCZ file explicitly designated by the user as corrected.' }
        if (-not $m) { throw 'MuseScore is required to read the user-designated reference MSCZ.' }
        $referenceXml = Join-Path $dir 'reference-score.musicxml'
        $referenceExport = Invoke-ScoreProcess $m @('-o',$referenceXml,$ReferenceMscz) 300 $dir 'reference-musicxml-export'
        if ($referenceExport.exitCode -ne 0 -or -not (Test-Path -LiteralPath $referenceXml)) { throw 'Could not export MusicXML from the reference MSCZ.' }
        $referenceBuild = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-structure.py",'reference','--xml',$referenceXml,'--reference-score',$ReferenceMscz,'--out',$dir) 60 $dir 'reference-baseline'
        if ($referenceBuild.exitCode -ne 0 -or -not $referenceBuild.stdout) { throw "Could not build the reference MSCZ timeline: $($referenceBuild.stderr)" }
        $referenceBaseline = Join-Path $dir 'reference-baseline.json'
        $report.referenceMscz = $ReferenceMscz
        $report.referenceBaseline = $referenceBuild.stdout | ConvertFrom-Json
    }
    $runRecognition = {
        param([string]$Profile, [string]$RecognitionInput)
        $attemptDir = Join-Path $omr $Profile
        [void][IO.Directory]::CreateDirectory($attemptDir)
        $run = Invoke-ScoreProcess $a @('-batch','-transcribe','-export','-save','-output',$attemptDir,'--',$RecognitionInput) $TimeoutSeconds $dir ("audiveris-$Profile") $childEnv
        $attempt = [ordered]@{profile=$Profile; input=$RecognitionInput; outputDirectory=$attemptDir; exitCode=$run.exitCode; timedOut=$run.timedOut; status='failed'; musicXml=$null; qualityPenalty=$null; errors=@()}
        if (($run.stdout + $run.stderr) -match 'Could not initialize TessBaseAPI|couldn.t load any languages|No installed OCR languages|No OCR is available') {
            $report.warnings += "Text OCR unavailable in $Profile attempt: titles and lyrics may be missing."
        }
        if ($run.exitCode -ne 0) {
            $attempt.errors += "Audiveris exit $($run.exitCode), timeout=$($run.timedOut)."
            return [pscustomobject]@{attempt=$attempt; xmls=@(); contentProcess=$null; content=$null}
        }
        $xmls = @(Get-ChildItem -LiteralPath $attemptDir -Recurse -File | Where-Object { $_.Extension -in @('.mxl','.musicxml') })
        if ($xmls.Count -eq 0) {
            $attempt.errors += 'Audiveris produced no MXL/MusicXML.'
            return [pscustomobject]@{attempt=$attempt; xmls=@(); contentProcess=$null; content=$null}
        }
        foreach ($candidateXml in $xmls) {
            try {
                $details = Get-MusicXmlDetails $candidateXml.FullName
                $details | Add-Member -NotePropertyName recognitionProfile -NotePropertyValue $Profile
                $report.candidates += $details
            } catch { $report.candidates += @{path=$candidateXml.FullName; bytes=$candidateXml.Length; recognitionProfile=$Profile; validationError=$_.Exception.Message} }
        }
        if ($xmls.Count -gt 1) {
            $attempt.status = 'multiple_outputs'
            $attempt.errors += 'Multiple MusicXML outputs require movement selection.'
            return [pscustomobject]@{attempt=$attempt; xmls=$xmls; contentProcess=$null; content=$null}
        }
        $candidateOut = Join-Path $dir ("candidate-$Profile")
        [void][IO.Directory]::CreateDirectory($candidateOut)
        $checkArgs = @('-X','utf8',"$PSScriptRoot/score-structure.py",'check','--xml',$xmls[0].FullName,'--selection',(Join-Path $dir 'selection.json'),'--out',$candidateOut)
        if ($referenceBaseline) { $checkArgs += @('--reference',$referenceBaseline) }
        $checked = Invoke-ScoreProcess $python $checkArgs 60 $dir ("content-$Profile")
        $contentJson = if ($checked.stdout) { $checked.stdout | ConvertFrom-Json } else { $null }
        $attempt.musicXml = $xmls[0].FullName
        $attempt.status = if ($checked.exitCode -eq 0) { 'passed_checked_structure' } elseif ($checked.exitCode -eq 3) { 'failed_content_validation' } else { 'failed_inspection' }
        if ($contentJson -and $contentJson.PSObject.Properties['qualityPenalty']) { $attempt.qualityPenalty = [int64]$contentJson.qualityPenalty }
        if ($contentJson -and $contentJson.errors) { $attempt.errors += @($contentJson.errors) }
        return [pscustomobject]@{attempt=$attempt; xmls=$xmls; contentProcess=$checked; content=$contentJson}
    }
    $original = & $runRecognition 'original' $omrInput
    $report.recognitionAttempts += $original.attempt
    if ($original.attempt.status -eq 'multiple_outputs') {
        $report.status = 'needs_selection'
        throw 'Audiveris produced multiple movements. Review candidates in report.json; nothing was silently selected.'
    }
    $chosen = if ($original.xmls.Count -eq 1 -and $original.contentProcess.exitCode -in @(0,3)) { $original } else { $null }
    if ($RecognitionProfile -eq 'auto' -and (-not $chosen -or $chosen.contentProcess.exitCode -eq 3)) {
        $preparedInput = Join-Path $dir 'omr-input-grayscale-400.pdf'
        $preprocess = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/prepare-omr-input.py",'--input',$omrInput,'--output',$preparedInput,'--report',(Join-Path $dir 'omr-input-grayscale-400.json'),'--dpi','400') 600 $dir 'omr-input-grayscale-400'
        if ($preprocess.exitCode -eq 0 -and (Test-Path -LiteralPath $preparedInput)) {
            $fallback = & $runRecognition 'grayscale-400' $preparedInput
            $report.recognitionAttempts += $fallback.attempt
            if ($fallback.attempt.status -eq 'multiple_outputs') {
                $report.warnings += 'Grayscale fallback produced multiple movements and was not selected automatically.'
            } elseif ($fallback.xmls.Count -eq 1 -and $fallback.contentProcess.exitCode -in @(0,3)) {
                if (-not $chosen -or $fallback.contentProcess.exitCode -eq 0 -or
                    ($chosen.contentProcess.exitCode -eq 3 -and $fallback.attempt.qualityPenalty -lt $chosen.attempt.qualityPenalty)) { $chosen = $fallback }
            }
        } else { $report.warnings += 'Automatic grayscale fallback could not be prepared; original diagnostics were retained.' }
    }
    if (-not $chosen) { throw 'Audiveris produced no parseable single MusicXML candidate in either recognition attempt. Inspect retained OMR and logs.' }
    $chosenXml = $chosen.xmls[0].FullName
    $xml = Join-Path $dir $(if ([IO.Path]::GetExtension($chosenXml) -ieq '.mxl') { 'score.mxl' } else { 'score.musicxml' })
    Copy-Item -LiteralPath $chosenXml -Destination $xml -ErrorAction Stop
    $content = $chosen.contentProcess
    $report.contentValidation = $chosen.content
    $report.selectedRecognitionProfile = $chosen.attempt.profile
    $report.contentValidation | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $dir 'content-musicxml.json') -Encoding UTF8
    $report.warnings += "Selected OMR attempt: $($chosen.attempt.profile). Candidate choice uses reviewed structure only, not note accuracy."
    if ($content.exitCode -ne 0) {
        if ($content.exitCode -ne 3) { throw "MusicXML content inspection failed; the draft cannot safely continue. See content-musicxml logs: $($content.stdout) $($content.stderr)" }
        if ($OutputMode -eq 'validated') {
            $report.status = 'failed_content_validation'
            throw "MusicXML structure gate blocked validated exports. See content-musicxml.json/stdout.log: $($content.stdout)"
        }
        $report.warnings += 'Draft mode: recognized MusicXML has content-validation errors. A correction draft will still be generated; see content-musicxml.json.'
    }
    $report.warnings += @($report.contentValidation.warnings)
    $omrFiles = @(Get-ChildItem -LiteralPath $omr -Recurse -Filter *.omr)
    if ($omrFiles.Count -eq 0) { $report.warnings += 'Audiveris did not save an OMR project; MusicXML and logs are retained.' }
    if (-not $m) { throw 'MuseScore is missing. MusicXML/OMR are retained in audiveris; install MuseScore Studio 4 and use the documented resume commands.' }
    @{schemaVersion=6; startedUtc=$report.startedUtc; outputMode=$OutputMode; recognitionProfile=$RecognitionProfile; selectedRecognitionProfile=$report.selectedRecognitionProfile; referenceMscz=$report.referenceMscz; referenceBaseline=$referenceBaseline; inputPdf=$InputPdf; inputPages=$inputInfo.pages; sourceSha256=$selection.sourceSha256; sourcePages=$selection.sourcePages; selection=(Join-Path $dir 'selection.json'); musicXml=$xml; layoutMode=$LayoutMode; exportMidi=[bool]$ExportMidi} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $dir 'run.json') -Encoding UTF8
    $score = Join-Path $dir 'score.mscz'
    $imported = Join-Path $dir 'score-imported.mscz'
    $assigned = Join-Path $dir 'score-playback.mscz'
    $result = Invoke-ScoreProcess $m @('-o',$imported,$xml) 300 $dir 'musescore-import'
    if ($result.exitCode -ne 0 -or -not (Test-Path -LiteralPath $imported)) { throw 'MuseScore import failed; inspect musescore-import logs.' }
    $assignment = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-playback.py",'apply','--score',$imported,'--selection',(Join-Path $dir 'selection.json'),'--output',$assigned,'--report',(Join-Path $dir 'playback-assignment.json')) 60 $dir 'playback-assignment'
    if ($assignment.stdout) { $report.playbackAssignment = $assignment.stdout | ConvertFrom-Json }
    $layoutInput = $assigned
    if ($assignment.exitCode -ne 0) {
        if ($OutputMode -eq 'validated') {
            $report.status = 'failed_playback_validation'
            throw "Playback assignment blocked validated exports: $($assignment.stdout) $($assignment.stderr)"
        }
        $layoutInput = $imported
        $report.warnings += 'Draft mode: playback assignment failed. The MSCZ uses the imported playback setup and requires correction; see playback-assignment.json.'
    }
    $laidOut = Join-Path $dir 'score-layout.mscz'
    $layout = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-layout.py",'apply','--score',$layoutInput,'--output',$laidOut,'--mode',$LayoutMode,'--report',(Join-Path $dir 'layout-assignment.json')) 60 $dir 'layout-assignment'
    if ($layout.stdout) { $report.layoutAssignment = $layout.stdout | ConvertFrom-Json }
    $finalInput = $laidOut
    if ($layout.exitCode -ne 0) {
        if ($OutputMode -eq 'validated') {
            $report.status = 'failed_layout_validation'
            throw "Layout preparation blocked validated exports: $($layout.stdout) $($layout.stderr)"
        }
        $finalInput = $layoutInput
        $report.warnings += 'Draft mode: layout preparation failed. The MSCZ keeps the preceding layout and requires correction; see layout-assignment.json.'
    }
    $steps = @(@{label='musescore-save-playback'; input=$finalInput; output=$score}, @{label='musescore-proof'; input=$score; output=(Join-Path $dir 'score-proof.pdf')})
    if ($ExportMidi) { $steps += @{label='musescore-midi'; input=$score; output=(Join-Path $dir 'score.mid')} }
    foreach ($step in $steps) {
        $result = Invoke-ScoreProcess $m @('-o',$step.output,$step.input) 300 $dir $step.label
        if ($result.exitCode -ne 0 -or -not (Test-Path -LiteralPath $step.output) -or (Get-Item -LiteralPath $step.output).Length -eq 0) { throw "$($step.label) failed (exit $($result.exitCode)); see its stdout/stderr logs. MusicXML retained." }
    }
    # Invoke verifier in a child PowerShell so its exit cannot terminate report generation.
    $psExe = (Get-Process -Id $PID).Path
    $verified = Invoke-ScoreProcess $psExe @('-NoProfile','-ExecutionPolicy','Bypass','-File',"$PSScriptRoot/verify-output.ps1",'-RunDirectory',$dir,'-MuseScorePath',$m,'-PdfInfoPath',$pdf,'-PythonPath',$python,'-OutputMode',$OutputMode) 1200 $dir 'verification'
    if ($verified.stdout) { $report.verification = $verified.stdout | ConvertFrom-Json }
    if ($report.verification) {
        $report.contentValidation = $report.verification.contentValidation
        if ($report.verification.savedContentValidation) { $report.measureNumberValidation = $report.verification.savedContentValidation.measureNumberValidation }
        $verificationPath = Join-Path $dir 'verification.json'
        $report.verification | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $verificationPath -Encoding UTF8
        $worklistPath = Join-Path $dir 'correction-worklist.json'
        $worklist = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-correction.py",'--verification',$verificationPath,'--selection',(Join-Path $dir 'selection.json'),'--output',$worklistPath) 60 $dir 'correction-worklist'
        if ($worklist.exitCode -eq 0 -and $worklist.stdout) { $report.correctionWorklist = $worklist.stdout | ConvertFrom-Json }
        else { $report.warnings += 'Could not build the correction worklist; inspect verification.json directly.' }
    }
    if ($verified.exitCode -ne 0) {
        if ($verified.exitCode -eq 3) { $report.status = 'failed_content_validation' }
        if ($verified.exitCode -eq 4) { $report.status = 'failed_playback_validation' }
        if ($verified.exitCode -eq 5) { $report.status = 'failed_layout_validation' }
        throw 'Output verification failed; inspect verification.stdout.log and verification.stderr.log. Generated files are diagnostic drafts, not accepted deliverables.'
    }
    $report.warnings = @(@($report.warnings) + @($report.verification.warnings) | Select-Object -Unique)
    $report.draftUsable = $true
    if ($OutputMode -eq 'draft') {
        $report.status = if ($report.verification.status -eq 'draft_with_validation_issues') { 'editable_draft_needs_correction' } else { 'editable_draft_ready_for_review' }
    } else {
        $report.acceptancePassed = $true
        $report.status = 'completed_needs_manual_review'
    }
    if ($OpenInMuseScore) { Start-Process -FilePath $m -ArgumentList ('"' + $score + '"') | Out-Null }
} catch { $report.error = $_.Exception.Message }
$cleanupReady = $report.status -in @('completed_needs_manual_review','editable_draft_ready_for_review')
if ($dir -and -not $KeepIntermediate) {
    if ($cleanupReady) {
        try {
            $cleanupJson = & "$PSScriptRoot/cleanup-run.ps1" -RunDirectory $dir
            $report.cleanup = $cleanupJson | ConvertFrom-Json
        } catch {
            $report.cleanup.reason = 'cleanup_failed'
            $report.warnings += "Intermediate cleanup failed: $($_.Exception.Message)"
        }
    } else {
        $report.cleanup.reason = 'retained_for_selection_failure_or_correction'
    }
} elseif ($KeepIntermediate) {
    $report.cleanup.reason = 'keep_intermediate_requested'
}
$report.finishedUtc = [datetime]::UtcNow.ToString('o')
if ($dir) { Write-ScoreReport $report $dir }
$report | ConvertTo-Json -Depth 12
if ($report.status -eq 'needs_selection') { exit 2 }
if ($report.status -eq 'failed_content_validation') { exit 3 }
if ($report.status -eq 'failed_playback_validation') { exit 4 }
if ($report.status -eq 'failed_layout_validation') { exit 5 }
if ($report.status -notin @('completed_needs_manual_review','editable_draft_ready_for_review','editable_draft_needs_correction')) { exit 1 }
