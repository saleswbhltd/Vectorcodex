param(
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$commonFiles = 'C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\Common\Files'
$portableRoot = 'C:\Users\cmake\MT5'

$routes = @(
  @{
    Name = 'RoboF2 GoldX_Modular_v13 67196088'
    Destination = Join-Path $portableRoot 'RoboF2\MQL5\Files\GoldX_Modular_v13\LIVE\67196088\_CommonImported'
    Predicate = { param($file) $file.Name -like 'GoldX_Modular_v13*67196088*' }
  },
  @{
    Name = 'RoboF3 GoldX_Modular_v12 67196146'
    Destination = Join-Path $portableRoot 'RoboF3\MQL5\Files\GoldX_Modular_v12\LIVE\67196146\_CommonImported'
    Predicate = { param($file) $file.Name -like 'GoldX_Modular_v12*67196146*' }
  },
  @{
    Name = 'RoboF4 GoldX_Modular_v13 67197353'
    Destination = Join-Path $portableRoot 'RoboF4\MQL5\Files\GoldX_Modular_v13\LIVE\67197353\_CommonImported'
    Predicate = { param($file) $file.Name -like 'GoldX_Modular_v13*67197353*' }
  },
  @{
    Name = 'RoboF2 VECTOR80'
    Destination = Join-Path $portableRoot 'RoboF2\MQL5\Files\VECTOR80\_CommonImported'
    Predicate = { param($file) $file.Name -like 'VECTOR80*' -or $file.Name -like 'vector003*' -or $file.Name -like 'VECTOR_ZZBUF*' }
  },
  @{
    Name = 'RoboF1 SMC indicator'
    Destination = Join-Path $portableRoot 'RoboF1\MQL5\Files\SMCEA\_CommonImported'
    Predicate = { param($file) $file.Name -like 'SMCEA_H1OB_IND.csv' }
  }
)

$unmatchedDestination = Join-Path $portableRoot '_CommonFiles_Unmatched'

if (-not (Test-Path -LiteralPath $commonFiles)) {
  throw "Common files folder not found: $commonFiles"
}

$files = Get-ChildItem -LiteralPath $commonFiles -Recurse -File
$actions = New-Object System.Collections.Generic.List[object]

foreach ($file in $files) {
  $matchedRoutes = @($routes | Where-Object { & $_.Predicate $file })

  if ($matchedRoutes.Count -eq 1) {
    $destination = $matchedRoutes[0].Destination
    $routeName = $matchedRoutes[0].Name
  } elseif ($matchedRoutes.Count -gt 1) {
    $destination = Join-Path $unmatchedDestination 'Ambiguous'
    $routeName = 'Ambiguous'
  } else {
    $destination = Join-Path $unmatchedDestination 'NoCurrentPortableMatch'
    $routeName = 'No current portable match'
  }

  $relativePath = $file.FullName.Substring($commonFiles.Length).TrimStart('\')
  $targetPath = Join-Path $destination $relativePath

  $actions.Add([pscustomobject]@{
    Route = $routeName
    Source = $file.FullName
    Target = $targetPath
    Bytes = $file.Length
  })
}

if (-not $DryRun) {
  foreach ($action in $actions) {
    $targetDirectory = Split-Path -Parent $action.Target
    New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    Copy-Item -LiteralPath $action.Source -Destination $action.Target -Force
  }
}

$actions |
  Group-Object Route |
  ForEach-Object {
    [pscustomobject]@{
      Route = $_.Name
      Files = $_.Count
      MB = [math]::Round(($_.Group | Measure-Object Bytes -Sum).Sum / 1MB, 2)
      Destination = Split-Path -Parent $_.Group[0].Target
    }
  } |
  Sort-Object Route |
  Format-Table -AutoSize

if ($DryRun) {
  'DRY RUN ONLY - no files copied.'
} else {
  'COPY COMPLETE.'
}
