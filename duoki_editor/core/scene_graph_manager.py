import pandas as pd
import os
import sys
from duoki_editor.utils.excel_handler import ExcelHandler
from duoki_editor.utils.constants_loader import get_prefix_mapping

class SceneGraphManager:
    _instance = None
    _is_initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._is_initialized:
            self.excel_handler = ExcelHandler()
            self.scene_graph_data = None
            self.scene_graph_origin_data = None
            self.load_scene_graph_data()
            self.load_scene_graph_origin_data()
            self._is_initialized = True

    def _get_cache_dir(self):
        """
        获取cache目录路径，与Config类的逻辑保持一致
        """
        if getattr(sys, 'frozen', False):
            # 打包后的环境，使用_internal目录
            base_dir = os.path.join(os.path.dirname(sys.executable), "_internal")
            cache_dir = os.path.join(base_dir, "duoki_editor", "cache", "data")
        else:
            # 开发环境
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "data")
        return cache_dir

    def _add_scene_id_prefix(self, df, sheet_name):
        """
        根据sheet名为scene_id添加前缀
        
        Args:
            df (pd.DataFrame): 数据框
            sheet_name (str): sheet名称
            
        Returns:
            pd.DataFrame: 处理后的数据框
        """
        # 从配置文件获取前缀映射
        prefix_mapping = get_prefix_mapping()
        
        # 获取对应的前缀
        prefix = prefix_mapping.get(sheet_name, '')
        
        if prefix and 'scene_id' in df.columns:
            # 创建数据副本以避免修改原数据
            df_copy = df.copy()
            
            # 为scene_id添加前缀（如果前缀不存在）
            def add_prefix_if_not_exists(scene_id):
                if pd.isna(scene_id):
                    return scene_id
                scene_id_str = str(scene_id)
                if not scene_id_str.startswith(prefix):
                    return prefix + scene_id_str
                return scene_id_str
            
            df_copy['scene_id'] = df_copy['scene_id'].apply(add_prefix_if_not_exists)
            return df_copy
        
        return df

    def load_scene_graph_data(self):
        """
        加载SceneGraph.xlsx文件的所有sheets并缓存到内存。
        对每个sheet的scene_id添加前缀，然后将所有数据拼接在一起。
        """
        try:
            from duoki_editor.core.data_manager import DataManager
            excel_data = DataManager.load_table_from_mod_or_cache('SceneGraph.xlsx', 'restaurant')
            if not excel_data:
                print("警告: 未找到 SceneGraph.xlsx (mod或cache)")
                self.scene_graph_data = pd.DataFrame()
                return
            
            if not excel_data:
                print(f"警告: SceneGraph.xlsx 中没有找到任何工作表。")
                self.scene_graph_data = pd.DataFrame()
                return
            
            # 存储所有处理后的数据
            all_data = []
            
            # 遍历所有sheets
            for sheet_name, sheet_data in excel_data.items():
                if sheet_data.empty:
                    print(f"警告: 工作表 '{sheet_name}' 为空，跳过处理。")
                    continue
                
                # 为当前sheet的数据添加前缀
                processed_data = self._add_scene_id_prefix(sheet_data, sheet_name)
                
                # 添加sheet来源信息（可选，用于调试）
                processed_data = processed_data.copy()
                processed_data['_source_sheet'] = sheet_name
                
                all_data.append(processed_data)
            
            # 拼接所有数据
            if all_data:
                self.scene_graph_data = pd.concat(all_data, ignore_index=True)
            else:
                print("警告: 没有有效的数据可以加载。")
                self.scene_graph_data = pd.DataFrame()
                
        except Exception as e:
            print(f"加载SceneGraph.xlsx失败: {e}")
            self.scene_graph_data = pd.DataFrame()

    def get_scene_graph_data(self):
        """
        获取缓存的场景图数据
        
        Returns:
            pd.DataFrame: 场景图数据
        """
        return self.scene_graph_data if self.scene_graph_data is not None else pd.DataFrame()

    def load_scene_graph_origin_data(self):
        """
        加载SceneGraph.xlsx文件的所有sheets并缓存到内存（不添加scene_id前缀）。
        """
        try:
            from duoki_editor.core.data_manager import DataManager
            excel_data = DataManager.load_table_from_mod_or_cache('SceneGraph.xlsx', 'restaurant')
            if not excel_data:
                print("警告: 未找到 SceneGraph.xlsx (mod或cache)")
                self.scene_graph_origin_data = pd.DataFrame()
                return
            if not excel_data:
                print(f"警告: SceneGraph.xlsx 中没有找到任何工作表。")
                self.scene_graph_origin_data = pd.DataFrame()
                return
            all_data = []
            for sheet_name, sheet_data in excel_data.items():
                if sheet_data.empty:
                    print(f"警告: 工作表 '{sheet_name}' 为空，跳过处理。")
                    continue
                processed_data = sheet_data.copy()
                processed_data['_source_sheet'] = sheet_name
                all_data.append(processed_data)
            if all_data:
                self.scene_graph_origin_data = pd.concat(all_data, ignore_index=True)
            else:
                print("警告: 没有有效的原始数据可以加载。")
                self.scene_graph_origin_data = pd.DataFrame()
        except Exception as e:
            print(f"加载原始SceneGraph.xlsx失败: {e}")
            self.scene_graph_origin_data = pd.DataFrame()

    def get_scene_graph_origin_data(self):
        """
        获取未添加前缀的场景图原始数据
        
        Returns:
            pd.DataFrame: 原始场景图数据
        """
        return self.scene_graph_origin_data if self.scene_graph_origin_data is not None else pd.DataFrame()

    def search_by_scene_id(self, scene_id):
        """
        根据scene_id搜索数据
        
        Args:
            scene_id (str): 场景ID
            
        Returns:
            pd.DataFrame: 匹配的数据
        """
        if self.scene_graph_data is None or self.scene_graph_data.empty:
            return pd.DataFrame()
        
        if 'scene_id' not in self.scene_graph_data.columns:
            return pd.DataFrame()
        
        return self.scene_graph_data[self.scene_graph_data['scene_id'] == scene_id]

    def get_all_scene_ids(self):
        """
        获取所有scene_id列表
        
        Returns:
            list: scene_id列表
        """
        if self.scene_graph_data is None or self.scene_graph_data.empty:
            return []
        
        if 'scene_id' not in self.scene_graph_data.columns:
            return []
        
        return self.scene_graph_data['scene_id'].unique().tolist()

    def get_data_by_sheet_prefix(self, prefix):
        """
        根据前缀获取特定场景的数据
        
        Args:
            prefix (str): 前缀（如 '餐厅_', '动物园_' 等）
            
        Returns:
            pd.DataFrame: 匹配前缀的数据
        """
        if self.scene_graph_data is None or self.scene_graph_data.empty:
            return pd.DataFrame()
        
        if 'scene_id' not in self.scene_graph_data.columns:
            return pd.DataFrame()
        
        # 筛选以指定前缀开头的scene_id
        mask = self.scene_graph_data['scene_id'].astype(str).str.startswith(prefix)
        return self.scene_graph_data[mask]
    
    def get_data_by_sheet_name(self, sheet_name):
        """
        根据sheet名称获取对应的数据
        
        Args:
            sheet_name (str): sheet名称（如 'zoo', 'restaurant' 等）
        
        Returns:
            pd.DataFrame: 匹配sheet名称的数据
        """
        if self.scene_graph_data is None or self.scene_graph_data.empty:
            return pd.DataFrame()
        
        if '_source_sheet' not in self.scene_graph_data.columns:
            return pd.DataFrame()
        
        # 筛选指定sheet名称的数据
        mask = self.scene_graph_data['_source_sheet'] == sheet_name
        return self.scene_graph_data[mask]

    def get_origin_data_by_sheet_name(self, sheet_name):
        """
        根据sheet名称获取对应的原始数据（不带scene_id前缀）
        
        Args:
            sheet_name (str): sheet名称（如 'zoo', 'restaurant' 等）
        
        Returns:
            pd.DataFrame: 匹配sheet名称的原始数据
        """
        if self.scene_graph_origin_data is None or self.scene_graph_origin_data.empty:
            return pd.DataFrame()
        if '_source_sheet' not in self.scene_graph_origin_data.columns:
            return pd.DataFrame()
        mask = self.scene_graph_origin_data['_source_sheet'] == sheet_name
        return self.scene_graph_origin_data[mask]
