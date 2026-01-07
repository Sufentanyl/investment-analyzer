#!/bin/bash

# VPS信息
VPS_HOST="104.129.11.185"
VPS_USER="root"
VPS_PASS="jyb10291225"
PUBLIC_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGlaRLsFsxn4eQ54UiMFg3gCNl9rYH1o6KxcE99gujym nas"

# 使用sshpass复制公钥（如果安装了）
if command -v sshpass &> /dev/null; then
    sshpass -p "$VPS_PASS" ssh-copy-id -o StrictHostKeyChecking=no "$VPS_USER@$VPS_HOST" <<< "y" 2>/dev/null
else
    # 备用方案：通过SSH直接添加
    echo "正在配置SSH密钥认证..."

    # 创建临时期待脚本
    cat > /tmp/ssh_setup.exp << 'EOF'
#!/usr/bin/expect -f
set timeout 30
set password "jyb10291225"
set pubkey "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGlaRLsFsxn4eQ54UiMFg3gCNl9rYH1o6KxcE99gujym nas"

spawn ssh -o StrictHostKeyChecking=no root@104.129.11.185 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && echo 'SSH密钥配置成功'"

expect {
    "password:" {
        send "$password\r"
        exp_continue
    }
    eof
}
EOF

    # 如果有expect，使用它
    if command -v expect &> /dev/null; then
        expect /tmp/ssh_setup.exp
        rm -f /tmp/ssh_setup.exp
    else
        echo "错误: 需要安装 sshpass 或 expect"
        exit 1
    fi
fi

echo "配置完成！"
