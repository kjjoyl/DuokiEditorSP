from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PyQt6.QtCore import QUrl, QObject, pyqtSignal, QThread
from .tts_cache import TTSCache
import re
from queue import Queue

class AudioFetcher(QThread):
    """音频获取线程"""
    audio_ready = pyqtSignal(str)  # 音频准备好的信号
    all_fetched = pyqtSignal()     # 所有音频获取完成的信号
    error_occurred = pyqtSignal(str)  # 错误发生信号
    
    def __init__(self, cache, api_key):
        super().__init__()
        self.cache = cache
        self.api_key = api_key
        self.text_queue = Queue()
        self.running = True
    
    def add_text(self, text):
        """添加文本到队列"""
        self.text_queue.put(text)
    
    def run(self):
        while self.running:
            if self.text_queue.empty():
                # 队列为空但还在运行，等待新任务
                self.msleep(100)
                continue
                
            prefixed_text = self.text_queue.get()
            
            # 分离speaker前缀和实际文本
            parts = prefixed_text.split('_', 1)
            if len(parts) == 2:
                speaker, text = parts
            else:
                # 如果没有前缀，使用默认值
                speaker = "default"
                text = prefixed_text
            
            # 使用带前缀的文本查询缓存
            audio_path = self.cache.get_audio_path(prefixed_text)
            if audio_path is None:
                try:
                    print(f"从API获取音频: {text[:20]}... (speaker: {speaker})")
                    # 使用通用的TTS API调用方法
                    result = self.cache.call_tts_api(text, speaker=speaker)
                    
                    # 检查是否有错误
                    if 'error' in result:
                        error_msg = result['error']
                        print(f"TTS API返回错误: {error_msg}")
                        self.error_occurred.emit(f"TTS服务错误: {error_msg}")
                        continue
                    
                    # 处理不同引擎的返回结果
                    audio_url = None
                    audio_path = None
                    
                    if 'data' in result and 'audio' in result['data']:
                        # Minimax引擎返回格式 - 返回URL
                        audio_url = result['data']['audio']
                        # 使用带前缀的文本保存音频，确保缓存区分不同speaker
                        audio_path = self.cache.download_audio(audio_url, prefixed_text)
                    elif 'audio_path' in result:
                        # 火山引擎返回格式 - 已经解码并保存为文件
                        audio_path = result['audio_path']
                    elif 'data' in result and 'audio_url' in result['data']:
                        # 兼容其他可能返回audio_url的引擎
                        audio_url = result['data']['audio_url']
                        # 使用带前缀的文本保存音频，确保缓存区分不同speaker
                        audio_path = self.cache.download_audio(audio_url, prefixed_text)
                    
                    if audio_path is None:
                        print(f"获取音频失败")
                        self.error_occurred.emit("音频下载失败，请检查网络连接")
                        continue
                except Exception as e:
                    print(f"TTS API调用异常: {e}")
                    self.error_occurred.emit(f"TTS服务异常: {str(e)}")
                    continue
            
            # 发送音频准备好的信号
            self.audio_ready.emit(str(audio_path))
            
            # 标记任务完成
            self.text_queue.task_done()
            
            # 检查是否所有任务都完成了
            if self.text_queue.empty():
                self.all_fetched.emit()
    
    def stop(self):
        """停止线程"""
        self.running = False
        self.wait()

