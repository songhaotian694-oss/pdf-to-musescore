Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding

function Assert-AbsolutePath([string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path) -or $Path -match '^[A-Za-z]:[^\\/]') { throw "Use an absolute path: $Path" }
    [IO.Path]::GetFullPath($Path)
}

function Find-ScoreTool([string]$Kind, [string]$Override) {
    if ($Override) {
        $p = Assert-AbsolutePath $Override
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { return $null }
        return $p
    }
    $configPath = Join-Path $PSScriptRoot '../config.local.json'
    if (Test-Path -LiteralPath $configPath) {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $prop = $config.PSObject.Properties[$Kind]
        if ($prop -and $prop.Value -and (Test-Path -LiteralPath $prop.Value -PathType Leaf)) { return [string]$prop.Value }
    }
    $names = switch ($Kind) { Audiveris { @('Audiveris.exe') } MuseScore { @('MuseScore4.exe','mscore.exe') } PdfInfo { @('pdfinfo.exe') } Python { @('python.exe') } }
    foreach ($name in $names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    if ($Kind -in @('PdfInfo','Python')) { return $null }
    $uninstalls = @(Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue)
    $roots = @( $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    $folders = @($uninstalls | Where-Object { $_.PSObject.Properties['DisplayName'] -and $_.DisplayName -match $Kind -and $_.PSObject.Properties['InstallLocation'] } | ForEach-Object { $_.InstallLocation })
    foreach ($root in $roots) {
        $folders += @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Where-Object Name -match $Kind | ForEach-Object FullName)
    }
    foreach ($folder in ($folders | Where-Object { $_ } | Select-Object -Unique)) {
        foreach ($name in $names) {
            foreach ($rel in @($name, "bin/$name", "Audiveris/$name")) {
                $p = Join-Path $folder $rel
                if (Test-Path -LiteralPath $p -PathType Leaf) { return [IO.Path]::GetFullPath($p) }
            }
        }
    }
    return $null
}

function Invoke-ScoreProcess {
    param([string]$Executable, [string[]]$Arguments, [int]$TimeoutSeconds = 300, [string]$LogDirectory, [string]$Label = 'command', [hashtable]$Environment = @{})
    if ([IO.Path]::GetExtension($Executable) -ne '.exe') { throw 'Use a native .exe launcher; shell/batch launchers are not supported.' }
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $Executable
    # Windows CommandLineToArgvW quoting; no shell interprets input paths.
    $quoted = foreach ($arg in $Arguments) {
        '"' + [regex]::Replace([regex]::Replace($arg, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
    }
    $psi.Arguments = $quoted -join ' '
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [Text.Encoding]::UTF8
    foreach ($key in $Environment.Keys) { $psi.EnvironmentVariables[$key] = $Environment[$key] }
    $p = New-Object Diagnostics.Process
    $p.StartInfo = $psi
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        [void]$p.Start()
        $stdoutTask = $p.StandardOutput.ReadToEndAsync()
        $stderrTask = $p.StandardError.ReadToEndAsync()
        $timedOut = -not $p.WaitForExit($TimeoutSeconds * 1000)
        if ($timedOut) {
            try { $p.Kill($true) } catch { try { $p.Kill() } catch {} }
            $p.WaitForExit()
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $code = $p.ExitCode
        if ($timedOut) { $code = 124 }
        $result = [pscustomobject]@{ executable=$Executable; arguments=$Arguments; exitCode=$code; timedOut=$timedOut; seconds=[math]::Round($timer.Elapsed.TotalSeconds,2); stdout=$stdout; stderr=$stderr }
        if ($LogDirectory) {
            [IO.File]::WriteAllText((Join-Path $LogDirectory "$Label.stdout.log"), $stdout)
            [IO.File]::WriteAllText((Join-Path $LogDirectory "$Label.stderr.log"), $stderr)
            $entry = $result | Select-Object executable,arguments,exitCode,timedOut,seconds | ConvertTo-Json -Compress -Depth 5
            Add-Content -LiteralPath (Join-Path $LogDirectory 'conversion.log') -Value $entry -Encoding UTF8
        }
        return $result
    } finally { $p.Dispose() }
}

function Get-PdfDetails([string]$Path, [string]$PdfInfoPath) {
    $full = Assert-AbsolutePath $Path
    $file = Get-Item -LiteralPath $full
    if ($file.PSIsContainer -or $file.Extension -ine '.pdf' -or $file.Length -lt 8) { throw 'Input must be a non-empty PDF file.' }
    $stream = [IO.File]::OpenRead($full)
    try { $bytes = New-Object byte[] 5; [void]$stream.Read($bytes,0,5) } finally { $stream.Dispose() }
    if ([Text.Encoding]::ASCII.GetString($bytes) -ne '%PDF-') { throw 'Invalid PDF header. Supply the original printed sheet-music PDF.' }
    $pages = $null
    if ($PdfInfoPath) {
        $info = Invoke-ScoreProcess $PdfInfoPath @($full) 30
        if ($info.exitCode -ne 0 -or $info.stdout -notmatch '(?m)^Pages:\s+(\d+)') { throw 'PDF cannot be parsed by pdfinfo; check corruption, encryption or password protection.' }
        $pages = [int]$Matches[1]
        if ($pages -lt 1) { throw 'PDF has no pages.' }
        if ($info.stdout -match '(?m)^Encrypted:\s+yes') { throw 'Encrypted PDF: provide an authorized, unlocked copy.' }
    }
    [pscustomobject]@{ path=$full; exists=$true; bytes=$file.Length; pages=$pages; pageCountVerified=($null -ne $pages) }
}

function Read-SafeXml([string]$Text) {
    $settings = New-Object Xml.XmlReaderSettings
    $settings.DtdProcessing = [Xml.DtdProcessing]::Ignore
    $settings.XmlResolver = $null
    $settings.MaxCharactersInDocument = 50000000
    $reader = [Xml.XmlReader]::Create((New-Object IO.StringReader($Text)), $settings)
    try { $doc = New-Object Xml.XmlDocument; $doc.XmlResolver = $null; $doc.Load($reader); return ,$doc } finally { $reader.Dispose() }
}

function Get-MusicXmlDetails([string]$Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if ([IO.Path]::GetExtension($Path) -ieq '.mxl') {
        $zip = [IO.Compression.ZipFile]::OpenRead($Path)
        try {
            $container = $zip.GetEntry('META-INF/container.xml')
            if (-not $container) { throw 'MXL has no META-INF/container.xml.' }
            $r = New-Object IO.StreamReader($container.Open())
            try { $meta = Read-SafeXml $r.ReadToEnd() } finally { $r.Dispose() }
            $root = $meta.SelectSingleNode('//*[local-name()="rootfile"]')
            if (-not $root) { throw 'MXL has no MusicXML rootfile.' }
            $entry = $zip.GetEntry($root.GetAttribute('full-path'))
            if (-not $entry -or $entry.Length -gt 50000000) { throw 'Missing or oversized MusicXML rootfile.' }
            $r = New-Object IO.StreamReader($entry.Open())
            try { $doc = Read-SafeXml $r.ReadToEnd() } finally { $r.Dispose() }
        } finally { $zip.Dispose() }
    } else { $doc = Read-SafeXml ([IO.File]::ReadAllText($Path)) }
    if ($doc.DocumentElement.LocalName -notin @('score-partwise','score-timewise')) { throw 'XML is not a MusicXML score.' }
    $notes = $doc.SelectNodes('//*[local-name()="note"]')
    if ($notes.Count -eq 0) { throw 'MusicXML contains no notes/rests; this may be a text-only PDF or failed OMR.' }
    $voices = @($doc.SelectNodes('//*[local-name()="voice"]') | ForEach-Object InnerText | Select-Object -Unique)
    [pscustomobject]@{ path=$Path; bytes=(Get-Item -LiteralPath $Path).Length; title=($doc.SelectNodes('//*[local-name()="work-title" or local-name()="movement-title"]') | ForEach-Object InnerText) -join '; '; parts=$doc.SelectNodes('//*[local-name()="score-part"]').Count; measures=$doc.SelectNodes('//*[local-name()="measure"]').Count; notes=$notes.Count; pageBreaks=$doc.SelectNodes('//*[local-name()="print" and @new-page="yes"]').Count; lyrics=$doc.SelectNodes('//*[local-name()="lyric"]').Count; voices=$voices.Count }
}

function Get-CorrectionWarnings {
    @('OMR output is not guaranteed musically correct; no note-accuracy percentage has been measured.', 'Compare meter, clefs, key signatures, accidentals, slurs, dots, ties across bars, lyrics and voices with the source PDF.', 'MusicXML import can change layout, page breaks and notation. Review the proof PDF and listen to playback.')
}

function Write-ScoreReport($Report, [string]$Directory) {
    $Report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $Directory 'report.json') -Encoding UTF8
    $template = [IO.File]::ReadAllText((Join-Path $PSScriptRoot '../assets/report-template.md'))
    $body = $template.Replace('{{STATUS}}', [string]$Report.status).Replace('{{ERROR}}', [string]$Report.error).Replace('{{INPUT}}', [string]$Report.inputPdf).Replace('{{WARNINGS}}', (($Report.warnings | ForEach-Object { '- ' + $_ }) -join "`n"))
    [IO.File]::WriteAllText((Join-Path $Directory 'report.md'), $body)
}
