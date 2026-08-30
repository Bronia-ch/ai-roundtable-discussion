$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $root 'AI圆桌讨论APP-delivery.zip'
$items = @('backend/app','backend/tests','backend/app/schema.sql','frontend/src','frontend/package.json','frontend/tsconfig.json','docs','README.md','.gitignore','start_demo.bat','delivery_verification.txt')
if (Test-Path $out) { Remove-Item -LiteralPath $out -Force }
Compress-Archive -Path ($items | ForEach-Object { Join-Path $root $_ }) -DestinationPath $out -CompressionLevel Optimal
Get-FileHash -Algorithm SHA256 $out | Set-Content (Join-Path $root 'AI圆桌讨论APP-delivery.zip.sha256')
Write-Host "Created $out"
