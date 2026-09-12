Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

$token = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Paste your GitHub Personal Access Token (starts with ghp_):`n`n(The token creation tab is open in Brave with 'repo' scope already checked)",
    "Sync SnapStreak to GitHub (IAndrexI/SC)",
    ""
)

if ([string]::IsNullOrWhiteSpace($token)) {
    exit
}

$token = $token.Trim()
$git = "C:\Users\Andrex\AppData\Local\Programs\Git\cmd\git.exe"
$url = "https://$token@github.com/IAndrexI/SC.git"

$output = & $git push -u $url main 2>&1

if ($LASTEXITCODE -eq 0) {
    & $git remote set-url origin "https://github.com/IAndrexI/SC.git"
    [System.Windows.Forms.MessageBox]::Show("SUCCESS! All project files are now synced to https://github.com/IAndrexI/SC", "SnapStreak Sync Complete", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
} else {
    [System.Windows.Forms.MessageBox]::Show("Push failed with error:`n$output", "Sync Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
}
