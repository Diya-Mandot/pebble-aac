<#
.SYNOPSIS
  Deploys Pebble AAC to the Workshop Studio AWS account: backend Lambdas + API Gateway (via
  backend/template.yaml) and the built frontend behind a password-gated CloudFront distribution.

.EXAMPLE
  .\deploy.ps1 -SitePassword pebblehackathon
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SitePassword
)

$ErrorActionPreference = 'Stop'

if ($SitePassword -match '[,\s]') {
    Write-Host "SitePassword must not contain spaces or commas (breaks --parameter-overrides parsing)." -ForegroundColor Red
    exit 1
}

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RepoRoot 'backend'
$BuildDir = Join-Path $BackendDir '.build'
$StackName = 'pebble-aac'
$Region = 'us-east-1'

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][scriptblock]$Script
    )
    Write-Host "==> $Description" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    $result = & $Script
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Description (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
    return $result
}

# --- 1. Credentials -----------------------------------------------------------------------
$envFile = Join-Path $BackendDir '.env'
if (-not (Test-Path $envFile)) {
    Write-Host "backend\.env not found. Copy backend\.env.example, fill in fresh Workshop Studio credentials, and re-run." -ForegroundColor Red
    exit 1
}
Write-Host "==> Loading credentials from backend\.env (authoritative -- overrides any shell creds)" -ForegroundColor Cyan
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    $idx = $line.IndexOf('=')
    if ($idx -lt 0) { return }
    $key = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1).Trim()
    Set-Item -Path "env:$key" -Value $value
}

Write-Host "==> Verifying AWS credentials" -ForegroundColor Cyan
$global:LASTEXITCODE = 0
$identityJson = aws sts get-caller-identity --output json
if ($LASTEXITCODE -ne 0) {
    Write-Host "AWS credentials check failed (see error above)." -ForegroundColor Red
    Write-Host "If that said ExpiredToken: get fresh short-lived credentials from the Workshop Studio event portal's 'AWS Console'/'CLI' access panel, paste them into backend\.env, and re-run this script." -ForegroundColor Yellow
    exit 1
}
$identity = $identityJson | ConvertFrom-Json
if ($identity.Arn -notmatch 'assumed-role/WSParticipantRole/') {
    Write-Host "Unexpected caller identity: $($identity.Arn)" -ForegroundColor Red
    Write-Host "Expected a WSParticipantRole session (from backend\.env) -- refusing to deploy into the wrong account." -ForegroundColor Red
    exit 1
}
$AccountId = $identity.Account
Write-Host "Deploying as $($identity.Arn) (account $AccountId, region $Region)" -ForegroundColor Green

# --- 2. Lambda dependency bundle (Linux wheels; no Docker/SAM CLI available) --------------
Write-Host "==> Building Lambda dependency bundle" -ForegroundColor Cyan
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
New-Item -ItemType Directory -Path $BuildDir | Out-Null

$global:LASTEXITCODE = 0
# jsonschema's `referencing` dependency needs typing-extensions on Python <3.13 (marker
# `python_version < '3.13'`), but pip evaluates that marker against the CURRENT interpreter, not
# the --python-version target below -- on a 3.13+ dev machine it silently skips typing-extensions,
# which then crashes the Lambda (Python 3.12) at import time. Installed explicitly to sidestep that.
pip install -r (Join-Path $BackendDir 'requirements.txt') "typing_extensions>=4.12.0" `
    --target $BuildDir `
    --platform manylinux2014_x86_64 `
    --implementation cp `
    --python-version 3.12 `
    --only-binary=:all: `
    --upgrade
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip install failed." -ForegroundColor Red
    exit 1
}

Copy-Item -Path (Join-Path $BackendDir 'src') -Destination $BuildDir -Recurse -Container
Copy-Item -Path (Join-Path $BackendDir 'fixtures') -Destination $BuildDir -Recurse -Container
Get-ChildItem -Path $BuildDir -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

