import pandas as pd
import os
import sys
from duoki_editor.utils.excel_handler import ExcelHandler

class CharacterTableManager:
    _instance = None
    _is_initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._is_initialized:
            self.excel_handler = ExcelHandler()
            self.character_table_data = None
            self.load_character_table_data()
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

    def load_character_table_data(self):
        """
        加载CharacterTable.xlsx文件并缓存到内存。
        """
        try:
            from duoki_editor.core.data_manager import DataManager
            excel_data = DataManager.load_table_from_mod_or_cache('CharacterTable.xlsx', 'common')
            if not excel_data:
                print("警告: 未找到 CharacterTable.xlsx (mod或cache)")
                self.character_table_data = pd.DataFrame()
                return
            if "Sheet" in excel_data:
                self.character_table_data = excel_data["Sheet"]
                
                # 确保id列是数值类型
                if 'id' in self.character_table_data.columns:
                    self.character_table_data['id'] = pd.to_numeric(
                        self.character_table_data['id'], 
                        errors='coerce'
                    ).fillna(0).astype(int)
                
                print(f"CharacterTable.xlsx 加载成功并缓存到内存，共 {len(self.character_table_data)} 行数据。")
            else:
                print(f"警告: CharacterTable.xlsx 中未找到 'Sheet' 工作表。")
                self.character_table_data = pd.DataFrame()
        except Exception as e:
            print(f"加载CharacterTable.xlsx失败: {e}")
            self.character_table_data = pd.DataFrame()

    def get_character_table_data(self):
        """
        获取缓存的角色表数据
        
        Returns:
            pd.DataFrame: 角色表数据
        """
        return self.character_table_data if self.character_table_data is not None else pd.DataFrame()

    def search_by_speaker(self, speaker, id_gte=30000):
        """
        根据speaker名称搜索角色数据
        
        匹配规则：
        1. 角色id必须大于30000
        2. 使用npc_name_map进行名称转换后完全匹配
        
        Args:
            speaker (str): 要查找的speaker名称
            
        Returns:
            pd.DataFrame: 匹配的角色数据
        """
        if self.character_table_data is None or self.character_table_data.empty:
            return pd.DataFrame()
        
        if 'name' not in self.character_table_data.columns or 'id' not in self.character_table_data.columns:
            return pd.DataFrame()

        # 根据转换后的speaker名称进行完全匹配，并且id必须大于30000
        matched_characters = self.character_table_data[
            (self.character_table_data['id'] > id_gte) & 
            (self.character_table_data['name'] == speaker)
        ]
        
        return matched_characters

    def get_default_voice_id_by_speaker(self, speaker):
        """
        根据speaker名称获取default_voice_id
        
        Args:
            speaker (str): 要查找的speaker名称
            
        Returns:
            int or None: default_voice_id，如果未找到则返回None
        """
        matched_characters = self.search_by_speaker(speaker)
        
        if matched_characters.empty:
            print(f"警告: 在CharacterTable中未找到匹配 '{speaker[:2]}' 且id>30000的角色。")
            return None
            
        # 获取第一个匹配的角色
        default_voice_id = matched_characters.iloc[0].get('default_voice_id')
        if not default_voice_id or pd.isna(default_voice_id):
            print(f"警告: 匹配的角色没有设置default_voice_id。")
            return None
            
        return default_voice_id

    def get_base_id_by_speaker(self, speaker):
        """
        根据speaker名称获取base_id
        
        Args:
            speaker (str): 要查找的speaker名称
            
        Returns:
            int or None: base_id，如果未找到则返回None
        """
        matched_characters = self.search_by_speaker(speaker)
        
        if matched_characters.empty:
            print(f"警告: 在CharacterTable中未找到匹配 '{speaker}' 且id>30000的角色。")
            return None
            
        # 获取第一个匹配的角色
        base_id = matched_characters.iloc[0].get('base_id')
        if not base_id or pd.isna(base_id):
            print(f"警告: 匹配的角色没有设置base_id。")
            return None
            
        return base_id

    def get_id_by_speaker(self, speaker):
        """
        根据speaker名称获取id
        
        Args:
            speaker (str): 要查找的speaker名称
            
        Returns:
            int or None: base_id，如果未找到则返回None
        """
        matched_characters = self.search_by_speaker(speaker)
        
        if matched_characters.empty:
            print(f"警告: 在CharacterTable中未找到匹配 '{speaker}'")
            return None
            
        # 获取第一个匹配的角色
        id = matched_characters.iloc[0].get('id')
        if not id or pd.isna(id):
            print(f"警告: 匹配的角色没有设置id。")
            return None
            
        return id

    def search_by_id(self, character_id):
        """
        根据角色ID搜索数据
        
        Args:
            character_id (int): 角色ID
            
        Returns:
            pd.DataFrame: 匹配的数据
        """
        if self.character_table_data is None or self.character_table_data.empty:
            return pd.DataFrame()
        
        if 'id' not in self.character_table_data.columns:
            return pd.DataFrame()
        
        return self.character_table_data[self.character_table_data['id'] == character_id]

    def get_all_character_ids(self):
        """
        获取所有角色ID列表
        
        Returns:
            list: 角色ID列表
        """
        if self.character_table_data is None or self.character_table_data.empty:
            return []
        
        if 'id' not in self.character_table_data.columns:
            return []
        
        return self.character_table_data['id'].tolist()

    def get_characters_above_id(self, min_id=30000):
        """
        获取ID大于指定值的角色数据
        
        Args:
            min_id (int): 最小ID值，默认30000
            
        Returns:
            pd.DataFrame: 符合条件的角色数据
        """
        if self.character_table_data is None or self.character_table_data.empty:
            return pd.DataFrame()
        
        if 'id' not in self.character_table_data.columns:
            return pd.DataFrame()
        
        return self.character_table_data[self.character_table_data['id'] > min_id]

    def get_base_id_by_id(self, character_id):
        df = self.get_character_table_data()
        if df.empty or 'id' not in df.columns or 'base_id' not in df.columns:
            return None
        key = str(character_id).strip()
        matched = df[df['id'].astype(str).str.strip() == key]
        if matched.empty:
            print(f"警告: 未找到匹配的id: {character_id}")
            return None
        val = matched.iloc[0].get('base_id')
        if pd.isna(val) or val == '':
            print("警告: 匹配项未设置base_id。")
            return None
        try:
            return int(val)
        except Exception:
            return val

    def get_base_id_by_name(self, name):
        df = self.get_character_table_data()
        if df.empty or 'name' not in df.columns or 'base_id' not in df.columns:
            return None
        key = str(name).strip()
        matched = df[df['name'].astype(str).str.strip() == key]
        if matched.empty:
            print(f"警告: 未找到匹配的name: {name}")
            return None
        val = matched.iloc[0].get('base_id')
        if pd.isna(val) or val == '':
            print("警告: 匹配项未设置base_id。")
            return None
        try:
            return int(val)
        except Exception:
            return val

    def get_name_by_base_id(self, base_id):
        df = self.get_character_table_data()
        if df.empty or 'base_id' not in df.columns or 'name' not in df.columns:
            return None
        if 'id' in df.columns:
            try:
                df = df[df['id'] > 30000]
            except Exception:
                pass
        key = str(base_id).strip()
        matched = df[df['base_id'].astype(str).str.strip() == key]
        if matched.empty:
            print(f"警告: 未找到匹配的base_id: {base_id}")
            return None
        val = matched.iloc[0].get('name')
        if pd.isna(val) or str(val).strip() == '':
            print("警告: 匹配项未设置name。")
            return None
        return str(val)
