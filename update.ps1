# Run after closing Project Orbit. Updates only a clean checkout that tracks GitHub.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

try {
    if (-not (Test-Path -LiteralPath '.git')) {
        throw 'This is not a Git checkout. Clone the published Project Orbit repository first.'
    }
    $remotes = @(git remote)
    if ($LASTEXITCODE -ne 0 -or $remotes -notcontains 'origin') {
        throw 'No origin remote is configured. Publish the current local version to GitHub first.'
    }
    $remote = git remote get-url origin
    if ($LASTEXITCODE -ne 0 -or -not $remote) { throw 'Could not read origin remote.' }
    $upstream = git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $upstream) {
        throw 'The current branch has no upstream. Use a cloned checkout or configure branch tracking.'
    }
    $changes = git status --porcelain --untracked-files=normal
    if ($LASTEXITCODE -ne 0) { throw 'Could not check Git status.' }
    if ($changes) { throw 'The working tree has local changes. Save them before updating.' }

    Write-Host "Updating code from $remote ($upstream)..."
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw 'Git could not fast-forward. Project files were not overwritten.' }

    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        Write-Host 'Creating virtual environment...'
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check the Python installation.' }
    }
    Write-Host 'Updating dependencies...'
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not update dependencies.' }
    Write-Host 'Project Orbit is up to date. Run .\run.bat'
} catch {
    Write-Host "Update stopped: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
