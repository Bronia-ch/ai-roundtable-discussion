$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $root 'AI-roundtable-delivery.zip'
$checksum = "$out.sha256"
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-roundtable-delivery-" + [guid]::NewGuid().ToString('N'))
$items = @(
    'backend/app',
    'backend/tests',
    'backend/.env.example',
    'backend/requirements.txt',
    'backend/pytest.ini',
    'frontend/src',
    'frontend/tests',
    'frontend/e2e',
    'frontend/package.json',
    'frontend/package-lock.json',
    'frontend/index.html',
    'frontend/tsconfig.json',
    'frontend/vite.config.ts',
    'frontend/playwright.config.ts',
    'design-system',
    'docs',
    'README.md',
    '.gitignore',
    'start_demo.bat',
    'delivery_verification.txt'
)

try {
    New-Item -ItemType Directory -Path $stage | Out-Null
    foreach ($item in $items) {
        $source = Join-Path $root $item
        $destination = Join-Path $stage $item
        $parent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Recurse -Force
    }

    # 交付包只保留源码与必要文件，不夹带本机运行缓存。
    Get-ChildItem -LiteralPath $stage -Directory -Recurse -Filter '__pycache__' |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $stage -File -Recurse -Include '*.pyc', '*.pyo' |
        Remove-Item -Force

    if (Test-Path $out) { Remove-Item -LiteralPath $out -Force }
    if (Test-Path $checksum) { Remove-Item -LiteralPath $checksum -Force }
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $out -CompressionLevel Optimal
    $hash = Get-FileHash -Algorithm SHA256 $out
    "$($hash.Hash.ToLowerInvariant())  $(Split-Path -Leaf $out)" | Set-Content $checksum
    Write-Host "Created $out"
}
finally {
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $resolvedStage = [System.IO.Path]::GetFullPath($stage)
    if ((Test-Path $stage) -and $resolvedStage.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
