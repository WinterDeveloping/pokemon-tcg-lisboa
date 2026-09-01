# Pokemon TCG Lisboa - small desktop front-end for main.py
# Pick a time range and radius, generate the poster, preview it, share it.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SettingsPath = Join-Path $ScriptDir 'settings.json'
$OutputPath   = Join-Path $ScriptDir 'events.png'
$IcsPath      = Join-Path $ScriptDir 'events.ics'

# --- theme ---------------------------------------------------------------
$Bg     = [System.Drawing.Color]::FromArgb(17, 19, 26)
$Card   = [System.Drawing.Color]::FromArgb(31, 35, 46)
$Text   = [System.Drawing.Color]::FromArgb(238, 240, 246)
$Muted  = [System.Drawing.Color]::FromArgb(138, 146, 166)
$Accent = [System.Drawing.Color]::FromArgb(255, 203, 5)
$FontUI = New-Object System.Drawing.Font('Segoe UI', 10)

# --- settings ------------------------------------------------------------
$Settings = @{ Webhook = ''; Weeks = '8 semanas'; Radius = '30 km' }
if (Test-Path $SettingsPath) {
    try {
        $loaded = Get-Content $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($k in @('Webhook', 'Weeks', 'Radius')) {
            if ($loaded.PSObject.Properties.Name -contains $k -and $loaded.$k) { $Settings[$k] = $loaded.$k }
        }
    } catch { }   # a corrupt settings file should never block startup
}

function Save-Settings {
    try {
        [pscustomobject]$Settings | ConvertTo-Json | Set-Content $SettingsPath -Encoding UTF8
    } catch { }
}

# Runs main.py and returns @{ Ok; Count; Message }.
function Invoke-Generate {
    param([string]$Weeks, [string]$Radius, [string]$Webhook)

    $argList = @('main.py', '--radius', $Radius, '--out', $OutputPath, '--ics', $IcsPath)
    if ($Weeks -ne '0') { $argList += @('--weeks', $Weeks) }
    if ($Webhook)       { $argList += @('--discord', $Webhook) }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = 'python'
    $psi.Arguments              = ($argList | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
    $psi.WorkingDirectory       = $ScriptDir
    $psi.UseShellExecute        = $false
    $psi.CreateNoWindow         = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding  = [System.Text.Encoding]::UTF8
    $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
    } catch {
        return @{ Ok = $false; Count = 0; Message = 'Python não encontrado. Instala o Python e tenta outra vez.' }
    }

    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()

    if ($proc.ExitCode -ne 0) {
        $msg = $stderr.Trim()
        if (-not $msg) { $msg = 'Falhou (código ' + $proc.ExitCode + ').' }
        return @{ Ok = $false; Count = 0; Message = $msg }
    }

    $count = 0
    if ($stdout -match '(?m)^(\d+)\s+events') { $count = [int]$Matches[1] }
    if ($count -eq 0 -and $stdout -match 'No events found') {
        return @{ Ok = $false; Count = 0; Message = 'Nenhum evento neste período. Tenta alargar o raio.' }
    }
    return @{ Ok = $true; Count = $count; Message = '' }
}

# --- form ----------------------------------------------------------------
$form                 = New-Object System.Windows.Forms.Form
$form.Text            = 'Pokémon TCG · Lisboa'
$form.Size            = New-Object System.Drawing.Size(880, 720)
$form.MinimumSize     = New-Object System.Drawing.Size(760, 560)
$form.StartPosition   = 'CenterScreen'
$form.BackColor       = $Bg
$form.Font            = $FontUI