class TTSPlayer(QObject):
    play_finished = pyqtSignal()  # 播放完成信号
    error_occurred = pyqtSignal(str)  # 错误发生信号
    
    def __init__(self):
        super().__init__()
        self.api_key_minimax = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJHcm91cE5hbWUiOiLljJfkuqzlpYfngrnngbXmmbrnp5HmioDmnInpmZDlhazlj7giLCJVc2VyTmFtZSI6InBhbHUiLCJBY2NvdW50IjoicGFsdUAxODM3NDc0ODM0OTE3OTAwNjQ3IiwiU3ViamVjdElEIjoiMTk1NTUwMDk0MzgxMDI0MTEzNCIsIlBob25lIjoiIiwiR3JvdXBJRCI6IjE4Mzc0NzQ4MzQ5MTc5MDA2NDciLCJQYWdlTmFtZSI6IiIsIk1haWwiOiIiLCJDcmVhdGVUaW1lIjoiMjAyNS0wOS0xNyAxNDoyNToyNiIsIlRva2VuVHlwZSI6MSwiaXNzIjoibWluaW1heCJ9.b8_JgAgf8j0Ha9uWu1WaaWD9QgqPU6iK8plV2LDRoTeXMzTv1RFeojd49AgWBIv4YjvvzIvsuF-jEYHAPkL0gx4KzwgydcfHsYRRsIq48KJXgmk1Xaop9NQrqLr_N6uOFVTJ0e_XpUffsOKYUxyxrgBBPZ33hj97Ni2JDPx4NcjnJCCdx5fK3YFxJeSfrQJCHz5OIV7OS3n0ul-EJt15Vjh_9n1LnItUADvXTna7q1gUU0F9DEU63-VzPOrCujJ5aV-zAjBz176vaeekPpD55RDfrJkr01HrQlL7wk2VMOvmwtJaZdbD9c22pVMyBsJkBocYWKNBE-0j1rG1yQ-ROg"
        self.cache = TTSCache()
        
        # 创建播放器
        self.player = QMediaPlayer()
        
        # 设置日志级别，禁止输出详细信息
        from PyQt6.QtCore import QLoggingCategory
        QLoggingCategory.setFilterRules("*.debug=false\n*.info=false")
        
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # 创建音频获取线程
        self.fetcher = AudioFetcher(self.cache, self.api_key_minimax)
        self.fetcher.audio_ready.connect(self._on_audio_ready)
        self.fetcher.all_fetched.connect(self._on_all_fetched)
        self.fetcher.error_occurred.connect(self._on_error_occurred)
        self.fetcher.start()
        
        # 音频队列和状态控制
        self.audio_queue = Queue()
        self.is_playing = False
        self.all_segments_added = False
        self.active = True  # 全局活动状态标志
        self.row_finished_callback = None  # 行播放完成回调
        
        # 连接播放完成信号 - 只连接一次
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        
        # 监听音频设备变更
        self.media_devices = QMediaDevices()
        self.media_devices.audioOutputsChanged.connect(self._on_audio_devices_changed)
    
    def split_text_by_punctuation(self, text):
        """按标点符号分割文本"""
        pattern = r'[,\.!\?，。！？~…`]+'
        segments = re.split(pattern, text)
        return [seg.strip() for seg in segments if seg.strip()]
    
    def play_text(self, text, speaker="default"):
        """分段播放文本，增加speaker参数"""
        # 停止当前可能正在进行的播放
        self.stop()
        
        # 重置状态
        self.audio_queue = Queue()
        self.is_playing = False
        self.all_segments_added = False
        self.active = True  # 重置活动状态
        self.current_speaker = speaker  # 设置当前speaker
        
        # 检查是否使用自定义TTS
        from ..utils.config_manager import ConfigManager
        config_manager = ConfigManager()
        custom_tts = config_manager.get_custom_tts()
        
        if custom_tts:
            # 如果使用自定义TTS，不分割文本，传递完整句子
            segments = [text]
        else:
            # 分割文本
            segments = self.split_text_by_punctuation(text)
            
        if not segments:
            self.play_finished.emit()
            return
        
        # 添加所有文本片段到获取队列，并附加speaker信息
        for segment in segments:
            # 创建带有speaker前缀的文本
            prefixed_text = f"{speaker}_{segment}"
            self.fetcher.add_text(prefixed_text)
        
        # 标记所有片段已添加
        self.all_segments_added = True
    
    def _get_audio_duration(self, audio_path):
        """获取音频文件的时长（毫秒）"""
        try:
            # 创建临时播放器来获取音频时长
            temp_player = QMediaPlayer()
            temp_player.setSource(QUrl.fromLocalFile(audio_path))
            
            # 等待媒体加载完成
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import QEventLoop, QTimer
            
            loop = QEventLoop()
            duration = 0
            
            def on_duration_changed(d):
                nonlocal duration
                duration = d
                loop.quit()
            
            def on_timeout():
                loop.quit()
            
            temp_player.durationChanged.connect(on_duration_changed)
            
            # 设置5秒超时
            timer = QTimer()
            timer.timeout.connect(on_timeout)
            timer.start(5000)
            
            loop.exec()
            timer.stop()
            
            # 清理临时播放器
            temp_player.setSource(QUrl())
            temp_player = None
            
            return duration
        except Exception as e:
            print(f"获取音频时长失败: {e}")
            return 0

    def _on_audio_ready(self, audio_path):
        """音频准备好的回调"""
        # 检查是否处于活动状态，如果不是则忽略
        if not self.active:
            return
            
        # 获取音频时长并累加到总时长
        duration = self._get_audio_duration(audio_path)
        if not hasattr(self, 'total_audio_duration'):
            self.total_audio_duration = 0
        self.total_audio_duration += duration
        print(f"音频片段时长: {duration}ms, 累计总时长: {self.total_audio_duration}ms")
            
        # 将音频路径添加到播放队列
        self.audio_queue.put(audio_path)
        
        # 增加已获取片段计数
        if hasattr(self, 'segments_fetched'):
            self.segments_fetched += 1
            print(f"音频片段已获取: {self.segments_fetched}/{self.segments_count}")
        
        # 如果当前没有播放，开始播放
        if not self.is_playing and self.active:
            self._play_next()
    
    def _on_error_occurred(self, error_message):
        """处理错误信号"""
        print(f"TTS播放器收到错误: {error_message}")
        # 转发错误信号给上层
        self.error_occurred.emit(error_message)
    
    def _on_all_fetched(self):
        """所有音频获取完成的回调"""
        # 可以在这里添加日志或其他处理
        pass
    
    def _on_media_status_changed(self, status):
        """媒体状态改变的回调"""
        # 检查是否处于活动状态，如果不是则不继续播放
        if not self.active:
            return
            
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # 当前音频播放完成，播放下一个
            self.is_playing = False
            self._play_next()
    
    def _play_next(self):
        """播放下一个音频"""
        # 检查是否处于活动状态，如果不是则不继续播放
        if not self.active:
            return
            
        if self.audio_queue.empty():
            # 检查是否所有片段都已获取并播放完成
            if self.all_segments_added and hasattr(self, 'segments_count') and hasattr(self, 'segments_played'):
                if self.segments_played >= self.segments_count:
                    # 所有音频都播放完成
                    self.is_playing = False
                    print(f"行内所有片段播放完成 ({self.segments_played}/{self.segments_count})，触发行完成回调")
                    
                    # 停止心跳检测定时器
                    if hasattr(self, 'check_timer') and self.check_timer.isActive():
                        self.check_timer.stop()
                        print("停止心跳检测定时器")
                    
                    # 触发行播放完成回调
                    if self.row_finished_callback:
                        callback = self.row_finished_callback
                        self.row_finished_callback = None  # 清空回调，防止重复调用
                        callback()  # 调用回调
                    else:
                        # 如果没有行回调，则触发通用播放完成信号
                        self.play_finished.emit()
                else:
                    # 还有片段未获取，等待
                    print(f"等待更多音频片段: 已播放 {self.segments_played}/{self.segments_count}")
            return
        
        # 获取下一个音频路径并播放
        audio_path = self.audio_queue.get()
        print(f"播放下一个音频片段: {audio_path}")
        self.is_playing = True
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        self.player.play()
        
        # 增加已播放片段计数
        if hasattr(self, 'segments_played'):
            self.segments_played += 1
    
    def play_text_queue(self, text_speaker_pairs):
        """
        播放文本队列，每个文本使用对应的speaker
        
        Args:
            text_speaker_pairs: 包含(text, speaker)元组的列表
        """
        # 停止当前可能正在进行的播放
        self.stop()
        
        # 保存文本队列
        self.text_queue = text_speaker_pairs.copy()
        self.current_text_index = 0
        
        # 开始播放第一个文本
        if self.text_queue:
            text, speaker = self.text_queue[0]
            self.play_text(text, speaker)
            
            # 连接播放完成信号到队列处理函数
            try:
                self.play_finished.disconnect(self._on_queue_item_finished)
            except:
                pass
            self.play_finished.connect(self._on_queue_item_finished)
    
    def _on_queue_item_finished(self):
        """队列中的一项播放完成后的处理"""
        self.current_text_index += 1
        
        # 检查是否还有下一项
        if self.current_text_index < len(self.text_queue):
            # 播放下一项
            text, speaker = self.text_queue[self.current_text_index]
            self.play_text(text, speaker)
        else:
            # 所有项目播放完成
            try:
                self.play_finished.disconnect(self._on_queue_item_finished)
            except:
                pass
            # 发出播放完成信号
            self.play_finished.emit()
    
    def play_text_by_row(self, text, speaker="default", row_finished_callback=None):
        """
        按行播放文本，每行使用对应的speaker
        
        Args:
            text: 当前行的文本内容
            speaker: 当前行的speaker
            row_finished_callback: 行播放完成后的回调函数
        """
        # 停止当前可能正在进行的播放
        self.stop()
        
        # 重置状态
        self.audio_queue = Queue()
        self.is_playing = False
        self.all_segments_added = False
        self.active = True  # 重置活动状态
        self.current_speaker = speaker  # 设置当前speaker
        self.row_finished_callback = row_finished_callback  # 保存行播放完成回调
        self.segments_count = 0  # 添加片段计数
        self.segments_fetched = 0  # 添加已获取片段计数
        self.segments_played = 0  # 添加已播放片段计数
        self.total_audio_duration = 0  # 重置总音频时长
        
        # 初始化开始时间
        import time
        self._start_time = time.time()
        self._check_count = 0  # 重置检查计数
        
        # 连接播放完成信号到行完成回调
        try:
            self.play_finished.disconnect()
        except:
            pass
        
        self.play_finished.connect(self._on_row_finished)
        
        # 检查是否使用自定义TTS
        from ..utils.config_manager import ConfigManager
        config_manager = ConfigManager()
        custom_tts = config_manager.get_custom_tts()
        
        if custom_tts:
            # 如果使用自定义TTS，不分割文本，传递完整句子
            segments = [text]
        else:
            # 分割文本
            segments = self.split_text_by_punctuation(text)
        if not segments:
            print(f"行文本为空或无法分割: '{text}'")
            if self.row_finished_callback:
                self.row_finished_callback()
            return
        
        self.segments_count = len(segments)
        print(f"开始播放行: '{text}', 分割为 {self.segments_count} 个片段")
        
        # 添加所有文本片段到获取队列，并附加speaker信息
        for segment in segments:
            # 创建带有speaker前缀的文本
            prefixed_text = f"{speaker}_{segment}"
            self.fetcher.add_text(prefixed_text)
        
        # 标记所有片段已添加
        self.all_segments_added = True
        
        # 设置超时检查，确保所有片段都被处理
        from PyQt6.QtCore import QTimer
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self._check_progress)
        self.check_timer.start(10000)  # 10秒检查一次，给TTS更多时间
        
    def _check_progress(self):
        """检查播放进度，防止卡住"""
        if not self.active:
            if hasattr(self, 'check_timer') and self.check_timer.isActive():
                self.check_timer.stop()
                print("播放器非活动状态，停止心跳检测定时器")
            return
        
        print(f"检查播放进度: 已获取 {self.segments_fetched}/{self.segments_count}, 已播放 {self.segments_played}/{self.segments_count}")
            
        # 如果已经获取了所有片段但还没有播放完，继续等待
        if hasattr(self, 'segments_fetched') and hasattr(self, 'segments_count'):
            if self.segments_fetched >= self.segments_count and self.segments_played < self.segments_count:
                # 所有片段已获取但未播放完，基于音频时长判断是否需要继续等待
                if hasattr(self, 'total_audio_duration') and self.total_audio_duration > 0:
                    # 计算预期播放时间（音频时长 + 30秒缓冲时间）
                    expected_duration_seconds = (self.total_audio_duration / 1000) + 30
                    
                    # 计算已经等待的时间
                    if not hasattr(self, '_start_time'):
                        import time
                        self._start_time = time.time()
                    
                    import time
                    elapsed_time = time.time() - self._start_time
                    
                    print(f"音频总时长: {self.total_audio_duration/1000:.1f}秒, 已等待: {elapsed_time:.1f}秒, 预期时长: {expected_duration_seconds:.1f}秒")
                    
                    # 如果还没有超过预期时间，继续等待
                    if elapsed_time < expected_duration_seconds:
                        return
                else:
                    # 没有音频时长信息，继续等待
                    return
                
        # 如果长时间没有进展，可能是卡住了
        if self.row_finished_callback and (
            # 情况1: 队列为空且所有片段已添加
            (self.audio_queue.empty() and self.all_segments_added) or
            # 情况2: 基于音频时长的超时检查
            (hasattr(self, 'total_audio_duration') and hasattr(self, '_start_time'))
        ):
            if not hasattr(self, '_check_count'):
                self._check_count = 1
            else:
                self._check_count += 1
                
            # 计算动态超时次数（基于音频时长）
            max_check_count = 3  # 默认3次检查
            if hasattr(self, 'total_audio_duration') and self.total_audio_duration > 0:
                # 每30秒音频允许3次检查，最少3次，最多10次
                audio_duration_seconds = self.total_audio_duration / 1000
                max_check_count = max(3, min(10, int((audio_duration_seconds / 30) * 3) + 3))
            
            print(f"检查次数: {self._check_count}/{max_check_count}")
                
            # 达到最大检查次数时强制触发回调
            if self._check_count >= max_check_count:
                print(f"检测到可能卡住，强制触发行完成回调 (已获取 {self.segments_fetched}/{self.segments_count}, 已播放 {self.segments_played}/{self.segments_count})")
                callback = self.row_finished_callback
                self.row_finished_callback = None
                self.check_timer.stop()
                callback()
    
    def _on_row_finished(self):
        """行播放完成后的处理"""
        # 调用行播放完成回调
        if self.row_finished_callback:
            self.row_finished_callback()
    
    def stop(self):
        """停止播放"""
        # 设置为非活动状态，防止新的音频回调
        self.active = False
        
        # 停止心跳检测定时器
        if hasattr(self, 'check_timer'):
            self.check_timer.stop()
            print("停止心跳检测定时器")
        
        # 停止当前播放并等待状态稳定
        if self.player:
            self.player.stop()
            # 等待播放器状态稳定
            from PyQt6.QtWidgets import QApplication
            while self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
                QApplication.processEvents()
        
        # 释放媒体资源，避免文件锁定
        if self.player:
            self.player.setSource(QUrl())
            # 再次确保状态清理
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
        
        # 清空音频队列
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except:
                break
        
        # 重置所有状态变量
        self.is_playing = False
        self.all_segments_added = False
        if hasattr(self, 'segments_played'):
            self.segments_played = 0
        if hasattr(self, 'segments_count'):
            self.segments_count = 0
        self.row_finished_callback = None
        
        # 停止并重新创建fetcher线程
        if hasattr(self, 'fetcher') and self.fetcher:
            self.fetcher.stop()
            self.fetcher.wait()  # 等待线程结束
            # 重新创建fetcher
            self.fetcher = AudioFetcher(self.cache, self.api_key_minimax)
            self.fetcher.audio_ready.connect(self._on_audio_ready)
            self.fetcher.all_fetched.connect(self._on_all_fetched)
            self.fetcher.error_occurred.connect(self._on_error_occurred)
            self.fetcher.start()
            
    def _on_audio_devices_changed(self):
        """音频设备变更时的处理"""
        print("检测到音频设备变更")
        # 获取当前可用的音频输出设备
        available_devices = QMediaDevices.audioOutputs()
        
        # 如果没有可用设备，打印警告
        if not available_devices:
            print("警告: 没有可用的音频输出设备")
            return
            
        # 如果当前正在播放，记录当前位置并重新设置音频输出
        was_playing = False
        position = 0
        if self.player and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            was_playing = True
            position = self.player.position()
            self.player.pause()
            
        # 重新设置音频输出设备
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # 如果之前在播放，恢复播放
        if was_playing:
            self.player.setPosition(position)
            self.player.play()