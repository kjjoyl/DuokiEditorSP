import os
import sys
import shutil
import subprocess
from pathlib import Path

def build_windows():
    """Build Windows executable"""
    print("Building Windows executable...")
    
    # 清理之前的构建
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')
    
    # Use PyInstaller to package
    cmd = [
        "pyinstaller",
        "--name=DuokiEditor",
        "--windowed",
        "--icon=duoki_editor/resources/icons/app_icon.ico",
        # Include resources directory
        "--add-data=duoki_editor/resources;duoki_editor/resources",
        # Add config file
        "--add-data=duoki_editor/config.ini;duoki_editor",
        # Add constants file
        "--add-data=duoki_editor/constants.json;duoki_editor",
        # Add hidden imports
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtWidgets", 
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtMultimedia",
        "--hidden-import=pypinyin",
        "--hidden-import=pandas",
        "--hidden-import=openpyxl",
        "--hidden-import=requests",
        "--log-level=INFO",
        "--noconfirm",
        "--clean",
        "duoki_editor/main.py"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("Windows build completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error: {e}")
        return False

if __name__ == "__main__":
    # Only build for Windows
    if sys.platform.startswith('win'):
        success = build_windows()
        sys.exit(0 if success else 1)
    else:
        print("This script is only for Windows platform")
        sys.exit(1)
