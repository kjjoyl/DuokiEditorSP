"""
ShowImageNpc管理器
用于管理和查询ShowImageNpc.xlsx数据
"""

import os
import pandas as pd
from typing import Dict, List, Optional, Any
from duoki_editor.utils.excel_handler import ExcelHandler


class ShowImageNpcManager:
    """ShowImageNpc数据管理器"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ShowImageNpcManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.data = {}
            self.excel_handler = ExcelHandler()
            self.load_show_image_npc_data()
            ShowImageNpcManager._initialized = True
    
    def _get_cache_dir(self) -> str:
        """获取缓存目录路径"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        cache_dir = os.path.join(project_root, "cache", "data", "restaurant")
        return cache_dir
    
    def load_show_image_npc_data(self):
        """加载ShowImageNpc.xlsx数据"""
        try:
            from duoki_editor.core.data_manager import DataManager
            excel_data = DataManager.load_table_from_mod_or_cache('ShowImageNpc.xlsx', 'restaurant')
            if not excel_data:
                print("ShowImageNpc.xlsx数据为空或未找到(mod或cache)")
                return
            
            total_rows = 0
            for sheet_name, df in excel_data.items():
                if df is None or len(df) <= 1:
                    continue
                actual_data = df.iloc[1:].copy()
                for col in ['templateType', 'stage_type', 'npcSceneId', 'url_image']:
                    if col in actual_data.columns:
                        actual_data[col] = actual_data[col].astype(str)
                    else:
                        actual_data[col] = ''
                for col in ['id', 'npc1_base_id', 'npc2_base_id']:
                    if col in actual_data.columns:
                        actual_data[col] = pd.to_numeric(actual_data[col], errors='coerce')
                actual_data = actual_data.dropna(how='all')
                self.data[sheet_name] = actual_data
                total_rows += len(actual_data)
            print(f"ShowImageNpcManager已初始化，加载 {len(self.data)} 个sheet，共 {total_rows} 行数据")
                
        except Exception as e:
            print(f"加载ShowImageNpc.xlsx数据时出错: {e}")
    
    def get_url_image(self, template_type: str, stage_type: str, 
                     npc1_base_id: int, npc2_base_id: int) -> Optional[str]:
        """
        根据四个键查找匹配的url_image
        
        Args:
            template_type: 模板类型（如：唤醒、测体温、生病、洗澡、喂食）
            stage_type: 阶段类型（如：show_image_npc、zoo_shout等）
            npc1_base_id: NPC1的基础ID
            npc2_base_id: NPC2的基础ID
            
        Returns:
            匹配的url_image，如果没有找到则返回None
        """
        try:
            for sheet_name, df in self.data.items():
                # 查找匹配的行
                matches = df[
                    (df['templateType'] == template_type) &
                    (df['stage_type'] == stage_type) &
                    (df['npc1_base_id'] == npc1_base_id) &
                    (df['npc2_base_id'] == npc2_base_id)
                ]
                
                if not matches.empty:
                    # 如果有多个匹配项，取第一个
                    return matches.iloc[0]['url_image']
            
            return None
            
        except Exception as e:
            print(f"查询url_image时出错: {e}")
            return None

    def get_url_image_by_scene(self, npc_scene_id: str, stage_type: str,
                               npc1_base_id: int, npc2_base_id: int) -> Optional[str]:
        try:
            for sheet_name, df in self.data.items():
                matches = df[
                    (df['npcSceneId'] == npc_scene_id) &
                    (df['stage_type'] == stage_type) &
                    (df['npc1_base_id'] == npc1_base_id) &
                    (df['npc2_base_id'] == npc2_base_id)
                ]
                if not matches.empty:
                    return matches.iloc[0]['url_image']
            return None
        except Exception as e:
            print(f"根据npcSceneId查询url_image时出错: {e}")
            return None
    
    def search_by_template_type(self, template_type: str) -> List[Dict[str, Any]]:
        """
        根据模板类型搜索所有匹配的记录
        
        Args:
            template_type: 模板类型
            
        Returns:
            匹配的记录列表
        """
        results = []
        try:
            for sheet_name, df in self.data.items():
                matches = df[df['templateType'] == template_type]
                for _, row in matches.iterrows():
                    results.append({
                        'id': row['id'],
                        'templateType': row['templateType'],
                        'stage_type': row['stage_type'],
                        'npc1_base_id': row['npc1_base_id'],
                        'npc2_base_id': row['npc2_base_id'],
                        'url_image': row['url_image']
                    })
        except Exception as e:
            print(f"根据模板类型搜索时出错: {e}")
        
        return results
    
    def search_by_npc_ids(self, npc1_base_id: int, npc2_base_id: int) -> List[Dict[str, Any]]:
        """
        根据NPC ID组合搜索所有匹配的记录
        
        Args:
            npc1_base_id: NPC1的基础ID
            npc2_base_id: NPC2的基础ID
            
        Returns:
            匹配的记录列表
        """
        results = []
        try:
            for sheet_name, df in self.data.items():
                matches = df[
                    (df['npc1_base_id'] == npc1_base_id) &
                    (df['npc2_base_id'] == npc2_base_id)
                ]
                for _, row in matches.iterrows():
                    results.append({
                        'id': row['id'],
                        'templateType': row['templateType'],
                        'stage_type': row['stage_type'],
                        'npc1_base_id': row['npc1_base_id'],
                        'npc2_base_id': row['npc2_base_id'],
                        'url_image': row['url_image']
                    })
        except Exception as e:
            print(f"根据NPC ID搜索时出错: {e}")
        
        return results
    
    def get_all_template_types(self) -> List[str]:
        """获取所有可用的模板类型"""
        template_types = set()
        try:
            for sheet_name, df in self.data.items():
                template_types.update(df['templateType'].unique())
        except Exception as e:
            print(f"获取模板类型时出错: {e}")
        
        return sorted(list(template_types))
    
    def get_all_stage_types(self) -> List[str]:
        """获取所有可用的阶段类型"""
        stage_types = set()
        try:
            for sheet_name, df in self.data.items():
                stage_types.update(df['stage_type'].unique())
        except Exception as e:
            print(f"获取阶段类型时出错: {e}")
        
        return sorted(list(stage_types))
    
    def get_all_npc_ids(self) -> Dict[str, List[int]]:
        """获取所有可用的NPC ID"""
        npc_ids = {'npc1_base_id': set(), 'npc2_base_id': set()}
        try:
            for sheet_name, df in self.data.items():
                npc_ids['npc1_base_id'].update(df['npc1_base_id'].unique())
                npc_ids['npc2_base_id'].update(df['npc2_base_id'].unique())
        except Exception as e:
            print(f"获取NPC ID时出错: {e}")
        
        return {
            'npc1_base_id': sorted(list(npc_ids['npc1_base_id'])),
            'npc2_base_id': sorted(list(npc_ids['npc2_base_id']))
        }
    
    def get_data_count(self) -> int:
        """获取总数据行数"""
        total_count = 0
        try:
            for sheet_name, df in self.data.items():
                total_count += len(df)
        except Exception as e:
            print(f"获取数据行数时出错: {e}")
        
        return total_count
    
    def get_all_data(self) -> Dict[str, pd.DataFrame]:
        """获取所有数据"""
        return self.data.copy()


# 不在导入时创建全局实例，避免鉴权前初始化