$title           = New-Object System.Windows.Forms.Label
$title.Text      = 'Pokémon TCG · Lisboa'
$title.Font      = New-Object System.Drawing.Font('Segoe UI', 17, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = $Text
$title.Location  = New-Object System.Drawing.Point(24, 18)
$title.Size      = New-Object System.Drawing.Size(500, 34)
$form.Controls.Add($title)

$subtitle           = New-Object System.Windows.Forms.Label
$subtitle.Text      = 'Cups, Challenges e Pré-Releases perto de ti'
$subtitle.ForeColor = $Muted
$subtitle.Location  = New-Object System.Drawing.Point(26, 52)
$subtitle.Size      = New-Object System.Drawing.Size(500, 22)
$form.Controls.Add($subtitle)

function New-Label {
    param([string]$TextValue, [int]$X, [int]$Y)
    $l           = New-Object System.Windows.Forms.Label
    $l.Text      = $TextValue
    $l.ForeColor = $Muted
    $l.Location  = New-Object System.Drawing.Point($X, $Y)
    $l.Size      = New-Object System.Drawing.Size(230, 20)
    $form.Controls.Add($l)
    return $l
}

function New-Combo {
    param([int]$X, [int]$Y, [int]$W, [string[]]$Items, [string]$Selected)
    $c               = New-Object System.Windows.Forms.ComboBox
    $c.DropDownStyle = 'DropDownList'
    $c.Location      = New-Object System.Drawing.Point($X, $Y)
    $c.Size          = New-Object System.Drawing.Size($W, 28)
    $c.BackColor     = $Card
    $c.ForeColor     = $Text
    $c.FlatStyle     = 'Flat'
    foreach ($i in $Items) { [void]$c.Items.Add($i) }
    $c.SelectedIndex = 0
    if ($Selected -and $c.Items.Contains($Selected)) { $c.SelectedItem = $Selected }
    $form.Controls.Add($c)
    return $c
}

[void](New-Label 'Período' 24 92)
$cboWeeks = New-Combo 24 114 210 @('4 semanas', '6 semanas', '8 semanas', '12 semanas', '6 meses', 'Tudo') $Settings.Weeks

[void](New-Label 'Distância de Lisboa' 250 92)
$cboRadius = New-Combo 250 114 170 @('10 km', '15 km', '20 km', '30 km', '50 km') $Settings.Radius

$btnGenerate               = New-Object System.Windows.Forms.Button
$btnGenerate.Text          = 'Gerar imagem'
$btnGenerate.Location      = New-Object System.Drawing.Point(440, 113)
$btnGenerate.Size          = New-Object System.Drawing.Size(160, 30)
$btnGenerate.BackColor     = $Accent
$btnGenerate.ForeColor     = $Bg
$btnGenerate.FlatStyle     = 'Flat'
$btnGenerate.Font          = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
$btnGenerate.FlatAppearance.BorderSize = 0
$btnGenerate.UseVisualStyleBackColor   = $false
$form.Controls.Add($btnGenerate)

$status           = New-Object System.Windows.Forms.Label
$status.Text      = 'Escolhe o período e gera a imagem.'
$status.ForeColor = $Muted
$status.Location  = New-Object System.Drawing.Point(614, 119)
$status.Size      = New-Object System.Drawing.Size(230, 40)
$status.Anchor    = 'Top,Right'
$form.Controls.Add($status)

$preview             = New-Object System.Windows.Forms.PictureBox
$preview.Location    = New-Object System.Drawing.Point(24, 160)
$preview.Size        = New-Object System.Drawing.Size(820, 430)
$preview.SizeMode    = 'Zoom'
$preview.BackColor   = $Card
$preview.Anchor      = 'Top,Left,Bottom,Right'
$form.Controls.Add($preview)

[void](New-Label 'Webhook do Discord (opcional)' 24 600)
$txtWebhook             = New-Object System.Windows.Forms.TextBox
$txtWebhook.Location    = New-Object System.Drawing.Point(24, 622)
$txtWebhook.Size        = New-Object System.Drawing.Size(352, 26)
$txtWebhook.BackColor   = $Card
$txtWebhook.ForeColor   = $Text
$txtWebhook.BorderStyle = 'FixedSingle'
$txtWebhook.Text        = $Settings.Webhook
$txtWebhook.Anchor      = 'Bottom,Left,Right'
$form.Controls.Add($txtWebhook)

function New-FlatButton {
    param([string]$TextValue, [int]$X, [int]$Y, [int]$W)
    $b           = New-Object System.Windows.Forms.Button
    $b.Text      = $TextValue
    $b.Location  = New-Object System.Drawing.Point($X, $Y)
    $b.Size      = New-Object System.Drawing.Size($W, 30)
    $b.BackColor = $Card
    $b.ForeColor = $Text
    $b.FlatStyle = 'Flat'
    $b.Anchor    = 'Bottom,Right'
    $b.UseVisualStyleBackColor = $false
    $b.FlatAppearance.BorderColor = $Muted
    $form.Controls.Add($b)
    return $b
}

$btnOpen     = New-FlatButton 'Abrir'          388 621 76
$btnFolder   = New-FlatButton 'Pasta'          470 621 76
$btnCalendar = New-FlatButton 'Calendário'     552 621 104
$btnDiscord  = New-FlatButton 'Discord'        662 621 182

$btnOpen.Enabled     = $false
$btnFolder.Enabled   = $false
$btnCalendar.Enabled = $false
$btnDiscord.Enabled  = $false

# --- behaviour -----------------------------------------------------------
$weeksMap  = @{ '4 semanas' = '4'; '6 semanas' = '6'; '8 semanas' = '8'; '12 semanas' = '12'; '6 meses' = '26'; 'Tudo' = '0' }

# Load into memory then dispose, so events.png is never locked for rewriting.
function Show-Preview {
    if (-not (Test-Path $OutputPath)) { return }
    if ($preview.Image) { $preview.Image.Dispose(); $preview.Image = $null }
    $bytes  = [System.IO.File]::ReadAllBytes($OutputPath)
    $stream = New-Object System.IO.MemoryStream(, $bytes)
    $preview.Image = [System.Drawing.Image]::FromStream($stream)
}

function Set-Busy {
    param([bool]$Busy, [string]$Message)
    $btnGenerate.Enabled = -not $Busy
    $cboWeeks.Enabled    = -not $Busy
    $cboRadius.Enabled   = -not $Busy
    $status.Text         = $Message
    if ($Busy) { $status.ForeColor = $Accent } else { $status.ForeColor = $Muted }
    [System.Windows.Forms.Application]::DoEvents()
}

$doGenerate = {
    param([string]$Webhook)

    Set-Busy $true 'A obter eventos…'
    $weeks  = $weeksMap[[string]$cboWeeks.SelectedItem]
    $radius = ([string]$cboRadius.SelectedItem) -replace '[^\d]', ''

    $result = Invoke-Generate -Weeks $weeks -Radius $radius -Webhook $Webhook

    if ($result.Ok) {
        Show-Preview
        $btnOpen.Enabled     = $true
        $btnFolder.Enabled   = $true
        $btnCalendar.Enabled = $true
        $btnDiscord.Enabled  = $true
        $msg = "$($result.Count) eventos."
        if ($Webhook) { $msg += ' Enviado para o Discord.' }
        Set-Busy $false $msg
        $status.ForeColor = $Text
    } else {
        Set-Busy $false $result.Message
        $status.ForeColor = [System.Drawing.Color]::FromArgb(255, 120, 120)
    }

    $Settings.Weeks   = [string]$cboWeeks.SelectedItem
    $Settings.Radius  = [string]$cboRadius.SelectedItem
    $Settings.Webhook = $txtWebhook.Text.Trim()
    Save-Settings
}

$btnGenerate.Add_Click({ & $doGenerate '' })

$btnDiscord.Add_Click({
    $hook = $txtWebhook.Text.Trim()
    if (-not $hook) {
        [void][System.Windows.Forms.MessageBox]::Show(
            'Cola o URL do webhook primeiro.' + [Environment]::NewLine + [Environment]::NewLine +
            'Definições do servidor > Integracoes > Webhooks > Novo webhook > Copiar URL.',
            'Webhook em falta', 'OK', 'Information')
        return
    }
    & $doGenerate $hook
})

$btnCalendar.Add_Click({
    if (-not (Test-Path $IcsPath)) { return }
    $choice = [System.Windows.Forms.MessageBox]::Show(
        'Abrir events.ics no teu calendário?' + [Environment]::NewLine + [Environment]::NewLine +
        'Sim  - importa os eventos agora (cópia estática).' + [Environment]::NewLine +
        'Não  - mostra o ficheiro na pasta para o publicares como subscrição.',
        'Calendário', 'YesNoCancel', 'Question')
    if ($choice -eq 'Yes') { Start-Process $IcsPath }
    elseif ($choice -eq 'No') { Start-Process explorer.exe "/select,`"$IcsPath`"" }
})

$btnOpen.Add_Click({
    if (Test-Path $OutputPath) { Start-Process $OutputPath }
})

$btnFolder.Add_Click({
    if (Test-Path $OutputPath) { Start-Process explorer.exe "/select,`"$OutputPath`"" }
})

$form.Add_Shown({
    if (Test-Path $OutputPath) {
        Show-Preview
        $btnOpen.Enabled     = $true
        $btnFolder.Enabled   = $true
        $btnDiscord.Enabled  = $true
        if (Test-Path $IcsPath) { $btnCalendar.Enabled = $true }
        $status.Text = 'Imagem anterior carregada.'
    }
    $form.Activate()
})

[void]$form.ShowDialog()
