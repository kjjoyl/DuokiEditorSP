from PyQt6.QtWidgets import (
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout, 
    QSplitter,
    QTreeView, 
    QTableView, 
    QHeaderView, 
    QLabel,
    QComboBox,
    QDialog,
    QMessageBox,
    QMenu,
    QApplication,
    QLineEdit,
    QPushButton,
    QListWidgetItem,
    QSlider,
    QMenuBar,
    QScrollArea,
    QFileDialog
)
# 导入自定义抽屉式控件
from duoki_editor.modules.online_data.accordion_widget import AccordionWidget, FileListWidget
from PyQt6.QtCore import Qt, QDir, QModelIndex, QAbstractTableModel, QUrl, QTimer
from PyQt6.QtGui import QColor, QBrush, QFont, QStandardItemModel, QStandardItem, QPixmap, QDesktopServices, QMovie
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from duoki_editor.ui.toast import ToastManager
from duoki_editor.utils.config_manager import ConfigManager
import os
import pandas as pd
import re

class ExcelTableModel(QAbstractTableModel):
    """Excel数据表格模型"""
    
    def __init__(self, data=None):
        super().__init__()
        self._data = data
        self._headers = []
        self._data_types = []
        self._image_columns = set()  # 存储包含图片的列索引
        self._audio_columns = set()  # 存储包含音频的列索引
        self._highlighted_cells = set()  # 存储需要高亮的单元格位置 {(row, col), ...}
        
    def load_data(self, df):
        """加载数据"""
        if df is not None and len(df) >= 2:
            self.beginResetModel()
            # 提取表头（第1行）
            self._headers = df.columns.tolist()
            
            # 提取数据类型（第2行）
            self._data_types = [str(df.iloc[0, i]) for i in range(len(df.columns))]
            
            # 提取实际数据（第3行及以后）
            if len(df) > 1:
                self._data = df.iloc[1:].reset_index(drop=True)
            else:
                self._data = pd.DataFrame(columns=self._headers)
            
            # 检测包含图片文件名的列
            self._detect_image_columns()
            
            # 检测包含音频文件名的列
            self._detect_audio_columns()
                
            self.endResetModel()
            
            # 返回数据类型，用于类型表头
            return self._data_types
        return []
    
    def _detect_image_columns(self):
        """检测包含图片文件名的列"""
        self._image_columns.clear()
        if self._data is None or len(self._data) == 0:
            return
            
        # 图片文件扩展名模式
        image_pattern = re.compile(r'\.(jpg|jpeg|png|gif|bmp|webp)$', re.IGNORECASE)
        
        for col_idx in range(len(self._data.columns)):
            column_name = self._headers[col_idx] if col_idx < len(self._headers) else ""
            
            # 首先检查列名是否包含图片相关关键词
            image_keywords = ['image', 'img', 'pic', 'picture', 'photo', '图片', '图像']
            is_image_column_by_name = any(keyword.lower() in column_name.lower() for keyword in image_keywords)
            
            if is_image_column_by_name:
                self._image_columns.add(col_idx)
                print(f"通过列名检测到图片列: {column_name} (列索引: {col_idx})")
                continue
            
            # 检查该列的数据内容，扩大检测范围到前50行或所有行
            sample_size = min(50, len(self._data))  # 检查前50行或所有行
            image_count = 0
            
            for row_idx in range(sample_size):
                value = self._data.iloc[row_idx, col_idx]
                if pd.notna(value):
                    value_str = str(value).strip()
                    if value_str and image_pattern.search(value_str):
                        image_count += 1
            
            # 降低阈值：如果该列有超过10%的数据包含图片文件名，则标记为图片列
            if sample_size > 0 and image_count / sample_size >= 0.1:
                self._image_columns.add(col_idx)
                print(f"通过内容检测到图片列: {column_name} (列索引: {col_idx}, 图片文件比例: {image_count}/{sample_size})")
    
    def _detect_audio_columns(self):
        """检测包含音频文件名的列"""
        self._audio_columns.clear()
        if self._data is None or len(self._data) == 0:
            return
            
        # 音频文件扩展名模式
        audio_pattern = re.compile(r'\.(mp3|wav|ogg|m4a)$', re.IGNORECASE)
        
        for col_idx in range(len(self._data.columns)):
            column_name = self._headers[col_idx] if col_idx < len(self._headers) else ""
            
            # 首先检查列名是否包含音频相关关键词
            '''
            audio_keywords = ['audio', 'sound', 'music', 'voice', '音频', '声音', '音乐', '语音']
            is_audio_column_by_name = any(keyword.lower() in column_name.lower() for keyword in audio_keywords)
            
            if is_audio_column_by_name:
                self._audio_columns.add(col_idx)
                print(f"通过列名检测到音频列: {column_name} (列索引: {col_idx})")
                continue
            '''
            
            # 检查该列的数据内容，扩大检测范围到前50行或所有行
            sample_size = min(50, len(self._data))  # 检查前50行或所有行
            audio_count = 0
            
            for row_idx in range(sample_size):
                value = self._data.iloc[row_idx, col_idx]
                if pd.notna(value):
                    value_str = str(value).strip()
                    if value_str and audio_pattern.search(value_str):
                        audio_count += 1
            
            # 降低阈值：如果该列有超过10%的数据包含音频文件名，则标记为音频列
            if sample_size > 0 and audio_count / sample_size >= 0.1:
                self._audio_columns.add(col_idx)
                print(f"通过内容检测到音频列: {column_name} (列索引: {col_idx}, 音频文件比例: {audio_count}/{sample_size})")
    
    def is_image_column(self, column):
        """检查指定列是否为图片列"""
        return column in self._image_columns
        
    def is_audio_column(self, column):
        """检查指定列是否为音频列"""
        return column in self._audio_columns
    
    def set_highlighted_cells(self, cells):
        """设置需要高亮的单元格"""
        self._highlighted_cells = set(cells)
        # 通知视图更新
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount()-1, self.columnCount()-1))
    
    def clear_highlights(self):
        """清除所有高亮"""
        self._highlighted_cells.clear()
        # 通知视图更新
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount()-1, self.columnCount()-1))
    
    def rowCount(self, parent=QModelIndex()):
        if self._data is None:
            return 0
        return len(self._data)
    
    def columnCount(self, parent=QModelIndex()):
        if self._data is None or len(self._data) == 0:
            return 0
        return len(self._data.columns)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._data is None:
            return None
            
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]
            # 处理空值，不显示"nan"
            if pd.isna(value) or str(value).lower() in ['nan', 'none', '']:
                return ""
            return str(value)
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            # 如果是搜索高亮的单元格，设置橙色字体
            if (index.row(), index.column()) in self._highlighted_cells:
                return QBrush(QColor(255, 140, 0))  # 橙色字体
            # 如果是图片列，设置为饱和度较低的蓝色超链接样式
            elif self.is_image_column(index.column()):
                value = self._data.iloc[index.row(), index.column()]
                if pd.notna(value) and str(value).strip():
                    return QBrush(QColor(70, 130, 180))  # 钢蓝色，饱和度较低
            # 如果是音频列，设置为蓝色超链接样式（与图片链接相同）
            elif self.is_audio_column(index.column()):
                value = self._data.iloc[index.row(), index.column()]
                if pd.notna(value) and str(value).strip():
                    return QBrush(QColor(70, 130, 180))  # 钢蓝色，与图片链接相同
            return None
        
        elif role == Qt.ItemDataRole.BackgroundRole:
            # 不设置特殊背景色，让系统处理选中状态
            return None
        
        elif role == Qt.ItemDataRole.FontRole:
            # 如果是图片列或音频列，设置为下划线字体
            if self.is_image_column(index.column()) or self.is_audio_column(index.column()):
                value = self._data.iloc[index.row(), index.column()]
                if pd.notna(value) and str(value).strip():
                    font = QFont()
                    font.setUnderline(True)
                    return font
            return None
        

                
        return None
    
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal and section < len(self._headers):
                return self._headers[section]
            elif orientation == Qt.Orientation.Vertical:
                # 行号从1开始
                return str(section + 1)
        return None

