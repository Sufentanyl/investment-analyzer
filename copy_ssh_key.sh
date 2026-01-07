#!/bin/bash
# 在Git Bash中执行此脚本

echo "正在配置SSH密钥到VPS..."

# 使用一次密码登录，自动配置公钥
ssh -o StrictHostKeyChecking=no root@104.129.11.185 'bash -s' << 'ENDSSH'
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGlaRLsFsxn4eQ54UiMFg3gCNl9rYH1o6KxcE99gujym nas" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "✅ SSH密钥配置成功！"
ENDSSH

echo "配置完成！"
