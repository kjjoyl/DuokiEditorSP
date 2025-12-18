import pandas as pd
import os
import sys
from duoki_editor.utils.excel_handler import ExcelHandler
from duoki_editor.core.character_table_manager import CharacterTableManager

class SpeechParametersManager:
    _instance = None
    _is_initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._is_initialized:
            self.excel_handler = ExcelHandler()
            self.speech_parameters_table = None
            self.load_speech_parameters_table()
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

    def load_speech_parameters_table(self):
        """
        加载SpeechParametersTable.xlsx文件并缓存到内存。
        """
        try:
            from duoki_editor.core.data_manager import DataManager
            excel_data = DataManager.load_table_from_mod_or_cache('SpeechParametersTable.xlsx', 'common')
            if not excel_data:
                print("警告: 未找到 SpeechParametersTable.xlsx (mod或cache)")
                self.speech_parameters_table = pd.DataFrame()
                return
            if "Sheet1" in excel_data: # 假设数据在第一个工作表
                self.speech_parameters_table = excel_data["Sheet1"]
                # 确保 'id' 列是数值类型
                self.speech_parameters_table['id'] = pd.to_numeric(self.speech_parameters_table['id'], errors='coerce').fillna(0).astype(int)
                print("SpeechParametersTable.xlsx 加载成功并缓存到内存。")
            else:
                print(f"警告: SpeechParametersTable.xlsx 中未找到 'Sheet1' 工作表。")
                self.speech_parameters_table = pd.DataFrame()
        except Exception as e:
            print(f"加载SpeechParametersTable.xlsx失败: {e}")
            self.speech_parameters_table = pd.DataFrame()

    def get_voice_id_from_speaker(self, speaker, with_prefix=True):
        """
        根据speaker获取voice_id，使用CharacterTableManager
        
        Args:
            speaker (str): 角色名称
            with_prefix (bool): 是否返回带前缀的voice_id。
                               True: 返回完整voice_type (如 "minimax_xxx" 或 "volcano_xxx")
                               False: 返回去掉前缀的voice_id (如 "xxx")
            
        Returns:
            str or None: voice_id，如果未找到则返回None
        """
        # 使用CharacterTableManager获取default_voice_id
        character_manager = CharacterTableManager()
        default_voice_id = character_manager.get_default_voice_id_by_speaker(speaker)
        
        if default_voice_id is None:
            return None
        
        # 使用default_voice_id从SpeechParametersTable中获取voice_type
        if self.speech_parameters_table is None or self.speech_parameters_table.empty:
            print("警告: SpeechParametersTable数据为空。")
            return None
        
        # 根据default_voice_id从SpeechParametersTable获取voice_type和其他参数
        filtered_params = self.speech_parameters_table[self.speech_parameters_table['id'] == default_voice_id]
        if filtered_params.empty:
            print(f"警告: 在SpeechParametersTable中未找到id为 {default_voice_id} 的语音参数。")
            return None
            
        # 获取voice_type
        voice_type = filtered_params.iloc[0].get('voice_type')
        
        # 根据with_prefix参数决定返回格式
        if not with_prefix and voice_type:
            # 去掉前缀
            if voice_type.startswith("minimax_"):
                return voice_type[len("minimax_"):]
            elif voice_type.startswith("volcano_"):
                return voice_type[len("volcano_"):]
        
        # 返回完整voice_type
        return voice_type

    def get_voice_type_by_id(self, character_id, with_prefix=True):
        """
        根据角色ID直接获取voice_type
        
        Args:
            character_id (str or int): 角色ID
            with_prefix (bool): 是否返回带前缀的voice_type。
                               True: 返回完整voice_type (如 "minimax_xxx" 或 "volcano_xxx")
                               False: 返回去掉前缀的voice_id (如 "xxx")
            
        Returns:
            str or None: voice_type，如果未找到则返回None
        """
        if self.speech_parameters_table is None or self.speech_parameters_table.empty:
            print("警告: SpeechParametersTable数据为空。")
            return None
        
        # 确保character_id是整数类型
        try:
            character_id = int(character_id)
        except (ValueError, TypeError):
            print(f"警告: 无效的角色ID: {character_id}")
            return None
        
        # 根据character_id从SpeechParametersTable获取voice_type
        filtered_params = self.speech_parameters_table[self.speech_parameters_table['id'] == character_id]
        if filtered_params.empty:
            print(f"警告: 在SpeechParametersTable中未找到id为 {character_id} 的语音参数。")
            return None
            
        # 获取voice_type
        voice_type = filtered_params.iloc[0].get('voice_type')
        
        # 返回完整voice_type
        return voice_type

    def get_speech_parameters(self, speaker):
        """
        根据speaker查找对应的语音参数（voice_id, speed, vol, pitch, emotion_type）。
        
        Args:
            speaker (str): 要查找的speaker名称。
            
        Returns:
            dict: 包含voice_id, speed, vol, pitch, emotion_type的字典，如果未找到则返回默认值。
        """
        default_params = {
            "voice_id": "male-qn-qingse",
            "speed": 1,
            "vol": 1,
            "pitch": 1,
            "emotion_type": "happy"
        }

        if self.speech_parameters_table is None or self.speech_parameters_table.empty:
            return default_params

        # 检查 'character_types' 列是否存在
        if 'character_types' not in self.speech_parameters_table.columns:
            print("警告: SpeechParametersTable.xlsx 中未找到 'character_types' 列，使用默认参数。")
            return default_params

        filtered_df = self.speech_parameters_table[
            (self.speech_parameters_table['id'] >= 30000) & 
            (self.speech_parameters_table['character_types'] == speaker)
        ]

        if not filtered_df.empty:
            row = filtered_df.iloc[0]
            voice_type = row.get('voice_type')
            speed = row.get('speed_ratio', default_params['speed'])
            vol = row.get('volume_ratio', default_params['vol'])
            pitch = row.get('pitch_ratio', default_params['pitch'])
            emotion_type = row.get('emotion_type', default_params['emotion_type'])
            
            # 处理emotion_type为NaN或空值的情况
            import pandas as pd
            if pd.isna(emotion_type) or emotion_type is None or str(emotion_type).strip() == '':
                emotion_type = default_params['emotion_type']

            if isinstance(voice_type, str) and voice_type.startswith("minimax_"):
                voice_id = voice_type[len("minimax_"):]
            else:
                voice_id = voice_type if voice_type else default_params['voice_id']
            
            return {
                "voice_id": voice_id,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
                "emotion_type": emotion_type
            }
        return default_params
