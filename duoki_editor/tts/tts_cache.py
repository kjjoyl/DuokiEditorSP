import os
import hashlib
import requests
import json
from pathlib import Path
from duoki_editor.core.speech_parameters_manager import SpeechParametersManager
from duoki_editor.core.character_table_manager import CharacterTableManager
from duoki_editor.utils.config_manager import ConfigManager
from pydub import AudioSegment
import io

class TTSCache:
    def __init__(self, cache_dir=None):
        # 设置默认缓存目录为项目下的cache/audio
        if cache_dir is None:
            base_dir = Path(__file__).parent.parent
            self.cache_dir = base_dir / "cache" / "audio"
        else:
            self.cache_dir = Path(cache_dir)
            
        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.speech_params_manager = SpeechParametersManager() # 初始化语音参数管理器
        self.character_table_manager = CharacterTableManager() # 初始化角色表管理器
        
        # 初始化配置管理器
        self.config_manager = ConfigManager()
        
        # 添加全局变量存储当前使用的TTS API类型
        self.current_tts_api_type = None  # 可能的值: "custom", "volcano", "minimax"
        self.current_audio_format = None  # 存储当前音频格式: "mp3", "wav", "pcm"等
        
        # 从配置文件获取API密钥
        self.minimax_api_key = self.config_manager.get_minimax_api_key()
        self.volcano_appid = self.config_manager.get_volcano_appid()
        self.volcano_token = self.config_manager.get_volcano_token()
    
    def _detect_audio_format(self, audio_data):
        """检测音频数据的格式"""
        # 检查文件头部的魔数来判断格式
        if audio_data.startswith(b'RIFF') and b'WAVE' in audio_data[:12]:
            return 'wav'
        elif audio_data.startswith(b'ID3') or audio_data.startswith(b'\xff\xfb') or audio_data.startswith(b'\xff\xf3') or audio_data.startswith(b'\xff\xf2'):
            return 'mp3'
        elif audio_data.startswith(b'OggS'):
            return 'ogg'
        elif audio_data.startswith(b'fLaC'):
            return 'flac'
        else:
            # 检查是否为PCM格式（通常没有特定的文件头，需要通过其他方式判断）
            # PCM格式检测需要非常严格的条件，避免误识别
            if len(audio_data) >= 2048:  # 至少需要2KB才能进行有效的PCM检测
                try:
                    # 检查是否有明显的文件头标识
                    has_known_header = (audio_data.startswith(b'RIFF') or 
                                      audio_data.startswith(b'ID3') or 
                                      audio_data.startswith(b'OggS') or 
                                      audio_data.startswith(b'fLaC') or
                                      audio_data.startswith(b'\xff\xfb') or  # MP3 frame header
                                      audio_data.startswith(b'\xff\xfa') or  # MP3 frame header
                                      audio_data.startswith(b'\x00\x00') or  # 可能的空数据
                                      len(audio_data) < 100)                 # 数据太小
                    
                    # 只有在以下条件都满足时才识别为PCM：
                    # 1. 没有已知的文件头
                    # 2. 数据长度是2的倍数（16位PCM）
                    # 3. 数据长度足够大（至少2KB）
                    # 4. 数据看起来像音频数据（有足够的变化）
                    # 5. 数据不是全0、全255或其他明显的非音频模式
                    if (not has_known_header and 
                        len(audio_data) >= 2048 and 
                        len(audio_data) % 2 == 0):  # 只检查16位PCM
                        
                        # 检查数据的随机性和分布
                        sample_data = audio_data[:2048]
                        unique_bytes = len(set(sample_data))
                        
                        # 检查是否有足够的数据变化
                        if unique_bytes > 50:  # 提高变化要求
                            # 检查数据分布是否合理（不全是极值）
                            zero_count = sample_data.count(0)
                            ff_count = sample_data.count(255)
                            
                            # 如果0或255的比例过高，可能不是有效的PCM数据
                            if (zero_count < len(sample_data) * 0.8 and 
                                ff_count < len(sample_data) * 0.8):
                                
                                # 额外检查：确保数据长度合理（不能太小）
                                if len(audio_data) >= 4096:  # 至少4KB
                                    print(f"检测到PCM格式，数据长度: {len(audio_data)} bytes")
                                    return 'pcm'
                except:
                    pass
            
            # 默认假设为wav格式
            return 'wav'
    
    def _convert_pcm_to_wav(self, pcm_data, sample_rate=16000, channels=1, sample_width=2):
        """将PCM数据转换为WAV格式
        Args:
            pcm_data: PCM音频数据
            sample_rate: 采样率，默认16000Hz
            channels: 声道数，默认1（单声道）
            sample_width: 采样位宽，默认2字节（16位）
        """
        try:
            import wave
            import io
            
            # 验证PCM数据的有效性
            if not pcm_data or len(pcm_data) < 2:
                print(f"PCM数据无效: 长度 {len(pcm_data)} 字节，至少需要2字节")
                return pcm_data
            
            # 确保数据长度是采样位宽的倍数
            expected_frame_size = channels * sample_width
            if len(pcm_data) % expected_frame_size != 0:
                # 截断到最近的完整帧
                truncated_length = (len(pcm_data) // expected_frame_size) * expected_frame_size
                if truncated_length < expected_frame_size:
                    print(f"PCM数据太小，无法形成完整帧: {len(pcm_data)} bytes")
                    return pcm_data
                pcm_data = pcm_data[:truncated_length]
                print(f"PCM数据已截断到完整帧: {truncated_length} bytes")
            
            # 创建WAV文件的内存缓冲区
            wav_buffer = io.BytesIO()
            
            # 创建WAV文件
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(channels)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(pcm_data)
            
            wav_data = wav_buffer.getvalue()
            print(f"PCM转WAV成功: {len(pcm_data)} bytes -> {len(wav_data)} bytes")
            return wav_data
            
        except Exception as e:
            print(f"PCM转WAV失败: {e}")
            return pcm_data  # 返回原始数据

    def _convert_audio_to_mp3(self, audio_data, source_format='wav'):
        """将音频数据转换为MP3格式"""
        try:
            # 如果已经是MP3格式，直接返回原数据
            if source_format == 'mp3':
                return audio_data
            
            # 使用BytesIO创建内存中的文件对象
            audio_io = io.BytesIO(audio_data)
            
            # 根据源格式加载音频
            if source_format == 'wav':
                audio = AudioSegment.from_wav(audio_io)
            elif source_format == 'ogg':
                audio = AudioSegment.from_ogg(audio_io)
            elif source_format == 'flac':
                audio = AudioSegment.from_file(audio_io, format='flac')
            else:
                # 尝试自动检测格式
                audio = AudioSegment.from_file(audio_io)
            
            # 转换为MP3格式
            mp3_io = io.BytesIO()
            audio.export(mp3_io, format='mp3', bitrate='128k')
            mp3_data = mp3_io.getvalue()
            
            print(f"音频格式转换成功: {source_format} -> mp3")
            return mp3_data
            
        except Exception as e:
            print(f"音频格式转换失败: {e}")
            print("提示: 如果是格式转换问题，可能需要安装ffmpeg")
            # 如果转换失败，检查是否是WAV格式但直接保存为MP3的情况
            if source_format == 'wav':
                print("警告: WAV格式音频将直接保存为MP3文件，可能导致播放问题")
                print("建议安装ffmpeg以支持音频格式转换")
            # 返回原始数据
            return audio_data
    
    def _get_text_hash(self, text, speaker=None):
        """生成文本的哈希值作为文件名
        
        格式为：speaker_text，保留text中的所有符号
        """
        hash_text = text
        print(f"说话人： {speaker}")
        if speaker:
            hash_text = f"{speaker}_{text}"
        print(f"要获取md5的文本： {hash_text}")
        return hashlib.md5(hash_text.encode('utf-8')).hexdigest()
    
    def get_audio_path(self, text, speaker=None):
        """获取文本对应的音频文件路径，按优先级遍历所有格式文件
        优先级：wav > pcm > mp3 > ogg
        """
        text_hash = self._get_text_hash(text, speaker)
        
        # 按优先级检查不同格式的文件
        formats = ['wav', 'pcm', 'mp3', 'ogg']
        
        for format_ext in formats:
            audio_path = self.cache_dir / f"{text_hash}.{format_ext}"
            if audio_path.exists():
                print(f"从缓存加载{format_ext}格式音频: {text}")
                return str(audio_path)
        
        # 所有格式都不存在，返回None
        print(f"缓存中未找到音频: {text[:20]}")
        return None
    
    def download_audio(self, url, text, speaker=None):
        """下载音频文件"""
        text_hash = self._get_text_hash(text, speaker)
        audio_path = self.cache_dir / f"{text_hash}.mp3"
        
        # 下载音频文件
        try:
            # 设置30秒超时，包括连接超时(10秒)和读取超时(20秒)
            response = requests.get(url, stream=True, timeout=(10, 20))
            with open(audio_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"下载并缓存音频成功: {text[:20]}...")
            return str(audio_path)
        except requests.exceptions.Timeout:
            print(f"下载音频超时: {url}")
            if audio_path.exists():
                audio_path.unlink()  # 删除可能部分下载的文件
            return None
        except requests.exceptions.ConnectionError:
            print(f"下载音频连接错误: {url}")
            if audio_path.exists():
                audio_path.unlink()  # 删除可能部分下载的文件
            return None
        except Exception as e:
            print(f"下载音频失败: {e}")
            if audio_path.exists():
                audio_path.unlink()  # 删除可能部分下载的文件
            return None
    
    def call_tts_api(self, text, speaker="default", speed=None, emotion=None, engine=None, voice_id_override=None):
        """根据配置中的tts_engine调用相应的TTS API"""
        # 读取用户选择的语音引擎
        engine = (engine or self.config_manager.get_tts_engine() or 'custom').strip().lower()
        
        if engine == 'custom':
            # 使用自定义TTS API（需要配置自定义URL）
            custom_tts = self.config_manager.get_custom_tts()
            if custom_tts and str(custom_tts).strip():
                self.current_tts_api_type = 'custom'
                print(f"调用TTS API，引擎类型: custom, text: {text}, speaker: {speaker}")
                return self.call_custom_tts(text, speaker, str(custom_tts).strip())
            else:
                # 若选择了custom但未配置URL，回退到minimax
                print("已选择 custom 语音引擎，但未配置自定义TTS URL，回退到 minimax")
                self.current_tts_api_type = 'minimax'
                self.current_audio_format = 'mp3'
                return self.call_minimax_tts(text, speaker)
        elif engine == 'volcano':
            self.current_tts_api_type = 'volcano'
            self.current_audio_format = 'mp3'
            print(f"调用TTS API，引擎类型: volcano, text: {text}, speaker: {speaker}")
            return self.call_volcano_tts(text, speaker, speed=speed, emotion=emotion, voice_id_override=voice_id_override)
        elif engine == 'minimax':
            self.current_tts_api_type = 'minimax'
            self.current_audio_format = 'mp3'
            print(f"调用TTS API，引擎类型: minimax, text: {text}, speaker: {speaker}")
            return self.call_minimax_tts(text, speaker, speed=speed, emotion=emotion, voice_id_override=voice_id_override)
        elif engine == 'elevenlabs':
            self.current_tts_api_type = 'elevenlabs'
            self.current_audio_format = 'mp3'
            print(f"调用TTS API，引擎类型: elevenlabs, text: {text}, speaker: {speaker}")
            default_voice_id = "KfcOXyYXfJ51vqufTZxR"
            vid = (voice_id_override or default_voice_id)
            return self.call_elevenlabs_tts(text, voice_id=vid, speed=speed, stability=1)
        else:
            # 未知值时默认使用minimax
            print(f"未知语音引擎 '{engine}'，使用默认 minimax")
            self.current_tts_api_type = 'minimax'
            self.current_audio_format = 'mp3'
            return self.call_minimax_tts(text, speaker, speed=speed, emotion=emotion)

    def call_elevenlabs_tts(self, text, voice_id, model_id="eleven_multilingual_v2", speed=None, stability=1, output_format="mp3_44100_128"):
        api_key = self.config_manager.get_elevenlabs_api_key()
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={output_format}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "speed": (speed if speed is not None else 1),
                "stability": stability
            }
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=(10, 30))
            content_type = response.headers.get('content-type', '')
            text_hash = self._get_text_hash(text, speaker=voice_id)
            ext = 'mp3'
            if 'wav' in content_type:
                ext = 'wav'
            audio_path = self.cache_dir / f"{text_hash}.{ext}"
            if ('audio' in content_type or 'mpeg' in content_type or 'mp3' in content_type or 'octet-stream' in content_type or 'wav' in content_type) and response.content:
                with open(audio_path, 'wb') as f:
                    f.write(response.content)
                self.current_tts_api_type = 'elevenlabs'
                self.current_audio_format = ext
                return {"audio_path": str(audio_path), "success": True}
            else:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                audio_url = None
                if isinstance(data, dict):
                    audio_url = data.get('audio') or data.get('data', {}).get('audio') or data.get('audio_url')
                if audio_url:
                    audio_resp = requests.get(audio_url, timeout=(10, 30))
                    audio_ct = audio_resp.headers.get('content-type', '')
                    ext = 'mp3'
                    if 'wav' in audio_ct:
                        ext = 'wav'
                    audio_path = self.cache_dir / f"{text_hash}.{ext}"
                    with open(audio_path, 'wb') as f:
                        f.write(audio_resp.content)
                    self.current_tts_api_type = 'elevenlabs'
                    self.current_audio_format = ext
                    return {"audio_path": str(audio_path), "success": True}
                else:
                    return {"error": "生成失败", "response_json": data, "response_text": getattr(response, 'text', '')}
        except requests.exceptions.Timeout:
            return {"error": "请求超时，请检查网络连接或稍后重试"}
        except requests.exceptions.ConnectionError:
            return {"error": "网络连接错误，请检查网络设置"}
        except requests.exceptions.RequestException as e:
            return {"error": f"请求异常: {str(e)}"}
        except Exception as e:
            return {"error": f"调用异常: {str(e)}"}

    def call_elevenlabs_voice_changer(self, audio_file_path, voice_id, output_format="mp3_44100_128"):
        api_key = self.config_manager.get_elevenlabs_api_key()
        url = f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}?output_format={output_format}"
        if not audio_file_path or not os.path.exists(audio_file_path):
            return {"error": "文件不存在"}
        headers = {
            "xi-api-key": api_key
        }
        try:
            print(f"音色转换请求: voice_id={voice_id}, file={audio_file_path}, format={output_format}")
            with open(audio_file_path, 'rb') as f:
                files = {"audio": f}
                data = {"model_id": "eleven_multilingual_sts_v2"}
                print(f"音色转换请求: voice_id={voice_id}, file={audio_file_path}, format={output_format}")
                response = requests.post(url, headers=headers, files=files, data=data, timeout=(10, 30))
            content_type = response.headers.get('content-type', '')
            ext = 'mp3'
            if 'wav' in content_type:
                ext = 'wav'
            text_key = f"voice_changer:{voice_id}:{os.path.basename(audio_file_path)}"
            text_hash = self._get_text_hash(text_key, speaker=voice_id)
            audio_path = self.cache_dir / f"{text_hash}.{ext}"
            if ('audio' in content_type or 'mpeg' in content_type or 'mp3' in content_type or 'octet-stream' in content_type or 'wav' in content_type) and response.content:
                with open(audio_path, 'wb') as f:
                    f.write(response.content)
                self.current_tts_api_type = 'elevenlabs_sts'
                self.current_audio_format = ext
                print(f"音色转换保存: path={audio_path}")
                return {"audio_path": str(audio_path), "success": True}
            else:
                data = {}
                try:
                    data = response.json()
                except Exception:
                    pass
                audio_url = None
                if isinstance(data, dict):
                    audio_url = data.get('audio') or data.get('data', {}).get('audio') or data.get('audio_url')
                if audio_url:
                    audio_resp = requests.get(audio_url, timeout=(10, 30))
                    audio_ct = audio_resp.headers.get('content-type', '')
                    ext = 'mp3'
                    if 'wav' in audio_ct:
                        ext = 'wav'
                    with open(audio_path, 'wb') as f:
                        f.write(audio_resp.content)
                    self.current_tts_api_type = 'elevenlabs_sts'
                    self.current_audio_format = ext
                    print(f"音色转换保存: path={audio_path}")
                    return {"audio_path": str(audio_path), "success": True}
                return {"error": "生成失败", "response_json": data, "response_text": getattr(response, 'text', '')}
        except requests.exceptions.Timeout:
            return {"error": "请求超时，请检查网络连接或稍后重试"}
        except requests.exceptions.ConnectionError:
            return {"error": "网络连接错误，请检查网络设置"}
        except requests.exceptions.RequestException as e:
            return {"error": f"请求异常: {str(e)}"}
        except Exception as e:
            return {"error": f"调用异常: {str(e)}"}

    def call_minimax_tts(self, text, speaker="default", speed=None, emotion=None, voice_id_override=None):
        """调用Minimax TTS API"""
        url = "https://api.minimaxi.com/v1/t2a_v2"
        
        # 获取语音参数
        speech_params = self.speech_params_manager.get_speech_parameters(speaker)
        # 获取不带前缀的voice_id
        voice_id = (voice_id_override or self.speech_params_manager.get_voice_id_from_speaker(speaker, with_prefix=False))
        if voice_id is None:
            voice_id = "male-qn-qingse"
        speed = (speed if speed is not None else speech_params.get("speed"))
        if isinstance(speed, (int, float)):
            speed = float(speed)
        elif isinstance(speed, str):
            s = speed.strip()
            speed = float(s) if s and s.replace('.', '', 1).isdigit() else 1.0
        else:
            speed = 1.0
        vol = speech_params["vol"]
        pitch = speech_params["pitch"]
        emotion = emotion if (emotion is not None and str(emotion).strip() != "") else speech_params.get("emotion_type")
        print(f"调用Minimax TTS API参数：speaker: {speaker}, voice_id={voice_id}, speed={speed}, vol={vol}, pitch={pitch}, emotion={emotion}")
        
        # 处理emotion为空或nan的情况
        if emotion is None or str(emotion).lower() == 'nan' or str(emotion).strip() == '':
            emotion = ""

        payload = json.dumps({
            "model": "speech-2.5-hd-preview",
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed,
                "vol": vol,
                "pitch": pitch,
                "emotion": emotion
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1
            },
            "subtitle_enable": False,
            "language_boost": "English",
            "output_format": "url"
        })
        
        headers = {
            'Authorization': f'Bearer {self.minimax_api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            # 设置30秒超时，包括连接超时(10秒)和读取超时(20秒)
            response = requests.post(url, headers=headers, data=payload, timeout=(10, 20))
            result = response.json()
            
            # 如果响应中包含音频URL，则下载并保存到缓存
            if 'data' in result and 'audio' in result['data']:
                audio_url = result['data']['audio']
                
                try:
                    # 下载音频文件
                    audio_response = requests.get(audio_url, timeout=(10, 30))
                    audio_response.raise_for_status()
                    
                    # 获取音频数据
                    audio_data = audio_response.content
                    
                    # 设置当前音频格式为mp3（Minimax固定返回mp3）
                    self.current_audio_format = "mp3"
                    
                    # 生成文本的哈希值作为文件名
                    text_hash = self._get_text_hash(text, speaker)
                    audio_path = self.cache_dir / f"{text_hash}.mp3"
                    
                    # 保存音频文件到缓存
                    with open(audio_path, 'wb') as f:
                        f.write(audio_data)
                    print(f"保存Minimax音频成功: {text_hash}...")
                    
                    # 在结果中添加音频文件路径，以便上层调用者使用
                    result['audio_path'] = str(audio_path)
                    
                except Exception as e:
                    print(f"下载或保存Minimax音频失败: {e}")
                    return {"error": f"下载音频失败: {str(e)}"}
            
            return result
        except requests.exceptions.Timeout:
            print(f"Minimax TTS API请求超时")
            return {"error": "请求超时，请检查网络连接或稍后重试"}
        except requests.exceptions.ConnectionError:
            print(f"Minimax TTS API连接错误")
            return {"error": "网络连接错误，请检查网络设置"}
        except requests.exceptions.RequestException as e:
            print(f"Minimax TTS API请求异常: {e}")
            return {"error": f"请求异常: {str(e)}"}
    
    def call_volcano_tts(self, text, speaker, speed=None, emotion=None, voice_id_override=None):
        """调用火山引擎TTS API"""
        url = "https://openspeech.bytedance.com/api/v1/tts"
        
        # 从speaker获取不带前缀的voice_id
        speech_params = self.speech_params_manager.get_speech_parameters(speaker)

        print(f"调用火山 TTS API，text: {text}, speaker: {speaker}，参数：{speech_params}")
        # 获取不带前缀的voice_id
        voice_id = (voice_id_override or self.speech_params_manager.get_voice_id_from_speaker(speaker, with_prefix=False))
        if voice_id is None:
            voice_id = "zh_male_M392_conversation_wvae_bigtts"
        speed = (speed if speed is not None else speech_params.get("speed"))
        if isinstance(speed, (int, float)):
            speed = float(speed)
        elif isinstance(speed, str):
            s = speed.strip()
            speed = float(s) if s and s.replace('.', '', 1).isdigit() else 1.0
        else:
            speed = 1.0
        vol = speech_params["vol"]
        pitch = speech_params["pitch"]
        emotion = emotion if (emotion is not None and str(emotion).strip() != "") else speech_params.get("emotion_type")
        
        # 处理emotion为空或nan的情况
        enable_emotion = True
        if emotion is None or str(emotion).lower() == 'nan' or str(emotion).strip() == '':
            emotion = ""
            enable_emotion = False
        
        payload = json.dumps({
            "app": {
                "appid": self.volcano_appid,
                "token": "access_token",
                "cluster": "volcano_tts",
            },
            "user": {
                "uid": "uid123"
            },
            "audio": {
                "voice_type": voice_id,
                "encoding": "mp3",
                "speed_ratio": speed,
                "emotion": emotion,
                "enable_emotion": enable_emotion
            },
            "request": {
                "reqid": "uuid",
                "text": text,
                "operation": "query",
            }
        })
        
        headers = {
            'Authorization': f'Bearer; {self.volcano_token}',
            'Content-Type': 'application/json'
        }
        
        try:
            # 设置30秒超时，包括连接超时(10秒)和读取超时(20秒)
            response = requests.post(url, headers=headers, data=payload, timeout=(10, 20))
            result = response.json()
            
            # 将完整响应保存到日志文件
            self._save_volcano_response_log(result)
            
            print(f"火山引擎TTS API响应已保存到日志文件")
            
            # 如果响应中包含base64编码的音频数据，则解码并保存
            if 'data' in result:
                # 获取base64编码的音频数据
                audio_base64 = result['data']
                
                # 解码base64数据
                import base64
                try:
                    audio_data = base64.b64decode(audio_base64)
                    
                    # 检测音频格式
                    detected_format = self._detect_audio_format(audio_data)
                    print(f"检测到音频格式: {detected_format}")
                    
                    # 设置当前音频格式
                    self.current_audio_format = detected_format
                    
                    # 生成文本的哈希值作为文件名
                    text_hash = self._get_text_hash(text, speaker)
                    audio_path = self.cache_dir / f"{text_hash}.mp3"
                
                    # 解码base64数据并保存为文件
                    with open(audio_path, 'wb') as f:
                        f.write(audio_data)
                    print(f"保存火山引擎音频成功: {text_hash}...")
                    
                    # 在结果中添加音频文件路径，以便上层调用者使用
                    result['audio_path'] = str(audio_path)
                except Exception as e:
                    print(f"解码或保存base64音频数据失败: {e}")
            
            return result
        except requests.exceptions.Timeout:
            print(f"火山引擎TTS API请求超时")
            return {"error": "请求超时，请检查网络连接或稍后重试"}
        except requests.exceptions.ConnectionError:
            print(f"火山引擎TTS API连接错误")
            return {"error": "网络连接错误，请检查网络设置"}
        except requests.exceptions.RequestException as e:
            print(f"火山引擎TTS API请求异常: {e}")
            return {"error": f"请求异常: {str(e)}"}
        except Exception as e:
            print(f"调用火山引擎TTS API失败: {e}")
            return {"error": str(e)}
            
    def _save_volcano_response_log(self, response_data):
        """保存火山引擎响应数据到日志文件"""
        import datetime
        
        # 创建日志目录
        log_dir = self.cache_dir.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用固定的日志文件名
        log_file = log_dir / "volcano_tts_responses.json"
        
        # 获取当前时间作为记录标识
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 准备要添加的日志条目
        log_entry = {
            "timestamp": timestamp,
            "response": response_data
        }
        
        # 读取现有日志文件或创建新的
        try:
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    try:
                        log_data = json.load(f)
                    except json.JSONDecodeError:
                        log_data = {"responses": []}
            else:
                log_data = {"responses": []}
            
            # 添加新的响应数据
            log_data["responses"].append(log_entry)
            
            # 保存回文件
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            
            print(f"火山引擎响应数据已添加到日志文件: {log_file}")
        except Exception as e:
            print(f"保存火山引擎响应日志失败: {e}")
    
    def call_custom_tts(self, text, speaker, tts_url):
        """调用自定义TTS API"""
        print(f"调用自定义TTS API: {tts_url}, text: {text}, speaker: {speaker}")
        
        # 获取character_id，使用get_id_by_speaker方法
        character_id = self.character_table_manager.get_id_by_speaker(speaker)
        if character_id is None:
            # 如果没有找到对应的character_id，使用默认值
            character_id = "3001"
            print(f"未找到speaker '{speaker}' 对应的character_id，使用默认值: {character_id}")
        else:
            character_id = str(character_id)
            print(f"找到speaker '{speaker}' 对应的character_id: {character_id}")
        
        # 构建请求体
        payload = {
            "text": text,
            "charter_id": character_id
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        try:
            # 发送GET请求
            response = requests.get(tts_url, headers=headers, params=payload, timeout=(10, 30))
            print(f"自定义TTS 响应体: {response}")
            if response.status_code == 200:
                # 检查响应内容类型
                content_type = response.headers.get('content-type', '')
                
                if 'audio' in content_type or 'mp3' in content_type:
                    # 获取音频数据
                    audio_data = response.content
                    
                    # 检测音频格式
                    detected_format = self._detect_audio_format(audio_data)
                    print(f"检测到音频格式: {detected_format}")
                    
                    # 设置当前音频格式
                    self.current_audio_format = detected_format
                    
                    # 生成文本的哈希值作为文件名
                    text_hash = self._get_text_hash(text, speaker)
                    
                    # 如果是PCM格式，转换为WAV格式以确保兼容性
                    if detected_format == 'pcm':
                        print("检测到PCM格式，转换为WAV格式以提高播放兼容性")
                        wav_data = self._convert_pcm_to_wav(audio_data)
                        audio_path = self.cache_dir / f"{text_hash}.wav"
                        with open(audio_path, 'wb') as f:
                            f.write(wav_data)
                        print(f"保存WAV格式音频文件成功: {text_hash}.wav")
                    else:
                        # 直接保存为检测到的格式
                        audio_path = self.cache_dir / f"{text_hash}.{detected_format}"
                        with open(audio_path, 'wb') as f:
                            f.write(audio_data)
                        print(f"保存{detected_format}格式音频文件成功: {text_hash}.{detected_format}")
                    
                    # 返回结果，包含音频文件路径
                    return {
                        'audio_path': str(audio_path),
                        'success': True
                    }
                else:
                    # 尝试解析JSON响应
                    try:
                        result = response.json()
                        print(f"自定义TTS API响应: {result}")
                        return result
                    except json.JSONDecodeError:
                        # 如果不是JSON，直接当作音频数据处理
                        audio_data = response.content
                        
                        # 检测音频格式
                        detected_format = self._detect_audio_format(audio_data)
                        print(f"检测到音频格式: {detected_format}")
                        
                        # 生成文本的哈希值作为文件名
                        text_hash = self._get_text_hash(text, speaker)
                        
                        # 如果是PCM格式，转换为WAV格式以确保兼容性
                        if detected_format == 'pcm':
                            print("检测到PCM格式，转换为WAV格式以提高播放兼容性")
                            wav_data = self._convert_pcm_to_wav(audio_data)
                            audio_path = self.cache_dir / f"{text_hash}.wav"
                            with open(audio_path, 'wb') as f:
                                f.write(wav_data)
                            print(f"保存WAV格式音频文件成功: {text_hash}.wav")
                        else:
                            # 直接保存为检测到的格式
                            audio_path = self.cache_dir / f"{text_hash}.{detected_format}"
                            with open(audio_path, 'wb') as f:
                                f.write(audio_data)
                            print(f"保存{detected_format}格式音频文件成功: {text_hash}.{detected_format}")
                        
                        # 返回结果，包含音频文件路径
                        return {
                            'audio_path': str(audio_path),
                            'success': True
                        }
            else:
                print(f"自定义TTS API请求失败，状态码: {response.status_code}")
                return {"error": f"API请求失败，状态码: {response.status_code}"}
                
        except requests.exceptions.Timeout:
            print(f"自定义TTS API请求超时")
            return {"error": "请求超时，请检查网络连接或稍后重试"}
        except requests.exceptions.ConnectionError:
            print(f"自定义TTS API连接错误")
            return {"error": "网络连接错误，请检查网络设置"}
        except requests.exceptions.RequestException as e:
            print(f"自定义TTS API请求异常: {e}")
            return {"error": f"请求异常: {str(e)}"}
        except Exception as e:
            print(f"自定义TTS API调用异常: {e}")
            return {"error": f"调用异常: {str(e)}"}
