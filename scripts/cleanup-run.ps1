[CmdletBinding()]
param([Parameter(Mandatory)][string]$RunDirectory)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RunDirectory).Path.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
$rootPrefix = $root + [IO.Path]::DirectorySeparatorChar
if (-not (Test-Path -LiteralPath (Join-Path $root 'run.json') -PathType Leaf)) {
    throw 'Refusing cleanup: run.json is missing from the requested run directory.'
}

function Assert-RunChild([string]$Path) {
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not $resolved.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing cleanup outside the run directory: $resolved"
    }
    return $resolved
}

$removed = [Collections.Generic.List[string]]::new()
$directoryPatterns = @('audiveris','runtime-data','source-thumbnails','candidate-*','saved-content-*','structure-verify-*')
foreach ($pattern in $directoryPatterns) {
    foreach ($item in @(Get-ChildItem -LiteralPath $root -Directory | Where-Object { $_.Name -like $pattern })) {
        $safePath = Assert-RunChild $item.FullName
        Remove-Item -LiteralPath $safePath -Recurse -Force
        $removed.Add($item.Name)
    }
}

$filePatterns = @(
    '*.stdout.log','*.stderr.log',
    'score-imported.mscz','score-playback.mscz','score-layout.mscz',
    'omr-input-grayscale-*.pdf','omr-input-grayscale-*.json',
    'verify-reopen-*.musicxml','verify-playback-*.mid',
    'playback-verify-*.json','layout-verify-*.json',
    'reference-score.musicxml'
)
foreach ($pattern in $filePatterns) {
    foreach ($item in @(Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Name -like $pattern })) {
        $safePath = Assert-RunChild $item.FullName
        Remove-Item -LiteralPath $safePath -Force
        $removed.Add($item.Name)
    }
}

$selectionPath = Join-Path $root 'selection.json'
if (Test-Path -LiteralPath $selectionPath -PathType Leaf) {
    $selection = Get-Content -LiteralPath $selectionPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($selection.PSObject.Properties['selectedPdf'] -and $selection.selectedPdf) {
        $selectedPdf = [IO.Path]::GetFullPath([string]$selection.selectedPdf)
        if ($selectedPdf.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $selectedPdf -PathType Leaf)) {
            $safePath = Assert-RunChild $selectedPdf
            Remove-Item -LiteralPath $safePath -Force
            $removed.Add([IO.Path]::GetFileName($safePath))
            $selection.selectedPdf = $null
            $selection | Add-Member -NotePropertyName selectedPdfRemovedAfterValidation -NotePropertyValue $true -Force
            $selection | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $selectionPath -Encoding UTF8
        }
    }
}

$retained = @(@(Get-ChildItem -LiteralPath $root -File | Select-Object -ExpandProperty Name) + @('report.json','report.md') | Sort-Object -Unique)
[ordered]@{
    requested = $true
    performed = $true
    reason = 'completed_and_ready_for_review'
    removed = @($removed | Sort-Object -Unique)
    retained = $retained
} | ConvertTo-Json -Depth 4 -Compress
