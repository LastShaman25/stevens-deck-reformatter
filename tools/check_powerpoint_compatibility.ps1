param([string]$Deck, [string]$Report)
# Read-only compatibility probe for synthetic test decks only.
$ErrorActionPreference = 'Stop'
$app = $null
$presentation = $null
$alreadyRunning = $false
try {
    try {
        $existing = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')
        $alreadyRunning = $true
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($existing)
    } catch { }
    $app = New-Object -ComObject PowerPoint.Application
    $presentation = $app.Presentations.Open($Deck, $true, $false, $false)
    $charts = @()
    $links = 0
    $notes = $false
    foreach ($slide in $presentation.Slides) {
        $links += $slide.Hyperlinks.Count
        foreach ($shape in $slide.Shapes) {
            if ($shape.HasChart -eq -1) {
                $series = $shape.Chart.SeriesCollection(1)
                $charts += @{ values = @($series.Values); categories = @($series.XValues) }
            }
        }
        foreach ($shape in $slide.NotesPage.Shapes) {
            if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                if ($shape.TextFrame.TextRange.Text.Contains('Keep these speaker notes: 42 is not 24.')) { $notes = $true }
            }
        }
    }
    if ($charts.Count -ne 1 -or $links -lt 2 -or -not $notes) { throw 'Native chart, link, or notes compatibility check failed.' }
    if (($charts[0].values -join ',') -ne '12,34') { throw 'Native chart values changed.' }
    @{ renderer = 'Microsoft PowerPoint'; version = $app.Version; slides = $presentation.Slides.Count;
       charts = $charts; hyperlink_count = $links; notes_preserved = $notes; status = 'passed' } |
       ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Report -Encoding utf8
} finally {
    if ($null -ne $presentation) { $presentation.Close(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($presentation) }
    if ($null -ne $app) {
        if (-not $alreadyRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
    }
}
