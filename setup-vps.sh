#!/bin/bash
# ========================================
# VPS Git 配置脚本
# VPS: ***REMOVED***
# ========================================

echo "========================================"
echo "  VPS Git Setup Script"
echo "  IP: ***REMOVED***"
echo "========================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ============================================
# Step 1: 检查并安装 Git
# ============================================
echo -e "${YELLOW}[Step 1/5] Checking Git installation...${NC}"
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version)
    echo -e "${GREEN}✓ Git already installed: $GIT_VERSION${NC}"
else
    echo "  Installing Git..."
    apt-get update -qq
    apt-get install -y git
    echo -e "${GREEN}✓ Git installed successfully${NC}"
fi
echo ""

# ============================================
# Step 2: 配置 Git（需要用户输入）
# ============================================
echo -e "${YELLOW}[Step 2/5] Configure Git${NC}"
echo ""
echo "Please enter your GitHub information:"
echo "--------------------------------------"

read -p "GitHub Username: " GITHUB_USERNAME
read -p "GitHub Email: " GITHUB_EMAIL

git config --global user.name "$GITHUB_USERNAME"
git config --global user.email "$GITHUB_EMAIL"
echo -e "${GREEN}✓ Git configured${NC}"
echo ""

# ============================================
# Step 3: 配置 GitHub Token（用于免密推送）
# ============================================
echo -e "${YELLOW}[Step 3/5] Setup GitHub Token (Optional)${NC}"
echo ""
echo "This allows you to push to GitHub without password."
echo "If you don't have a token, press Enter to skip."
echo ""
echo "Get token from: https://github.com/settings/tokens"
echo "--------------------------------------"

read -p "GitHub Token (press Enter to skip): " GITHUB_TOKEN

if [ -n "$GITHUB_TOKEN" ]; then
    # 保存 Token 到 Git 凭据（使用 HTTPS 时）
    git config --global credential.helper store
    echo "https://${GITHUB_USERNAME}:${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    chmod 600 ~/.git-credentials
    echo -e "${GREEN}✓ Token saved${NC}"
else
    echo -e "${YELLOW}! Skipped token setup${NC}"
fi
echo ""

# ============================================
# Step 4: 更新 investment-analyzer
# ============================================
echo -e "${YELLOW}[Step 4/5] Update investment-analyzer${NC}"
echo ""

read -p "Your GitHub repository URL (https://github.com/xxx/investment-analyzer.git): " REPO_URL

if [ -n "$REPO_URL" ]; then
    cd ~/investment-analyzer || {
        echo -e "${RED}✗ investment-analyzer directory not found${NC}"
        exit 1
    }

    echo "  → Backing up current code..."
    cp -r src src.backup.$(date +%Y%m%d_%H%M%S)

    echo "  → Checking if already a git repo..."
    if [ -d .git ]; then
        echo "  → Git repo exists, pulling latest code..."
        git remote set-url origin "$REPO_URL" 2>/dev/null
        git remote add origin "$REPO_URL" 2>/dev/null
        git pull origin main || git pull origin master
    else
        echo "  → Initializing new git repo..."
        git init
        git remote add origin "$REPO_URL"
        git pull origin main || git pull origin master
    fi

    echo "  → Restarting containers..."
    docker compose restart
    echo -e "${GREEN}✓ investment-analyzer updated${NC}"
else
    echo -e "${YELLOW}! Skipped investment-analyzer update${NC}"
fi
echo ""

# ============================================
# Step 5: 安装一键更新脚本
# ============================================
echo -e "${YELLOW}[Step 5/5] Install update script${NC}"
echo ""

cat > ~/update-all.sh << 'EOF'
#!/bin/bash
# 一键更新所有项目

echo "========================================"
echo "  Auto Update All Projects"
echo "========================================"
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# 更新 investment-analyzer
echo -e "${BLUE}[1/2]${NC} ${YELLOW}Updating investment-analyzer...${NC}"
cd ~/investment-analyzer || exit 1
git pull origin main 2>/dev/null || git pull
docker compose restart
echo -e "${GREEN}✓ Done${NC}"
echo ""

# 更新 media-brain
echo -e "${BLUE}[2/2]${NC} ${YELLOW}Updating media-brain...${NC}"
cd ~/media-brain || exit 1
if [ -d .git ]; then
    git pull 2>/dev/null
fi
docker compose restart
echo -e "${GREEN}✓ Done${NC}"
echo ""

echo "========================================"
echo -e "${GREEN}All updates completed!${NC}"
echo "========================================"
EOF

chmod +x ~/update-all.sh
echo -e "${GREEN}✓ Update script installed: ~/update-all.sh${NC}"
echo ""

# ============================================
# 完成
# ============================================
echo "========================================"
echo -e "${GREEN}Setup Completed!${NC}"
echo "========================================"
echo ""
echo "What's next:"
echo ""
echo "1. Update all projects anytime:"
echo "   ~/update-all.sh"
echo ""
echo "2. Check logs:"
echo "   docker logs -f investment-analyzer"
echo "   docker logs -f media-brain"
echo ""
echo "3. Add media-brain to Git (optional):"
echo "   cd ~/media-brain"
echo "   git init"
echo "   git add ."
echo "   git commit -m 'Initial commit'"
echo ""
echo "========================================"
echo ""
