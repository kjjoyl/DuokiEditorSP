#!/usr/bin/env python3
"""
macOS构建脚本
"""
import os
import sys
import subprocess
import shutil

def build_macos():
    """构建macOS应用程序"""
    print('Building macOS application...')
    
    # 清理之前的构建
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')
    
    # 构建应用
    cmd = [
        'pyinstaller',
        'DuokiEditor.spec'
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print('PyInstaller build completed successfully!')
        
        # 后处理：签名和公证
        app_path = 'dist/DuokiEditor.app'
        if os.path.exists(app_path):
            print('Post-processing macOS app...')
            post_process_macos_app(app_path)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f'Build failed with error: {e}')
        return False

def post_process_macos_app(app_path):
    """后处理macOS应用：签名和公证"""
    print(f'Post-processing {app_path}...')
    
    # 检查是否有开发者证书
    developer_id = get_developer_identity()
    
    if developer_id:
        print(f'Found developer identity: {developer_id}')
        sign_app(app_path, developer_id)
    else:
        print('No developer identity found. Creating ad-hoc signature...')
        create_adhoc_signature(app_path)
    
    # 移除扩展属性（quarantine标记）
    remove_quarantine_attributes(app_path)

def get_developer_identity():
    """获取开发者身份"""
    try:
        result = subprocess.run([
            'security', 'find-identity', '-v', '-p', 'codesigning'
        ], capture_output=True, text=True, check=True)
        
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if 'Developer ID Application' in line:
                # 提取身份标识
                parts = line.split('"')
                if len(parts) >= 2:
                    return parts[1]
        return None
    except subprocess.CalledProcessError:
        return None

def sign_app(app_path, identity):
    """使用开发者证书签名应用"""
    print(f'Signing app with identity: {identity}')
    
    try:
        # 深度签名
        subprocess.run([
            'codesign', '--force', '--deep', '--sign', identity,
            '--entitlements', 'entitlements.plist',
            '--options', 'runtime',
            app_path
        ], check=True)
        
        print('App signed successfully!')
        
        # 验证签名
        subprocess.run(['codesign', '--verify', '--verbose', app_path], check=True)
        print('Signature verification passed!')
        
    except subprocess.CalledProcessError as e:
        print(f'Signing failed: {e}')
        print('Falling back to ad-hoc signature...')
        create_adhoc_signature(app_path)

def create_adhoc_signature(app_path):
    """创建ad-hoc签名"""
    print('Creating ad-hoc signature...')
    
    try:
        # Ad-hoc签名
        subprocess.run([
            'codesign', '--force', '--deep', '--sign', '-',
            '--entitlements', 'entitlements.plist',
            app_path
        ], check=True)
        
        print('Ad-hoc signature created successfully!')
        
    except subprocess.CalledProcessError as e:
        print(f'Ad-hoc signing failed: {e}')

def remove_quarantine_attributes(app_path):
    """移除quarantine属性"""
    print('Removing quarantine attributes...')
    
    try:
        # 移除quarantine属性
        subprocess.run(['xattr', '-dr', 'com.apple.quarantine', app_path], 
                      check=False)  # 不检查返回码，因为属性可能不存在
        
        # 移除其他可能的属性
        subprocess.run(['xattr', '-cr', app_path], check=False)
        
        print('Quarantine attributes removed!')
        
    except subprocess.CalledProcessError as e:
        print(f'Warning: Could not remove quarantine attributes: {e}')

if __name__ == '__main__':
    success = build_macos()
    sys.exit(0 if success else 1)