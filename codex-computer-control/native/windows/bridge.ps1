# Windows PowerShell 5.1: persistent JSON-lines bridge. No downloaded runtime/compiler.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$references = @('System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll','WindowsBase.dll','UIAutomationClient.dll','UIAutomationTypes.dll')
$paths = @()
foreach ($name in $references) { $assembly = [Reflection.Assembly]::LoadWithPartialName([IO.Path]::GetFileNameWithoutExtension($name)); if ($null -eq $assembly) { throw ('Missing Windows assembly: ' + $name) }; $paths += $assembly.Location }
Add-Type -Path (Join-Path $PSScriptRoot 'Native.cs') -ReferencedAssemblies $paths
function Await-WinRT($operation, [Type]$resultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
    $task = $method.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.GetAwaiter().GetResult()
}
function Get-Ocr($request, $line) {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
    $null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
    $null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
    $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    $fileName = Join-Path ([IO.Path]::GetTempPath()) ('ccc-' + [Guid]::NewGuid().ToString('N') + '.png')
    $stream = $null
    $bitmap = $null
    try {
        $offset = [ComputerControl]::SaveOcrImage($line, $fileName) | ConvertFrom-Json
        $file = Await-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($fileName)) ([Windows.Storage.StorageFile])
        $stream = Await-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await-WinRT ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        if ($null -eq $engine) { throw 'No Windows OCR language installed; enable a supported language in Windows settings.' }
        $result = Await-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $rows = @()
        foreach ($row in $result.Lines) {
            $left = [double]::PositiveInfinity; $top = [double]::PositiveInfinity; $right = 0.0; $bottom = 0.0
            foreach ($word in $row.Words) { $box=$word.BoundingRect; $left=[Math]::Min($left,$box.X); $top=[Math]::Min($top,$box.Y); $right=[Math]::Max($right,$box.X+$box.Width); $bottom=[Math]::Max($bottom,$box.Y+$box.Height) }
            if (-not [double]::IsInfinity($left)) { $rows += @{text=$row.Text;x=[int][Math]::Round($offset[0]+($left+$right)/2);y=[int][Math]::Round($offset[1]+($top+$bottom)/2)} }
        }
        return @{rows=@($rows);source='windows-ocr'}
    } finally {
        if ($null -ne $bitmap) { $bitmap.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
        Remove-Item -LiteralPath $fileName -ErrorAction SilentlyContinue
    }
}
while ($null -ne ($line = [Console]::ReadLine())) {
    $request = $null
    try {
        $request = $line | ConvertFrom-Json
        $identity = $null
        if ($request.op -eq 'text') {
            $status = [ComputerControl]::Dispatch('{"id":0,"op":"status"}') | ConvertFrom-Json
            $identity = $status.result.app_id
        }
        $reply = [ComputerControl]::Dispatch($line) | ConvertFrom-Json
        if ($request.op -eq 'text' -and $reply.ok) {
            $rows = @($reply.result.rows)
            $target = $request.target -replace '\s',''
            $matches = @($rows | Where-Object { ($_.text -replace '\s','') -ceq $target })
            if ($target -and $matches.Count -eq 0) {
                $until = [DateTime]::UtcNow.AddMilliseconds(80)
                while ($matches.Count -eq 0 -and [DateTime]::UtcNow -lt $until) {
                    [ComputerControl]::Guard($identity)
                    Start-Sleep -Milliseconds 12
                    $retry = @{id=$request.id;op='text_accessibility';expected=$request.expected;region=$request.region} | ConvertTo-Json -Depth 8 -Compress
                    $updated = [ComputerControl]::Dispatch($retry) | ConvertFrom-Json
                    if (-not $updated.ok) { throw $updated.error }
                    $reply.result=$updated.result;$rows=@($reply.result.rows)
                    $matches=@($rows | Where-Object { ($_.text -replace '\s','') -ceq $target })
                }
            }
            if (-not $request.accessibility_only -and ($rows.Count -eq 0 -or ($target -and $matches.Count -eq 0))) {
                $reply.result = Get-Ocr $request $line
            }
            [ComputerControl]::Guard($identity)
        }
        [Console]::WriteLine(($reply | ConvertTo-Json -Depth 30 -Compress))
    } catch {
        [Console]::WriteLine((@{id=$request.id;ok=$false;error=$_.Exception.Message} | ConvertTo-Json -Depth 5 -Compress))
    }
}