class AudioPlayerDialog(QDialog):
    """音频播放器弹窗"""
    
    def __init__(self, audio_filename, auth_manager=None, parent=None):
        # 设置全局异常处理
        import sys
        import traceback
        self._old_excepthook = sys.excepthook
        sys.excepthook = self._global_exception_handler
        super().__init__(parent)
        self.audio_filename = str(audio_filename)
        self.auth_manager = auth_manager
        self.network_manager = QNetworkAccessManager()
        
        # 配置网络管理器以忽略SSL错误
        from PyQt6.QtNetwork import QSslConfiguration, QSslSocket
        ssl_config = QSslConfiguration.defaultConfiguration()
        ssl_config.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyNone)
        QSslConfiguration.setDefaultConfiguration(ssl_config)
        
        # 连接SSL错误信号以忽略SSL错误
        self.network_manager.sslErrors.connect(lambda reply, errors: reply.ignoreSslErrors())
        
        # 创建缓存目录
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "cache", "sound")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 初始化媒体播放器
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # 连接播放器信号
        self.player.errorOccurred.connect(self.handle_player_error)
        self.player.playbackStateChanged.connect(self.update_play_button)
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        
        self.init_ui()
        self.download_audio()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("音频播放器")
        self.setModal(True)
        self.resize(400, 150)
        
        # 创建布局
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 文件名标签
        self.file_label = QLabel(f"文件: {self.audio_filename}")
        layout.addWidget(self.file_label)
        
        # 状态标签
        self.status_label = QLabel("正在下载音频...")
        layout.addWidget(self.status_label)
        
        # 进度条
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setEnabled(False)
        self.progress_slider.sliderMoved.connect(self.set_position)
        layout.addWidget(self.progress_slider)
        
        # 时间标签
        time_layout = QHBoxLayout()
        self.current_time_label = QLabel("00:00")
        self.duration_label = QLabel("00:00")
        time_layout.addWidget(self.current_time_label)
        time_layout.addStretch()
        time_layout.addWidget(self.duration_label)
        layout.addLayout(time_layout)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        self.play_button = QPushButton("播放")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_playback)
        control_layout.addWidget(self.play_button)
        
        layout.addLayout(control_layout)
        self.setLayout(layout)
    
    def download_audio(self):
        """下载音频文件"""
        cfg = ConfigManager()
        server_url = cfg.get_server_url()
        base_url = server_url + "client_resources/getFile?path=client/restaurant/sound/"
        audio_url = base_url + self.audio_filename
        
        # 检查缓存
        safe_filename = os.path.basename(self.audio_filename.replace('/', os.path.sep))
        cache_file_path = os.path.join(self.cache_dir, safe_filename)
        if os.path.exists(cache_file_path):
            print(f"✅ 使用缓存的音频文件: {cache_file_path}")
            self.load_audio_from_cache(cache_file_path)
            return
        
        # 下载音频
        try:
            request = QNetworkRequest(QUrl(audio_url))
            
            # 添加Cookie到请求头
            if self.auth_manager:
                header_value = self.auth_manager.get_cookie_header()
                if header_value:
                    request.setRawHeader(b'Cookie', header_value.encode())
            
            reply = self.network_manager.get(request)
            reply.finished.connect(lambda: self.on_audio_downloaded(reply))
            self.status_label.setText("正在下载音频...")
        except Exception as e:
            print(f"❌ 音频下载异常: {e}")
            self.status_label.setText("下载失败")
            toast_manager = ToastManager(self.parent())
            toast_manager.show_error("音频下载失败")
    
    def on_audio_downloaded(self, reply):
        """音频下载完成"""
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                
                # 保存到缓存
                # 规范化文件名，替换路径分隔符
                safe_filename = os.path.basename(self.audio_filename.replace('/', os.path.sep))
                cache_file_path = os.path.join(self.cache_dir, safe_filename)
                with open(cache_file_path, 'wb') as f:
                    f.write(data.data())
                
                print(f"✅ 音频下载成功: {cache_file_path}")
                self.load_audio_from_cache(cache_file_path)
            else:
                error_string = reply.errorString()
                print(f"❌ 音频下载失败: {error_string}")
                self.status_label.setText("下载失败")
                toast_manager = ToastManager(self.parent())
                toast_manager.show_error("音频下载失败")
        except Exception as e:
            print(f"❌ 音频处理异常: {e}")
            self.status_label.setText("处理失败")
            toast_manager = ToastManager(self.parent())
            toast_manager.show_error("音频下载失败")
        finally:
            reply.deleteLater()
    
    def load_audio_from_cache(self, file_path):
        """从缓存加载音频"""
        try:
            self.player.setSource(QUrl.fromLocalFile(file_path))
            self.status_label.setText("准备就绪")
            self.play_button.setEnabled(True)
            self.progress_slider.setEnabled(True)
            # 自动播放
            QTimer.singleShot(500, self.player.play)
        except Exception as e:
            print(f"❌ 加载音频失败: {e}")
            self.status_label.setText("加载失败")
            toast_manager = ToastManager(self.parent())
            toast_manager.show_error("音频加载失败")
    
    def toggle_playback(self):
        """切换播放/暂停状态"""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    
    def update_play_button(self, state):
        """更新播放按钮状态"""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setText("暂停")
        else:
            self.play_button.setText("播放")
    
    def update_position(self, position):
        """更新进度条位置"""
        self.progress_slider.setValue(position)
        # 更新时间标签
        
    def _global_exception_handler(self, exc_type, exc_value, exc_traceback):
        """全局异常处理函数"""
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"音频播放器全局异常: {error_msg}")
        # 尝试安全关闭
        try:
            self.close()
        except:
            pass
        # 调用原始的异常处理器
        if self._old_excepthook:
            self._old_excepthook(exc_type, exc_value, exc_traceback)
    
    def closeEvent(self, event):
        """窗口关闭事件，确保正确释放资源"""
        try:
            # 恢复原始的异常处理器
            import sys
            if hasattr(self, '_old_excepthook') and self._old_excepthook:
                sys.excepthook = self._old_excepthook
            
            # 停止播放
            self.player.stop()
            # 释放资源
            self.player.setSource(QUrl())
            
            # 安全断开所有信号连接
            try:
                self.player.errorOccurred.disconnect()
            except:
                pass
                
            try:
                self.player.playbackStateChanged.disconnect()
            except:
                pass
                
            try:
                self.player.positionChanged.disconnect()
            except:
                pass
                
            try:
                self.player.durationChanged.disconnect()
            except:
                pass
            
            # 释放网络管理器资源
            if hasattr(self, 'network_manager'):
                self.network_manager.deleteLater()
            
            # 释放音频输出
            if hasattr(self, 'audio_output'):
                self.audio_output.deleteLater()
            
            # 释放播放器
            self.player.deleteLater()
            
        except Exception as e:
            print(f"关闭音频播放器时发生错误: {e}")
        
        # 接受关闭事件
        event.accept()
        seconds = position // 1000
        minutes = seconds // 60
        seconds %= 60
        self.current_time_label.setText(f"{minutes:02d}:{seconds:02d}")
    
    def update_duration(self, duration):
        """更新总时长"""
        self.progress_slider.setRange(0, duration)
        # 更新时间标签
        seconds = duration // 1000
        minutes = seconds // 60
        seconds %= 60
        self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")
    
    def set_position(self, position):
        """设置播放位置"""
        self.player.setPosition(position)
    
    def handle_player_error(self, error, error_string):
        """处理播放器错误"""
        print(f"❌ 播放器错误: {error_string}")
        self.status_label.setText(f"播放错误: {error_string}")
    
    def closeEvent(self, event):
        """关闭事件"""
        self.player.stop()
        super().closeEvent(event)


