# PowerShell脚本：配置SSH私钥登录
# 使用方法：在PowerShell中运行 .\setup_ssh.ps1

$VPS_HOST = "104.129.11.185"
$VPS_USER = "root"
$VPS_PASS = "jyb10291225"
$PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGlaRLsFsxn4eQ54UiMFg3gCNl9rYH1o6KxcE99gujym nas"

Write-Host "正在配置SSH密钥认证到 $VPS_HOST ..." -ForegroundColor Green

# 创建SSH命令
$sshCommand = @"
mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$PUBLIC_KEY' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo '✅ SSH密钥配置成功！'
"@

# 使用plink（如果安装了PuTTY）或者ssh
$plinkPath = "C:\Program Files\PuTTY\plink.exe"
$sshPath = "ssh"

# 检测是否有plink
if (Test-Path $plinkPath) {
    Write-Host "使用PuTTY plink..." -ForegroundColor Yellow
    $echo = $VPS_PASS | & $plinkPath -ssh -batch -pw $VPS_PASS $VPS_USER@$VPS_HOST $sshCommand
} else {
    Write-Host "使用SSH（可能需要手动输入密码）..." -ForegroundColor Yellow
    $echo = & $sshPath $VPS_USER@$VPS_HOST $sshCommand
}

Write-Host $echo
Write-Host "`n配置完成！现在可以测试私钥连接。" -ForegroundColor Green
