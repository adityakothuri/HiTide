# Run the checked-in ECC reviewer definitions through the installed Claude CLI.
# Reviewers have read-only tools, separate logs, and never modify or commit code.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if (-not (Get-Command claude.cmd -ErrorAction SilentlyContinue)) {
    throw 'Claude Code is missing. Install Claude Code, sign in, then rerun this task.'
}
$authText = & claude.cmd auth status
try { $authState = ($authText -join "`n") | ConvertFrom-Json } catch { throw 'Could not check Claude Code login. Run claude auth login in your terminal.' }
if (-not $authState.loggedIn) { throw 'Claude Code is not signed in. Run claude auth login in your terminal, then rerun ECC: parallel reviews.' }
$logDir = Join-Path $repoRoot '.claude/ecc/reviews'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$reviewers = @('database-reviewer', 'fastapi-reviewer', 'code-reviewer')
$jobs = foreach ($reviewer in $reviewers) {
    Start-Job -ArgumentList $repoRoot, $reviewer, $logDir -ScriptBlock {
        param($root, $agentName, $outputDir)
        Set-Location -LiteralPath $root
        $prompt = 'Review the current uncommitted evidence-to-drone milestone. Read docs/evidence-plan.md and inspect backend/evidence, backend/app/main.py and frontend/src/evidence. Apply your checked-in ECC agent instructions. Do not edit files, launch agents, execute commands, commit, or read .env/secrets. Return only actionable findings with severity and file/line, plus residual limitations.'
        $result = & claude.cmd --print --agent $agentName --tools 'Read,Glob,Grep' --permission-mode dontAsk $prompt 2>&1
        $exitCode = $LASTEXITCODE
        $result | Set-Content -LiteralPath (Join-Path $outputDir "$agentName.txt") -Encoding utf8
        [pscustomobject]@{ Agent = $agentName; ExitCode = $exitCode; Log = Join-Path $outputDir "$agentName.txt" }
    }
}
$results = $jobs | Receive-Job -Wait -AutoRemoveJob
$results | Format-Table -AutoSize
if ($results | Where-Object { $_.ExitCode -ne 0 }) { throw 'One or more harness reviews failed; see their logs.' }
