#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能老师技能 - 快速依赖检查和安装脚本（Python版本）
用于在技能加载时自动检查和安装依赖
"""

import subprocess
import sys
import os
import importlib
from pathlib import Path

class DependencyManager:
    """依赖管理器"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.installed = []
    
    def log(self, message, level="INFO"):
        """日志输出"""
        prefix = {
            "INFO": "✅",
            "WARN": "⚠️",
            "ERROR": "❌",
            "INSTALL": "📦"
        }
        print(f"{prefix.get(level, '•')} {message}")
    
    def check_command(self, command):
        """检查命令是否存在"""
        try:
            result = subprocess.run(
                [command, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def check_python_package(self, package_name, import_name=None):
        """检查 Python 包是否安装"""
        import_name = import_name or package_name
        try:
            importlib.import_module(import_name)
            return True
        except ImportError:
            return False
    
    def install_python_package(self, package_name, import_name=None):
        """安装 Python 包"""
        import_name = import_name or package_name
        
        try:
            self.log(f"安装 {package_name}...", "INSTALL")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name, "--quiet"],
                check=True,
                capture_output=True,
                timeout=60
            )
            self.log(f"{package_name} 安装成功", "INFO")
            self.installed.append(package_name)
            return True
        except subprocess.CalledProcessError as e:
            self.log(f"{package_name} 安装失败: {e}", "ERROR")
            self.errors.append(f"Python package: {package_name}")
            return False
        except subprocess.TimeoutExpired:
            self.log(f"{package_name} 安装超时", "ERROR")
            self.errors.append(f"Python package: {package_name}")
            return False
    
    def check_and_install_python_package(self, package_name, import_name=None, required=True):
        """检查并安装 Python 包"""
        import_name = import_name or package_name
        
        if self.check_python_package(package_name, import_name):
            self.log(f"{package_name} 已安装", "INFO")
            return True
        else:
            if required:
                return self.install_python_package(package_name, import_name)
            else:
                self.log(f"{package_name} 未安装（可选）", "WARN")
                self.warnings.append(f"Python package (optional): {package_name}")
                return False
    
    def check_node_package(self, package_name):
        """检查 Node.js 包是否安装"""
        try:
            result = subprocess.run(
                ["node", "-e", f"require('{package_name}')"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def install_node_package(self, package_name):
        """安装 Node.js 包"""
        try:
            self.log(f"安装 {package_name}...", "INSTALL")
            
            # 检查是否在项目目录
            if os.path.exists("package.json"):
                subprocess.run(
                    ["npm", "install", package_name, "--save", "--quiet"],
                    check=True,
                    capture_output=True,
                    timeout=60
                )
            else:
                # 全局安装或创建临时项目
                subprocess.run(
                    ["npm", "install", "-g", package_name, "--quiet"],
                    check=True,
                    capture_output=True,
                    timeout=60
                )
            
            self.log(f"{package_name} 安装成功", "INFO")
            self.installed.append(package_name)
            return True
        except subprocess.CalledProcessError as e:
            self.log(f"{package_name} 安装失败: {e}", "ERROR")
            self.errors.append(f"Node package: {package_name}")
            return False
        except subprocess.TimeoutExpired:
            self.log(f"{package_name} 安装超时", "ERROR")
            self.errors.append(f"Node package: {package_name}")
            return False
    
    def check_and_install_node_package(self, package_name, required=True):
        """检查并安装 Node.js 包"""
        if self.check_node_package(package_name):
            self.log(f"{package_name} 已安装", "INFO")
            return True
        else:
            if required:
                return self.install_node_package(package_name)
            else:
                self.log(f"{package_name} 未安装（可选）", "WARN")
                self.warnings.append(f"Node package (optional): {package_name}")
                return False
    
    def setup_all(self):
        """安装所有依赖"""
        print("\n" + "="*50)
        print("  智能老师技能 - 依赖自动安装")
        print("="*50 + "\n")
        
        # 1. 检查 Python
        self.log("检查 Python 环境...")
        python_version = sys.version_info
        if python_version.major >= 3 and python_version.minor >= 6:
            self.log(f"Python {python_version.major}.{python_version.minor}.{python_version.micro}")
        else:
            self.log("Python 版本过低，需要 3.6+", "ERROR")
            self.errors.append("Python version")
        
        print()
        
        # 2. 安装 Python 必需包
        self.log("检查 Python 必需包...")
        required_python_packages = [
            ("pillow", "PIL"),           # 图像处理
            ("requests", "requests"),     # HTTP 请求
        ]
        
        for package_name, import_name in required_python_packages:
            self.check_and_install_python_package(package_name, import_name, required=True)
        
        print()
        
        # 3. 安装 Python 可选包
        self.log("检查 Python 可选包...")
        optional_python_packages = [
            ("pytesseract", "pytesseract"),   # OCR（可选）
            ("python-docx", "docx"),          # Word 文档（可选，用 Node.js docx 替代）
            ("openpyxl", "openpyxl"),          # Excel（可选）
        ]
        
        for package_name, import_name in optional_python_packages:
            self.check_and_install_python_package(package_name, import_name, required=False)
        
        print()
        
        # 4. 检查 Node.js
        self.log("检查 Node.js 环境...")
        if self.check_command("node"):
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True
            )
            self.log(f"Node.js {result.stdout.strip()}")
        else:
            self.log("Node.js 未安装", "ERROR")
            self.errors.append("Node.js")
        
        print()
        
        # 5. 安装 Node.js 包
        self.log("检查 Node.js 包...")
        self.check_and_install_node_package("docx", required=True)
        
        print()
        
        # 6. 检查可选系统依赖
        self.log("检查系统可选依赖...")
        if self.check_command("tesseract"):
            self.log("tesseract OCR 引擎已安装", "INFO")
        else:
            self.log("tesseract 未安装（OCR 功能不可用）", "WARN")
            self.warnings.append("tesseract (optional)")
        
        print()
        
        # 7. 总结
        print("="*50)
        
        if self.errors:
            self.log("安装完成，但有以下错误：", "ERROR")
            for error in self.errors:
                print(f"  - {error}")
            return False
        
        if self.warnings:
            self.log("安装完成，有以下警告：", "WARN")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if self.installed:
            self.log(f"本次安装了 {len(self.installed)} 个依赖包：", "INSTALL")
            for package in self.installed:
                print(f"  - {package}")
        
        self.log("所有必需依赖安装完成！", "INFO")
        print("="*50 + "\n")
        
        return True


def main():
    """主函数"""
    manager = DependencyManager()
    success = manager.setup_all()
    
    if success:
        print("✅ 智能老师技能已就绪！")
        return 0
    else:
        print("❌ 部分依赖安装失败，请检查错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())
