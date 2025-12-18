#!/bin/bash

echo "🍎 DuokiEditor Mac环境设置脚本"
echo "=================================="

# 检查是否安装了Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ 未检测到Homebrew，正在安装..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "✅ Homebrew已安装"
fi

# 安装Chrome（如果未安装）
if [ ! -d "/Applications/Google Chrome.app" ]; then
    echo "📥 正在安装Google Chrome..."
    brew install --cask google-chrome
else
    echo "✅ Google Chrome已安装"
fi

# 安装chromedriver
echo "🚗 正在安装chromedriver..."
brew install chromedriver

# 检查chromedriver路径
CHROMEDRIVER_PATH=$(which chromedriver)
if [ -n "$CHROMEDRIVER_PATH" ]; then
    echo "✅ chromedriver已安装在: $CHROMEDRIVER_PATH"
    
    # 解除Mac安全限制
    echo "🔓 正在解除Mac安全限制..."
    xattr -d com.apple.quarantine "$CHROMEDRIVER_PATH" 2>/dev/null || true
    chmod +x "$CHROMEDRIVER_PATH"
    
    echo "✅ chromedriver权限设置完成"
else
    echo "❌ chromedriver安装失败"
    exit 1
fi

# 安装Python依赖
echo "🐍 正在安装Python依赖..."
pip3 install selenium beautifulsoup4 requests

# 验证安装
echo "🧪 验证安装..."
python3 -c "
import selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import requests
from bs4 import BeautifulSoup
print('✅ 所有Python依赖已正确安装')
"

echo ""
echo "🎉 Mac环境设置完成！"
echo "现在可以运行测试脚本："
echo "python3 test_username_scraper.py"
echo ""
echo "如果遇到问题，请检查："
echo "1. Chrome版本: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --version"
echo "2. chromedriver版本: chromedriver --version"
echo "3. 确保两者版本兼容"