class ImagePreviewDialog(QDialog):
    """图片预览弹窗"""
    
    def __init__(self, image_filename, auth_manager=None, parent=None, toast_manager=None, config_manager=None):
        super().__init__(parent)
        # 处理图片文件名中的{level}占位符，替换为1
        self.image_filename = str(image_filename).replace('{level}', '1')
        self.auth_manager = auth_manager
        self.toast_manager = toast_manager
        self.config_manager = config_manager
        self.network_manager = QNetworkAccessManager()
        
        # 配置网络管理器以忽略SSL错误
        from PyQt6.QtNetwork import QSslConfiguration, QSslSocket
        ssl_config = QSslConfiguration.defaultConfiguration()
        ssl_config.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyNone)
        QSslConfiguration.setDefaultConfiguration(ssl_config)
        
        # 连接SSL错误信号以忽略SSL错误
        self.network_manager.sslErrors.connect(lambda reply, errors: reply.ignoreSslErrors())
        
        self.current_url = None
        self.current_attempt = 0  # 当前尝试次数
        self.movie = None  # 用于GIF动画
        self.original_pixmap = None  # 保存原始图片
        self.current_scale = 1.0  # 当前缩放比例
        self.init_ui()
        self.try_load_image()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle(f"图片预览 - {self.image_filename}")
        self.setModal(True)
        self.resize(600, 400)
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 创建主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 添加菜单栏到布局
        main_layout.addWidget(self.menu_bar)
        
        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: black; border: none; }")
        
        # 创建图片标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("QLabel { background-color: black; border: none; }")
        self.image_label.setText("正在加载图片...")
        
        self.scroll_area.setWidget(self.image_label)
        main_layout.addWidget(self.scroll_area)
        
        self.setLayout(main_layout)
    
    def try_load_image(self):
        """尝试加载图片，先尝试common/image路径"""
        cfg = ConfigManager()
        server_url = cfg.get_server_url()
        base_url = server_url + "client_resources/getFile?path=client/common/image/"
        self.current_url = base_url + str(self.image_filename)
        self.current_attempt = 1
        self.load_image(self.current_url)
    
    def load_image(self, image_url):
        """加载图片"""
        try:
            request = QNetworkRequest(QUrl(image_url))
            
            if self.auth_manager:
                header_value = self.auth_manager.get_cookie_header()
                if header_value:
                    request.setRawHeader(b'Cookie', header_value.encode())
                else:
                    print("⚠️ 警告: 没有可用的Cookie")
            else:
                print("⚠️ 警告: 没有认证管理器")
            
            reply = self.network_manager.get(request)
            reply.finished.connect(lambda: self.on_image_loaded(reply))
        except Exception as e:
            print(f"❌ 图片加载异常: {e}")
            self.try_next_path()
    
    def on_image_loaded(self, reply):
        """图片加载完成"""
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                
                # 检查是否是GIF动画
                if self.is_gif_data(data):
                    self.load_gif_animation(data)
                else:
                    # 静态图片处理
                    pixmap = QPixmap()
                    if pixmap.loadFromData(data):
                        self.display_static_image(pixmap)
                    else:
                        print("❌ 图片数据解析失败")
                        self.try_next_path()
            else:
                # 加载失败，尝试下一个路径
                error_code = reply.error()
                error_string = reply.errorString()
                http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                self.try_next_path()
        except Exception as e:
            print(f"❌ 图片加载处理异常: {e}")
            self.try_next_path()
        finally:
            reply.deleteLater()
    
    def is_gif_data(self, data):
        """检查数据是否为GIF格式"""
        # GIF文件的魔数是 'GIF87a' 或 'GIF89a'
        return data.startsWith(b'GIF87a') or data.startsWith(b'GIF89a')
    
    def load_gif_animation(self, data):
        """加载GIF动画"""
        try:
            # 停止之前的动画
            if self.movie:
                self.movie.stop()
                self.movie = None
            
            # 创建临时文件来存储GIF数据
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.gif') as temp_file:
                temp_file.write(data.data())
                temp_file_path = temp_file.name
            
            # 创建QMovie对象
            self.movie = QMovie(temp_file_path)
            if self.movie.isValid():
                # 设置动画到标签
                self.image_label.setMovie(self.movie)
                
                # 获取第一帧来计算窗口大小和保存原始图片
                self.movie.jumpToFrame(0)
                first_frame = self.movie.currentPixmap()
                if not first_frame.isNull():
                    # 保存第一帧作为原始图片（用于另存为功能）
                    self.original_pixmap = first_frame
                    self.current_scale = 1.0
                    self.resize_window_for_image(first_frame)
                
                # 开始播放动画
                self.movie.start()
                print("✅ GIF动画加载成功")
            else:
                print("❌ GIF动画无效")
                self.try_next_path()
                
            # 清理临时文件
            import os
            try:
                os.unlink(temp_file_path)
            except:
                pass
                
        except Exception as e:
            print(f"❌ GIF动画加载失败: {e}")
            self.try_next_path()
    
    def display_static_image(self, pixmap):
        """显示静态图片"""
        # 停止任何正在播放的动画
        if self.movie:
            self.movie.stop()
            self.movie = None
            self.image_label.setMovie(None)
        
        # 保存原始图片
        self.original_pixmap = pixmap
        self.current_scale = 1.0
        
        # 设置图片
        self.image_label.setPixmap(pixmap)
        self.resize_window_for_image(pixmap)
        print("✅ 静态图片加载成功")
    
    def resize_window_for_image(self, pixmap):
        """根据图片大小调整窗口"""
        if pixmap.width() > 0 and pixmap.height() > 0:
            # 获取屏幕尺寸
            screen = QApplication.primaryScreen().geometry()
            max_width = int(screen.width() * 0.9)  # 屏幕宽度的90%
            max_height = int(screen.height() * 0.9)  # 屏幕高度的90%
            
            # 计算窗口大小（图片大小 + 菜单栏高度）
            menu_height = self.menu_bar.height() if hasattr(self, 'menu_bar') else 25
            
            if pixmap.width() > max_width or (pixmap.height() + menu_height) > max_height:
                # 需要缩放以适应屏幕
                available_height = max_height - menu_height
                scale_w = max_width / pixmap.width()
                scale_h = available_height / pixmap.height()
                scale = min(scale_w, scale_h)
                
                # 重要：更新当前缩放比例以反映实际显示的缩放
                self.current_scale = scale
                
                new_width = int(pixmap.width() * scale)
                new_height = int(pixmap.height() * scale)
            else:
                # 使用原始尺寸
                self.current_scale = 1.0
                new_width = pixmap.width()
                new_height = pixmap.height()
            
            # 设置窗口大小（图片大小 + 菜单栏高度）
            total_height = new_height + menu_height
            self.resize(new_width, total_height)
            
            # 设置图片标签的固定大小
            self.image_label.setFixedSize(new_width, new_height)
            
            # 如果是静态图片且需要缩放，则缩放显示
            if not self.movie and (new_width != pixmap.width() or new_height != pixmap.height()):
                scaled_pixmap = pixmap.scaled(
                    new_width, new_height,
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_label.setPixmap(scaled_pixmap)
            
            # 居中显示窗口
            self.move(
                (screen.width() - new_width) // 2,
                (screen.height() - total_height) // 2
            )
    
    def try_next_path(self):
        """尝试下一个路径"""
        self.current_attempt += 1
        
        if self.current_attempt == 2:
            # 尝试restaurant/image路径
            cfg = ConfigManager()
            server_url = cfg.get_server_url()
            base_url = server_url + "client_resources/getFile?path=client/restaurant/image/"
            self.current_url = base_url + str(self.image_filename)
            self.image_label.setText("尝试restaurant路径加载图片...")
            self.load_image(self.current_url)
        elif self.current_attempt == 3:
            # 尝试cosplay/image路径
            cfg = ConfigManager()
            server_url = cfg.get_server_url()
            base_url = server_url + "client_resources/getFile?path=client/cosplay/image/"
            self.current_url = base_url + str(self.image_filename)
            self.image_label.setText("尝试cosplay路径加载图片...")
            self.load_image(self.current_url)
        else:
            # 所有路径都失败了
            self.show_error("所有路径都无法加载图片")
    
    def show_error(self, error_message):
        """显示错误信息"""
        self.image_label.setText(f"图片加载失败\n\n已尝试路径:\n• client/common/image/\n• client/restaurant/image/\n• client/cosplay/image/\n\n错误信息: {error_message}")
    
    def create_menu_bar(self):
        """创建菜单栏"""
        self.menu_bar = QMenuBar(self)
        
        # 文件菜单
        file_menu = self.menu_bar.addMenu("文件")
        save_as_action = file_menu.addAction("另存为...")
        save_as_action.setShortcut("Ctrl+S")
        save_as_action.triggered.connect(self.save_as)
        
        # 视图菜单
        view_menu = self.menu_bar.addMenu("视图")
        
        zoom_in_action = view_menu.addAction("放大")
        zoom_in_action.setShortcut("+")
        zoom_in_action.triggered.connect(self.zoom_in)
        
        zoom_out_action = view_menu.addAction("缩小")
        zoom_out_action.setShortcut("-")
        zoom_out_action.triggered.connect(self.zoom_out)
        
        zoom_reset_action = view_menu.addAction("原大小")
        zoom_reset_action.setShortcut("\\")
        zoom_reset_action.triggered.connect(self.zoom_reset)
    
    def save_as(self):
        """另存为功能"""
        if not self.original_pixmap:
            QMessageBox.warning(self, "警告", "没有可保存的图片")
            return
        
        # 获取文件扩展名
        import os
        file_ext = os.path.splitext(self.image_filename)[1]
        if not file_ext:
            file_ext = ".png"
        
        # 获取上次另存为的路径
        if self.config_manager:
            last_save_path = self.config_manager.get_image_last_save_path()
            full_suggested_path = os.path.join(last_save_path, self.image_filename)
        else:
            full_suggested_path = self.image_filename
        
        # 打开保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "另存为", 
            full_suggested_path,
            f"图片文件 (*{file_ext});;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                # 保存原始图片
                self.original_pixmap.save(file_path)
                
                # 保存成功后更新配置的另存为路径
                if self.config_manager:
                    self.config_manager.set_image_last_save_path(file_path)
                
                # 使用toast显示成功提示
                if hasattr(self, 'toast_manager') and self.toast_manager:
                    self.toast_manager.show_success(f"图片已保存到: {os.path.basename(file_path)}")
                else:
                    # 如果没有toast管理器，使用MessageBox作为备选
                    QMessageBox.information(self, "成功", f"图片已保存到: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存失败: {str(e)}")
    
    def zoom_in(self):
        """放大图片"""
        if not self.original_pixmap:
            return
        
        self.current_scale *= 1.1
        self.update_image_display()
    
    def zoom_out(self):
        """缩小图片"""
        if not self.original_pixmap:
            return
        
        self.current_scale /= 1.1
        if self.current_scale < 0.1:
            self.current_scale = 0.1
        self.update_image_display()
    
    def zoom_reset(self):
        """重置为原大小"""
        if not self.original_pixmap:
            return
        
        self.current_scale = 1.0
        self.update_image_display()
        # 重新调整窗口大小以适应原图
        self.resize_window_for_image(self.original_pixmap)
    
    def update_image_display(self):
        """更新图片显示"""
        if not self.original_pixmap:
            return
        
        # 计算缩放后的尺寸
        new_width = int(self.original_pixmap.width() * self.current_scale)
        new_height = int(self.original_pixmap.height() * self.current_scale)
        
        # 缩放图片
        scaled_pixmap = self.original_pixmap.scaled(
            new_width, new_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # 更新显示
        self.image_label.setPixmap(scaled_pixmap)
        self.image_label.resize(scaled_pixmap.size())
    
    def keyPressEvent(self, event):
        """处理键盘事件"""
        if event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
            self.zoom_in()
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_out()
        elif event.key() == Qt.Key.Key_Backslash:
            self.zoom_reset()
        else:
            super().keyPressEvent(event)
    
    def closeEvent(self, event):
        """关闭事件，清理资源"""
        # 停止GIF动画
        if self.movie:
            self.movie.stop()
            self.movie = None
        
        # 清理网络管理器
        if hasattr(self, 'network_manager'):
            self.network_manager.deleteLater()
        
        super().closeEvent(event)

class OnlineDataViewer(QWidget):
    """线上数据查看器"""
    
    def __init__(self, data_manager, auth_manager=None, config_manager=None):
        super().__init__()
        self.data_manager = data_manager
        self.auth_manager = auth_manager
        self.config_manager = config_manager
        
        # 搜索相关变量
        self.search_results = []  # 存储搜索结果的位置 [(row, col), ...]
        self.current_search_index = -1  # 当前搜索结果索引
        self.last_search_text = ""  # 上次搜索的文本
        
        self.init_ui()
    
    def init_ui(self):
        # 创建主布局
        main_layout = QHBoxLayout()
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 创建左侧文件树
        self.create_file_tree()
        splitter.addWidget(self.file_tree)
        
        # 创建右侧数据视图
        data_view_container = self.create_data_view()
        splitter.addWidget(data_view_container)
        
        # 设置分割器初始大小，左侧宽度减半
        splitter.setSizes([150, 850])
        
        # 添加分割器到主布局
        main_layout.addWidget(splitter)
        
        # 设置布局
        self.setLayout(main_layout)
    
    def create_file_tree(self):
        """创建抽屉式文件视图"""
        # 创建抽屉式控件
        self.file_tree = AccordionWidget()
        
        # 加载文件系统
        self.load_file_system()
    
    def load_file_system(self):
        """加载文件系统到抽屉式控件"""
        # 清空抽屉控件
        self.file_tree.clear()
        
        # 获取缓存目录
        cache_dir = self.data_manager.config.xlsx_cache_dir
        
        # 加载目录结构
        self._load_directory_to_accordion(cache_dir)
    
    def _load_directory_to_accordion(self, directory):
        """加载目录到抽屉式控件"""
        # 遍历目录
        dirs = []
        files = []
        
        # 先收集所有目录和文件
        for item in os.listdir(directory):
            path = os.path.join(directory, item)
            if os.path.isdir(path):
                dirs.append((item, path))
            elif item.endswith(('.xlsx', '.xls')):
                files.append((item, path))
        
        # 按名称排序
        dirs.sort(key=lambda x: x[0])
        files.sort(key=lambda x: x[0])
        
        # 先添加所有目录作为抽屉
        for dir_name, dir_path in dirs:
            # 创建抽屉项
            drawer = self.file_tree.add_item(dir_name, dir_path)
            
            # 创建文件列表控件
            file_list = FileListWidget()
            drawer.set_content(file_list)
            
            # 递归加载子目录中的文件
            self._load_files_to_list(dir_path, file_list)
            
            # 连接文件点击信号
            file_list.file_clicked.connect(self.on_file_selected)
        
        # 如果根目录有文件，创建一个"根目录文件"抽屉
        if files:
            root_drawer = self.file_tree.add_item(os.path.basename(directory), directory)
            root_file_list = FileListWidget()
            root_drawer.set_content(root_file_list)
            
            # 添加文件到列表
            for file_name, file_path in files:
                item = QListWidgetItem(file_name)
                item.setData(Qt.ItemDataRole.UserRole, file_path)
                root_file_list.addItem(item)
            
            # 连接文件点击信号
            root_file_list.file_clicked.connect(self.on_file_selected)
    
    def _load_files_to_list(self, directory, file_list):
        """加载目录中的文件到列表控件"""
        files = []
        
        # 收集所有Excel文件
        for item in os.listdir(directory):
            path = os.path.join(directory, item)
            if item.endswith(('.xlsx', '.xls')) and os.path.isfile(path):
                files.append((item, path))
        
        # 按名称排序
        files.sort(key=lambda x: x[0])
        
        # 添加文件到列表
        for file_name, file_path in files:
            item = QListWidgetItem(file_name)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            file_list.addItem(item)
    
    def _load_directory(self, parent_item, directory):
        """递归加载目录（保留原方法以兼容旧代码）"""
        # 遍历目录
        for item in os.listdir(directory):
            path = os.path.join(directory, item)
            
            # 创建项
            tree_item = QStandardItem(item)
            tree_item.setData(path)
            
            # 如果是目录，递归加载
            if os.path.isdir(path):
                parent_item.appendRow(tree_item)
                self._load_directory(tree_item, path)
            # 如果是Excel文件，添加到树中
            elif item.endswith(('.xlsx', '.xls')):
                parent_item.appendRow(tree_item)
            # 其他类型的文件不添加
            elif not item.endswith(('.xlsx', '.xls')):
                tree_item.setEnabled(False)
    
    def create_data_view(self):
        """创建数据视图"""
        # 创建垂直布局
        self.data_view_container = QWidget()
        data_layout = QVBoxLayout(self.data_view_container)
        data_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建sheet选择器区域
        sheet_container = QWidget()
        sheet_layout = QHBoxLayout(sheet_container)
        sheet_layout.setContentsMargins(5, 5, 5, 5)
        
        # 添加“打开目录”按钮（位于文件名标签左侧）
        self.open_dir_btn = QPushButton("打开目录")
        self.open_dir_btn.setMinimumWidth(80)
        self.open_dir_btn.clicked.connect(self.on_open_current_dir)
        sheet_layout.addWidget(self.open_dir_btn)

        # 添加表格名称标签（左对齐）
        self.table_name_label = QLabel("未选择文件")
        self.table_name_label.setStyleSheet("font-weight: bold; font-size: 14px; color: white;")
        self.table_name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table_name_label.setMinimumWidth(200)
        sheet_layout.addWidget(self.table_name_label)
        
        # 添加弹性空间（左侧）
        sheet_layout.addStretch(1)
        
        # 添加搜索框和按钮（居中）
        search_label = QLabel("搜索:")
        sheet_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索内容...")
        self.search_input.setMinimumWidth(200)
        self.search_input.returnPressed.connect(self.search_next)  # 回车键搜索
        self.search_input.textChanged.connect(self.on_search_text_changed)  # 文本变化时处理
        sheet_layout.addWidget(self.search_input)
        
        self.search_button = QPushButton("搜索")
        self.search_button.setMinimumWidth(60)
        self.search_button.clicked.connect(self.search_next)
        sheet_layout.addWidget(self.search_button)
        
        # 添加弹性空间（右侧）
        sheet_layout.addStretch(1)
        
        # 添加标签（右对齐）
        sheet_label = QLabel("工作表:")
        sheet_layout.addWidget(sheet_label)
        
        # 创建sheet选择器（右对齐）
        self.sheet_selector = QComboBox()
        self.sheet_selector.setMinimumWidth(150)
        self.sheet_selector.currentIndexChanged.connect(self.on_sheet_changed)
        sheet_layout.addWidget(self.sheet_selector)
        
        # 添加sheet选择器区域到主布局
        data_layout.addWidget(sheet_container)
        
        # 创建表格视图
        self.data_view = QTableView()
        self.data_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.data_view.horizontalHeader().setStretchLastSection(True)
        
        # 设置列宽上限为1000像素
        self.data_view.horizontalHeader().setMaximumSectionSize(1000)
        
        # 设置右键菜单策略
        self.data_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_view.customContextMenuRequested.connect(self.show_context_menu)
        
        # 创建表格模型
        self.table_model = ExcelTableModel()
        self.data_view.setModel(self.table_model)
        
        # 设置表格样式
        self.data_view.setAlternatingRowColors(True)
        
        # 设置选中样式，统一使用亮灰色背景
        self.data_view.setStyleSheet("""
            QTableView::item:selected {
                background-color: #606060;  /* 亮灰色背景 */
            }
        """)
        
        # 连接点击事件
        self.data_view.clicked.connect(self.on_table_clicked)
        
        # 添加表格到主布局
        data_layout.addWidget(self.data_view)

        return self.data_view_container
    
    def on_sheet_changed(self, index):
        """处理工作表切换事件"""
        print(f"切换工作表: {index}")  # 添加调试信息
        if index < 0 or not hasattr(self, 'current_file_data') or not self.current_file_data:
            return
                
        sheet_name = self.sheet_selector.currentText()
        print(f"选择的工作表: {sheet_name}")  # 添加调试信息
        if sheet_name in self.current_file_data:
            df = self.current_file_data[sheet_name]
            print(f"工作表数据行数: {len(df)}")  # 添加调试信息
                
            # 清除搜索高亮和搜索状态
            self.table_model.clear_highlights()
            self.search_results = []
            self.current_search_index = -1
            self.last_search_text = ""
            # 清空搜索输入框
            if hasattr(self, 'search_input'):
                self.search_input.clear()
                
            # 加载数据到表格模型
            self.table_model.load_data(df)
            self.data_view.reset()  # 强制刷新视图
                
            # 更新窗口标题和表格名称
            if hasattr(self, 'current_file_path'):
                file_name = os.path.basename(self.current_file_path)
                self.setWindowTitle(f"线上数据 - {file_name} - {sheet_name}")
                self.table_name_label.setText(f"{file_name}")
    
    def on_file_selected(self, file_path):
        """处理文件选择事件"""
        # 直接使用传入的文件路径
            
        # 检查是否是Excel文件
        if file_path and os.path.isfile(file_path) and file_path.endswith(('.xlsx', '.xls')):
            try:
                # 获取相对路径
                rel_path = os.path.relpath(file_path, self.data_manager.config.xlsx_cache_dir)
                
                # 调试输出，查看路径转换情况
                print(f"原始文件路径: {file_path}")
                print(f"转换后的相对路径: {rel_path}")
                print(f"缓存目录: {self.data_manager.config.xlsx_cache_dir}")
                
                # 从数据管理器获取数据
                file_data = self.data_manager.get_file_data(rel_path)
                
                # 调试输出，查看数据管理器内部缓存情况
                print(f"数据管理器缓存的文件列表: {self.data_manager.get_all_files()}")
                print(f"查询的文件是否在缓存中: {rel_path in self.data_manager.get_all_files()}")
                
                if file_data:
                    # 清除搜索高亮和搜索状态
                    self.table_model.clear_highlights()
                    self.search_results = []
                    self.current_search_index = -1
                    self.last_search_text = ""
                    # 清空搜索输入框
                    if hasattr(self, 'search_input'):
                        self.search_input.clear()
                        
                    # 更新sheet选择器
                    self.sheet_selector.blockSignals(True)
                    self.sheet_selector.clear()
                    sheet_names = list(file_data.keys())
                    self.sheet_selector.addItems(sheet_names)
                    self.sheet_selector.blockSignals(False)
                        
                    # 获取第一个工作表
                    sheet_name = sheet_names[0]
                    df = file_data[sheet_name]
                        
                    # 加载数据到表格模型
                    self.table_model.load_data(df)
                        
                    # 更新窗口标题和表格名称
                    file_name = os.path.basename(file_path)
                    self.setWindowTitle(f"线上数据 - {file_name} - {sheet_name}")
                    self.table_name_label.setText(f"{file_name}")
                        
                    # 保存当前文件数据
                    self.current_file_data = file_data
                    self.current_file_path = file_path
                        
                    # 成功从数据管理器加载
                    print(f"从数据管理器加载文件成功: {rel_path}")
                else:
                    # 尝试直接加载文件
                    try:
                        # 加载文件数据，使用更安全的方式
                        excel_data = pd.read_excel(
                            file_path, 
                            sheet_name=None,
                            engine='openpyxl'  # 明确指定引擎
                        )
                        if excel_data:
                            # 清除搜索高亮和搜索状态
                            self.table_model.clear_highlights()
                            self.search_results = []
                            self.current_search_index = -1
                            self.last_search_text = ""
                            # 清空搜索输入框
                            if hasattr(self, 'search_input'):
                                self.search_input.clear()
                                
                            # 更新sheet选择器
                            self.sheet_selector.blockSignals(True)
                            self.sheet_selector.clear()
                            sheet_names = list(excel_data.keys())
                            self.sheet_selector.addItems(sheet_names)
                            self.sheet_selector.blockSignals(False)
                                
                            sheet_name = sheet_names[0]
                            df = excel_data[sheet_name]
                                
                            # 加载数据到表格模型
                            self.table_model.load_data(df)
                                
                            # 更新窗口标题和表格名称
                            file_name = os.path.basename(file_path)
                            self.setWindowTitle(f"线上数据 - {file_name} - {sheet_name}")
                            self.table_name_label.setText(f"{file_name}")
                                
                            # 保存当前文件数据
                            self.current_file_data = excel_data
                            self.current_file_path = file_path
                            
                            # 直接加载成功后，应该将数据添加到数据管理器的缓存中
                            print(f"直接加载文件成功: {file_path}")
                            print(f"尝试将数据添加到数据管理器缓存...")
                            # 这里可以调用数据管理器的方法将数据添加到缓存
                            # self.data_manager.add_file_data(rel_path, excel_data)
                        else:
                            print(f"直接加载文件失败: {file_path}")
                    except Exception as e:
                        print(f"直接加载文件出错: {e}")
            except Exception as e:
                print(f"加载文件时出错: {e}")
    
    def on_table_clicked(self, index):
        """处理表格点击事件"""
        if not index.isValid():
            return
        
        # 获取单元格数据
        column = index.column()
        cell_data = self.table_model.data(index, Qt.ItemDataRole.DisplayRole)
        if not cell_data:
            return
            
        # 检查是否是图片列
        if self.table_model.is_image_column(column):
            # 直接传递图片文件名给弹窗，让弹窗内部处理URL拼接和多路径尝试
            dialog = ImagePreviewDialog(str(cell_data), self.auth_manager, self, self.toast_manager, self.config_manager)
            dialog.exec()
        
        # 检查是否是音频列或者是MP3文件
        elif self.table_model.is_audio_column(column) or str(cell_data).lower().endswith('.mp3'):
            # 使用单例模式创建音频播放器对话框
            # 如果已有实例，会先关闭旧实例再创建新实例
            if not hasattr(self, '_audio_player_dialog') or not self._audio_player_dialog or not self._audio_player_dialog.isVisible():
                self._audio_player_dialog = AudioPlayerDialog(str(cell_data), self.auth_manager, self)
                # 在对话框关闭时清除引用
                self._audio_player_dialog.finished.connect(lambda: setattr(self, '_audio_player_dialog', None))
            else:
                # 如果已有实例，先关闭它
                try:
                    self._audio_player_dialog.close()
                    self._audio_player_dialog = None
                except Exception as e:
                    print(f"关闭旧的音频播放器实例时出错: {e}")
                # 创建新实例
                self._audio_player_dialog = AudioPlayerDialog(str(cell_data), self.auth_manager, self)
                self._audio_player_dialog.finished.connect(lambda: setattr(self, '_audio_player_dialog', None))
            
            # 显示对话框
            self._audio_player_dialog.exec()
    
    def show_context_menu(self, position):
        """显示右键菜单"""
        # 获取点击位置的索引
        index = self.data_view.indexAt(position)
        if not index.isValid():
            return
        
        # 获取单元格内容
        cell_data = self.table_model.data(index, Qt.ItemDataRole.DisplayRole)
        if not cell_data or str(cell_data).strip() == "":
            return
        
        # 创建右键菜单
        context_menu = QMenu(self)
        
        # 添加复制动作
        copy_action = context_menu.addAction("复制")
        copy_action.triggered.connect(lambda: self.copy_cell_content(str(cell_data)))
        
        # 显示菜单
        context_menu.exec(self.data_view.mapToGlobal(position))
    
    def copy_cell_content(self, content):
        """复制单元格内容到剪贴板"""
        clipboard = QApplication.clipboard()
        clipboard.setText(str(content))
        
        # 显示Toast提示
        if hasattr(self, 'toast_manager') and self.toast_manager:
            self.toast_manager.show_toast("已复制到剪贴板")

    def on_open_current_dir(self):
        """打开当前表格所在目录"""
        dir_path = None
        if hasattr(self, 'current_file_path') and self.current_file_path:
            dir_path = os.path.dirname(self.current_file_path)
        elif hasattr(self, 'data_manager') and hasattr(self.data_manager, 'config') and hasattr(self.data_manager.config, 'xlsx_cache_dir'):
            dir_path = self.data_manager.config.xlsx_cache_dir
        if dir_path and os.path.isdir(dir_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(dir_path))
            print(f"[线上数据] 打开目录: {dir_path}")
        else:
            print("[线上数据] 打开目录失败: 路径无效")
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_error("无法打开目录")
    
    def search_next(self):
        """搜索下一个匹配项"""
        search_text = self.search_input.text().strip()
        if not search_text:
            return
        
        # 如果搜索文本改变了，重新搜索
        if search_text != self.last_search_text:
            self.perform_search(search_text)
            self.last_search_text = search_text
        
        # 如果没有搜索结果，返回
        if not self.search_results:
            QMessageBox.information(self, "搜索", "未找到匹配项")
            return
        
        # 获取当前选中的单元格
        current_index = self.data_view.currentIndex()
        current_cell = (current_index.row(), current_index.column()) if current_index.isValid() else None
        
        # 判断当前选中的单元格是否在搜索结果中
        if current_cell and current_cell in self.search_results:
            # 如果当前选中的是匹配单元格，搜索下一个
            current_pos = self.search_results.index(current_cell)
            self.current_search_index = (current_pos + 1) % len(self.search_results)
        else:
            # 如果当前选中的不是匹配单元格，从头开始
            self.current_search_index = 0
        
        # 高亮显示当前搜索结果
        self.highlight_search_result()
    
    def perform_search(self, search_text):
        """执行搜索，查找所有匹配项"""
        self.search_results.clear()
        self.current_search_index = -1
        
        if not hasattr(self, 'data_view') or not self.data_view.model():
            return
        
        model = self.data_view.model()
        if not model:
            return
        
        # 清除之前的高亮
        model.clear_highlights()
        
        # 搜索所有单元格
        for row in range(model.rowCount()):
            for col in range(model.columnCount()):
                index = model.index(row, col)
                cell_data = model.data(index, Qt.ItemDataRole.DisplayRole)
                if cell_data and search_text.lower() in str(cell_data).lower():
                    self.search_results.append((row, col))
        
        # 高亮所有匹配的单元格
        if self.search_results:
            model.set_highlighted_cells(self.search_results)
    
    def highlight_search_result(self):
        """高亮显示当前搜索结果"""
        if not self.search_results or self.current_search_index < 0:
            return
        
        row, col = self.search_results[self.current_search_index]
        
        # 滚动到当前搜索结果
        model = self.data_view.model()
        index = model.index(row, col)
        self.data_view.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)
        
        # 选中当前搜索结果
        self.data_view.setCurrentIndex(index)
    
    def on_search_text_changed(self, text):
        """搜索文本变化时的处理"""
        if not text.strip():
            # 如果搜索框为空，清除所有高亮
            if hasattr(self, 'data_view') and self.data_view.model():
                self.data_view.model().clear_highlights()
            self.search_results.clear()
            self.current_search_index = -1
            self.last_search_text = ""
