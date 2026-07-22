$ws = New-Object -ComObject WScript.Shell
if ($ws.AppActivate("BlastGame")) {
    Write-Host "focused"
} else {
    Write-Host "not found"
}
