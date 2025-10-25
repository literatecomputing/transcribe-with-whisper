<#
.SYNOPSIS
  Windows PowerShell wrapper for bin/new-release (bash)

.DESCRIPTION
  When called with no arguments, shows the latest GitHub Release for the current repo.
  When called with a single version argument (e.g. 0.7.8 or v0.7.8) it will create an annotated
  git tag (prefixed with 'v' if needed), push it, and create a GitHub Release using the GitHub CLI (gh).

  Requires: git and gh to be installed and authenticated.
#>
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]
    $Args
)

function Ensure-Command($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Error "Required command not found: $name"
        exit 1
    }
}

Ensure-Command git
Ensure-Command gh

if ($Args.Count -eq 0) {
    # show latest release
    try {
        $tag = gh release list --limit 1 --json tagName --jq '.[0].tagName' 2>$null
    } catch {
        $tag = $null
    }
    if (-not [string]::IsNullOrEmpty($tag)) {
        Write-Output "Latest release: $tag"
        gh release view $tag --json tagName,name,body,createdAt,publishedAt,url --jq '{tag: .tagName, name: .name, url: .url, published: .publishedAt, created: .createdAt, notes: .body}'
        exit 0
    } else {
        Write-Output "No releases found in this repository."
        exit 0
    }
}

if ($Args.Count -ne 1) {
    Write-Output "Usage: $($MyInvocation.MyCommand.Name) [version]  (e.g. 0.7.8 or v0.7.8)"
    exit 2
}

$raw = $Args[0]
if ($raw -like 'v*') { $tag = $raw } else { $tag = "v$raw" }
Write-Output "Preparing release for tag: $tag"

# ensure working tree is clean
$dirty = (git status --porcelain)
if ($dirty) {
    Write-Error "Working tree has changes. Please commit or stash them before creating a release."
    exit 1
}

# check local tag
try { git rev-parse $tag >$null 2>&1; $localTagExists = $true } catch { $localTagExists = $false }
if ($localTagExists) {
    Write-Error "Tag $tag already exists locally. Aborting."
    exit 1
}

# check remote tag
$remote = git ls-remote --tags origin --refs "refs/tags/$tag" 2>$null
if (-not [string]::IsNullOrEmpty($remote)) {
    Write-Error "Tag $tag already exists on remote. Aborting."
    exit 1
}

$currentHead = git rev-parse --verify HEAD
Write-Output "Creating annotated tag $tag for commit $currentHead"
git tag -a $tag -m "Release $tag"
Write-Output "Pushing tag $tag to origin"
git push origin "refs/tags/$tag"
Write-Output "Creating GitHub Release for $tag"
gh release create $tag --title "Release $tag" --notes "Automated release created by bin/new-release" --target $currentHead
Write-Output "Release $tag created successfully."
exit 0
