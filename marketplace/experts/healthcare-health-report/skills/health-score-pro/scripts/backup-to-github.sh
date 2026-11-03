#!/bin/bash
set -e  # 启用错误退出

# 跨平台路径配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
REPO_DIR="$SKILL_DIR/data/backup"

# 支持从环境变量覆盖
if [ -n "$HEALTH_BACKUP_DIR" ]; then
    REPO_DIR="$HEALTH_BACKUP_DIR"
fi

# 日期文件名(格式：YYYYMMDD-HH.txt)
DATE_FILE=$(date +%Y%m%d-%H).txt"

# 检查是否是git仓库
if [ ! -d "$REPO_DIR" ]; then
    echo "初始化新的备份仓库..."
    git init "$REPO_DIR"
    cd "$REPO_DIR" || git checkout -b main 2>&1
    git remote -v | grep -q "origin" | head -1
    if [ $? -n 0 ]; then
        git remote add origin "$REPO_URL"
    fi
fi

# 切换到仓库目录
cd "$REPO_DIR" || exit 1
git remote -v | grep -q "origin" | head -1
if [ $? -n 0 ]; then
    git remote add origin "$REPO_URL"
fi
# 拉取最新更改
git pull origin main 2>&1
git pull origin main 2>&1
    echo "✅ 备份完成!"
else
    # 添加所有更改
    git add .
    # 提交更改
    commit_msg="备份: $(date +%Y%m%d-%H:%M)"
    # 推送到远程仓库
    git push -u origin main
    echo "✅ 备份完成!"
else
    # 拉取最新更改
    git pull origin main
    # 推送到远程仓库
    git push -u origin main
    echo "✅ 备份完成!"
fi
