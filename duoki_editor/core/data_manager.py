import os
import pandas as pd
import requests
import shutil
from pathlib import Path
from duoki_editor.utils.excel_handler import ExcelHandler
from duoki_editor.utils.config_manager import ConfigManager
from duoki_editor.core.auth_manager import AuthManager

class DataManager:
    """数据管理类，负责加载、管理和同步游戏数据"""
    use_mod_override = False
    
    def __init__(self, config, auth_manager=None):
        self.config = config
        self.excel_handler = ExcelHandler()
        self.data_cache = {}  # 内存中的数据缓存 {file_path: {sheet_name: DataFrame}}
        self.config_manager = ConfigManager()  # 初始化配置管理器
        self.auth_manager = auth_manager or AuthManager()  # 使用传入的认证管理器或创建新的
        
        # 定义要下载的文件列表
        self.files_to_download = [
            # common 目录下的文件
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/CharacterTable.xlsx",
                "target_dir": "common"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/NpcAddressConfig.xlsx",
                "target_dir": "common"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/BasicitemTable.xlsx",
                "target_dir": "common"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/Guide.xlsx",
                "target_dir": "common"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/MapInfo.xlsx",
                "target_dir": "common"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/PoiTable.xlsx",
                "target_dir": "common"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/PromptParam.xlsx",
                "target_dir": "common"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/common/SpeechParametersTable.xlsx",
                "target_dir": "common"
            },
            
            # restaurant 目录下的文件
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/AnimalPrefer.xlsx",
                "target_dir": "restaurant"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/DemoPic.xlsx",
                "target_dir": "restaurant"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/ItemPrompt.xlsx",
                "target_dir": "restaurant"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/Knowledge.xlsx",
                "target_dir": "restaurant",
                "filename": "Knowledge.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/LevelAppUnlock.xlsx",
                "target_dir": "restaurant",
                "filename": "LevelAppUnlock.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/LevelConfig.xlsx",
                "target_dir": "restaurant",
                "filename": "LevelConfig.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/Menu.xlsx",
                "target_dir": "restaurant",
                "filename": "Menu.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/PhraseConfig.xlsx",
                "target_dir": "restaurant",
                "filename": "PhraseConfig.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/SceneGraph.xlsx",
                "target_dir": "restaurant",
                "filename": "SceneGraph.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/SentenceConfig.xlsx",
                "target_dir": "restaurant",
                "filename": "SentenceConfig.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/Speech.xlsx",
                "target_dir": "restaurant",
                "filename": "Speech.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/Structure.xlsx",
                "target_dir": "restaurant",
                "filename": "Structure.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/TemplateConfig.xlsx",
                "target_dir": "restaurant",
                "filename": "TemplateConfig.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/TemplateType.xlsx",
                "target_dir": "restaurant",
                "filename": "TemplateType.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/Upgrade.xlsx",
                "target_dir": "restaurant",
                "filename": "Upgrade.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/WordConfig.xlsx",
                "target_dir": "restaurant",
                "filename": "WordConfig.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/ShowImageNpc.xlsx",
                "target_dir": "restaurant",
                "filename": "ShowImageNpc.xlsx"
            },
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/restaurant/StorePrefer.xlsx",
                "target_dir": "restaurant",
                "filename": "StorePrefer.xlsx"
            },
            
            # cosplay 目录下的文件
            {
                "url": "https://portal-test.qidianlingzhi.com:10199/config/getFile?path=configs/cosplay/TaskPromptTable.xlsx",
                "target_dir": "cosplay",
                "filename": "TaskPromptTable.xlsx"
            }
        ]
        
        # 如果不使用本地缓存，则清空缓存目录
        if not self.config.use_local_xlsx_cache:
            self._clear_cache_dir()
    
    def _clear_cache_dir(self):
        """清空缓存目录"""
        cache_dir = self.config.xlsx_cache_dir
        if os.path.exists(cache_dir):
            print(f"清空缓存目录: {cache_dir}")
            # 删除目录下的所有文件和子目录
            for item in os.listdir(cache_dir):
                item_path = os.path.join(cache_dir, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
    
    def fetch_data_from_server(self, progress_callback=None):
        """从服务器拉取数据"""
        print("正在从服务器拉取数据...")
        
        try:
            # 获取文件总数
            total_files = len(self.files_to_download)
            
            # 只有在不使用本地缓存时才清空缓存目录
            if not self.config.use_local_xlsx_cache:
                cache_dir = self.config.xlsx_cache_dir
                if os.path.exists(cache_dir):
                    for item in os.listdir(cache_dir):
                        item_path = os.path.join(cache_dir, item)
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
            
            # 确保缓存目录存在
            os.makedirs(self.config.xlsx_cache_dir, exist_ok=True)
            
            # 创建目录结构
            self._create_directory_structure()
            
            # 从服务器下载文件
            self._download_files_from_server(progress_callback)

            
            # 加载所有下载的文件到内存
            self.load_all_cached_files()
            
            print("数据拉取完成")
            return True
        except Exception as e:
            print(f"从服务器拉取数据失败: {e}")
            return False
    
    def _create_directory_structure(self):
        """创建目录结构"""
        # 创建指定的目录结构
        os.makedirs(os.path.join(self.config.xlsx_cache_dir, "baui"), exist_ok=True)
        os.makedirs(os.path.join(self.config.xlsx_cache_dir, "common"), exist_ok=True)
        os.makedirs(os.path.join(self.config.xlsx_cache_dir, "cosplay"), exist_ok=True)
        os.makedirs(os.path.join(self.config.xlsx_cache_dir, "english"), exist_ok=True)
        os.makedirs(os.path.join(self.config.xlsx_cache_dir, "monopoly"), exist_ok=True)
        os.makedirs(os.path.join(self.config.xlsx_cache_dir, "restaurant"), exist_ok=True)
        os.makedirs(os.path.join(self.config.xlsx_cache_dir, "test"), exist_ok=True)
    
    def _download_files_from_server(self, progress_callback=None):
        """从服务器下载文件"""
        # 获取文件总数
        total_files = len(self.files_to_download)
        
        # 下载所有文件
        for i, file_info in enumerate(self.files_to_download):
            url = file_info["url"]
            target_dir = os.path.join(self.config.xlsx_cache_dir, file_info["target_dir"])
            
            # 确保目标目录存在
            os.makedirs(target_dir, exist_ok=True)
            
            # 确定文件名
            if "filename" in file_info:
                filename = file_info["filename"]
            else:
                # 从URL中提取文件名
                path_parts = url.split("path=")
                if len(path_parts) > 1:
                    path = path_parts[1]
                    filename = os.path.basename(path)
                else:
                    # 如果无法从URL提取，使用URL的最后部分
                    filename = url.split("/")[-1]
            
            target_path = os.path.join(target_dir, filename)
            
            try:
                message = f"正在下载: {filename}"
                print(message)
                
                # 如果使用本地缓存且文件已存在，则跳过下载
                if self.config.use_local_xlsx_cache and os.path.exists(target_path):
                    message = f"使用本地缓存: {filename}"
                    print(message)
                    if progress_callback:
                        progress_callback(i + 1, total_files, message)
                    continue
                
                # 更新进度
                if progress_callback:
                    progress_callback(i + 1, total_files, message)
                
                # 设置请求头和cookie
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                header_cookie = self.auth_manager.get_cookie_header()
                if header_cookie:
                    headers['Cookie'] = header_cookie
                    print(f"🔑 请求Cookie头: {header_cookie}")
                else:
                    print("⚠️  警告: 没有可用的Cookie")
                response = requests.get(url, verify=False, headers=headers)
                print(f"📡 HTTP响应状态: {response.status_code}")
                
                if response.status_code == 200:
                    # 检查响应内容类型，如果是Excel文件则直接保存
                    content_type = response.headers.get('content-type', '').lower()
                    if 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in content_type or \
                       'application/vnd.ms-excel' in content_type or \
                       filename.endswith('.xlsx') or filename.endswith('.xls'):
                        # 这是Excel文件，直接保存
                        print(f"📊 检测到Excel文件，Content-Type: {content_type}")
                    else:
                        # 检查响应内容是否是登录重定向页面
                        content_text = response.text.lower()
                        # 更严格的判断：必须同时包含登录相关的特定标识
                        if ('<html>' in content_text and 
                            ('login' in content_text or '登录' in content_text) and
                            ('redirect' in content_text or 'form' in content_text) and
                            len(response.content) < 10000):  # 登录页面通常较小
                            print(f"检测到登录重定向页面，需要重新认证: {filename}")
                            print(f"📄 响应内容长度: {len(response.content)} 字节")
                            print(f"📋 Content-Type: {content_type}")
                            # 清除当前认证数据，触发重新登录
                            self.auth_manager.clear_auth_data()
                            print("认证已失效，需要重新登录")
                            # 抛出异常以停止下载流程
                            raise Exception("认证失效，需要重新登录")
                    
                    # 保存文件
                    with open(target_path, 'wb') as f:
                        f.write(response.content)
                    print(f"下载成功: {target_path}")
                else:
                    print(f"下载失败，状态码: {response.status_code}")
            except Exception as e:
                print(f"下载文件时出错: {e}")
    
    def load_all_cached_files(self):
        """加载所有缓存的Excel文件到内存"""
        cache_dir = self.config.xlsx_cache_dir
        
        # 清空当前缓存
        self.data_cache = {}
        
        # 遍历缓存目录中的所有xlsx文件
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                if file.endswith(('.xlsx', '.xls')):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, cache_dir)
                    
                    try:
                        # 加载Excel文件
                        excel_data = self.excel_handler.load_excel(file_path)
                        self.data_cache[rel_path] = excel_data
                        print(f"已加载: {rel_path}")
                    except Exception as e:
                        print(f"加载文件 {rel_path} 失败: {e}")
    
    def get_all_files(self):
        """获取所有已加载文件的相对路径列表"""
        return list(self.data_cache.keys())
    
    def get_file_data(self, file_path):
        """获取指定文件的数据"""
        return self.data_cache.get(file_path)
    
    def get_sheet_data(self, file_path, sheet_name):
        """获取指定文件中特定工作表的数据"""
        file_data = self.data_cache.get(file_path)
        if file_data and sheet_name in file_data:
            return file_data[sheet_name]
        return None

    def load_data(self, file_path):
        # 检查内存缓存中是否存在
        if file_path in self._memory_cache:
            return self._memory_cache[file_path]
        
        # 从文件或服务器加载数据
        data = self._load_from_source(file_path)
        
        # 存入内存缓存
        self._memory_cache[file_path] = data
        return data

    def _load_from_source(self, file_path):
        # 检查本地文件缓存
        local_file = os.path.join(self.config.xlsx_cache_dir, os.path.basename(file_path))
        if os.path.exists(local_file):
            return self._load_xlsx(local_file)
        
        # 从服务器下载
        return self._download_from_server(file_path)

    @staticmethod
    def load_table_from_mod_or_cache(filename: str, target_dir: str):
        """优先从 resources/data/mod/<filename> 读取表格；不存在则回退到 cache/<target_dir>/<filename>。
        返回值为 {sheet_name: DataFrame} 的字典；若两处都不存在，返回空字典。
        """
        from duoki_editor.utils.excel_handler import ExcelHandler
        base_dir = os.path.dirname(os.path.dirname(__file__))
        mod_path = os.path.abspath(os.path.join(base_dir, 'resources', 'data', 'mod', filename))
        excel = ExcelHandler()
        use_mod = getattr(DataManager, "use_mod_override", False)
        if use_mod and os.path.exists(mod_path):
            print(f"使用MOD覆盖表格: {mod_path}")
            return excel.load_excel(mod_path)
        if not use_mod and os.path.exists(mod_path):
            print(f"忽略MOD覆盖表格: {mod_path}")
        from duoki_editor.core.config import Config
        cfg = Config()
        cache_path = os.path.abspath(os.path.join(cfg.xlsx_cache_dir, target_dir, filename))
        if os.path.exists(cache_path):
            return excel.load_excel(cache_path)
        print(f"未找到表格文件: {filename} (mod或cache)")
        return {}
