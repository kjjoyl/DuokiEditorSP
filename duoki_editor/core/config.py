import os
import sys
from pathlib import Path

class Config:
    """配置类"""
    
    def __init__(self):
        # 设置默认值
        # 检查是否在打包后的环境中运行
        if getattr(sys, 'frozen', False):
            # 打包后的环境，使用_internal目录
            base_dir = os.path.join(os.path.dirname(sys.executable), "_internal")
            self.xlsx_cache_dir = os.path.join(base_dir, "duoki_editor", "cache", "data")
        else:
            # 开发环境
            self.xlsx_cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache\\data")
        
        self.use_local_xlsx_cache = False  # 是否使用本地xlsx文件缓存
        
        # 确保缓存目录存在
        os.makedirs(self.xlsx_cache_dir, exist_ok=True)
        
        # 加载配置
        self.load()
    
    def load(self):
        """加载配置"""
        # 这里可以从配置文件加载
        pass
    
    def save(self):
        """保存配置"""
        # 这里可以保存到配置文件
        pass
    
    def set_use_local_cache(self, value=True):
        """设置是否使用本地xlsx文件缓存"""
        self.use_local_xlsx_cache = value
        print(f"xlsx文件缓存状态: {'启用' if value else '禁用'}")