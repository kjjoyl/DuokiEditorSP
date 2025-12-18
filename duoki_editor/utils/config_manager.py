import os
import sys
import configparser
from pathlib import Path

class ConfigManager:
    """配置文件管理类，用于处理INI配置文件"""
    
    def __init__(self):
        """初始化配置管理器"""
        # 确定配置文件路径
        if getattr(sys, 'frozen', False):
            if sys.platform == 'darwin':
                base_dir = os.path.expanduser('~/Library/Application Support/DuokiEditor')
                self.config_dir = base_dir
            else:
                base_dir = os.path.dirname(sys.executable)
                self.config_dir = os.path.join(base_dir, '_internal', 'duoki_editor')
        else:
            # 开发环境
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.config_dir = os.path.join(base_dir, 'duoki_editor')
        
        # 确保配置目录存在
        os.makedirs(self.config_dir, exist_ok=True)

        if sys.platform == 'darwin':
            self._output_base_dir = os.path.join(self.config_dir, 'output')
        else:
            self._output_base_dir = './output'
        
        # 旧配置文件路径（用于迁移）
        old_cache_dir = os.path.join(self.config_dir, 'cache')
        old_config_path = os.path.join(old_cache_dir, 'config.ini')
        
        # 新配置文件路径
        self.config_path = os.path.join(self.config_dir, 'config.ini')
        
        # 如果旧配置文件存在但新配置文件不存在，则迁移
        if os.path.exists(old_config_path) and not os.path.exists(self.config_path):
            import shutil
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            shutil.copy2(old_config_path, self.config_path)
        self.config = configparser.ConfigParser()
        
        # 加载配置文件，如果不存在则创建默认配置
        self.load_config()
    
    def load_config(self):
        """加载配置文件，如果不存在则创建默认配置"""
        if os.path.exists(self.config_path):
            self.config.read(self.config_path, encoding='utf-8')
        
        # 确保主要配置节存在
        if 'General' not in self.config:
            self.config['General'] = {}
        
        # 确保UI配置节存在
        if 'UI' not in self.config:
            self.config['UI'] = {}

        # 确保KEY配置节存在
        if 'KEY' not in self.config:
            self.config['KEY'] = {}

        # 确保API配置节存在
        if 'API' not in self.config:
            self.config['API'] = {}

        # 确保PATH配置节存在
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        
        # 确保AI配置节存在
        if 'AI' not in self.config:
            self.config['AI'] = {}
        
        # 设置PATH默认值
        if 'audio_last_open_path' not in self.config['PATH']:
            self.config['PATH']['audio_last_open_path'] = './'
        if 'last_open_path' not in self.config['PATH']:
            self.config['PATH']['last_open_path'] = './'
        if 'image_last_open_path' not in self.config['PATH']:
            self.config['PATH']['image_last_open_path'] = './'
        if 'content_validator_last_open_path' not in self.config['PATH']:
            self.config['PATH']['content_validator_last_open_path'] = './'
        if 'format_validator_last_open_path' not in self.config['PATH']:
            self.config['PATH']['format_validator_last_open_path'] = './'
        # 图片配置页“选择图片目录”的最近打开路径
        if 'story_image_last_open_path' not in self.config['PATH']:
            self.config['PATH']['story_image_last_open_path'] = './'
        # 参考图片最后一次上传目录（用于“上传附件”对话框初始目录）
        if 'reference_image_directory' not in self.config['PATH']:
            self.config['PATH']['reference_image_directory'] = './'
        if 'image_output_directory' not in self.config['PATH']:
            self.config['PATH']['image_output_directory'] = os.path.join(self._output_base_dir, 'image')
        if 'data_output_directory' not in self.config['PATH']:
            self.config['PATH']['data_output_directory'] = os.path.join(self._output_base_dir, 'data')
        if 'voice_output_directory' not in self.config['PATH']:
            self.config['PATH']['voice_output_directory'] = os.path.join(self._output_base_dir, 'voice')
        if 'sfx_output_directory' not in self.config['PATH']:
            self.config['PATH']['sfx_output_directory'] = os.path.join(self._output_base_dir, 'sfx')
        if 'scene_output_directory' not in self.config['PATH']:
            self.config['PATH']['scene_output_directory'] = os.path.join(self._output_base_dir, 'scene')
        if 'avatar_output_directory' not in self.config['PATH']:
            self.config['PATH']['avatar_output_directory'] = os.path.join(self._output_base_dir, 'avatar')
        if 'npc_output_directory' not in self.config['PATH']:
            self.config['PATH']['npc_output_directory'] = os.path.join(self._output_base_dir, 'npc')
        if 'script_output_directory' not in self.config['PATH']:
            self.config['PATH']['script_output_directory'] = os.path.join(self._output_base_dir, 'script')
        
        # 知识点生成-最近打开路径与默认输出目录
        if 'knowledge_last_open_path' not in self.config['PATH']:
            self.config['PATH']['knowledge_last_open_path'] = './'
        if 'knowledge_output_directory' not in self.config['PATH']:
            self.config['PATH']['knowledge_output_directory'] = os.path.join(self._output_base_dir, 'knowledge')

        # 设置默认值（如果不存在）            
        if 'language' not in self.config['General']:
            self.config['General']['language'] = 'zh_CN'
        # 语音引擎默认值
        if 'tts_engine' not in self.config['General']:
            self.config['General']['tts_engine'] = 'custom'
        if 'role' not in self.config['General']:
            self.config['General']['role'] = ''
        if 'user_name' not in self.config['General']:
            self.config['General']['user_name'] = ''
            
        if 'theme' not in self.config['UI']:
            self.config['UI']['theme'] = 'Fusion'  # 默认为系统样式
            
        if 'toolbar_position' not in self.config['UI']:
            self.config['UI']['toolbar_position'] = 'top'

        if 'image_npc_desaturate' not in self.config['UI']:
            self.config['UI']['image_npc_desaturate'] = '1'
            
        if 'coze_duoki_content_bot_id' not in self.config['KEY']:
            self.config['KEY']['coze_duoki_content_bot_id'] = "7563610146597847079"

        if 'coze_duoki_image_bot_id' not in self.config['KEY']:
            self.config['KEY']['coze_duoki_image_bot_id'] = "7568381015052599305"

        if 'coze_duoki_script_bot_id' not in self.config['KEY']:
            self.config['KEY']['coze_duoki_script_bot_id'] = "7584402902635773993"            
        # 设置飞书相关的KEY默认值
            
        if 'feishu_table_id' not in self.config['KEY']:
            self.config['KEY']['feishu_table_id'] = 'tblFrmsWjMRcaaez'
            
        if 'feishu_tenant_access_token' not in self.config['KEY']:
            self.config['KEY']['feishu_tenant_access_token'] = ""

        if 'feishu_access_token_expire_at' not in self.config['KEY']:
            self.config['KEY']['feishu_access_token_expire_at'] = ""
        
            
        # 设置API默认值
        if 'server_url' not in self.config['API']:
            self.config['API']['server_url'] = 'https://portal-test.qidianlingzhi.com:10199/'

        if 'custom_tts' not in self.config['API']:
            self.config['API']['custom_tts'] = 'https://portal-test.qidianlingzhi.com:10199/user/genTTS'
            
        if 'coze_api' not in self.config['API']:
            self.config['API']['coze_api'] = 'https://api.coze.cn/'
            
        # 设置AI默认值
        if 'coze_conversation_dialog_id' not in self.config['AI']:
            self.config['AI']['coze_conversation_dialog_id'] = ""

        if 'coze_content_conversation_dialog_id' not in self.config['AI']:
            self.config['AI']['coze_content_conversation_dialog_id'] = ""
            
        if 'coze_image_conversation_dialog_id' not in self.config['AI']:
            self.config['AI']['coze_image_conversation_dialog_id'] = ""
            
        if 'coze_script_conversation_dialog_id' not in self.config['AI']:
            self.config['AI']['coze_script_conversation_dialog_id'] = ""
            
        # 保存配置（如果是新创建的）
        if not os.path.exists(self.config_path):
            self.save_config()
    
    def save_config(self):
        """保存配置到文件"""
        with open(self.config_path, 'w', encoding='utf-8') as configfile:
            self.config.write(configfile)
    
    def get_last_open_path(self, module_type='audio'):
        """获取上次打开的文件路径
        
        Args:
            module_type (str): 模块类型，'audio' 或 'image'
        """
        if module_type == 'image':
            path = self.config['PATH'].get('image_last_open_path', './')
        else:
            path = self.config['PATH'].get('audio_last_open_path', './')
        
        if path and os.path.exists(path):
            return path
        return './'
    
    def set_last_open_path(self, path, module_type='audio'):
        """设置上次打开的文件路径
        
        Args:
            path (str): 文件路径
            module_type (str): 模块类型，'audio' 或 'image'
        """
        if path:
            # 保存目录路径而不是文件路径
            if os.path.isfile(path):
                path = os.path.dirname(path)
            
            if module_type == 'image':
                self.config['PATH']['image_last_open_path'] = path
            else:
                self.config['PATH']['audio_last_open_path'] = path
            
            self.save_config()
    
    def get_image_last_save_path(self):
        """获取图片上次另存为的路径"""
        path = self.config['PATH'].get('image_last_save_path', './')
        
        if path and os.path.exists(path):
            return path
        return './'
    
    def set_image_last_save_path(self, path):
        """设置图片上次另存为的路径
        
        Args:
            path (str): 文件路径或目录路径
        """
        if path:
            # 保存目录路径而不是文件路径
            if os.path.isfile(path):
                path = os.path.dirname(path)
            
            self.config['PATH']['image_last_save_path'] = path
            self.save_config()

    # 参考图片目录（“上传附件”用）
    def get_reference_image_directory(self):
        """获取最后一次上传附件使用的目录路径
        
        返回存在的路径，否则返回'./'
        """
        path = self.config['PATH'].get('reference_image_directory', './')
        if path and os.path.exists(path):
            return path
        return './'

    def set_reference_image_directory(self, path):
        """设置最后一次上传附件使用的目录路径
        
        若传入文件路径，则取其所在目录；保存后立即写入配置文件
        """
        if not path:
            return
        # 统一保存为目录路径
        if os.path.isfile(path):
            path = os.path.dirname(path)
        self.config['PATH']['reference_image_directory'] = path
        self.save_config()

    # 图片配置页“选择图片目录”的最近打开路径
    def get_story_image_last_open_path(self):
        path = self.config['PATH'].get('story_image_last_open_path', './')
        return path if path else './'

    def set_story_image_last_open_path(self, path):
        if not path:
            return
        p = str(path).replace('\\', '/')
        self.config['PATH']['story_image_last_open_path'] = p
        self.save_config()

    def ensure_story_image_last_open_path(self):
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'story_image_last_open_path' not in self.config['PATH']:
            self.config['PATH']['story_image_last_open_path'] = './'
            self.save_config()
        return self.get_story_image_last_open_path()

    def get_img2img_last_open_path(self):
        path = self.config['PATH'].get('img2img_last_open_path', './')
        return path if path else './'

    def set_img2img_last_open_path(self, path):
        if not path:
            return
        p = str(path).replace('\\', '/')
        # 统一保存为目录路径
        if os.path.isfile(p):
            p = os.path.dirname(p)
        self.config['PATH']['img2img_last_open_path'] = p
        self.save_config()

    def ensure_img2img_last_open_path(self):
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'img2img_last_open_path' not in self.config['PATH']:
            self.config['PATH']['img2img_last_open_path'] = './'
            self.save_config()
        return self.get_img2img_last_open_path()

    def get_img2img_output_directory(self):
        return self.config['PATH'].get('img2img_output_directory', os.path.join(getattr(self, '_output_base_dir', './output'), 'img2img'))

    def set_img2img_output_directory(self, directory):
        d = str(directory or './output/img2img')
        self.config['PATH']['img2img_output_directory'] = d
        self.save_config()

    def ensure_img2img_output_directory(self):
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'img2img_output_directory' not in self.config['PATH']:
            self.config['PATH']['img2img_output_directory'] = os.path.join(getattr(self, '_output_base_dir', './output'), 'img2img')
            self.save_config()
        return self.get_img2img_output_directory()

    def ensure_reference_image_directory(self):
        """确保参考图片目录键存在并返回路径（必要时创建目录）"""
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'reference_image_directory' not in self.config['PATH']:
            self.config['PATH']['reference_image_directory'] = './'
            self.save_config()
        path = self.get_reference_image_directory()
        try:
            # 如果不是相对当前目录，且不存在则创建
            if path != './' and not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
        except Exception:
            # 忽略创建错误，返回原路径
            pass
        return path
    
    def get_theme(self):
        """获取UI主题/样式设置"""
        return self.config['UI'].get('theme', 'windows11')
    
    def set_theme(self, theme):
        """设置UI主题/样式"""
        # 支持所有QApplication样式，不再限制为light/dark
        if theme and isinstance(theme, str):
            self.config['UI']['theme'] = theme
            self.save_config()
    
    def get_toolbar_position(self):
        """获取工具栏位置设置"""
        return self.config['UI'].get('toolbar_position', 'top')
    
    def set_toolbar_position(self, position):
        """设置工具栏位置"""
        if position in ['top', 'bottom', 'left', 'right']:
            self.config['UI']['toolbar_position'] = position
            self.save_config()

    def get_image_npc_desaturate(self):
        v = self.config['UI'].get('image_npc_desaturate', '1')
        try:
            f = float(v)
        except Exception:
            f = 1.0
        if f < 0:
            f = 0.0
        if f > 1:
            f = 1.0
        return f

    def set_image_npc_desaturate(self, value):
        try:
            f = float(value)
        except Exception:
            f = 1.0
        if f < 0:
            f = 0.0
        if f > 1:
            f = 1.0
        self.config['UI']['image_npc_desaturate'] = str(f)
        self.save_config()

    def get_role(self):
        v = self.config['General'].get('role', 'admin')
        return v if v else 'admin'

    def set_role(self, role):
        r = str(role or 'admin')
        self.config['General']['role'] = r
        self.save_config()
    
    def get_general_user_name(self):
        v = self.config['General'].get('user_name', '')
        return v or ''
    
    def set_general_user_name(self, username: str):
        self.config['General']['user_name'] = str(username or '')
        self.save_config()
    
    def clear_general_user_name(self):
        if self.has_option('General', 'user_name'):
            self.remove_option('General', 'user_name')
            self.save_config()
            return True
        return False

    def ensure_image_npc_desaturate(self):
        if 'UI' not in self.config:
            self.config['UI'] = {}
        if 'image_npc_desaturate' not in self.config['UI']:
            self.config['UI']['image_npc_desaturate'] = '1'
            self.save_config()
        return self.get_image_npc_desaturate()

    # 语音引擎相关方法
    def get_tts_engine(self):
        """获取语音引擎设置（custom/volcano/minimax）"""
        return self.config['General'].get('tts_engine', 'custom')

    def set_tts_engine(self, engine):
        """设置语音引擎，并立即保存到配置"""
        try:
            engine_norm = (engine or 'custom').strip().lower()
        except Exception:
            engine_norm = 'custom'
        if engine_norm not in ['custom', 'volcano', 'minimax', 'elevenlabs']:
            engine_norm = 'custom'
        self.config['General']['tts_engine'] = engine_norm
        self.save_config()
            
    # TTS API密钥相关方法
    def get_minimax_api_key(self):
        """获取Minimax API密钥"""
        return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiLljJfkuqzlpYfngrnngbXmmbrnp5HmioDmnInpmZDlhazlj7giLCJVc2VyTmFtZSI6InBhbHUiLCJBY2NvdW50IjoicGFsdUAxODM3NDc0ODM0OTE3OTAwNjQ3IiwiU3ViamVjdElEIjoiMTk1NTUwMDk0MzgxMDI0MTEzNCIsIlBob25lIjoiIiwiR3JvdXBJRCI6IjE4Mzc0NzQ4MzQ5MTc5MDA2NDciLCJQYWdlTmFtZSI6IiIsIk1haWwiOiIiLCJDcmVhdGVUaW1lIjoiMjAyNS0wOS0xNyAxNDoyNToyNiIsIlRva2VuVHlwZSI6MSwiaXNzIjoibWluaW1heCJ9.b8_JgAgf8j0Ha9uWu1WaaWD9QgqPU6iK8plV2LDRoTeXMzTv1RFeojd49AgWBIv4YjvvzIvsuF-jEYHAPkL0gx4KzwgydcfHsYRRsIq48KJXgmk1Xaop9NQrqLr_N6uOFVTJ0e_XpUffsOKYUxyxrgBBPZ33hj97Ni2JDPx4NcjnJCCdx5fK3YFxJeSfrQJCHz5OIV7OS3n0ul-EJt15Vjh_9n1LnItUADvXTna7q1gUU0F9DEU63-VzPOrCujJ5aV-zAjBz176vaeekPpD55RDfrJkr01HrQlL7wk2VMOvmwtJaZdbD9c22pVMyBsJkBocYWKNBE-0j1rG1yQ-ROg"
    
    def get_volcano_appid(self):
        """获取火山引擎AppID"""
        return '4562179438'

    def get_volcano_token(self):
        """获取火山引擎Token"""
        return 'z7FratZoNJoIhWblqDSFNZivuRnV5ZF_'

    def get_scene_output_directory(self):
        return self.config['PATH'].get('scene_output_directory', './output/scene')

    def set_scene_output_directory(self, path):
        try:
            p = str(path or './output/scene')
        except Exception:
            p = './output/scene'
        self.config['PATH']['scene_output_directory'] = p
        self.save_config()

    def get_avatar_output_directory(self):
        return self.config['PATH'].get('avatar_output_directory', './output/avatar')

    def set_avatar_output_directory(self, path):
        try:
            p = str(path or './output/avatar')
        except Exception:
            p = './output/avatar'
        self.config['PATH']['avatar_output_directory'] = p
        self.save_config()

    def ensure_avatar_output_directory(self):
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'avatar_output_directory' not in self.config['PATH']:
            self.config['PATH']['avatar_output_directory'] = os.path.join(getattr(self, '_output_base_dir', './output'), 'avatar')
            self.save_config()
        path = self.get_avatar_output_directory()
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

    def get_wuyun_token(self):
        """获取wuyun API密钥"""
        return 'sk-OSBnhAyjjFJW8uf2XssOeYFYdDf2Fji0Lgba7wqtDcwJIRZ2'


    def get_cookie(self):
        """获取Cookie"""
        v = self.config['KEY'].get('COOKIE', '')
        if not v:
            v = self.config['KEY'].get('cookie', '')
        return v

    def set_cookie(self, cookie):
        """设置Cookie"""
        self.config['KEY']['COOKIE'] = cookie
        self.save_config()

    def clear_cookie(self):
        """清除Cookie"""
        if self.has_option('KEY', 'COOKIE'):
            self.remove_option('KEY', 'COOKIE')
            self.save_config()
            return True
        return False
    
    def get_custom_tts(self):
        """获取自定义TTS URL"""
        return self.get('API', 'custom_tts')
    
    def set_custom_tts(self, custom_tts):
        """设置自定义TTS URL"""
        self.set('API', 'custom_tts', custom_tts)
    
    def get(self, section, key, fallback=None):
        """通用获取配置方法"""
        if section not in self.config:
            return fallback
        return self.config[section].get(key, fallback)
    
    def set(self, section, key, value):
        """通用设置配置方法"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value
    
    def save(self):
        """保存配置文件"""
        self.save_config()
    
    def has_option(self, section, option):
        """检查指定节和选项是否存在"""
        return section in self.config and option in self.config[section]
    
    def remove_option(self, section, option):
        """移除指定节中的选项"""
        if self.has_option(section, option):
            del self.config[section][option]
            return True
        return False
    
    # Coze相关配置方法
    def get_coze_token(self):
        """获取Coze API Token"""
        return 'pat_WO3EGU8G2Y19qsQltTxSm7AXg2GKrTt686vFRffmZRzYzcxoWklzTtC0b4nmi6xF'
    
    def get_coze_api(self):
        """获取Coze API URL"""
        return self.config['API'].get('coze_api', 'https://api.coze.cn/')
    
    def set_coze_api(self, api_url):
        """设置Coze API URL"""
        self.config['API']['coze_api'] = api_url
        self.save_config()
    
    def get_coze_duoki_content_bot_id(self):
        """获取Coze多奇文案生成器Bot ID"""
        return self.config['KEY'].get('coze_duoki_content_bot_id', '')
    
    def get_coze_duoki_image_bot_id(self):
        """获取Coze多奇图片生成器Bot ID"""
        return self.config['KEY'].get('coze_duoki_image_bot_id', '')

    def get_coze_duoki_script_bot_id(self):
        """获取Coze多奇脚本生成器Bot ID"""
        return self.config['KEY'].get('coze_duoki_script_bot_id', '')

    def get_coze_conversation_dialog_id(self):
        """获取对白生成器会话ID"""
        return self.config['AI'].get('coze_conversation_dialog_id', '')
    
    def set_coze_conversation_dialog_id(self, conversation_id):
        """设置对白生成器会话ID"""
        self.config['AI']['coze_conversation_dialog_id'] = conversation_id
        self.save_config()

    def get_coze_content_conversation_dialog_id(self):
        """获取Coze多奇内容文案生成会话ID"""
        return self.config['AI'].get('coze_content_conversation_dialog_id', '')
    
    def set_coze_content_conversation_dialog_id(self, conversation_id):
        """设置Coze多奇内容文案生成会话ID"""
        self.config['AI']['coze_content_conversation_dialog_id'] = conversation_id
        self.save_config()
    
    def get_coze_image_conversation_dialog_id(self):
        """获取Coze多奇图片生成器会话ID"""
        return self.config['AI'].get('coze_image_conversation_dialog_id', '')
    
    def set_coze_image_conversation_dialog_id(self, conversation_id):
        """设置Coze多奇图片生成器会话ID"""
        self.config['AI']['coze_image_conversation_dialog_id'] = conversation_id
        self.save_config()
        
    def get_coze_script_conversation_dialog_id(self):
        """获取Coze多奇脚本生成器会话ID"""
        return self.config['AI'].get('coze_script_conversation_dialog_id', '')
    
    def set_coze_script_conversation_dialog_id(self, conversation_id):
        """设置Coze多奇脚本生成器会话ID"""
        self.config['AI']['coze_script_conversation_dialog_id'] = conversation_id
        self.save_config()
    
    def get_voice_output_directory(self):
        """获取语音输出目录"""
        return self.config['PATH'].get('voice_output_directory', './output/voice')
    
    def set_voice_output_directory(self, directory):
        """设置语音输出目录"""
        self.config['PATH']['voice_output_directory'] = directory
        self.save_config()

    def get_sfx_output_directory(self):
        """获取音效输出目录"""
        return self.config['PATH'].get('sfx_output_directory', './output/sfx')

    def set_sfx_output_directory(self, directory):
        """设置音效输出目录"""
        self.config['PATH']['sfx_output_directory'] = directory
        self.save_config()

    # 知识点生成路径相关
    def get_knowledge_last_open_path(self):
        path = self.config['PATH'].get('knowledge_last_open_path', './')
        if path and os.path.exists(path):
            return path
        return './'

    def set_knowledge_last_open_path(self, path):
        if not path:
            return
        p = path
        if os.path.isfile(p):
            p = os.path.dirname(p)
        self.config['PATH']['knowledge_last_open_path'] = p
        self.save_config()

    def get_knowledge_output_directory(self):
        return self.config['PATH'].get('knowledge_output_directory', os.path.join(getattr(self, '_output_base_dir', './output'), 'knowledge'))

    def set_knowledge_output_directory(self, directory):
        """设置知识点输出目录"""
        self.config['PATH']['knowledge_output_directory'] = directory
        self.save_config()

    def ensure_knowledge_output_directory(self):
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'knowledge_output_directory' not in self.config['PATH']:
            self.config['PATH']['knowledge_output_directory'] = os.path.join(getattr(self, '_output_base_dir', './output'), 'knowledge')
            self.save_config()
        path = self.get_knowledge_output_directory()
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

    def get_npc_output_directory(self):
        return self.config['PATH'].get('npc_output_directory', os.path.join(getattr(self, '_output_base_dir', './output'), 'npc'))

    def set_npc_output_directory(self, directory):
        """设置NPC输出目录"""
        self.config['PATH']['npc_output_directory'] = directory
        self.save_config()

    def ensure_npc_output_directory(self):
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'npc_output_directory' not in self.config['PATH']:
            self.config['PATH']['npc_output_directory'] = os.path.join(getattr(self, '_output_base_dir', './output'), 'npc')
            self.save_config()
        path = self.get_npc_output_directory()
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

    def get_script_output_directory(self):
        return self.config['PATH'].get('script_output_directory', os.path.join(getattr(self, '_output_base_dir', './output'), 'script'))

    def set_script_output_directory(self, directory):
        """设置脚本输出目录"""
        self.config['PATH']['script_output_directory'] = directory
        self.save_config()

    def ensure_script_output_directory(self):
        if 'PATH' not in self.config:
            self.config['PATH'] = {}
        if 'script_output_directory' not in self.config['PATH']:
            self.config['PATH']['script_output_directory'] = os.path.join(getattr(self, '_output_base_dir', './output'), 'script')
            self.save_config()
        path = self.get_script_output_directory()
        if path and not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        return path

    def get_elevenlabs_api_key(self):
        """获取ElevenLabs API密钥"""
        return 'sk_b4cabe86bf9754cfd46148ce4477b8326ad34bfa6368559f'
    
    # 飞书相关配置方法
    def get_feishu_app_id(self):
        """获取飞书应用ID"""
        return 'cli_a87595f209f2d00d'
    
    def get_feishu_app_secret(self):
        """获取飞书应用密钥"""
        return 'egKRPDQ4CSKZpkCHkk4A0fGlRaLA7BxZ'
    
    def get_feishu_user_access_token(self):
        """获取飞书用户访问令牌"""
        return 'DW0WbSjM4aDcJBseiN2cJnAdnPh'
    
    def get_feishu_tenant_access_token(self):
        """获取飞书租户访问令牌"""
        return self.config['KEY'].get('feishu_tenant_access_token', '')
    
    def set_feishu_tenant_access_token(self, token):
        """设置飞书租户访问令牌"""
        self.config['KEY']['feishu_tenant_access_token'] = token
        self.save_config()
    
    def get_feishu_refresh_token(self):
        """获取飞书刷新令牌"""
        return self.config['KEY'].get('feishu_refresh_token', '')
    
    def set_feishu_refresh_token(self, token):
        """设置飞书刷新令牌"""
        self.config['KEY']['feishu_refresh_token'] = token
        self.save_config()
    
    def get_feishu_app_token(self):
        """获取飞书应用令牌"""
        return self.config['KEY'].get('feishu_app_token', '')
    
    def set_feishu_app_token(self, token):
        """设置飞书应用令牌"""
        self.config['KEY']['feishu_app_token'] = token
        self.save_config()
    
    def get_feishu_table_id(self):
        """获取飞书表格ID"""
        return self.config['KEY'].get('feishu_table_id', '')
    
    def get_feishu_access_token_expire_at(self):
        """获取飞书访问令牌过期时间"""
        return self.config['KEY'].get('feishu_access_token_expire_at', '')
    
    def set_feishu_access_token_expire_at(self, expire_at):
        """设置飞书访问令牌过期时间"""
        self.config['KEY']['feishu_access_token_expire_at'] = expire_at
        self.save_config()
