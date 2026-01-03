#!/bin/bash
# ========================================
# VPS 快速部署脚本
# ========================================

echo "========================================"
echo "  VPS 部署脚本 - 回测系统更新"
echo "========================================"
echo ""

# 1. 备份重要文件
echo "📦 备份重要配置文件..."
cd ~/investment-analyzer
cp .env .env.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || echo "⚠️ .env 不存在"
cp config.yaml config.yaml.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || echo "⚠️ config.yaml 不存在"

# 备份数据目录
if [ -d "data" ]; then
    echo "📦 备份数据文件..."
    cp -r data data.backup.$(date +%Y%m%d_%H%M%S)
fi

echo ""

# 2. 备份整个项目目录
echo "📦 备份整个项目目录..."
cd ~
BACKUP_DIR="investment-analyzer-backup-$(date +%Y%m%d_%H%M%S)"
mv investment-analyzer "$BACKUP_DIR"
echo "✅ 项目已备份到: $BACKUP_DIR"
echo ""

# 3. 克隆最新代码
echo "📥 从GitHub克隆最新代码..."
git clone https://github.com/Sufentanyl/investment-analyzer.git
cd investment-analyzer
echo "✅ 克隆完成"
echo ""

# 4. 恢复配置文件
echo "🔧 恢复配置文件..."
if [ -f "../$BACKUP_DIR/.env.backup."* ]; then
    cp ../$BACKUP_DIR/.env.backup.* .env
    echo "✅ .env 已恢复"
fi

if [ -f "../$BACKUP_DIR/config.yaml.backup."* ]; then
    cp ../$BACKUP_DIR/config.yaml.backup.* config.yaml
    echo "✅ config.yaml 已恢复"
fi

# 恢复数据文件
if [ -d "../$BACKUP_DIR/data.backup."* ]; then
    cp -r ../$BACKUP_DIR/data.backup.*/data/* data/
    echo "✅ data 已恢复"
fi

echo ""

# 5. 设置文件权限
echo "🔐 设置文件权限..."
chmod 600 .env 2>/dev/null || echo "⚠️ .env 不存在"
chmod 644 config.yaml 2>/dev/null || echo "⚠️ config.yaml 不存在"
echo "✅ 权限设置完成"
echo ""

# 6. 查看最新提交
echo "📜 最新提交记录："
git log --oneline -5
echo ""

# 7. 重启容器
echo "🔄 重启Docker容器..."
docker compose down
docker compose up -d --build
echo ""

# 8. 等待容器启动
echo "⏳ 等待容器启动..."
sleep 15
echo ""

# 9. 检查容器状态
echo "✅ 容器状态："
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# 10. 查看日志
echo "📊 最新日志（最近30行）："
docker compose logs --tail=30
echo ""

echo "========================================"
echo "  部署完成！"
echo "========================================"
echo ""
echo "📍 项目目录: ~/investment-analyzer"
echo "📦 备份目录: ~/$BACKUP_DIR"
echo ""
echo "🧪 测试回测功能："
echo "   在Telegram发送: /backtest 30 hold_3_days"
echo ""
echo "📊 查看Dashboard:"
echo "   http://***REMOVED***:8501"
echo ""
echo "🔍 查看日志:"
echo "   docker logs -f investment-analyzer"
echo ""
