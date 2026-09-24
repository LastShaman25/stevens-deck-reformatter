param([Parameter(Mandatory=$true)][string]$InputDeck,
      [Parameter(Mandatory=$true)][string]$OutputPdf)
$ErrorActionPreference = 'Stop'
$app = $null
$deck = $null
$alreadyRunning = $false
$mutex = New-Object System.Threading.Mutex($false, 'Local\StevensSlideStudioRenderer')
$acquired = $false
$oldSecurity = $null
try {
    try { $acquired = $mutex.WaitOne(110000) } catch [System.Threading.AbandonedMutexException] { $acquired = $true }
    if (-not $acquired) { throw 'PowerPoint renderer is busy.' }
    try {
        $existing = [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application')
        $alreadyRunning = $true
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($existing)
    } catch { }
    $app = New-Object -ComObject PowerPoint.Application
    $oldSecurity = $app.AutomationSecurity
    $app.AutomationSecurity = 3
    $deck = $app.Presentations.Open($InputDeck, $true, $false, $false)
    $deck.SaveAs($OutputPdf, 32)
    @{ renderer = 'Microsoft PowerPoint'; version = $app.Version; slides = $deck.Slides.Count } | ConvertTo-Json -Compress
} finally {
    if ($null -ne $deck) { $deck.Close(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($deck) }
    if ($null -ne $app) {
        if ($null -ne $oldSecurity) { $app.AutomationSecurity = $oldSecurity }
        if (-not $alreadyRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
    }
    if ($acquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