# --- 3. Artifact bucket for `cloudformation package` --------------------------------------
$ArtifactBucket = "pebble-aac-artifacts-$AccountId"
Write-Host "==> Ensuring artifact bucket $ArtifactBucket exists" -ForegroundColor Cyan
$global:LASTEXITCODE = 0
$existingBuckets = aws s3api list-buckets --query "Buckets[].Name" --output text
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to list S3 buckets." -ForegroundColor Red
    exit 1
}
if ($existingBuckets -notmatch [regex]::Escape($ArtifactBucket)) {
    $global:LASTEXITCODE = 0
    aws s3api create-bucket --bucket $ArtifactBucket --region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create artifact bucket $ArtifactBucket." -ForegroundColor Red
        exit 1
    }
}

# --- 4. Decide whether ApiOriginSecret needs to be (re)generated --------------------------
Write-Host "==> Checking for an existing '$StackName' stack" -ForegroundColor Cyan
Write-Host "    (an AWS error just below is expected and harmless on the very first deploy)" -ForegroundColor DarkGray
$global:LASTEXITCODE = 0
$stackJson = aws cloudformation describe-stacks --stack-name $StackName --region $Region --output json
$stackExists = ($LASTEXITCODE -eq 0)

$needsNewSecret = $true
if ($stackExists) {
    $stackInfo = $stackJson | ConvertFrom-Json
    $status = $stackInfo.Stacks[0].StackStatus
    if ($status -eq 'ROLLBACK_COMPLETE') {
        Write-Host "Existing stack is in ROLLBACK_COMPLETE (failed first create) -- deleting it before retrying." -ForegroundColor Yellow
        Invoke-Native "Deleting failed stack" { aws cloudformation delete-stack --stack-name $StackName --region $Region }
        Invoke-Native "Waiting for stack deletion" { aws cloudformation wait stack-delete-complete --stack-name $StackName --region $Region }
        $stackExists = $false
    } else {
        $needsNewSecret = $false
    }
}

