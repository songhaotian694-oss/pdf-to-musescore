[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InputPdf,
    [string]$OutputDirectory,
    [switch]$ExportMidi,
    [switch]$OpenInMuseScore,
    [bool]$KeepIntermediate = $true,
    [switch]$Force,
    [string]$AudiverisPath,
    [string]$MuseScorePath,
    [string]$PdfInfoPath,
    [string]$TessdataDirectory,
    [string]$SelectionPlan,
    [string]$GroupId,
    [string]$PythonPath,
    [ValidateSet('draft','validated')][string]$OutputMode = 'draft',
    [ValidateSet('reflow','source')][string]$LayoutMode = 'reflow',
    [ValidateRange(30,7200)][int]$TimeoutSeconds = 1800
)
. "$PSScriptRoot/common.ps1"
$dir = $null
$report = [ordered]@{schemaVersion=3; status='failed'; outputMode=$OutputMode; acceptancePassed=$false; draftUsable=$false; inputPdf=$InputPdf; outputDirectory=$null; startedUtc=[datetime]::UtcNow.ToString('o'); finishedUtc=$null; error=''; warnings=@(Get-CorrectionWarnings); candidates=@(); dependencies=@{}; preflight=$null; selection=$null; contentValidation=$null; playbackAssignment=$null; layoutAssignment=$null; verification=$null}
try {
    $InputPdf = Assert-AbsolutePath $InputPdf
    if (-not $KeepIntermediate) { throw 'Intermediate files are required for correction; keep -KeepIntermediate true.' }
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
    $result = Invoke-ScoreProcess $a @('-batch','-transcribe','-export','-save','-output',$omr,'--',$omrInput) $TimeoutSeconds $dir 'audiveris' $childEnv
    if ($result.exitCode -ne 0) { throw "Audiveris failed (exit $($result.exitCode), timeout=$($result.timedOut)); inspect audiveris.stdout.log and audiveris.stderr.log. Intermediate files retained." }
    if (($result.stdout + $result.stderr) -match 'Could not initialize TessBaseAPI|couldn.t load any languages|No installed OCR languages|No OCR is available') {
        $report.warnings += 'Text OCR unavailable: titles and lyrics may be missing. Install legacy-compatible tesseract-ocr/tessdata language data and retry if text matters.'
    }
    $xmls = @(Get-ChildItem -LiteralPath $omr -Recurse -File | Where-Object { $_.Extension -in @('.mxl','.musicxml') })
    if ($xmls.Count -eq 0) { throw 'Audiveris produced no MXL/MusicXML. Check that the PDF contains clear printed staves; inspect retained OMR/logs.' }
    foreach ($xml in $xmls) {
        try { $report.candidates += Get-MusicXmlDetails $xml.FullName }
        catch {
            $report.candidates += @{path=$xml.FullName; bytes=$xml.Length; validationError=$_.Exception.Message}
            if ($xmls.Count -eq 1) { throw }
        }
    }
    if ($xmls.Count -gt 1) {
        $report.status = 'needs_selection'
        throw 'Multiple MusicXML outputs: review candidates in report.json (size, title, parts, measures and page breaks) and ask the user which movements to convert. Nothing was silently selected.'
    }
    $xml = $xmls[0].FullName
    $content = Invoke-ScoreProcess $python @('-X','utf8',"$PSScriptRoot/score-structure.py",'check','--xml',$xml,'--selection',(Join-Path $dir 'selection.json'),'--out',$dir) 60 $dir 'content-musicxml'
    if ($content.stdout) { $report.contentValidation = $content.stdout | ConvertFrom-Json }
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
    @{schemaVersion=3; startedUtc=$report.startedUtc; outputMode=$OutputMode; inputPdf=$InputPdf; inputPages=$inputInfo.pages; sourceSha256=$selection.sourceSha256; sourcePages=$selection.sourcePages; selection=(Join-Path $dir 'selection.json'); musicXml=$xml; layoutMode=$LayoutMode; exportMidi=[bool]$ExportMidi} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $dir 'run.json') -Encoding UTF8
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
    if ($verified.exitCode -ne 0) {
        if ($verified.exitCode -eq 3) { $report.status = 'failed_content_validation' }
        if ($verified.exitCode -eq 4) { $report.status = 'failed_playback_validation' }
        if ($verified.exitCode -eq 5) { $report.status = 'failed_layout_validation' }
        throw 'Output verification failed; inspect verification.stdout.log and verification.stderr.log. Generated files are diagnostic drafts, not accepted deliverables.'
    }
    $report.contentValidation = $report.verification.contentValidation
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
$report.finishedUtc = [datetime]::UtcNow.ToString('o')
if ($dir) { Write-ScoreReport $report $dir }
$report | ConvertTo-Json -Depth 12
if ($report.status -eq 'needs_selection') { exit 2 }
if ($report.status -eq 'failed_content_validation') { exit 3 }
if ($report.status -eq 'failed_playback_validation') { exit 4 }
if ($report.status -eq 'failed_layout_validation') { exit 5 }
if ($report.status -notin @('completed_needs_manual_review','editable_draft_ready_for_review','editable_draft_needs_correction')) { exit 1 }

