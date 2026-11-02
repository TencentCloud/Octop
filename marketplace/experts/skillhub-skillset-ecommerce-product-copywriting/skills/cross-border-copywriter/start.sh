#!/bin/bash
# 跨境电商商品文案智能生成器（升级版）部署脚本
# Skill标识：cross_border_copywriter_v2
# 部署环境：Linux/Unix系统
# 功能：自动安装依赖、部署程序、设置运行权限、测试运行

# 定义变量
SKILL_NAME="cross_border_copywriter_v2"
PY_FILE="${SKILL_NAME}.py"
TXT_FILE="${SKILL_NAME}.txt"
MD_FILE="${SKILL_NAME}.md"
SH_FILE="${SKILL_NAME}.sh"
PYTHON_VERSION="3.7"

# 检查系统Python版本
check_python() {
    echo "============================================="
    echo "检查Python版本..."
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        PY_VERSION=$($PYTHON_CMD --version | awk '{print $2}')
        echo "当前Python版本：$PY_VERSION"
        # 比较版本（至少3.7）
        if [[ $(echo -e "$PY_VERSION\n$PYTHON_VERSION" | sort -V | head -n1) != "$PYTHON_VERSION" ]]; then
            echo "错误：Python版本需≥$PYTHON_VERSION，请升级Python后重新部署！"
            exit 1
        fi
    else
        echo "错误：未检测到Python3，请安装Python3.7及以上版本！"
        exit 1
    fi
}

# 检查文件完整性
check_files() {
    echo "============================================="
    echo "检查部署文件完整性..."
    FILES=("$PY_FILE" "$TXT_FILE" "$MD_FILE" "$SH_FILE")
    for file in "${FILES[@]}"; do
        if [ ! -f "$file" ]; then
            echo "错误：缺少部署文件 $file，请确保四份文件齐全！"
            exit 1
        fi
    done
    echo "所有部署文件齐全，继续部署..."
}

# 设置文件权限
set_permissions() {
    echo "============================================="
    echo "设置文件运行权限..."
    chmod +x "$PY_FILE"  # 给Python文件添加执行权限
    chmod +x "$SH_FILE"  # 给脚本文件添加执行权限
    echo "权限设置完成！"
}

# 测试运行程序
test_run() {
    echo "============================================="
    echo "测试运行Skill程序..."
    $PYTHON_CMD "$PY_FILE"
    if [ $? -eq 0 ]; then
        echo "测试运行成功！Skill部署完成！"
    else
        echo "测试运行失败，请检查程序代码或运行环境！"
        exit 1
    fi
}

# 部署完成提示
deploy_complete() {
    echo "============================================="
    echo "【跨境电商商品文案智能生成器（升级版）】部署完成！"
    echo "Skill标识：$SKILL_NAME"
    echo "运行方式："
    echo "  1. 直接运行：$PYTHON_CMD $PY_FILE"
    echo "  2. 作为模块调用：导入CrossBorderCopywriter类"
    echo "  3. 查看配置说明：cat $TXT_FILE"
    echo "  4. 查看详细文档：cat $MD_FILE"
    echo "============================================="
}

# 执行部署流程
main() {
    check_python
    check_files
    set_permissions
    test_run
    deploy_complete
}

# 启动部署
main
