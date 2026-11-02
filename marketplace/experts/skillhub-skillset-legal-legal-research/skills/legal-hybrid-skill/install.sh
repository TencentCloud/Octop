#!/bin/bash

# 法律助手(官方API+本地兜底) 技能安装脚本

# 功能：检查Python环境、安装依赖包、提示技能导入步骤

# 适用系统：Linux/MacOS（Windows系统请直接使用pip命令安装依赖）

# 运行方式：chmod +x install.sh && ./install.sh



# 1. 检查Python环境

echo "=== 检查Python环境 ==="

if command -v python3 &> /dev/null; then

    PYTHON_CMD="python3"

elif command -v python &> /dev/null; then

    PYTHON_CMD="python"

else

    echo "❌ 未检测到Python环境，请先安装Python 3.7及以上版本"

    exit 1

fi



# 检查Python版本

PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")

REQUIRED_VERSION="3.7"

if [ $(echo "$PYTHON_VERSION $REQUIRED_VERSION" | awk '{print ($1 >= $2) ? 1 : 0}') -eq 0 ]; then

    echo "❌ Python版本过低（当前版本：$PYTHON_VERSION），请升级至3.7及以上版本"

    exit 1

fi

echo "✅ Python环境正常（版本：$PYTHON_VERSION）"



# 2. 检查pip工具

echo -e "\n=== 检查pip工具 ==="

if command -v pip3 &> /dev/null; then

    PIP_CMD="pip3"

elif command -v pip &> /dev/null; then

    PIP_CMD="pip"

else

    echo "❌ 未检测到pip工具，正在尝试安装pip..."

    $PYTHON_CMD -m ensurepip --upgrade

    PIP_CMD="pip"

fi

echo "✅ pip工具正常"



# 3. 安装依赖包（对应requirements.txt）

echo -e "\n=== 安装依赖包 ==="

if [ -f "requirements.txt" ]; then

    $PIP_CMD install -r requirements.txt

    if [ $? -eq 0 ]; then

        echo "✅ 依赖包安装完成"

    else

        echo "❌ 依赖包安装失败，请检查requirements.txt文件是否存在且格式正确"

        exit 1

    fi

else

    echo "❌ 未找到requirements.txt文件，请将脚本与requirements.txt放在同一目录下"

    exit 1

fi



# 4. 技能导入提示

echo -e "\n=== 安装完成提示 ==="

echo "1. 请将以下5个文件放入同一文件夹，压缩为ZIP压缩包："

echo "   - main.py（技能主程序）"

echo "   - law_db.json（本地法条库）"

echo "   - case_db.json（本地案例库）"

echo "   - info.json（技能配置文件）"

echo "   - requirements.txt（依赖配置文件）"

echo "2. 打开QClaw平台，进入「技能管理」，点击「导入技能」选择压缩包即可使用"

echo -e "\n✅ 技能安装准备完成，可开始导入使用！"
