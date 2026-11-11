#!/bin/bash
# ========================================
# 一键更新所有项目
# VPS: <YOUR_VPS_IP>
# 项目: investment-analyzer + media-brain
# ========================================

echo "========================================"
echo "  Auto Update All Projects"
echo "  VPS: <YOUR_VPS_IP>"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================
# 项目1: investment-analyzer
# ============================================
echo -e "${BLUE}[1/2]${NC} ${YELLOW}Updating investment-analyzer...${NC}"
cd ~/investment-analyzer || {
    echo -e "${RED}✗ Failed to cd to investment-analyzer${NC}"
    exit 1
}

echo "  → Pulling latest code from GitHub..."
if git pull origin main; then
    echo -e "${GREEN}  ✓ Code updated${NC}"
else
    echo -e "${RED}  ✗ Git pull failed${NC}"
    echo "  → Continuing with restart..."
fi

echo "  → Restarting Docker containers..."
if docker compose restart; then
    echo -e "${GREEN}  ✓ Containers restarted${NC}"
else
    echo -e "${RED}  ✗ Restart failed${NC}"
fi

echo -e "${GREEN}✓ investment-analyzer updated successfully!${NC}"
echo ""

# ============================================
# 项目2: media-brain
# ============================================
echo -e "${BLUE}[2/2]${NC} ${YELLOW}Updating media-brain...${NC}"
cd ~/media-brain || {
    echo -e "${RED}✗ Failed to cd to media-brain${NC}"
    exit 1
}

echo "  → Pulling latest code from GitHub..."
if git pull origin main 2>/dev/null || git pull; then
    echo -e "${GREEN}  ✓ Code updated${NC}"
else
    echo -e "${YELLOW}  ! Git pull failed (might not be a git repo yet)${NC}"
    echo "  → Skipping git pull, attempting restart..."
fi

echo "  → Restarting Docker containers..."
if docker compose restart; then
    echo -e "${GREEN}  ✓ Containers restarted${NC}"
else
    echo -e "${RED}  ✗ Restart failed${NC}"
fi

echo -e "${GREEN}✓ media-brain updated successfully!${NC}"
echo ""

# ============================================
# 检查容器状态
# ============================================
echo "========================================"
echo -e "${BLUE}Container Status:${NC}"
echo "========================================"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "========================================"
echo -e "${GREEN}All updates completed!${NC}"
echo "========================================"
echo ""
echo "View logs:"
echo "  investment-analyzer: docker logs -f investment-analyzer"
echo "  media-brain:         docker logs -f media-brain"
echo ""
echo "Update again anytime:"
echo "  ~/update-all.sh"
echo ""
