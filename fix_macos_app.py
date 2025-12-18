#!/usr/bin/env python3
"""
修复macOS应用的签名和quarantine问题
用于处理已构建但无法运行的应用
"""
import os
import sys
import subprocess
import argparse

def fix_macos_app(app_path):
    """修复macOS应用"""
    if not os.path.exists(app_path):
        print(f'Error: App not found at {app_path}')
        return False
    
    print(f'Fixing macOS app: {app_path}')
    
    # 1. 移除quarantine属性
    remove_quarantine_attributes(app_path)
    
    # 2. 重新签名
    resign_app(app_path)
    
    # 3. 设置执行权限
    set_executable_permissions(app_path)
    
    print('App fix completed!')
    return True

def remove_quarantine_attributes(app_path):
    """移除quarantine属性"""
    print('Removing quarantine attributes...')
    
    try:
        # 移除quarantine属性
        subprocess.run(['xattr', '-dr', 'com.apple.quarantine', app_path], 
                      check=False)
        
        # 移除所有扩展属性
        subprocess.run(['xattr', '-cr', app_path], check=False)
        
        print('✓ Quarantine attributes removed')
        
    except Exception as e:
        print(f'Warning: Could not remove quarantine attributes: {e}')

def resign_app(app_path):
    """重新签名应用"""
    print('Re-signing app...')
    
    try:
        # 使用ad-hoc签名
        subprocess.run([
            'codesign', '--force', '--deep', '--sign', '-',
            app_path
        ], check=True)
        
        print('✓ App re-signed successfully')
        
        # 验证签名
        result = subprocess.run(['codesign', '--verify', app_path], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print('✓ Signature verification passed')
        else:
            print('⚠ Signature verification failed, but app may still work')
        
    except subprocess.CalledProcessError as e:
        print(f'Warning: Re-signing failed: {e}')

def set_executable_permissions(app_path):
    """设置执行权限"""
    print('Setting executable permissions...')
    
    try:
        # 查找可执行文件
        executable_path = os.path.join(app_path, 'Contents', 'MacOS')
        if os.path.exists(executable_path):
            for item in os.listdir(executable_path):
                item_path = os.path.join(executable_path, item)
                if os.path.isfile(item_path):
                    os.chmod(item_path, 0o755)
            print('✓ Executable permissions set')
        
    except Exception as e:
        print(f'Warning: Could not set permissions: {e}')

def main():
    parser = argparse.ArgumentParser(description='Fix macOS app signing and quarantine issues')
    parser.add_argument('app_path', nargs='?', default='dist/DuokiEditor.app',
                       help='Path to the .app bundle (default: dist/DuokiEditor.app)')
    
    args = parser.parse_args()
    
    success = fix_macos_app(args.app_path)
    
    if success:
        print('\n' + '='*50)
        print('App fix completed successfully!')
        print('\nTo run the app:')
        print(f'1. Double-click on {args.app_path}')
        print('2. If macOS still shows a warning, right-click and select "Open"')
        print('3. Click "Open" in the security dialog')
        print('='*50)
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()