$ParamOverrides = @("SiteUsername=pebble", "SitePassword=$SitePassword")
if ($needsNewSecret) {
    $ApiOriginSecret = ([guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N'))
    $ParamOverrides += "ApiOriginSecret=$ApiOriginSecret"
    Write-Host "Generated a new API origin secret for this (first) deploy." -ForegroundColor Cyan
} else {
    # ApiOriginSecret is NoEcho, so it can never be read back -- omitting it here makes
    # `cloudformation deploy` retain the value already stored in the existing stack.
    Write-Host "Reusing the existing stack's API origin secret." -ForegroundColor Cyan
}

# --- 5. Package + deploy the stack ---------------------------------------------------------
$TemplatePath = Join-Path $BackendDir 'template.yaml'
$PackagedPath = Join-Path $BuildDir 'packaged.yaml'

Invoke-Native "Packaging CloudFormation template" {
    aws cloudformation package `
        --template-file $TemplatePath `
        --s3-bucket $ArtifactBucket `
        --output-template-file $PackagedPath `
        --region $Region
}

Write-Host "==> Deploying stack $StackName (first create is slow -- CloudFront can take 5-15 min)" -ForegroundColor Cyan
$global:LASTEXITCODE = 0
aws cloudformation deploy `
    --template-file $PackagedPath `
    --stack-name $StackName `
    --region $Region `
    --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND `
    --no-fail-on-empty-changeset `
    --parameter-overrides $ParamOverrides
if ($LASTEXITCODE -ne 0) {
    Write-Host "Stack deploy failed (see error above)." -ForegroundColor Red
    exit 1
}

$global:LASTEXITCODE = 0
$stackJson = aws cloudformation describe-stacks --stack-name $StackName --region $Region --output json
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not read stack status after deploy." -ForegroundColor Red
    exit 1
}
$stackInfo = $stackJson | ConvertFrom-Json
$finalStatus = $stackInfo.Stacks[0].StackStatus
if ($finalStatus -ne 'CREATE_COMPLETE' -and $finalStatus -ne 'UPDATE_COMPLETE') {
    Write-Host "Stack did not reach a healthy state (status: $finalStatus) -- not touching the frontend." -ForegroundColor Red
    exit 1
}

$outputs = @{}
foreach ($o in $stackInfo.Stacks[0].Outputs) { $outputs[$o.OutputKey] = $o.OutputValue }
$SiteUrl = $outputs['SiteUrl']
$SiteBucketName = $outputs['SiteBucketName']
$DistributionId = $outputs['DistributionId']
$ApiUrl = $outputs['ApiUrl']
Write-Host "Stack ready ($finalStatus)." -ForegroundColor Green

# --- 6. Build + upload the frontend ---------------------------------------------------------
Write-Host "==> Building frontend" -ForegroundColor Cyan
$global:LASTEXITCODE = 0
npm run build --prefix $RepoRoot
if ($LASTEXITCODE -ne 0) {
    Write-Host "Frontend build failed." -ForegroundColor Red
    exit 1
}

$DistDir = Join-Path $RepoRoot 'dist'
if (-not (Test-Path $DistDir)) {
    Write-Host "dist\ not found after build." -ForegroundColor Red
    exit 1
}

$ContentTypeMap = @{
    '.html'  = 'text/html'
    '.js'    = 'text/javascript'
    '.mjs'   = 'text/javascript'
    '.css'   = 'text/css'
    '.svg'   = 'image/svg+xml'
    '.json'  = 'application/json'
    '.png'   = 'image/png'
    '.jpg'   = 'image/jpeg'
    '.jpeg'  = 'image/jpeg'
    '.ico'   = 'image/x-icon'
    '.mp3'   = 'audio/mpeg'
    '.woff'  = 'font/woff'
    '.woff2' = 'font/woff2'
    '.txt'   = 'text/plain'
}

Write-Host "==> Uploading frontend to s3://$SiteBucketName" -ForegroundColor Cyan
$files = Get-ChildItem -Path $DistDir -Recurse -File
$indexFile = $null
foreach ($f in $files) {
    $relativePath = $f.FullName.Substring($DistDir.Length + 1).Replace('\', '/')
    if ($relativePath -eq 'index.html') { $indexFile = $f; continue } # uploaded last, see below
    $ext = $f.Extension.ToLowerInvariant()
    $contentType = $ContentTypeMap[$ext]
    if (-not $contentType) { $contentType = 'application/octet-stream' }
    $cacheControl = 'no-cache'
    if ($relativePath.StartsWith('assets/')) { $cacheControl = 'public, max-age=31536000, immutable' }

    $global:LASTEXITCODE = 0
    aws s3 cp $f.FullName "s3://$SiteBucketName/$relativePath" `
        --content-type $contentType --cache-control $cacheControl --region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to upload $relativePath." -ForegroundColor Red
        exit 1
    }
}

if ($indexFile) {
    # Uploaded last so a mid-deploy failure never leaves a live index.html pointing at
    # not-yet-uploaded hashed assets.
    $global:LASTEXITCODE = 0
    aws s3 cp $indexFile.FullName "s3://$SiteBucketName/index.html" `
        --content-type 'text/html' --cache-control 'no-cache' --region $Region
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to upload index.html." -ForegroundColor Red
        exit 1
    }
}

Write-Host "==> Pruning stale assets from previous deploys" -ForegroundColor Cyan
$global:LASTEXITCODE = 0
aws s3 sync $DistDir "s3://$SiteBucketName" --delete --size-only --region $Region
if ($LASTEXITCODE -ne 0) {
    Write-Host "S3 prune sync failed." -ForegroundColor Red
    exit 1
}

Invoke-Native "Invalidating CloudFront cache" {
    aws cloudfront create-invalidation --distribution-id $DistributionId --paths "/*"
}

Write-Host ""
Write-Host "Deployed." -ForegroundColor Green
Write-Host "Site:     $SiteUrl" -ForegroundColor Green
Write-Host "Username: pebble" -ForegroundColor Green
Write-Host "Raw API:  $ApiUrl (gated by a CloudFront-only shared secret -- not directly usable)" -ForegroundColor Green
