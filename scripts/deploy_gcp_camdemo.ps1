param(
    [string]$ProjectId = "kmark-489115",
    [string]$Region = "asia-south1",
    [string]$ServiceName = "camdemo",
    [string]$RuntimeBucket = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Get-LocalEnvValue([string]$Key) {
    $path = Join-Path (Get-Location) ".env.local"
    if (-not (Test-Path $path)) {
        return $null
    }
    foreach ($raw in Get-Content $path) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $name, $value = $line.Split("=", 2)
        if ($name.Trim() -eq $Key) {
            return $value.Trim().Trim("'`"")
        }
    }
    return $null
}

$probeKey = $env:PROBE42_API_KEY
if (-not $probeKey) {
    $probeKey = Get-LocalEnvValue "PROBE42_API_KEY"
}
if (-not $probeKey) {
    throw "PROBE42_API_KEY was not found in environment or .env.local"
}

$googleKey = $env:GOOGLE_API_KEY
if (-not $googleKey) {
    $googleKey = Get-LocalEnvValue "GOOGLE_API_KEY"
}

$envVars = @"
PROBE42_API_KEY: "$probeKey"
GOOGLE_CLOUD_PROJECT: "$ProjectId"
GOOGLE_CLOUD_LOCATION: "us-central1"
"@

$envFile = Join-Path $env:TEMP "camdemo-cloudrun-env.yaml"
$envVars | Set-Content -Path $envFile -Encoding UTF8

try {
    gcloud config set account kpmggcp01@gmail.com | Out-Null
    gcloud config set project $ProjectId | Out-Null
    gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com --project $ProjectId

    $volumeArgs = @()
    if ($RuntimeBucket) {
        # Create the GCS bucket if it doesn't exist
        $bucketExists = $true
        try { gsutil ls -b "gs://$RuntimeBucket" 2>&1 | Out-Null } catch { $bucketExists = $false }
        if (-not $bucketExists -or $LASTEXITCODE -ne 0) {
            gsutil mb -l $Region "gs://$RuntimeBucket"
            Write-Host "Created GCS bucket: $RuntimeBucket"
        }
        $volumeArgs = @(
            "--execution-environment", "gen2",
            "--add-volume", "name=runtime-db,type=cloud-storage,bucket=$RuntimeBucket",
            "--add-volume-mount", "volume=runtime-db,mount-path=/app/runtime-db"
        )
        Write-Host "Mounting gs://$RuntimeBucket at /app/runtime-db for persistent storage"
    } else {
        Write-Host "WARNING: No RuntimeBucket specified - SQLite data will be lost on redeploy"
    }

    $deployArgs = @(
        "run", "deploy", $ServiceName,
        "--quiet",
        "--project", $ProjectId,
        "--region", $Region,
        "--source", ".",
        "--port", $Port,
        "--memory", "2Gi",
        "--cpu", "2",
        "--timeout", "900",
        "--concurrency", "8",
        "--max-instances", "1",
        "--allow-unauthenticated",
        "--env-vars-file", $envFile
    )
    $deployArgs += $volumeArgs

    & gcloud @deployArgs
}
finally {
    if (Test-Path $envFile) {
        Remove-Item $envFile -Force
    }
}
