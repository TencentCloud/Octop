#!/bin/bash
# 智能老师技能依赖自动安装脚本
# 此脚本会自动检测并安装所有需要的依赖

set -e  # 遇到错误立即退出

echo "========================================="
echo "  智能老师技能 - 依赖自动安装脚本"
echo "========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
log_info "检测到操作系统: $OS"

# 1. 检测并安装 Python
check_python() {
    log_info "检查 Python 环境..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        log_info "Python 已安装: $PYTHON_VERSION"
        return 0
    else
        log_warn "Python 未安装，正在尝试安装..."
        
        if [[ "$OS" == "macos" ]]; then
            if command -v brew &> /dev/null; then
                brew install python3
            else
                log_error "Homebrew 未安装，请先安装 Homebrew: https://brew.sh/"
                return 1
            fi
        elif [[ "$OS" == "linux" ]]; then
            if command -v apt-get &> /dev/null; then
                sudo apt-get update
                sudo apt-get install -y python3 python3-pip
            elif command -v yum &> /dev/null; then
                sudo yum install -y python3 python3-pip
            else
                log_error "无法自动安装 Python，请手动安装"
                return 1
            fi
        fi
        
        return 0
    fi
}

# 2. 检测并安装 Node.js
check_nodejs() {
    log_info "检查 Node.js 环境..."
    
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        log_info "Node.js 已安装: $NODE_VERSION"
        return 0
    else
        log_warn "Node.js 未安装，正在尝试安装..."
        
        if [[ "$OS" == "macos" ]]; then
            if command -v brew &> /dev/null; then
                brew install node
            else
                log_error "Homebrew 未安装，请先安装 Homebrew: https://brew.sh/"
                return 1
            fi
        elif [[ "$OS" == "linux" ]]; then
            if command -v apt-get &> /dev/null; then
                curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
                sudo apt-get install -y nodejs
            elif command -v yum &> /dev/null; then
                curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -
                sudo yum install -y nodejs
            else
                log_error "无法自动安装 Node.js，请手动安装"
                return 1
            fi
        fi
        
        return 0
    fi
}

# 3. 安装 Python 依赖
install_python_deps() {
    log_info "安装 Python 依赖包..."
    
    # 创建虚拟环境（可选）
    if [[ ! -d "$HOME/.workbuddy/venv" ]]; then
        log_info "创建 Python 虚拟环境..."
        python3 -m venv "$HOME/.workbuddy/venv"
    fi
    
    # 激活虚拟环境
    source "$HOME/.workbuddy/venv/bin/activate"
    
    # 安装必要的 Python 包
    PYTHON_PACKAGES=(
        "pillow"        # 图像处理
        "pytesseract"   # OCR 文字识别
        "requests"      # HTTP 请求
        "openpyxl"      # Excel 处理
        "python-docx"   # Word 文档处理
    )
    
    for package in "${PYTHON_PACKAGES[@]}"; do
        if python3 -c "import $package" 2>/dev/null; then
            log_info "$package 已安装"
        else
            log_info "安装 $package..."
            pip install "$package" --quiet
        fi
    done
    
    log_info "Python 依赖安装完成"
}

# 4. 安装 Node.js 依赖
install_nodejs_deps() {
    log_info "安装 Node.js 依赖包..."
    
    # 检查是否在项目目录
    if [[ -f "package.json" ]]; then
        npm install --quiet
        log_info "Node.js 依赖安装完成"
    else
        log_info "未找到 package.json，跳过 npm install"
    fi
    
    # 安装全局包
    NODE_PACKAGES=(
        "docx"          # Word 文档生成
    )
    
    # 检查 docx 包
    if ! node -e "require('docx')" 2>/dev/null; then
        log_info "安装 docx 包..."
        npm install docx --save --quiet 2>/dev/null || true
    fi
}

# 5. 安装系统依赖（OCR 相关）
install_system_deps() {
    log_info "检查系统依赖..."
    
    if [[ "$OS" == "macos" ]]; then
        # 检查 tesseract（OCR引擎）
        if ! command -v tesseract &> /dev/null; then
            log_info "安装 tesseract OCR 引擎..."
            brew install tesseract tesseract-lang
        else
            log_info "tesseract 已安装"
        fi
        
        # 检查 imagemagick（图像处理）
        if ! command -v convert &> /dev/null; then
            log_info "安装 imagemagick..."
            brew install imagemagick
        else
            log_info "imagemagick 已安装"
        fi
        
    elif [[ "$OS" == "linux" ]]; then
        # 检查 tesseract
        if ! command -v tesseract &> /dev/null; then
            log_info "安装 tesseract OCR 引擎..."
            if command -v apt-get &> /dev/null; then
                sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim
            elif command -v yum &> /dev/null; then
                sudo yum install -y tesseract tesseract-langpack-chi_sim
            fi
        else
            log_info "tesseract 已安装"
        fi
        
        # 检查 imagemagick
        if ! command -v convert &> /dev/null; then
            log_info "安装 imagemagick..."
            if command -v apt-get &> /dev/null; then
                sudo apt-get install -y imagemagick
            elif command -v yum &> /dev/null; then
                sudo yum install -y ImageMagick
            fi
        else
            log_info "imagemagick 已安装"
        fi
    fi
}

# 6. 验证安装
verify_installation() {
    log_info "验证依赖安装..."
    
    local errors=0
    
    # 验证 Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 验证失败"
        ((errors++))
    fi
    
    # 验证 Node.js
    if ! command -v node &> /dev/null; then
        log_error "Node.js 验证失败"
        ((errors++))
    fi
    
    # 验证 Python 包
    if ! python3 -c "import PIL" 2>/dev/null; then
        log_error "Pillow 验证失败"
        ((errors++))
    fi
    
    # 验证 Node.js docx 包
    if [[ -f "package.json" ]]; then
        if ! node -e "require('docx')" 2>/dev/null; then
            log_warn "docx 包未在项目中安装，将在首次使用时安装"
        fi
    fi
    
    # 验证 OCR（可选）
    if ! command -v tesseract &> /dev/null; then
        log_warn "tesseract 未安装（OCR 功能不可用）"
    fi
    
    if [[ $errors -eq 0 ]]; then
        log_info "✅ 所有依赖验证通过"
        return 0
    else
        log_error "❌ 部分依赖验证失败，请检查错误信息"
        return 1
    fi
}

# 主执行流程
main() {
    echo ""
    log_info "开始安装智能老师技能依赖..."
    echo ""
    
    # 执行安装步骤
    check_python || { log_error "Python 安装失败"; exit 1; }
    check_nodejs || { log_error "Node.js 安装失败"; exit 1; }
    install_python_deps || { log_error "Python 依赖安装失败"; exit 1; }
    install_nodejs_deps || { log_error "Node.js 依赖安装失败"; exit 1; }
    install_system_deps || { log_warn "系统依赖安装失败，部分功能可能不可用"; }
    
    echo ""
    log_info "安装完成，正在验证..."
    echo ""
    
    verify_installation || { log_error "验证失败，请手动检查"; exit 1; }
    
    echo ""
    log_info "========================================="
    log_info "  🎉 智能老师技能依赖安装完成！"
    log_info "========================================="
    echo ""
}

# 执行主函数
main
