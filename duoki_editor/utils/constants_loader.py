"""
常量配置加载器
用于从constants.json文件中加载各种特殊常量和规则
"""
import json
import os
from typing import Dict, Any

class ConstantsLoader:
    """常量配置加载器"""
    
    _instance = None
    _constants = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConstantsLoader, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._constants is None:
            self._load_constants()
    
    def _load_constants(self):
        """加载常量配置文件"""
        try:
            # 获取duoki_editor目录下的constants.json文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            duoki_editor_dir = os.path.dirname(current_dir)
            constants_path = os.path.join(duoki_editor_dir, 'constants.json')
            
            if not os.path.exists(constants_path):
                raise FileNotFoundError(f"常量配置文件不存在: {constants_path}")
            
            with open(constants_path, 'r', encoding='utf-8') as f:
                self._constants = json.load(f)
                
        except Exception as e:
            print(f"加载常量配置文件失败: {e}")
            # 提供默认配置作为后备
            self._constants = {
                "prefix_mapping": {},
                "app_name_map": {},
                "npc_id_map_1": {},
                "npc_id_map_2": {},
                "npc_id_map_3": {}
            }
    
    def get_prefix_mapping(self) -> Dict[str, str]:
        """获取前缀映射"""
        return self._constants.get("prefix_mapping", {})
    
    def get_app_name_map(self) -> Dict[str, str]:
        """获取应用名称映射"""
        return self._constants.get("app_name_map", {})
    
    def get_npc_id_map_1(self) -> Dict[str, str]:
        """获取NPC ID映射1"""
        return self._constants.get("npc_id_map_1", {})
    
    def get_npc_id_map_2(self) -> Dict[str, str]:
        """获取NPC ID映射2"""
        return self._constants.get("npc_id_map_2", {})
    
    def get_npc_id_map_3(self) -> Dict[str, str]:
        """获取NPC ID映射3"""
        return self._constants.get("npc_id_map_3", {})
    
    def get_app_id_map(self) -> Dict[str, int]:
        """获取应用ID映射"""
        return self._constants.get("app_id_map", {})
    
    def get_ai_platforms(self) -> Dict[str, str]:
        """获取AI平台配置"""
        return self._constants.get("ai_platforms", {})
    
    def get_ai_tokens(self) -> Dict[str, str]:
        """获取AI令牌配置"""
        return self._constants.get("ai_tokens", {})
    
    def get_ai_agents(self) -> Dict[str, list]:
        """获取AI智能体配置"""
        return self._constants.get("ai_agents", {})
    
    def get_agent_bot_ids(self) -> Dict[str, str]:
        """获取智能体Bot ID配置"""
        return self._constants.get("agent_bot_ids", {})
    
    def get_agent_conversation_ids(self) -> Dict[str, str]:
        """获取智能体会话ID配置"""
        return self._constants.get("agent_conversation_ids", {})
    
    def get_bgm_list(self, map_name: str | None = None) -> list:
        """获取BGM列表
        如果传入map_name，则从json中按键返回对应列表；否则返回空或全局默认。
        """
        bgm_conf = self._constants.get("bgm", [])
        if isinstance(bgm_conf, dict):
            if map_name:
                return bgm_conf.get(map_name, [])
            # 未提供map_name，返回空列表，避免混淆
            return []
        # 兼容旧格式：若为列表则直接返回
        return bgm_conf

    def get_tts_emotions(self, engine: str | None = None):
        """获取TTS情绪枚举
        engine为None时返回完整字典；提供engine时返回对应列表。
        """
        emotions = self._constants.get("tts_emotions", {})
        if engine is None:
            return emotions
        try:
            key = str(engine).strip().lower()
        except Exception:
            key = ""
        if isinstance(emotions, dict):
            return emotions.get(key, [])
        return []

    def get_image_references(self) -> Dict[str, str]:
        """获取图片参考映射(image_references)"""
        return self._constants.get("image_references", {})

    def get_map_manager(self) -> Dict[str, str]:
        """获取地图与管理者映射(map_manager)"""
        return self._constants.get("map_manager", {})

    def get_voice_seed(self) -> Dict[str, list]:
        return self._constants.get("voice_seed", {})
    
    def get_voice_speed(self) -> Dict[str, list]:
        return self._constants.get("voice_speed", {})
    
    def get_npc_id_map(self, map_type: int = 2) -> Dict[str, str]:
        """获取指定类型的NPC ID映射"""
        if map_type == 1:
            return self.get_npc_id_map_1()
        if map_type == 2:
            return self.get_npc_id_map_2()
        return self.get_npc_id_map_3()
    
    def reload(self):
        """重新加载配置文件"""
        self._constants = None
        self._load_constants()


# 创建全局实例
constants_loader = ConstantsLoader()

# 提供便捷的函数接口
def get_prefix_mapping() -> Dict[str, str]:
    """获取前缀映射"""
    return constants_loader.get_prefix_mapping()

def get_app_name_map() -> Dict[str, str]:
    """获取应用名称映射"""
    return constants_loader.get_app_name_map()

def get_npc_id_map_1() -> Dict[str, str]:
    """获取NPC ID映射1"""
    return constants_loader.get_npc_id_map_1()

def get_npc_id_map_2() -> Dict[str, str]:
    """获取NPC ID映射2"""
    return constants_loader.get_npc_id_map_2()

def get_npc_id_map_3() -> Dict[str, str]:
    """获取NPC ID映射3"""
    return constants_loader.get_npc_id_map_3()

def get_npc_id_map(map_type: int = 2) -> Dict[str, str]:
    """获取指定类型的NPC ID映射"""
    return constants_loader.get_npc_id_map(map_type)

def get_app_id_map() -> Dict[str, int]:
    """获取应用ID映射"""
    return constants_loader.get_app_id_map()

def get_ai_platforms() -> Dict[str, str]:
    """获取AI平台配置"""
    return constants_loader.get_ai_platforms()

def get_ai_tokens() -> Dict[str, str]:
    """获取AI令牌配置"""
    return constants_loader.get_ai_tokens()

def get_ai_agents() -> Dict[str, list]:
    """获取AI智能体配置"""
    return constants_loader.get_ai_agents()

def get_agent_bot_ids() -> Dict[str, str]:
    """获取智能体Bot ID配置"""
    return constants_loader.get_agent_bot_ids()

def get_agent_conversation_ids() -> Dict[str, str]:
    """获取智能体会话ID配置"""
    return constants_loader.get_agent_conversation_ids()

def get_bgm_list(map_name: str | None = None) -> list:
    """获取BGM列表，支持按地图名称获取"""
    return constants_loader.get_bgm_list(map_name)

def get_image_references() -> Dict[str, str]:
    """获取图片参考映射(image_references)"""
    return constants_loader.get_image_references()

def get_map_manager() -> Dict[str, str]:
    """获取地图与管理者映射(map_manager)"""
    return constants_loader.get_map_manager()

def reload_constants():
    """重新加载配置文件"""
    
def get_voice_seed() -> Dict[str, list]:
    return constants_loader.get_voice_seed()
    constants_loader.reload()

def get_voice_speed() -> Dict[str, list]:
    return constants_loader.get_voice_speed()
