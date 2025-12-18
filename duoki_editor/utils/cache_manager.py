"""
缓存管理器 - 用于清除QtWebEngine和应用的各种缓存数据
"""

import os
import shutil
import platform
from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWebEngineCore import QWebEngineProfile


class CacheManager:
    """缓存管理器，提供清除各种缓存的功能"""
    
    def __init__(self):
        self.app_name = "DuokiEditor"
    
    def get_webengine_cache_paths(self):
        """获取QtWebEngine缓存路径"""
        paths = []
        
        # 获取标准缓存路径
        cache_location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        data_location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        
        # QtWebEngine缓存路径
        webengine_cache_paths = [
            os.path.join(cache_location, "QtWebEngine"),
            os.path.join(data_location, "QtWebEngine"),
        ]
        
        # 平台特定路径
        if platform.system() == "Windows":
            # Windows路径
            appdata = os.environ.get('APPDATA', '')
            if appdata:
                webengine_cache_paths.append(os.path.join(appdata, self.app_name, "QtWebEngine"))
        elif platform.system() == "Darwin":  # macOS
            # macOS路径
            home = os.path.expanduser("~")
            webengine_cache_paths.extend([
                os.path.join(home, "Library", "Application Support", self.app_name, "QtWebEngine"),
                os.path.join(home, "Library", "Caches", self.app_name, "QtWebEngine"),
            ])
        elif platform.system() == "Linux":
            # Linux路径
            home = os.path.expanduser("~")
            webengine_cache_paths.extend([
                os.path.join(home, ".cache", self.app_name, "QtWebEngine"),
                os.path.join(home, ".local", "share", self.app_name, "QtWebEngine"),
            ])
        
        # 过滤存在的路径
        for path in webengine_cache_paths:
            if os.path.exists(path):
                paths.append(path)
        
        return paths
    
    def clear_webengine_profile_cache(self, profile: QWebEngineProfile):
        """清除指定QWebEngineProfile的缓存"""
        try:
            if profile:
                # 清除cookies
                cookie_store = profile.cookieStore()
                cookie_store.deleteAllCookies()
                
                # 清除HTTP缓存
                profile.clearHttpCache()
                
                # 清除访问历史
                profile.clearAllVisitedLinks()
                
                print("✅ 已清除WebEngine Profile缓存")
                return True
        except Exception as e:
            print(f"❌ 清除WebEngine Profile缓存失败: {e}")
            return False
    
    def clear_webengine_disk_cache(self):
        """清除磁盘上的QtWebEngine缓存文件"""
        cleared_paths = []
        failed_paths = []
        
        cache_paths = self.get_webengine_cache_paths()
        
        for path in cache_paths:
            try:
                if os.path.exists(path):
                    print(f"🧹 清除缓存目录: {path}")
                    shutil.rmtree(path)
                    cleared_paths.append(path)
                    print(f"✅ 已清除: {path}")
            except Exception as e:
                print(f"❌ 清除失败 {path}: {e}")
                failed_paths.append((path, str(e)))
        
        return cleared_paths, failed_paths
    
    def get_cache_info(self):
        """获取缓存信息"""
        info = {
            "cache_paths": self.get_webengine_cache_paths(),
            "total_size": 0,
            "file_count": 0
        }
        
        for path in info["cache_paths"]:
            if os.path.exists(path):
                try:
                    for root, dirs, files in os.walk(path):
                        info["file_count"] += len(files)
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                info["total_size"] += os.path.getsize(file_path)
                            except (OSError, IOError):
                                pass
                except Exception as e:
                    print(f"获取缓存信息失败 {path}: {e}")
        
        return info
    
    def format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def clear_all_cache(self, profile: QWebEngineProfile = None):
        """清除所有缓存（内存和磁盘）"""
        results = {
            "profile_cleared": False,
            "disk_cleared_paths": [],
            "disk_failed_paths": [],
            "total_success": False
        }
        
        # 清除Profile缓存
        if profile:
            results["profile_cleared"] = self.clear_webengine_profile_cache(profile)
        
        # 清除磁盘缓存
        cleared_paths, failed_paths = self.clear_webengine_disk_cache()
        results["disk_cleared_paths"] = cleared_paths
        results["disk_failed_paths"] = failed_paths
        
        # 判断总体是否成功
        results["total_success"] = (
            (not profile or results["profile_cleared"]) and 
            len(results["disk_failed_paths"]) == 0
        )
        
        return results