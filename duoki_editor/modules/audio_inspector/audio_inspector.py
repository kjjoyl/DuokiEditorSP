from contextlib import nullcontext
from tarfile import NUL
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QFileDialog, QTableView, QHeaderView, QMessageBox, QTextEdit,
                            QListWidget, QSplitter, QLineEdit, QTableWidget, QTableWidgetItem,
                            QComboBox, QStyledItemDelegate, QMenu, QApplication, QDialog, QDialogButtonBox, QTabWidget, QGroupBox, QCheckBox, QGridLayout, QScrollArea, QSizePolicy, QAbstractItemView, QRadioButton, QSlider, QButtonGroup)
from PyQt6.QtCore import Qt, QAbstractTableModel, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QKeyEvent, QAction, QPixmap, QMovie, QPainter, QImage, QColor, QIntValidator, QStandardItemModel, QStandardItem
import json
import pandas as pd
import os
import requests
import threading
import math  # 添加math模块导入
from duoki_editor.tts.tts_player import TTSPlayer  # 使用相对导入
from duoki_editor.tts.tts_cache import TTSCache
from duoki_editor.utils.worker_thread import ThreadPoolRunner
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl
from duoki_editor.core.scene_graph_manager import SceneGraphManager  # 导入SceneGraphManager
from duoki_editor.core.character_table_manager import CharacterTableManager  # 导入CharacterTableManager
from duoki_editor.core.show_image_npc_manager import ShowImageNpcManager  # 导入ShowImageNpcManager
from duoki_editor.utils.config_manager import ConfigManager  # 导入ConfigManager
from duoki_editor.core.auth_manager import AuthManager  # 导入AuthManager
from duoki_editor.ui.toast import Toast  # 导入Toast
from duoki_editor.core.template_config_manager import TemplateConfigManager
from duoki_editor.core.speech_manager import SpeechManager
from duoki_editor.utils.constants_loader import get_npc_id_map_2


class SquareImageContainer(QLabel):
    """正方形图片容器，强制高度等于宽度"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #000000; color: white;")  # 黑色背景，白色文字
        self.setText("图片加载中...")
        self.setVisible(False)  # 默认隐藏
        self.current_movie = None  # 存储当前的QMovie对象
        self.background_pixmap = None  # 存储背景图片
        self.gif_movie = None  # 存储GIF动画
        self.gif_position = None  # 存储GIF动画位置 (x, y)
        self.gif_size = None  # 存储GIF动画大小 (width, height)
        self.gif_timer = None
        self.gif_fps = 15
    
    def resizeEvent(self, event):
        """重写resizeEvent以强制保持正方形"""
        super().resizeEvent(event)
        width = self.width()
        if width > 0:
            self.setFixedHeight(width)
    
    def sizeHint(self):
        """提供尺寸建议"""
        return QSize(300, 300)  # 默认300x300的正方形
    
    def setMovie(self, movie):
        """设置QMovie对象以播放GIF动画"""
        # 停止之前的动画
        if self.current_movie:
            self.current_movie.stop()
        
        self.current_movie = movie
        if movie:
            super().setMovie(movie)
            movie.start()
        else:
            super().setMovie(None)
    
    def setPixmap(self, pixmap):
        """重写setPixmap方法，停止当前动画"""
        # 停止当前动画
        if self.current_movie:
            self.current_movie.stop()
            self.current_movie = None
        super().setPixmap(pixmap)
    
    def setBackgroundWithGif(self, background_pixmap, gif_movie, gif_x, gif_y, gif_width, gif_height):
        """设置背景图片和GIF动画的位置"""
        self.clearGif()

        self.background_pixmap = background_pixmap
        self.gif_movie = gif_movie
        self.gif_position = (gif_x, gif_y)
        self.gif_size = (gif_width, gif_height)
        
        # 停止之前的动画
        if self.current_movie:
            self.current_movie.stop()
            self.current_movie = None
        
        # 设置背景图片
        super().setPixmap(background_pixmap)
        
        # 使用定时器推进帧
        if gif_movie:
            try:
                from PyQt6.QtGui import QMovie
                gif_movie.setCacheMode(QMovie.CacheMode.CacheAll)
                gif_movie.jumpToFrame(0)
                gif_movie.stop()
            except Exception:
                pass
            if self.gif_timer is None:
                self.gif_timer = QTimer(self)
            try:
                delay = int(1000 / max(1, self.gif_fps))
                self.gif_timer.setInterval(delay)
                self.gif_timer.timeout.disconnect()
            except Exception:
                pass
            self.gif_timer.timeout.connect(self._advanceGifFrame)
            self.gif_timer.start()
            self.updateGifFrame()

    def clearGif(self):
        if self.gif_timer:
            try:
                self.gif_timer.stop()
            except Exception:
                pass
            self.gif_timer = None
        if self.gif_movie:
            try:
                self.gif_movie.frameChanged.disconnect(self.updateGifFrame)
            except Exception:
                pass
            try:
                self.gif_movie.stop()
            except Exception:
                pass
            self.gif_movie = None
        self.background_pixmap = None
        self.gif_position = None
        self.gif_size = None

    def _advanceGifFrame(self):
        if not self.gif_movie:
            return
        try:
            self.gif_movie.jumpToNextFrame()
        except Exception:
            pass
        self.updateGifFrame()
    
    def updateGifFrame(self):
        """更新GIF动画帧"""
        if not self.background_pixmap or not self.gif_movie or not self.gif_position or not self.gif_size:
            return
        
        # 创建新的合成图片
        combined_pixmap = self.background_pixmap.copy()
        painter = QPainter(combined_pixmap)
        
        # 获取当前GIF帧
        current_frame = self.gif_movie.currentPixmap()
        if not current_frame.isNull():
            # 缩放GIF帧到指定大小
            scaled_frame = current_frame.scaled(
                self.gif_size[0], self.gif_size[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # 在指定位置绘制GIF帧
            painter.drawPixmap(self.gif_position[0], self.gif_position[1], scaled_frame)
        
        painter.end()
        
        # 更新显示
        super().setPixmap(combined_pixmap)

class AudioTableModel(QAbstractTableModel):
    """音频数据表格模型"""
    def __init__(self, data=None):
        super().__init__()
        self._data = data if data is not None else pd.DataFrame(columns=['stage_name', 'speaker', 'dialog'])
        self._original_data = None  # 存储原始数据
        self.highlighted_row = None
        
    def rowCount(self, parent=None):
        return len(self._data)
        
    def columnCount(self, parent=None):
        return 3  # 显示speaker、dialog和stage_name三列
        
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
            
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                value = self._data.iloc[index.row()].get('stage_name', '')
                # 处理空值，不显示"nan"
                if pd.isna(value) or str(value).lower() in ['nan', 'none', '']:
                    return ""
                return str(value)
            elif index.column() == 1:
                value = self._data.iloc[index.row()].get('speaker', '')
                # 处理空值，不显示"nan"
                if pd.isna(value) or str(value).lower() in ['nan', 'none', '']:
                    return ""
                return str(value)
            elif index.column() == 2:
                value = self._data.iloc[index.row()].get('dialog', '')
                # 处理空值，不显示"nan"
                if pd.isna(value) or str(value).lower() in ['nan', 'none', '']:
                    return ""
                return str(value)
        elif role == Qt.ItemDataRole.ForegroundRole:
            # 为高亮行提供橙红色文本
            if hasattr(self, 'highlighted_row') and self.highlighted_row == index.row():
                from PyQt6.QtGui import QColor
                return QColor('orange')  # 使用红色作为高亮颜色
                
        return None
        
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
            
        if orientation == Qt.Orientation.Horizontal:
            return ['stage_name', 'speaker', 'dialog'][section]
            
        return str(section + 1)
        
    def load_data(self, data):
        """加载数据到模型"""
        self.beginResetModel()
        # 保存原始数据的完整副本
        self._original_data = data.copy()
        
        # 创建显示数据，默认使用speaker和param1列
        display_data = pd.DataFrame()
        display_data['speaker'] = data['speaker'].copy()
        display_data['dialog'] = data['param1'].copy()
        
        self._data = display_data
        self.endResetModel()
        
    def update_display(self, column_name, speaker_mapping):
        """更新显示数据"""
        if self._original_data is None:
            return
            
        self.beginResetModel()
        
        # 从_original_data中读取三列并存入到_data，按照新的列顺序：stage_name, speaker, dialog
        display_data = pd.DataFrame()
        
        # 第0列：添加stage_name列
        if 'stage_name' in self._original_data.columns:
            display_data['stage_name'] = self._original_data['stage_name'].copy()
        else:
            # 如果原始数据中没有stage_name列，填充空值
            display_data['stage_name'] = ''
        
        # 第1列：处理speaker列，应用映射
        speakers = self._original_data['speaker'].copy()
        for old_val, new_val in speaker_mapping.items():
            speakers = speakers.replace(old_val, new_val)
        
        # 将speaker字段中的"duoki"替换为"多奇"
        speakers = speakers.replace('duoki', '多奇')
            
        display_data['speaker'] = speakers
        
        # 第2列：使用选定的列作为dialog内容
        if column_name in self._original_data.columns:
            dialog_content = self._original_data[column_name].copy()
        else:
            dialog_content = self._original_data['param1'].copy()
        
        # 只有当列名不是param1时，才应用NPC名称替换
        if column_name != 'param1':
            # 应用NPC名称替换
            if hasattr(self, 'npc1_name') and self.npc1_name:
                dialog_content = dialog_content.str.replace('{npc1_name}', self.npc1_name)
                # 同时替换npc1_name_origin
                dialog_content = dialog_content.str.replace('{npc1_name_origin}', self.npc1_name)
            
            if hasattr(self, 'npc2_name') and self.npc2_name:
                dialog_content = dialog_content.str.replace('{npc2_name}', self.npc2_name)
                # 同时替换npc2_name_origin
                dialog_content = dialog_content.str.replace('{npc2_name_origin}', self.npc2_name)
            
        display_data['dialog'] = dialog_content
        
        # 更新_data为新的显示数据
        self._data = display_data
        self.endResetModel()

    def highlight_row(self, row):
        """高亮指定行"""
        # 先清除之前的高亮
        self.clear_highlight()
        
        # 设置新的高亮行
        self.highlighted_row = row
        # 发出数据变化信号，触发视图更新
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount()-1))
    
    def clear_highlight(self):
        """清除高亮"""
        if hasattr(self, 'highlighted_row') and self.highlighted_row is not None:
            old_row = self.highlighted_row
            self.highlighted_row = None  # 使用None而不是删除属性
            # 发出数据变化信号，触发视图更新
            self.dataChanged.emit(self.index(old_row, 0), self.index(old_row, self.columnCount()-1))

class AudioInspector(QWidget):
    render_request = pyqtSignal(object, int, int, object)
    def __init__(self, data_manager, auth_manager=None):
        super().__init__()
        self.data_manager = data_manager
        self.tts_player = TTSPlayer()
        # 连接TTS播放器的错误信号
        self.tts_player.error_occurred.connect(self.on_tts_error)
        self.current_column = 'param1'  # 当前选择的列
        self.current_speaker_mapping = {}  # 当前的speaker映射
        self.special_format_items = {}  # 存储从dialog中提取的特殊格式内容
        self.original_dialog_content = None  # 存储原始对话内容
        self.saved_values = {}  # 保存所有key-value对，在不同表单间共享
        self._toast_timer = None  # 防重复Toast提示的定时器
        self.current_file_path = None  # 存储当前文件路径
        self.current_speaker_name = None
        
        # 初始化图片缓存目录
        # 获取duoki_editor目录路径，使用与audio、data同级的cache目录
        duoki_editor_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.cache_dir = os.path.join(duoki_editor_dir, 'cache', 'image')
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 初始化SceneGraphManager
        self.scene_graph_manager = SceneGraphManager()
        print(f"SceneGraphManager已初始化，共加载 {len(self.scene_graph_manager.get_scene_graph_data())} 行场景图数据")
        
        # 初始化CharacterTableManager
        self.character_table_manager = CharacterTableManager()
        print(f"CharacterTableManager已初始化，共加载 {len(self.character_table_manager.get_character_table_data())} 行角色数据")
        
        # 初始化ShowImageNpcManager
        self.show_image_npc_manager = ShowImageNpcManager()
        
        # 初始化ConfigManager和AuthManager
        self.config_manager = ConfigManager()
        self.auth_manager = auth_manager if auth_manager is not None else AuthManager()
        self.template_config_manager = TemplateConfigManager()
        self.speech_manager = SpeechManager()
        
        
        self.render_request.connect(self._render_on_ui)
        self._bg_from_show_image_npc = False
        self._saturation_factor_override = None
        
        self.init_ui()
        
    def init_ui(self):
        # 创建主布局
        main_layout = QVBoxLayout(self)
        
        # 创建控件（但不添加到工具栏，稍后会重新分配位置）
        # 创建打开文件按钮
        self.open_file_btn = QPushButton("打开文件")
        self.open_file_btn.setFixedWidth(100) 
        self.open_file_btn.clicked.connect(self.open_file_dialog)
        
        # 创建文件名标签
        self.file_label = QLabel("未选择文件")
        
        # 创建当前对话标签（替代保存按钮位置）
        self.current_dialog_label = QLabel("未选择对话")
        from PyQt6.QtGui import QFont as _QFont
        _f = _QFont()
        _f.setBold(True)
        self.current_dialog_label.setFont(_f)
        
        # 创建播放和停止按钮容器
        self.button_container = QWidget()
        button_container_layout = QVBoxLayout(self.button_container)
        button_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建播放按钮
        self.play_button = QPushButton("播放音频")
        self.play_button.setFixedWidth(100)
        self.play_button.clicked.connect(self.play_audio)
        button_container_layout.addWidget(self.play_button)
        
        # 创建停止按钮（初始隐藏）
        self.stop_button = QPushButton("停止播放")
        self.stop_button.setFixedWidth(100)
        self.stop_button.clicked.connect(self.stop_audio)
        self.stop_button.setVisible(False)  # 初始状态隐藏而不是禁用
        button_container_layout.addWidget(self.stop_button)
        
        
        
        # 创建左侧布局（包含侧边栏列表和特殊格式内容表格）
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 在左侧布局顶部添加打开按钮和文件名
        top_left_layout = QHBoxLayout()
        top_left_layout.addWidget(self.open_file_btn)
        top_left_layout.addWidget(self.file_label)
        top_left_layout.addStretch(1)  # 添加弹性空间
        left_layout.addLayout(top_left_layout)
        
        # 创建页签容器替代原来的侧边栏列表
        self.tab_widget = QTabWidget()
        
        # 创建会话模式页签（原来的sidebar_list）
        self.conversation_tab = QWidget()
        conversation_layout = QVBoxLayout(self.conversation_tab)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        
        self.sidebar_list = QListWidget()
        self.sidebar_list.currentItemChanged.connect(self.on_sidebar_item_changed)
        conversation_layout.addWidget(self.sidebar_list)
        self.sidebar_list.itemDoubleClicked.connect(self.on_sidebar_item_double_clicked)
        
        # 创建整合模式页签
        self.integration_tab = QWidget()
        integration_layout = QVBoxLayout(self.integration_tab)
        integration_layout.setContentsMargins(0, 0, 0, 0)
        
        self.integration_list = QListWidget()
        self.integration_list.currentItemChanged.connect(self.on_integration_item_changed)
        integration_layout.addWidget(self.integration_list)
        self.integration_list.itemDoubleClicked.connect(self.on_integration_item_double_clicked)
        
        
        
        # 添加页签到页签容器
        self.tab_widget.addTab(self.conversation_tab, "会话模式")
        self.tab_widget.addTab(self.integration_tab, "整合模式")
        
        
        # 连接页签切换信号
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        # 创建内部分割器，用于调整页签容器和特殊格式内容表格的比例
        self.inner_splitter = QSplitter(Qt.Orientation.Vertical)
        self.inner_splitter.addWidget(self.tab_widget)
        
        # 添加特殊格式内容表格
        self.format_table = QTableWidget(0, 2)
        self.format_table.setHorizontalHeaderLabels(["key", "value"])
        self.format_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.format_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.format_table.setColumnWidth(0, 100)
        
        # 设置自定义委托
        self.format_delegate = FormatItemDelegate()
        self.format_table.setItemDelegate(self.format_delegate)
        self.format_table.setStyleSheet("""
            QToolTip {
                color: black;
                white-space: normal;
                background-color: orange;
            }
        """)
        
        # 添加到内部分割器
        self.inner_splitter.addWidget(self.format_table)
        
        # 添加图片容器，默认隐藏
        self.image_container = SquareImageContainer()
        
        # 添加图片容器到内部分割器
        self.inner_splitter.addWidget(self.image_container)
        
        # 设置分割比例（1:2）
        self.inner_splitter.setSizes([200, 100, 100])
        
        # 添加内部分割器到左侧布局
        left_layout.addWidget(self.inner_splitter)
        
        # 创建右侧区域容器
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 在右侧表格上方添加按钮区域
        top_right_layout = QHBoxLayout()

        # 当前对话名称标签 - 左对齐
        top_right_layout.addWidget(self.current_dialog_label)

        # 添加弹性空间
        top_right_layout.addStretch(1)

        # 饱和度控制
        self.saturation_label = QLabel("剧情图片饱和度")
        self.saturation_slider = QSlider(Qt.Orientation.Horizontal)
        self.saturation_slider.setMinimum(0)
        self.saturation_slider.setMaximum(100)
        self.saturation_slider.setSingleStep(5)
        self.saturation_slider.setPageStep(10)
        # 初始化为配置中的值，但不写回配置
        init_factor = self.config_manager.get_image_npc_desaturate()
        self._saturation_factor_override = init_factor
        self.saturation_slider.setValue(int(init_factor * 100))
        self.saturation_slider.valueChanged.connect(self.on_saturation_changed)
        self.saturation_value_label = QLabel(f"{init_factor:.2f}")
        top_right_layout.addWidget(self.saturation_label)
        top_right_layout.addWidget(self.saturation_slider)
        top_right_layout.addWidget(self.saturation_value_label)

        self.skip_duoki_checkbox = QCheckBox("跳过多奇")
        top_right_layout.addWidget(self.skip_duoki_checkbox)
        # 播放音频按钮 - 右对齐，宽度100
        self.play_button.setFixedWidth(100)
        self.stop_button.setFixedWidth(100)
        top_right_layout.addWidget(self.play_button)
        top_right_layout.addWidget(self.stop_button)
        
        right_layout.addLayout(top_right_layout)
        
        # 创建表格视图
        self.table_view = QTableView()
        self.table_model = AudioTableModel()
        self.table_view.setModel(self.table_model)
        
        # 设置表格样式
        self.table_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # stage_name列固定宽度
        self.table_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # speaker列固定宽度
        self.table_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # dialog列自适应
        self.table_view.setColumnWidth(0, 100)  # stage_name列宽度
        self.table_view.setColumnWidth(1, 80)   # speaker列宽度
        self.table_view.setAlternatingRowColors(True)
        
        # 连接双击事件到dialog列播放功能
        self.table_view.doubleClicked.connect(self.on_table_double_clicked)
        
        # 设置右键菜单策略
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)
        
        right_layout.addWidget(self.table_view)
        
        content_container = QWidget()
        content_layout = QHBoxLayout(content_container)
        content_layout.addWidget(left_widget, 1)
        content_layout.addWidget(right_widget, 3)
        
        self.qa_tab_widget = QTabWidget()
        conversation_qa_page = QWidget()
        conversation_qa_layout = QVBoxLayout(conversation_qa_page)
        conversation_qa_layout.setContentsMargins(5, 5, 5, 5)
        conversation_qa_layout.addWidget(content_container)
        knowledge_create_page = QWidget()
        knowledge_create_layout = QVBoxLayout(knowledge_create_page)
        knowledge_create_layout.setContentsMargins(5, 5, 5, 5)
        knowledge_qa_page = QWidget()
        knowledge_qa_layout = QVBoxLayout(knowledge_qa_page)
        knowledge_qa_layout.setContentsMargins(5, 5, 5, 5)

        qc_compare_page = QWidget()
        qc_compare_layout = QVBoxLayout(qc_compare_page)
        qc_compare_layout.setContentsMargins(5, 5, 5, 5)
        qc_compare_row = QHBoxLayout()

        qc_left_col = QWidget()
        qc_left_col_layout = QVBoxLayout(qc_left_col)
        qc_left_top = QHBoxLayout()
        self.qc_compare_stat_btn = QPushButton("统计")
        self.qc_compare_stat_btn.setFixedWidth(60)
        self.qc_compare_stat_btn.clicked.connect(self.on_qc_compare_stat)
        qc_left_top.addWidget(self.qc_compare_stat_btn)
        self.qc_compare_stat_label = QLabel("修改量：0/0")
        qc_left_top.addWidget(self.qc_compare_stat_label)
        qc_left_top.addStretch(1)
        self.qc_compare_reset_btn = QPushButton("重置")
        self.qc_compare_reset_btn.setFixedWidth(60)
        self.qc_compare_reset_btn.clicked.connect(self.on_qc_compare_reset)
        qc_left_top.addWidget(self.qc_compare_reset_btn)
        qc_left_col_layout.addLayout(qc_left_top)

        self.qc_filter_group = QGroupBox()
        self.qc_filter_group.setContentsMargins(0, 0, 0, 0)
        qc_filter_layout = QHBoxLayout(self.qc_filter_group)
        self.qc_filter_checkboxes = []
        for name in ["e0", "e1", "e2", "e3", "e4"]:
            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.stateChanged.connect(self.on_qc_filter_changed)
            qc_filter_layout.addWidget(cb)
            self.qc_filter_checkboxes.append(cb)
        qc_left_col_layout.addWidget(self.qc_filter_group)

        self.qc_compare_file_list = QListWidget()
        self.qc_compare_file_list.currentRowChanged.connect(self.on_qc_compare_file_selected)
        qc_left_col_layout.addWidget(self.qc_compare_file_list, 1)
        qc_compare_row.addWidget(qc_left_col, 1)

        qc_middle_col = QWidget()
        qc_middle_col_layout = QVBoxLayout(qc_middle_col)
        qc_middle_top = QHBoxLayout()
        self.qc_compare_open_dir_btn_1 = QPushButton("质检前目录")
        self.qc_compare_open_dir_btn_1.clicked.connect(self.on_qc_compare_open_directory_1)
        self.qc_compare_dir_label_1 = QLabel("未选择目录")
        qc_middle_top.addWidget(self.qc_compare_open_dir_btn_1)
        qc_middle_top.addWidget(self.qc_compare_dir_label_1)
        qc_middle_top.addStretch(1)
        qc_middle_col_layout.addLayout(qc_middle_top)
        self.qc_compare_dataform_1 = QTableView()
        self.qc_compare_dataform_1.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.qc_compare_dataform_1.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.qc_compare_dataform_1.setTextElideMode(Qt.TextElideMode.ElideNone)
        qc_middle_col_layout.addWidget(self.qc_compare_dataform_1, 1)
        qc_compare_row.addWidget(qc_middle_col, 3)

        qc_right_col = QWidget()
        qc_right_col_layout = QVBoxLayout(qc_right_col)
        qc_right_top = QHBoxLayout()
        self.qc_compare_open_dir_btn_2 = QPushButton("质检后目录")
        self.qc_compare_open_dir_btn_2.clicked.connect(self.on_qc_compare_open_directory_2)
        self.qc_compare_open_dir_btn_2.setEnabled(False)
        self.qc_compare_dir_label_2 = QLabel("未选择目录")
        qc_right_top.addWidget(self.qc_compare_open_dir_btn_2)
        qc_right_top.addWidget(self.qc_compare_dir_label_2)
        qc_right_top.addStretch(1)
        self.qc_compare_diff_label = QLabel("修改内容：0/0")
        qc_right_top.addWidget(self.qc_compare_diff_label)
        qc_right_col_layout.addLayout(qc_right_top)
        self.qc_compare_dataform_2 = QTableView()
        self.qc_compare_dataform_2.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.qc_compare_dataform_2.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.qc_compare_dataform_2.setTextElideMode(Qt.TextElideMode.ElideNone)
        qc_right_col_layout.addWidget(self.qc_compare_dataform_2, 1)
        qc_compare_row.addWidget(qc_right_col, 3)

        self._qc_scroll_syncing = False
        self._qc_hscroll_syncing = False
        self.qc_compare_dataform_1.verticalScrollBar().valueChanged.connect(self.on_qc_compare_vertical_scroll_1)
        self.qc_compare_dataform_2.verticalScrollBar().valueChanged.connect(self.on_qc_compare_vertical_scroll_2)
        self.qc_compare_dataform_1.horizontalScrollBar().valueChanged.connect(self.on_qc_compare_horizontal_scroll_1)
        self.qc_compare_dataform_2.horizontalScrollBar().valueChanged.connect(self.on_qc_compare_horizontal_scroll_2)

        qc_compare_layout.addLayout(qc_compare_row)
        self.qc_compare_before_dir = ""
        self.qc_compare_after_dir = ""

        real_debug_page = QWidget()
        real_debug_layout = QVBoxLayout(real_debug_page)
        real_debug_layout.setContentsMargins(5, 5, 5, 5)
        rd_columns = QHBoxLayout()
        real_debug_layout.addLayout(rd_columns)
        rd_left = QWidget()
        rd_left_layout = QVBoxLayout(rd_left)
        rd_top_row = QHBoxLayout()
        self.rd_search_input = QLineEdit()
        self.rd_search_input.returnPressed.connect(self.on_rd_search)
        self.rd_search_button = QPushButton("搜索")
        self.rd_search_button.clicked.connect(self.on_rd_search)
        rd_top_row.addWidget(self.rd_search_input)
        rd_top_row.addWidget(self.rd_search_button)
        rd_top_row.addStretch(1)
        self.rd_sheet_combo = QComboBox()
        rd_top_row.addWidget(self.rd_sheet_combo)
        rd_left_layout.addLayout(rd_top_row)
        self.rd_id_list = QListWidget()
        self.rd_id_list.currentRowChanged.connect(self.on_rd_id_changed)
        rd_left_layout.addWidget(self.rd_id_list, 2)
        rd_columns.addWidget(rd_left, 1)
        rd_right = QWidget()
        rd_right_layout = QVBoxLayout(rd_right)
        rd_right_top = QHBoxLayout()
        rd_right_top.addWidget(QLabel("用户id"))
        self.rd_user_id_edit = QLineEdit()
        self.rd_user_id_edit.setFixedWidth(150)
        self.rd_user_id_edit.setValidator(QIntValidator(0, 2147483647))
        rd_right_top.addWidget(self.rd_user_id_edit)
        rd_right_top.addStretch(1)
        self.rd_execute_btn = QPushButton("执行质检")
        self.rd_execute_btn.setFixedWidth(100)
        rd_right_top.addWidget(self.rd_execute_btn)
        rd_right_layout.addLayout(rd_right_top)
        self.rd_table = QTableWidget(0, 3)
        self.rd_table.setHorizontalHeaderLabels(["stage", "npc", "dialog"])
        self.rd_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.rd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.rd_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.rd_table.setColumnWidth(0, 100)
        self.rd_table.setColumnWidth(1, 80)
        rd_right_layout.addWidget(self.rd_table)
        rd_columns.addWidget(rd_right, 3)
        sheets = self.template_config_manager.get_sheet_names()
        for s in sheets:
            self.rd_sheet_combo.addItem(str(s))
        self.rd_sheet_combo.currentTextChanged.connect(self.on_rd_sheet_changed)
        if self.rd_sheet_combo.count() > 0:
            self.on_rd_sheet_changed(self.rd_sheet_combo.currentText())
        self.rd_execute_btn.clicked.connect(self.on_rd_execute_debug)
        knowledge_row = QHBoxLayout()
        left_col_1 = QWidget()
        left_col_1_layout = QVBoxLayout(left_col_1)
        file_row = QHBoxLayout()
        self.kg_open_file_btn = QPushButton("打开文件")
        self.kg_open_file_btn.clicked.connect(self.on_open_knowledge_file)
        self.kg_knowledge_file_label = QLabel("未选择文件")
        file_row.addWidget(self.kg_open_file_btn)
        file_row.addWidget(self.kg_knowledge_file_label)
        file_row.addStretch(1)
        self.kg_seed_generate_btn = QPushButton("生成种子")
        self.kg_seed_generate_btn.clicked.connect(self.on_generate_seeds)
        file_row.addWidget(self.kg_seed_generate_btn)
        left_col_1_layout.addLayout(file_row)
        self.seed_scroll = QScrollArea()
        self.seed_scroll.setWidgetResizable(True)
        self.seed_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.seed_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.seed_grid_container = QWidget()
        self.seed_grid = QGridLayout(self.seed_grid_container)
        self.seed_grid.setContentsMargins(8, 8, 8, 8)
        self.seed_grid.setSpacing(8)
        self.seed_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.seed_scroll.setWidget(self.seed_grid_container)
        left_col_1_layout.addWidget(self.seed_scroll)
        self.voice_group = QGroupBox()
        voice_group_layout = QVBoxLayout(self.voice_group)
        rate_row = QHBoxLayout()
        self.kg_radio_44_stereo = QRadioButton("44.1kHz 128kbps 双声道")
        self.kg_radio_16_mono = QRadioButton("16kHz 24kbps 单声道")
        self.kg_radio_44_stereo.setChecked(True)
        rate_row.addWidget(self.kg_radio_44_stereo)
        rate_row.addWidget(self.kg_radio_16_mono)
        voice_group_layout.addLayout(rate_row)
        male_row = QHBoxLayout()
        male_row.addWidget(QLabel("男声:"))
        self.male_engine_combo = QComboBox()
        self.male_engine_combo.setFixedWidth(120)
        male_row.addWidget(self.male_engine_combo)
        self.male_voice_combo = QComboBox()
        self.male_voice_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        male_row.addWidget(self.male_voice_combo, stretch=1)
        voice_group_layout.addLayout(male_row)
        female_row = QHBoxLayout()
        female_row.addWidget(QLabel("女声:"))
        self.female_engine_combo = QComboBox()
        self.female_engine_combo.setFixedWidth(120)
        female_row.addWidget(self.female_engine_combo)
        self.female_voice_combo = QComboBox()
        self.female_voice_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        female_row.addWidget(self.female_voice_combo, stretch=1)
        voice_group_layout.addLayout(female_row)
        self._init_voice_seed_combos()
        left_col_1_layout.addWidget(self.voice_group)
        left_col_2 = QWidget()
        left_col_2_layout = QVBoxLayout(left_col_2)
        self.config_table = QTableWidget(0, 5)
        self.config_table.setHorizontalHeaderLabels(["选择", "speaker", "gender", "voice", "speed"])
        try:
            self.config_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        except Exception:
            pass
        try:
            self.config_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            self.config_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            self.config_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            self.config_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            self.config_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            self.config_table.setMinimumWidth(520)
            left_col_2.setMinimumWidth(540)
        except Exception:
            pass
        select_row = QHBoxLayout()
        self.kg_select_all_btn = QPushButton("取消全选")
        self.kg_select_all_btn.clicked.connect(self.on_toggle_select_all_config_rows)
        self.start_generate_btn = QPushButton("开始生成")
        self.start_generate_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.start_generate_btn.clicked.connect(self.on_start_generate_knowledge)
        select_row.addWidget(self.kg_select_all_btn)
        select_row.addStretch(1)
        self.kg_mode_radio_transvoice = QRadioButton("转音色")
        self.kg_mode_radio_tts = QRadioButton("TTS生成")
        self.kg_mode_group = QButtonGroup(self)
        self.kg_mode_group.addButton(self.kg_mode_radio_transvoice)
        self.kg_mode_group.addButton(self.kg_mode_radio_tts)
        self.kg_mode_group.setExclusive(True)
        self.kg_mode_radio_transvoice.setChecked(True)
        select_row.addWidget(self.kg_mode_radio_transvoice)
        select_row.addWidget(self.kg_mode_radio_tts)
        select_row.addWidget(self.start_generate_btn)
        left_col_2_layout.addLayout(select_row)
        left_col_2_layout.addWidget(self.config_table)
        self.kg_set_output_dir_btn = QPushButton("配置目录")
        self.kg_set_output_dir_btn.clicked.connect(self.on_set_knowledge_output_directory)
        self.kg_output_dir_display = QLineEdit()
        self.kg_output_dir_display.setReadOnly(True)
        self.kg_output_dir_display.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.kg_open_output_dir_btn = QPushButton("打开目录")
        self.kg_open_output_dir_btn.clicked.connect(self.on_open_knowledge_output_directory)
        try:
            default_out = self.config_manager.ensure_knowledge_output_directory()
            self.kg_output_dir_display.setText(default_out)
        except Exception:
            pass
        right_col = QWidget()
        right_col_layout = QVBoxLayout(right_col)
        self.knowledge_scroll = QScrollArea()
        self.knowledge_scroll.setWidgetResizable(True)
        self.knowledge_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.knowledge_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.knowledge_grid_container = QWidget()

        self.frames_grid = QGridLayout(self.knowledge_grid_container)
        self.frames_grid.setContentsMargins(8, 8, 8, 8)
        self.frames_grid.setSpacing(8)
        self.frames_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.knowledge_scroll.setWidget(self.knowledge_grid_container)
        header_row = QHBoxLayout()
        header_left = QHBoxLayout()
        header_left.addWidget(self.kg_set_output_dir_btn)
        header_left.addWidget(self.kg_output_dir_display, stretch=1)
        header_left.addWidget(self.kg_open_output_dir_btn)
        header_row.addLayout(header_left)
        header_row.addStretch(1)
        self.kg_selected_word_label = QLabel("")
        self.kg_selected_word_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self.kg_selected_word_label)
        header_row.addStretch(1)
        header_right = QHBoxLayout()
        self.kg_play_all_btn = QPushButton("全部播放")
        self.kg_upload_all_btn = QPushButton("☢️全部上传")
        self.kg_generate_all_btn = QPushButton("☢️全部生成")
        self.kg_generate_all_btn.clicked.connect(self.on_generate_all)
        header_right.addWidget(self.kg_play_all_btn)
        header_right.addWidget(self.kg_generate_all_btn)
        header_right.addWidget(self.kg_upload_all_btn)
        header_row.addLayout(header_right)
        right_col_layout.addLayout(header_row)
        right_col_layout.addWidget(self.knowledge_scroll)
        knowledge_row.addWidget(left_col_1)
        knowledge_row.addWidget(left_col_2)
        knowledge_row.addWidget(right_col, 1)
        knowledge_create_layout.addLayout(knowledge_row)
        self.qa_tab_widget.addTab(conversation_qa_page, "会话质检")
        self.qa_tab_widget.addTab(knowledge_create_page, "知识点生成")
        self.qa_tab_widget.addTab(knowledge_qa_page, "知识点质检")
        self.qa_tab_widget.addTab(qc_compare_page, "质检比对")
        self.qa_tab_widget.addTab(real_debug_page, "真机调试")
        try:
            self.qa_tab_widget.currentChanged.connect(self.on_qa_tab_changed)
        except Exception:
            pass
        main_layout.addWidget(self.qa_tab_widget, 1)
        self.kg_player = QMediaPlayer()
        self.kg_audio_output = QAudioOutput()
        self.kg_player.setAudioOutput(self.kg_audio_output)
        self._kg_playing = False
        self._kg_current_path = None
        try:
            self.kg_player.playbackStateChanged.connect(self._on_kg_playback_state_changed)
        except Exception:
            pass

    def on_toggle_select_all_config_rows(self):
        rows = self.config_table.rowCount()
        to_uncheck = (self.kg_select_all_btn.text() == "取消全选")
        for r in range(rows):
            item = self.config_table.item(r, 0)
            if not item:
                continue
            item.setCheckState(Qt.CheckState.Unchecked if to_uncheck else Qt.CheckState.Checked)
        if to_uncheck:
            self.kg_select_all_btn.setText("全选")
            print("已取消全选")
        else:
            self.kg_select_all_btn.setText("取消全选")
            print("已全选")

    def _build_knowledge_mapping_by_speaker(self):
        mapping = {}
        rows = self.config_table.rowCount()
        for r in range(rows):
            chk_item = self.config_table.item(r, 0)
            checked = (chk_item and chk_item.checkState() == Qt.CheckState.Checked)
            speaker_item = self.config_table.item(r, 1)
            gender_item = self.config_table.item(r, 2)
            voice_item = self.config_table.item(r, 3)
            speed_item = self.config_table.item(r, 4)
            speaker = speaker_item.text().strip() if speaker_item else ""
            gender = gender_item.text().strip().lower() if gender_item else ""
            voice = voice_item.text().strip() if voice_item else ""
            speed = speed_item.text().strip() if speed_item else ""
            if not speaker:
                continue
            if speaker not in mapping:
                mapping[speaker] = {}
            group = mapping[speaker].setdefault(voice or "", [])
            group.append({
                "checked": checked,
                "gender": gender,
                "voice": voice,
                "speed": speed,
                "row": r,
            })
        return mapping

    def _play_audio_path(self, path):
        if not path:
            return
        self.kg_player.stop()
        self._kg_current_path = path
        self.kg_player.setSource(QUrl.fromLocalFile(path))
        self.kg_player.play()

    def _kg_clear_grid(self):
        while self.frames_grid.count():
            item = self.frames_grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._kg_group_frames = {}
        self._kg_speed_frames = {}
        self._kg_speed_paths = {}
        self._kg_grid_row_index = 0

    def _seed_safe_name(self, s: str) -> str:
        if not s:
            return ""
        import re
        s2 = s.replace(' ', '_')
        s2 = re.sub(r"[^\w\u4e00-\u9fff_]", "", s2)
        return s2

    def _build_knowledge_seed_frames(self, knowledges: list):
        # 清空旧grid
        while self.seed_grid.count():
            item = self.seed_grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._seed_frames = {}
        self._seed_order = []
        row = 0
        for k in knowledges:
            k = str(k).strip()
            if not k:
                continue
            frame = QWidget()
            frame.setObjectName("knowledge_frame")
            frame.setStyleSheet("QWidget#knowledge_frame{background:none;border:1px solid #ffffff;border-radius:4px;}")
            hl = QHBoxLayout(frame)
            hl.setContentsMargins(8, 8, 8, 8)
            name_label = QLabel(k)
            _f = QFont()
            _f.setBold(True)
            name_label.setFont(_f)
            name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            hl.addWidget(name_label, stretch=1)
            rows_container = QWidget()
            rows_vlayout = QVBoxLayout(rows_container)
            rows_vlayout.setContentsMargins(0, 0, 0, 0)
            rows_vlayout.setSpacing(4)
            rows_meta = {}
            for speed_key, label_text in [("slow", "慢："), ("medium", "中："), ("fast", "快：")]:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(6)
                speed_label = QLabel(label_text)
                speed_label.setStyleSheet("color:#ffffff;")
                row_layout.addWidget(speed_label)
                male_play = QPushButton("男声")
                male_play.setEnabled(False)
                male_play.setFixedWidth(40)
                male_regen = QPushButton("🔄️")
                male_regen.setFixedWidth(24)
                female_play = QPushButton("女声")
                female_play.setEnabled(False)
                female_play.setFixedWidth(40)
                female_regen = QPushButton("🔄️")
                female_regen.setFixedWidth(24)
                row_layout.addWidget(male_play)
                row_layout.addWidget(male_regen)
                row_layout.addWidget(female_play)
                row_layout.addWidget(female_regen)
                row_widget.setVisible(False)
                rows_vlayout.addWidget(row_widget)
                rows_meta[speed_key] = {
                    'widget': row_widget,
                    'label': speed_label,
                    'male_play': male_play,
                    'male_regen': male_regen,
                    'female_play': female_play,
                    'female_regen': female_regen,
                    'male_path': None,
                    'female_path': None,
                }
                male_play.clicked.connect(lambda _, kk=k, sp=speed_key: self._on_seed_play(kk, 'male', sp))
                female_play.clicked.connect(lambda _, kk=k, sp=speed_key: self._on_seed_play(kk, 'female', sp))
                male_regen.clicked.connect(lambda _, kk=k, sp=speed_key: self._on_seed_regenerate(kk, 'male', sp))
                female_regen.clicked.connect(lambda _, kk=k, sp=speed_key: self._on_seed_regenerate(kk, 'female', sp))
            hl.addWidget(rows_container)
            # 点击选择frame
            frame.setProperty('knowledge', k)
            frame.installEventFilter(self)
            self.seed_grid.addWidget(frame, row, 0)
            self._seed_frames[k] = {
                'frame': frame,
                'label': name_label,
                'rows': rows_meta,
            }
            self._seed_order.append(k)
            row += 1
        print(f"已生成knowledge frames: {len(self._seed_order)}")

    def _update_seed_frames_initial_status(self):
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        seed_dir = os.path.join(base_out, 'seed')
        os.makedirs(seed_dir, exist_ok=True)
        for k, meta in (getattr(self, '_seed_frames', {}) or {}).items():
            safe = self._seed_safe_name(k)
            all_ready = True
            for sp in ['slow', 'medium', 'fast']:
                male_path = os.path.join(seed_dir, f"{safe}-seed-male-{sp}.mp3")
                female_path = os.path.join(seed_dir, f"{safe}-seed-female-{sp}.mp3")
                male_exists = os.path.exists(male_path)
                female_exists = os.path.exists(female_path)
                row_meta = meta['rows'].get(sp) or {}
                row_meta['male_path'] = male_path if male_exists else None
                row_meta['female_path'] = female_path if female_exists else None
                if row_meta.get('male_play'):
                    row_meta['male_play'].setEnabled(male_exists)
                if row_meta.get('female_play'):
                    row_meta['female_play'].setEnabled(female_exists)
                if row_meta.get('label'):
                    row_meta['label'].setStyleSheet("color:#000000;")
                meta['rows'][sp] = row_meta
                if not (male_exists and female_exists):
                    all_ready = False
            if all_ready:
                meta['frame'].setStyleSheet("QWidget#knowledge_frame{background:#88ff88;border:1px solid #ffffff;border-radius:4px;}")
            else:
                meta['frame'].setStyleSheet("QWidget#knowledge_frame{background:#ff8888;border:1px solid #ffffff;border-radius:4px;}")
            meta['label'].setStyleSheet("color:#000000;")

    def eventFilter(self, obj, event):
        try:
            from PyQt6.QtCore import QEvent
            if obj and obj.objectName() == 'knowledge_frame' and event.type() == QEvent.Type.MouseButtonPress:
                k = obj.property('knowledge')
                if k:
                    self._select_knowledge_frame(k)
                    self._on_seed_selected_knowledge(k)
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _select_knowledge_frame(self, knowledge):
        for k, meta in (getattr(self, '_seed_frames', {}) or {}).items():
            all_ready = True
            for sp in ['slow', 'medium', 'fast']:
                rm = (meta.get('rows') or {}).get(sp) or {}
                if not (rm.get('male_path') and rm.get('female_path')):
                    all_ready = False
                    break
            bg = '#88ff88' if all_ready else '#ff8888'
            if k == knowledge:
                meta['frame'].setStyleSheet(f"QWidget#knowledge_frame{{background:{bg};border:3px solid #8888ff;border-radius:4px;}}")
                for sp, row_meta in (meta.get('rows') or {}).items():
                    w = row_meta.get('widget')
                    if w:
                        w.setVisible(True)
                    lbl = row_meta.get('label')
                    if lbl:
                        lbl.setStyleSheet("color:#000000;")
                    mp = row_meta.get('male_play')
                    fp = row_meta.get('female_play')
                    mp_enabled = bool(row_meta.get('male_path')) and os.path.exists(row_meta.get('male_path') or '')
                    fp_enabled = bool(row_meta.get('female_path')) and os.path.exists(row_meta.get('female_path') or '')
                    if mp:
                        mp.setEnabled(mp_enabled)
                    if fp:
                        fp.setEnabled(fp_enabled)
            else:
                meta['frame'].setStyleSheet(f"QWidget#knowledge_frame{{background:{bg};border:1px solid #ffffff;border-radius:4px;}}")
                for sp, row_meta in (meta.get('rows') or {}).items():
                    w = row_meta.get('widget')
                    if w:
                        w.setVisible(False)
                    lbl = row_meta.get('label')
                    if lbl:
                        lbl.setStyleSheet("color:#000000;")

    def _on_seed_play(self, knowledge, gender, speed='medium'):
        meta = (getattr(self, '_seed_frames', {}) or {}).get(knowledge)
        if not meta:
            return
        row_meta = (meta.get('rows') or {}).get(speed) or {}
        path = row_meta.get('male_path') if gender == 'male' else row_meta.get('female_path')
        if not path or not os.path.exists(path):
            return
        self._play_audio_path(path)

    def _on_seed_regenerate(self, knowledge, gender, speed='medium'):
        self._run_seed_tasks([{'knowledge': knowledge, 'gender': gender, 'single': True, 'speed': speed}], max_workers=1)

    def on_generate_seeds(self):
        tasks = []
        frames = getattr(self, '_seed_frames', {}) or {}
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        seed_dir = os.path.join(base_out, 'seed')
        os.makedirs(seed_dir, exist_ok=True)
        for k in (getattr(self, '_seed_order', []) or []):
            safe = self._seed_safe_name(k)
            for sp in ['slow', 'medium', 'fast']:
                male_path = os.path.join(seed_dir, f"{safe}-seed-male-{sp}.mp3")
                female_path = os.path.join(seed_dir, f"{safe}-seed-female-{sp}.mp3")
                if not os.path.exists(male_path):
                    tasks.append({'knowledge': k, 'gender': 'male', 'single': False, 'speed': sp})
                if not os.path.exists(female_path):
                    tasks.append({'knowledge': k, 'gender': 'female', 'single': False, 'speed': sp})
        print(f"开始生成全部种子: 任务数 {len(tasks)} (已存在的将跳过)" )
        if not tasks:
            QMessageBox.information(self, "提示", "种子语音已全部存在，无需生成")
            return
        self._run_seed_tasks(tasks, max_workers=1)

    def _run_seed_tasks(self, tasks, max_workers=1):
        if not tasks:
            return
        self.lock_generation_ui()
        self._seed_show_dialog = any(not (t.get('single', False)) for t in tasks)
        self._seed_success_count = 0
        self._seed_fail_count = 0
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        seed_dir = os.path.join(base_out, 'seed')
        os.makedirs(seed_dir, exist_ok=True)
        def worker_fn(t):
            knowledge = t['knowledge']
            gender = t['gender']
            speed_key = t.get('speed', 'medium')
            safe = self._seed_safe_name(knowledge)
            out_path = os.path.join(seed_dir, f"{safe}-seed-{'male' if gender=='male' else 'female'}-{speed_key}.mp3")
            if os.path.exists(out_path) and not t.get('single', False):
                print(f"跳过已存在的种子: {knowledge} - {gender} - {speed_key}")
                return {'status': 'skipped', 'knowledge': knowledge, 'gender': gender, 'path': out_path, 'single': t.get('single', False), 'speed': speed_key}
            engine = self.male_engine_combo.currentText().strip().lower() if gender == 'male' else self.female_engine_combo.currentText().strip().lower()
            voice = self.male_voice_combo.currentText().strip() if gender == 'male' else self.female_voice_combo.currentText().strip()
            from duoki_editor.utils.constants_loader import constants_loader
            vs = constants_loader.get_voice_speed()
            idx_map = {'slow': 0, 'medium': 1, 'fast': 2}
            idx = idx_map.get(speed_key, 1)
            gender_key = 'male' if gender == 'male' else 'female'
            arr = vs.get(gender_key)
            if isinstance(arr, (list, tuple)) and len(arr) > idx:
                speed_val = arr[idx]
            else:
                speed_val = 1.0
            tts_cache = TTSCache()
            if engine == 'elevenlabs':
                stab = 0.5 if (gender == 'female' and t.get('single', False)) else 1
                r = tts_cache.call_elevenlabs_tts(knowledge, voice_id=voice, speed=speed_val, stability=stab)
            else:
                r = tts_cache.call_tts_api(knowledge, speaker=None, speed=speed_val, emotion=None, engine=engine, voice_id_override=voice)
            if 'error' in (r or {}):
                print(f"种子生成失败: {knowledge}-{gender}: {json.dumps(r, ensure_ascii=False)}")
                return {'status': 'error', 'knowledge': knowledge, 'gender': gender, 'single': t.get('single', False), 'speed': speed_key}
            src = r.get('audio_path')
            if not src or not os.path.exists(src):
                print(f"种子生成失败: {knowledge}-{gender}: {json.dumps(r, ensure_ascii=False)}")
                return {'status': 'error', 'knowledge': knowledge, 'gender': gender, 'single': t.get('single', False), 'speed': speed_key}
            import shutil
            shutil.copy2(src, out_path)
            return {'status': 'success', 'knowledge': knowledge, 'gender': gender, 'path': out_path, 'single': t.get('single', False), 'speed': speed_key}
        self._seed_runner = ThreadPoolRunner(tasks, worker_fn, max_workers=max_workers)
        def on_item_done(res):
            knowledge = res.get('knowledge')
            gender = res.get('gender')
            path = res.get('path')
            speed_key = res.get('speed', 'medium')
            status = res.get('status')
            meta = (getattr(self, '_seed_frames', {}) or {}).get(knowledge)
            if not meta:
                return
            row_meta = (meta.get('rows') or {}).get(speed_key) or {}
            updated = False
            if status in ('success', 'skipped') and path and os.path.exists(path):
                if gender == 'male':
                    row_meta['male_path'] = path
                    if row_meta.get('male_play'):
                        row_meta['male_play'].setEnabled(True)
                else:
                    row_meta['female_path'] = path
                    if row_meta.get('female_play'):
                        row_meta['female_play'].setEnabled(True)
                updated = True
            else:
                print(f"重新生成失败或未更新: {knowledge} - {gender} - {speed_key}")
            meta['rows'][speed_key] = row_meta
            # 更新背景色与标签颜色，要求六个文件都存在
            all_ready = True
            for sp in ['slow', 'medium', 'fast']:
                rm2 = meta.get('rows', {}).get(sp) or {}
                if not (rm2.get('male_path') and rm2.get('female_path')):
                    all_ready = False
                    break
            if all_ready:
                meta['frame'].setStyleSheet("QWidget#knowledge_frame{background:#88ff88;border:1px solid #ffffff;border-radius:4px;}")
            else:
                meta['frame'].setStyleSheet("QWidget#knowledge_frame{background:#ff8888;border:1px solid #ffffff;border-radius:4px;}")
            meta['label'].setStyleSheet("color:#000000;")
            for sp, row_meta2 in (meta.get('rows') or {}).items():
                lbl2 = row_meta2.get('label')
                if lbl2:
                    lbl2.setStyleSheet("color:#000000;")
            if status == 'success':
                self._seed_success_count += 1
            elif status == 'skipped':
                self._seed_skipped_count = getattr(self, '_seed_skipped_count', 0) + 1
            else:
                self._seed_fail_count += 1
            if res.get('single') and hasattr(self, 'toast_manager') and self.toast_manager:
                if status == 'success':
                    self.toast_manager.show_success("重新生成成功")
                    if path and os.path.exists(path):
                        self._play_audio_path(path)
                elif status == 'skipped':
                    self.toast_manager.show_toast("已存在，跳过生成")
                else:
                    self.toast_manager.show_error("重新生成失败")
        def on_item_failed(res):
            knowledge = res.get('knowledge')
            meta = (getattr(self, '_seed_frames', {}) or {}).get(knowledge)
            if meta:
                meta['frame'].setStyleSheet("QWidget#knowledge_frame{background:#ff8888;border:1px solid #ffffff;border-radius:4px;}")
                meta['label'].setStyleSheet("color:#000000;")
            self._seed_fail_count += 1
        def on_finished():
            self.unlock_generation_ui()
            succ = getattr(self, '_seed_success_count', 0)
            fail = getattr(self, '_seed_fail_count', 0)
            skipped = getattr(self, '_seed_skipped_count', 0)
            print(f"种子语音生成完成: 成功 {succ} 个, 失败 {fail} 个, 跳过 {skipped} 个")
            if getattr(self, '_seed_show_dialog', False):
                try:
                    QMessageBox.information(self, "提示", f"种子语音生成完成\n成功: {succ}\n失败: {fail}\n跳过: {skipped}")
                except Exception:
                    pass
        try:
            self._seed_runner.item_done.connect(on_item_done)
            self._seed_runner.item_failed.connect(on_item_failed)
            self._seed_runner.finished.connect(on_finished)
        except Exception:
            pass
        self._seed_runner.start()

    def set_generation_ui_locked(self, locked: bool):
        self._generation_ui_locked = bool(locked)
        toggles = [
            getattr(self, 'kg_open_file_btn', None),
            getattr(self, 'kg_seed_generate_btn', None),
            getattr(self, 'kg_generate_all_btn', None),
            getattr(self, 'kg_select_all_btn', None),
            getattr(self, 'start_generate_btn', None),
            getattr(self, 'kg_set_output_dir_btn', None),
            getattr(self, 'kg_open_output_dir_btn', None),
            getattr(self, 'kg_play_all_btn', None),
            getattr(self, 'kg_upload_all_btn', None),
            getattr(self, 'male_engine_combo', None),
            getattr(self, 'male_voice_combo', None),
            getattr(self, 'female_engine_combo', None),
            getattr(self, 'female_voice_combo', None),
            getattr(self, 'kg_radio_44_stereo', None),
            getattr(self, 'kg_radio_16_mono', None),
            getattr(self, 'kg_mode_radio_transvoice', None),
            getattr(self, 'kg_mode_radio_tts', None),
            getattr(self, 'seed_scroll', None),
            getattr(self, 'config_table', None),
        ]
        for w in toggles:
            if w:
                w.setEnabled(not locked)

    def lock_generation_ui(self):
        self.set_generation_ui_locked(True)

    def unlock_generation_ui(self):
        self.set_generation_ui_locked(False)

    def _init_voice_seed_combos(self):
        from duoki_editor.utils.constants_loader import constants_loader
        seed = constants_loader.get_voice_seed()
        male_list = seed.get('男声') or []
        female_list = seed.get('女声') or []
        self.male_engine_combo.clear()
        self.female_engine_combo.clear()
        male_engines = []
        female_engines = []
        for item in male_list:
            t = str(item.get('tts', '')).strip()
            if t and t not in male_engines:
                male_engines.append(t)
        for item in female_list:
            t = str(item.get('tts', '')).strip()
            if t and t not in female_engines:
                female_engines.append(t)
        if male_engines:
            self.male_engine_combo.addItems(male_engines)
        if female_engines:
            self.female_engine_combo.addItems(female_engines)
        self.male_engine_combo.currentTextChanged.connect(self._on_male_engine_changed)
        self.female_engine_combo.currentTextChanged.connect(self._on_female_engine_changed)
        self._on_male_engine_changed(self.male_engine_combo.currentText())
        self._on_female_engine_changed(self.female_engine_combo.currentText())

    def _on_male_engine_changed(self, engine):
        from duoki_editor.utils.constants_loader import constants_loader
        seed = constants_loader.get_voice_seed()
        male_list = seed.get('男声') or []
        voices = []
        for item in male_list:
            if str(item.get('tts', '')).strip() == str(engine).strip():
                for v in item.get('voice') or []:
                    vs = str(v).strip()
                    if vs and vs not in voices:
                        voices.append(vs)
        self.male_voice_combo.clear()
        if voices:
            self.male_voice_combo.addItems(voices)

    def _on_female_engine_changed(self, engine):
        from duoki_editor.utils.constants_loader import constants_loader
        seed = constants_loader.get_voice_seed()
        female_list = seed.get('女声') or []
        voices = []
        for item in female_list:
            if str(item.get('tts', '')).strip() == str(engine).strip():
                for v in item.get('voice') or []:
                    vs = str(v).strip()
                    if vs and vs not in voices:
                        voices.append(vs)
        self.female_voice_combo.clear()
        if voices:
            self.female_voice_combo.addItems(voices)

    # 去掉原音色播放按钮

    def _play_speed_conv(self, row):
        paths = getattr(self, '_kg_speed_paths', {}).get(row) or {}
        p = paths.get('conv')
        if p:
            self._play_audio_path(p)

    def _kg_set_speed_frame_status(self, row, status, conv_path=None):
        sf = getattr(self, '_kg_speed_frames', {}).get(row)
        if not sf:
            return
        widget = sf['widget']
        play_conv_btn = sf['play_conv_btn']
        reject_btn = sf['reject_btn']
        upload_btn = sf['upload_btn']
        trans_btn = sf.get('trans_btn')
        tts_btn = sf.get('tts_btn')
        if status == 'idle':
            widget.setStyleSheet("QWidget#speed_frame{background: none; border:1px solid #ffffff; border-radius:4px;} QWidget#speed_frame QLabel{color:#ffffff;}")
            play_conv_btn.setVisible(False)
            reject_btn.setVisible(False)
            upload_btn.setVisible(False)
            if trans_btn:
                trans_btn.setVisible(True)
                trans_btn.setEnabled(True)
            if tts_btn:
                tts_btn.setVisible(True)
                tts_btn.setEnabled(True)
            self._kg_speed_paths[row] = {'conv': None}
        elif status == 'partial':
            widget.setStyleSheet("QWidget#speed_frame{background: none; border:1px solid #ffffff; border-radius:4px;} QWidget#speed_frame QLabel{color:#ffffff;}")
            self._kg_speed_paths[row] = {'conv': conv_path}
            play_conv_btn.setVisible(True)
            play_conv_btn.setEnabled(bool(conv_path))
            reject_btn.setVisible(False)
            upload_btn.setVisible(False)
            if trans_btn:
                trans_btn.setVisible(False)
            if tts_btn:
                tts_btn.setVisible(False)
        elif status == 'success':
            widget.setStyleSheet("QWidget#speed_frame{background:#88ff88; border:1px solid #ffffff; border-radius:4px;} QWidget#speed_frame QLabel{color:#000000;}")
            self._kg_speed_paths[row] = {'conv': conv_path}
            play_conv_btn.setVisible(True)
            play_conv_btn.setEnabled(bool(conv_path))
            reject_btn.setVisible(True)
            reject_btn.setEnabled(True)
            upload_btn.setVisible(True)
            upload_btn.setEnabled(True)
            if trans_btn:
                trans_btn.setVisible(False)
            if tts_btn:
                tts_btn.setVisible(False)
        elif status == 'error':
            widget.setStyleSheet("QWidget#speed_frame{background:#ff8888; border:1px solid #ffffff; border-radius:4px;} QWidget#speed_frame QLabel{color:#ffffff;}")
            self._kg_speed_paths[row] = {'conv': None}
            play_conv_btn.setVisible(True)
            play_conv_btn.setEnabled(False)
            reject_btn.setVisible(True)
            reject_btn.setEnabled(False)
            upload_btn.setVisible(True)
            upload_btn.setEnabled(False)
            if trans_btn:
                trans_btn.setVisible(False)
            if tts_btn:
                tts_btn.setVisible(False)

    def _kg_prepare_frames(self, mapping):
        self._kg_clear_grid()
        self._kg_group_frames = {}
        self._kg_speed_frames = {}
        self._kg_speed_paths = {}
        for speaker, voices in mapping.items():
            for voice_name, items in voices.items():
                frame, inner_grid, left_label = self._kg_create_group_container(speaker, voice_name)
                col = 0
                row_g = 0
                for it in items:
                    r = it['row']
                    speed_val = it['speed']
                    sf_widget, play_conv_btn, reject_btn, upload_btn, trans_btn, tts_btn = self._kg_create_speed_frame_widgets(f"速度：{speed_val}", 60)
                    play_conv_btn.clicked.connect(lambda _, rr=r: self._play_speed_conv(rr))
                    reject_btn.clicked.connect(lambda _, rr=r: self._kg_reject_row(rr))
                    trans_btn.clicked.connect(lambda _, rr=r: self._kg_generate_single_row(rr, mode='transvoice'))
                    tts_btn.clicked.connect(lambda _, rr=r: self._kg_generate_single_row(rr, mode='tts'))
                    play_conv_btn.setVisible(False)
                    reject_btn.setVisible(False)
                    upload_btn.setVisible(False)
                    trans_btn.setVisible(False)
                    tts_btn.setVisible(False)
                    inner_grid.addWidget(sf_widget, row_g, col)
                    self._kg_speed_frames[r] = {
                        'widget': sf_widget,
                        'play_conv_btn': play_conv_btn,
                        'reject_btn': reject_btn,
                        'upload_btn': upload_btn,
                        'trans_btn': trans_btn,
                        'tts_btn': tts_btn,
                        'speaker': speaker,
                        'voice_name': voice_name,
                        'speed': speed_val,
                        'gender': it.get('gender', ''),
                    }
                    col += 1
                    if col >= 3:
                        col = 0
                        row_g += 1
                idx = getattr(self, '_kg_grid_row_index', 0)
                self.frames_grid.addWidget(frame, idx, 0)
                self._kg_grid_row_index = idx + 1
                self._kg_group_frames[(speaker, voice_name)] = {'frame': frame, 'left_label': left_label}

    def _kg_reject_row(self, row):
        if getattr(self, '_kg_playing', False):
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_warning("音频播放中")
            return
        knowledge = str(getattr(self, '_kg_current_knowledge', '')).strip()
        if not knowledge:
            return
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        safe_knowledge = knowledge.replace(' ', '_')
        meta = getattr(self, '_kg_speed_frames', {}).get(row) or {}
        voice_name = str(meta.get('voice_name', '')).strip()
        speed_str = str(meta.get('speed', '')).strip() or '1'
        gender = str(meta.get('gender', '')).strip().lower()
        voice_override = self.male_voice_combo.currentText().strip() if gender == 'male' else self.female_voice_combo.currentText().strip()
        paths = getattr(self, '_kg_speed_paths', {}).get(row) or {}
        conv_path = paths.get('conv') or os.path.join(base_out, f"{safe_knowledge}-{voice_name}-{speed_str}.mp3")
        # 停止并清空播放器，避免文件占用
        self.kg_player.stop()
        try:
            self.kg_player.setSource(QUrl())
        except Exception:
            pass
        if conv_path and os.path.exists(conv_path):
            os.remove(conv_path)
            print(f"打回删除转音色: {conv_path}")
        self._kg_set_speed_frame_status(row, 'idle')
        self._mark_config_row_color(row, '#FFFFFF')
        item0 = self.config_table.item(row, 0)
        if item0:
            item0.setCheckState(Qt.CheckState.Checked)
        if hasattr(self, '_kg_finished_rows') and row in self._kg_finished_rows:
            self._kg_finished_rows.discard(row)
        self._kg_update_progress_label()

    def _on_kg_playback_state_changed(self, state):
        from PyQt6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._kg_playing = True
        else:
            self._kg_playing = False
            try:
                self.kg_player.setSource(QUrl())
            except Exception:
                pass

    def _mark_config_row_color(self, row, color_name):
        cols = self.config_table.columnCount()
        for c in range(cols):
            if c == 0:
                continue
            item = self.config_table.item(row, c)
            if item:
                item.setForeground(QColor(color_name))

    def on_start_generate_knowledge(self):
        knowledge = str(getattr(self, '_kg_current_knowledge', '')).strip()
        if not knowledge:
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_warning("请选择知识点")
            return
        self._kg_transcode_to_16k_mono = bool(getattr(self, 'kg_radio_16_mono', None) and self.kg_radio_16_mono.isChecked())
        self.lock_generation_ui()
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        mapping = self._build_knowledge_mapping_by_speaker()
        tasks = []
        group_counts = {}
        for speaker, voices in mapping.items():
            for voice_name, items in voices.items():
                selected = [it for it in items if it['checked']]
                if not selected:
                    continue
                key = (speaker, voice_name)
                group_counts[key] = len(selected)
                for it in selected:
                    gender = it['gender']
                    speed_val = it['speed']
                    if gender == 'male':
                        engine = self.male_engine_combo.currentText().strip().lower()
                        voice_override = self.male_voice_combo.currentText().strip()
                    else:
                        engine = self.female_engine_combo.currentText().strip().lower()
                        voice_override = self.female_voice_combo.currentText().strip()
                    tasks.append({
                        'speaker': speaker,
                        'voice_name': voice_name,
                        'row': it['row'],
                        'gender': gender,
                        'speed_val': speed_val,
                        'engine': engine,
                        'voice_override': voice_override,
                        'knowledge': knowledge,
                        'base_out': base_out
                    })
        self._kg_group_counts = group_counts
        self._kg_group_results = {k: [] for k in group_counts.keys()}
        self._kg_grid_row_index = getattr(self, '_kg_grid_row_index', 0)
        
        def worker_fn(t):
            if getattr(self._kg_runner, '_stopping', False):
                return {'status': 'aborted', 'row': t.get('row'), 'speaker': t.get('speaker'), 'voice_name': t.get('voice_name'), 'speed': str(t.get('speed_val', '1'))}
            speed_str = (str(t['speed_val']).strip() or '1')
            tts_cache = TTSCache()
            speaker = t['speaker']
            voice_name = t['voice_name']
            knowledge = t['knowledge']
            base_out = t['base_out']
            gender = str(t.get('gender', '')).strip().lower()
            if getattr(self._kg_runner, '_stopping', False):
                return {'status': 'aborted', 'row': t.get('row'), 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
            use_transvoice = bool(getattr(self, '_generate_all_running', False) or (hasattr(self, 'kg_mode_radio_transvoice') and self.kg_mode_radio_transvoice.isChecked()))
            if use_transvoice:
                print("使用模式：转音色")
                safe_seed = self._seed_safe_name(knowledge)
                seed_dir = os.path.join(base_out, 'seed')
                seed_type = ''
                if hasattr(self, 'knowledge_mapping_df'):
                    seed_type = str(self.knowledge_mapping_df.iloc[t['row']].get('speed_type', '')).strip().lower()
                if seed_type not in ['slow', 'medium', 'fast']:
                    print("缺少或无效speed_type，跳过该行的音色转换")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                seed_path = os.path.join(seed_dir, f"{safe_seed}-seed-{'male' if gender=='male' else 'female'}-{seed_type}.mp3")
                if not os.path.exists(seed_path):
                    print(f"找不到种子音频: {seed_path}")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                change_voice_id = ''
                if hasattr(self, 'knowledge_mapping_df'):
                    change_voice_id = str(self.knowledge_mapping_df.iloc[t['row']].get('change_voice_id', '')).strip()
                if not change_voice_id:
                    print("缺少转换音色ID")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                conv_result = tts_cache.call_elevenlabs_voice_changer(seed_path, change_voice_id)
                conv_path = None
                if 'audio_path' in (conv_result or {}):
                    conv_src = conv_result['audio_path']
                    safe_knowledge = knowledge.replace(' ', '_')
                    conv_filename = f"{safe_knowledge}-{voice_name}-{speed_str}.mp3"
                    conv_path = os.path.join(base_out, conv_filename)
                    import shutil
                    shutil.copy2(conv_src, conv_path)
                    if bool(getattr(self, '_kg_transcode_to_16k_mono', False)):
                        print(f"开始转码: 16kHz 24kbps 单声道 -> {conv_path}")
                        conv_path = self._apply_audio_transcode_if_needed(conv_path)
                        print(f"转码完成: {conv_path}")
                else:
                    print(f"音色转换失败接口返回: {json.dumps(conv_result, ensure_ascii=False)}")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                return {'status': 'success', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str, 'conv_path': conv_path}
            else:
                print("使用模式：TTS生成")
                voice_value = ''
                if hasattr(self, 'knowledge_mapping_df'):
                    try:
                        voice_value = str(self.knowledge_mapping_df.iloc[t['row']].get('voice', '')).strip()
                    except Exception:
                        voice_value = ''
                if not voice_value:
                    # 尝试从配置表获取
                    item = self.config_table.item(t['row'], 3) if hasattr(self, 'config_table') else None
                    voice_value = str(item.text()).strip() if item else ''
                if not voice_value:
                    print("缺少音色配置，无法进行TTS生成")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                prefix = voice_value.split('_', 1)[0].lower() if '_' in voice_value else voice_value.lower()
                override = voice_value.split('_', 1)[1] if '_' in voice_value else voice_value
                print(f"TTS引擎: {prefix}, voice_id: {override}")
                text = knowledge
                result = None
                if prefix == 'minimax':
                    result = tts_cache.call_minimax_tts(text, speaker="", speed=t['speed_val'], emotion=None, voice_id_override=override)
                elif prefix == 'volcano':
                    result = tts_cache.call_volcano_tts(text, speaker="", speed=t['speed_val'], emotion=None, voice_id_override=override)
                else:
                    result = tts_cache.call_minimax_tts(text, speaker="", speed=t['speed_val'], emotion=None, voice_id_override=override)
                if 'audio_path' in (result or {}):
                    conv_src = result['audio_path']
                    safe_knowledge = knowledge.replace(' ', '_')
                    conv_filename = f"{safe_knowledge}-{voice_name}-{speed_str}.mp3"
                    conv_path = os.path.join(base_out, conv_filename)
                    import shutil
                    shutil.copy2(conv_src, conv_path)
                    if bool(getattr(self, '_kg_transcode_to_16k_mono', False)):
                        print(f"开始转码: 16kHz 24kbps 单声道 -> {conv_path}")
                        conv_path = self._apply_audio_transcode_if_needed(conv_path)
                        print(f"转码完成: {conv_path}")
                    return {'status': 'success', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str, 'conv_path': conv_path}
                else:
                    print(f"TTS生成失败: {json.dumps(result, ensure_ascii=False)}")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
        self._kg_runner = ThreadPoolRunner(tasks, worker_fn, max_workers=3)
        self._kg_runner.item_started.connect(self._on_kg_item_started)
        self._kg_runner.item_done.connect(self._on_kg_item_done)
        self._kg_runner.item_failed.connect(self._on_kg_item_failed)
        self._kg_runner.finished.connect(self._on_kg_finished)
        self._kg_runner.start()

    def _on_kg_item_started(self, t):
        row = t.get('row')
        if row is not None:
            self._kg_set_speed_frame_status(row, 'idle')
            self._mark_config_row_color(row, '#FFA500')
            if hasattr(self, '_kg_finished_rows') and row in self._kg_finished_rows:
                self._kg_finished_rows.discard(row)
            self._kg_update_progress_label()

    def _on_kg_item_done(self, res):
        row = res.get('row')
        status = res.get('status')
        if row is not None:
            if status == 'success':
                self._kg_set_speed_frame_status(row, 'success', conv_path=res.get('conv_path'))
                self._mark_config_row_color(row, '#00AA00')
                item0 = self.config_table.item(row, 0)
                if item0:
                    item0.setCheckState(Qt.CheckState.Unchecked)
                cp = res.get('conv_path')
                if cp and os.path.exists(cp) and bool(res.get('autoplay')):
                    print(f"自动播放生成音频: {cp}")
                    self._play_audio_path(cp)
                if hasattr(self, '_kg_finished_rows'):
                    self._kg_finished_rows.add(row)
            else:
                self._kg_set_speed_frame_status(row, 'error')
                self._mark_config_row_color(row, '#CC0000')
                if hasattr(self, '_kg_finished_rows') and row in self._kg_finished_rows:
                    self._kg_finished_rows.discard(row)
            self._kg_update_progress_label()

    def _on_kg_item_failed(self, obj):
        t = obj.get('task', {})
        row = t.get('row')
        if row is not None:
            self._kg_set_speed_frame_status(row, 'error')
            self._mark_config_row_color(row, '#CC0000')
            if hasattr(self, '_kg_finished_rows') and row in self._kg_finished_rows:
                self._kg_finished_rows.discard(row)
            self._kg_update_progress_label()

    def _kg_add_group_frame(self, key):
        speaker, voice_name = key
        items = self._kg_group_results.get(key) or []
        try:
            items = sorted(items, key=lambda r: float(str(r.get('speed', '1')) or '1'))
        except Exception:
            pass
        frame, inner_grid, left_label = self._kg_create_group_container(speaker, voice_name)
        col = 0
        row_i = 0
        for r in items:
            sf_widget, play_conv_btn, reject_btn, upload_btn, _trans_btn, _tts_btn = self._kg_create_speed_frame_widgets(f"速度：{r.get('speed')}", 80)
            if r.get('status') == 'success':
                sf_widget.setStyleSheet("QWidget#speed_frame{background:#ffffff; border-radius:4px;} QWidget#speed_frame QLabel{color:#000000;}")
                if r.get('conv_path'):
                    play_conv_btn.clicked.connect(lambda _, p=r.get('conv_path'): self._play_audio_path(p))
                else:
                    play_conv_btn.setEnabled(False)
            else:
                sf_widget.setStyleSheet("QWidget#speed_frame{background:#ff6666; border-radius:4px;} QWidget#speed_frame QLabel{color:#ffffff;}")
                play_conv_btn.setEnabled(False)
                reject_btn.setEnabled(False)
                upload_btn.setEnabled(False)
            inner_grid.addWidget(sf_widget, row_i, col)
            col += 1
            if col >= 3:
                col = 0
                row_i += 1
        idx = getattr(self, '_kg_grid_row_index', 0)
        self.frames_grid.addWidget(frame, idx, 0)
        self._kg_grid_row_index = idx + 1
        self._kg_group_frames[(speaker, voice_name)] = {'frame': frame, 'left_label': left_label}

    def _kg_create_group_container(self, speaker, voice_name):
        frame = QGroupBox("")
        frame.setStyleSheet("QGroupBox{border:1px solid #ffffff;border-radius:6px;margin-top:6px;} QGroupBox::title{subcontrol-origin: margin; left:10px; padding:0 3px; color:#ffffff;}")
        vlayout = QVBoxLayout(frame)
        top_row = QHBoxLayout()
        knowledge_text = str(getattr(self, '_kg_current_knowledge', '') or '')
        left_label = QLabel(knowledge_text)
        f = QFont()
        f.setBold(True)
        left_label.setFont(f)
        top_row.addWidget(left_label)
        top_row.addStretch(1)
        right_label = QLabel(f"{speaker} {voice_name}")
        top_row.addWidget(right_label)
        vlayout.addLayout(top_row)
        inner_grid = QGridLayout()
        inner_grid.setColumnStretch(0, 1)
        inner_grid.setColumnStretch(1, 1)
        inner_grid.setColumnStretch(2, 1)
        vlayout.addLayout(inner_grid)
        return frame, inner_grid, left_label

    def _kg_update_group_labels(self, knowledge):
        for meta in (getattr(self, '_kg_group_frames', {}) or {}).values():
            lbl = meta.get('left_label')
            if lbl:
                lbl.setText(str(knowledge))

    def _kg_create_speed_frame_widgets(self, speed_text, play_width):
        sf_widget = QWidget()
        sf_widget.setObjectName("speed_frame")
        sf_widget.setStyleSheet("QWidget#speed_frame{background: none; border:1px solid #ffffff; border-radius:4px;} QWidget#speed_frame QLabel{color:#ffffff;}")
        sfl = QVBoxLayout(sf_widget)
        row = QHBoxLayout()
        sp_label = QLabel(speed_text)
        sp_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(sp_label)
        row.addStretch(1)
        trans_btn = QPushButton("转音色")
        trans_btn.setFixedWidth(70)
        trans_btn.setEnabled(True)
        tts_btn = QPushButton("TTS生成")
        tts_btn.setFixedWidth(70)
        tts_btn.setEnabled(True)
        play_conv_btn = QPushButton("播放")
        play_conv_btn.setFixedWidth(play_width)
        play_conv_btn.setEnabled(False)
        reject_btn = QPushButton("打回")
        reject_btn.setFixedWidth(40)
        reject_btn.setEnabled(False)
        upload_btn = QPushButton("上传")
        upload_btn.setFixedWidth(40)
        upload_btn.setEnabled(False)
        row.addWidget(trans_btn, 1)
        row.addWidget(tts_btn, 1)
        row.addWidget(reject_btn, 1)
        row.addWidget(upload_btn, 1)
        row.addWidget(play_conv_btn, 2)
        sfl.addLayout(row)
        return sf_widget, play_conv_btn, reject_btn, upload_btn, trans_btn, tts_btn

    def _kg_generate_single_row(self, row, mode):
        knowledge = str(getattr(self, '_kg_current_knowledge', '')).strip()
        if not knowledge:
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_warning("请选择知识点")
            return
        self._kg_transcode_to_16k_mono = bool(getattr(self, 'kg_radio_16_mono', None) and self.kg_radio_16_mono.isChecked())
        self.lock_generation_ui()
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        meta = getattr(self, '_kg_speed_frames', {}).get(row) or {}
        speaker = meta.get('speaker')
        voice_name = meta.get('voice_name')
        gender = meta.get('gender')
        speed_val = meta.get('speed')
        tasks = [{
            'speaker': speaker,
            'voice_name': voice_name,
            'row': row,
            'gender': gender,
            'speed_val': speed_val,
            'knowledge': knowledge,
            'base_out': base_out,
            'mode': mode
        }]
        def worker_fn(t):
            if getattr(self._kg_runner, '_stopping', False):
                return {'status': 'aborted', 'row': t.get('row'), 'speaker': t.get('speaker'), 'voice_name': t.get('voice_name'), 'speed': str(t.get('speed_val', '1'))}
            speed_str = (str(t['speed_val']).strip() or '1')
            tts_cache = TTSCache()
            speaker = t['speaker']
            voice_name = t['voice_name']
            knowledge = t['knowledge']
            base_out = t['base_out']
            gender = str(t.get('gender', '')).strip().lower()
            use_transvoice = str(t.get('mode', '')).strip().lower() == 'transvoice'
            if use_transvoice:
                print("使用模式：转音色")
                safe_seed = self._seed_safe_name(knowledge)
                seed_dir = os.path.join(base_out, 'seed')
                seed_type = ''
                if hasattr(self, 'knowledge_mapping_df'):
                    seed_type = str(self.knowledge_mapping_df.iloc[t['row']].get('speed_type', '')).strip().lower()
                if seed_type not in ['slow', 'medium', 'fast']:
                    print("缺少或无效speed_type，跳过该行的音色转换")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                seed_path = os.path.join(seed_dir, f"{safe_seed}-seed-{'male' if gender=='male' else 'female'}-{seed_type}.mp3")
                if not os.path.exists(seed_path):
                    print(f"找不到种子音频: {seed_path}")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                change_voice_id = ''
                if hasattr(self, 'knowledge_mapping_df'):
                    change_voice_id = str(self.knowledge_mapping_df.iloc[t['row']].get('change_voice_id', '')).strip()
                if not change_voice_id:
                    print("缺少转换音色ID")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                conv_result = tts_cache.call_elevenlabs_voice_changer(seed_path, change_voice_id)
                conv_path = None
                if 'audio_path' in (conv_result or {}):
                    conv_src = conv_result['audio_path']
                    safe_knowledge = knowledge.replace(' ', '_')
                    conv_filename = f"{safe_knowledge}-{voice_name}-{speed_str}.mp3"
                    conv_path = os.path.join(base_out, conv_filename)
                    import shutil
                    shutil.copy2(conv_src, conv_path)
                    if bool(getattr(self, '_kg_transcode_to_16k_mono', False)):
                        print(f"开始转码: 16kHz 24kbps 单声道 -> {conv_path}")
                        conv_path = self._apply_audio_transcode_if_needed(conv_path)
                        print(f"转码完成: {conv_path}")
                else:
                    print(f"音色转换失败接口返回: {json.dumps(conv_result, ensure_ascii=False)}")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                return {'status': 'success', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str, 'conv_path': conv_path, 'autoplay': True}
            else:
                print("使用模式：TTS生成")
                voice_value = ''
                if hasattr(self, 'knowledge_mapping_df'):
                    try:
                        voice_value = str(self.knowledge_mapping_df.iloc[t['row']].get('voice', '')).strip()
                    except Exception:
                        voice_value = ''
                if not voice_value:
                    item = self.config_table.item(t['row'], 3) if hasattr(self, 'config_table') else None
                    voice_value = str(item.text()).strip() if item else ''
                if not voice_value:
                    print("缺少音色配置，无法进行TTS生成")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
                prefix = voice_value.split('_', 1)[0].lower() if '_' in voice_value else voice_value.lower()
                override = voice_value.split('_', 1)[1] if '_' in voice_value else voice_value
                print(f"TTS引擎: {prefix}, voice_id: {override}")
                text = knowledge
                result = None
                if prefix == 'minimax':
                    result = tts_cache.call_minimax_tts(text, speaker="", speed=t['speed_val'], emotion=None, voice_id_override=override)
                elif prefix == 'volcano':
                    result = tts_cache.call_volcano_tts(text, speaker="", speed=t['speed_val'], emotion=None, voice_id_override=override)
                else:
                    result = tts_cache.call_minimax_tts(text, speaker="", speed=t['speed_val'], emotion=None, voice_id_override=override)
                if 'audio_path' in (result or {}):
                    conv_src = result['audio_path']
                    safe_knowledge = knowledge.replace(' ', '_')
                    conv_filename = f"{safe_knowledge}-{voice_name}-{speed_str}.mp3"
                    conv_path = os.path.join(base_out, conv_filename)
                    import shutil
                    shutil.copy2(conv_src, conv_path)
                    if bool(getattr(self, '_kg_transcode_to_16k_mono', False)):
                        print(f"开始转码: 16kHz 24kbps 单声道 -> {conv_path}")
                        conv_path = self._apply_audio_transcode_if_needed(conv_path)
                        print(f"转码完成: {conv_path}")
                    return {'status': 'success', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str, 'conv_path': conv_path, 'autoplay': True}
                else:
                    print(f"TTS生成失败: {json.dumps(result, ensure_ascii=False)}")
                    return {'status': 'error', 'row': t['row'], 'speaker': speaker, 'voice_name': voice_name, 'speed': speed_str}
        self._kg_runner = ThreadPoolRunner(tasks, worker_fn, max_workers=1)
        self._kg_runner.item_started.connect(self._on_kg_item_started)
        self._kg_runner.item_done.connect(self._on_kg_item_done)
        self._kg_runner.item_failed.connect(self._on_kg_item_failed)
        self._kg_runner.finished.connect(self._on_kg_finished)
        self._kg_runner.start()

    def _on_kg_finished(self):
        print("知识点生成与音色转换任务已完成")
        self._kg_update_progress_label()
        if getattr(self, '_generate_all_running', False):
            self._generate_all_index = getattr(self, '_generate_all_index', 0) + 1
            self._generate_all_next()
        else:
            self.unlock_generation_ui()

    def _apply_audio_transcode_if_needed(self, path):
        if not path or not os.path.exists(path):
            return path
        if hasattr(self, 'kg_radio_16_mono') and self.kg_radio_16_mono.isChecked():
            from pydub import AudioSegment
            audio = AudioSegment.from_file(path)
            tmp = path + ".tmp"
            audio = audio.set_frame_rate(16000).set_channels(1)
            audio.export(tmp, format="mp3", bitrate="24k")
            import os as _os
            _os.replace(tmp, path)
        return path

    def stop_all_tasks(self):
        runner = getattr(self, '_kg_runner', None)
        if runner:
            print("正在停止知识点生成线程池...")
            runner.stop()
            print("知识点生成线程池已停止")
        seed_runner = getattr(self, '_seed_runner', None)
        if seed_runner:
            print("正在停止种子生成线程池...")
            seed_runner.stop()
            print("种子生成线程池已停止")
        self.unlock_generation_ui()

    def on_generate_all(self):
        if getattr(self, '_generate_all_running', False):
            return
        self.lock_generation_ui()
        self._generate_all_running = True
        self._generate_all_index = 0
        self._generate_all_next()

    def _generate_all_next(self):
        order = getattr(self, '_seed_order', []) or []
        count = len(order)
        idx = getattr(self, '_generate_all_index', 0)
        if idx >= count:
            self._generate_all_running = False
            self.unlock_generation_ui()
            print("全部生成已完成")
            return
        knowledge = str(order[idx])
        self._select_knowledge_frame(knowledge)
        self._kg_current_knowledge = knowledge
        self._kg_update_group_labels(knowledge)
        if not knowledge:
            self._generate_all_index += 1
            self._generate_all_next()
            return
        self._kg_update_frames_initial_status(knowledge)
        rows = self.config_table.rowCount()
        pending = 0
        for r in range(rows):
            it0 = self.config_table.item(r, 0)
            if it0 and it0.checkState() == Qt.CheckState.Checked:
                pending += 1
        if pending > 0:
            print(f"开始批量生成: {knowledge}, 未完成数量: {pending}")
            self.on_start_generate_knowledge()
        else:
            print(f"跳过: {knowledge}, 已全部完成")
            self._generate_all_index += 1
            self._generate_all_next()

    def _replace_special_format_core(self, text, key_usage_counters=None, use_sequential_values=False):
        """
        核心的特殊格式替换逻辑
        
        Args:
            text: 要替换的文本
            key_usage_counters: 键使用计数器字典，用于顺序替换管道符分隔的值
            use_sequential_values: 是否使用顺序值替换（用于对话内容）
        
        Returns:
            替换后的文本
        """
        if not isinstance(text, str):
            text = str(text)
            
        for k, v in self.special_format_items.items():
            if not v:
                continue
                
            k_str = str(k)
            v_str = str(v)
            
            if k_str in text:
                if k_str == '{words}':
                    normalized = v_str.replace('，', ',')
                    parts = [val.strip() for val in normalized.split(',') if val.strip()]
                    if parts:
                        replacement = ''.join('[' + val + ']' for val in parts)
                        if '[{words}]' in text:
                            text = text.replace('[{words}]', replacement)
                        text = text.replace('{words}', replacement)
                elif '|' in v_str:
                    value_array = [val.strip() for val in v_str.split('|') if val.strip()]
                    
                    if len(value_array) > 1 and use_sequential_values and key_usage_counters is not None:
                        if k_str not in key_usage_counters:
                            key_usage_counters[k_str] = 0
                        
                        value_index = key_usage_counters[k_str] % len(value_array)
                        current_value = value_array[value_index]
                        key_usage_counters[k_str] += 1
                        
                        text = text.replace(k_str, current_value)
                    elif len(value_array) >= 1:
                        text = text.replace(k_str, value_array[0])
                else:
                    text = text.replace(k_str, v_str)
                    
        return text
        
    def on_table_double_clicked(self, index):
        """处理表格双击事件，只在dialog列（第2列）双击时播放该行内容"""
        # 检查是否正在完整播放，如果是则屏蔽双击操作
        if hasattr(self, 'is_playing') and self.is_playing:
            Toast.warning("会话播放中", self)
            return
            
        if index.column() == 2:  # 只处理dialog列的双击（现在是第2列）
            row = index.row()
            
            # 获取该行的speaker和dialog内容
            speaker_index = self.table_model.index(row, 1)  # speaker现在是第1列
            dialog_index = self.table_model.index(row, 2)   # dialog现在是第2列
            
            speaker = self.table_model.data(speaker_index, Qt.ItemDataRole.DisplayRole)
            dialog = self.table_model.data(dialog_index, Qt.ItemDataRole.DisplayRole)
            
            if dialog:  # 确保dialog内容不为空
                print(f"双击播放第 {row + 1} 行: '{dialog}', speaker: {speaker}")
                # 清除当前选择状态，避免选中样式覆盖高亮颜色
                self.table_view.clearSelection()
                # 使用抽象出的单行播放方法
                self.play_single_row(row, dialog, speaker)

    def on_sidebar_item_double_clicked(self, item):
        if hasattr(self, 'is_playing') and self.is_playing:
            return
        row = 0
        try:
            sel = self.table_view.selectionModel().currentIndex()
            if sel and sel.isValid():
                row = sel.row()
        except Exception:
            pass
        if self.table_model.rowCount() == 0:
            return
        speaker_index = self.table_model.index(row, 1)
        dialog_index = self.table_model.index(row, 2)
        speaker = self.table_model.data(speaker_index, Qt.ItemDataRole.DisplayRole)
        dialog = self.table_model.data(dialog_index, Qt.ItemDataRole.DisplayRole)
        if dialog:
            self.table_view.clearSelection()
            self.play_single_row(row, dialog, speaker)

    def on_integration_item_double_clicked(self, item):
        if hasattr(self, 'is_playing') and self.is_playing:
            return
        row = 0
        try:
            sel = self.table_view.selectionModel().currentIndex()
            if sel and sel.isValid():
                row = sel.row()
        except Exception:
            pass
        if self.table_model.rowCount() == 0:
            return
        speaker_index = self.table_model.index(row, 1)
        dialog_index = self.table_model.index(row, 2)
        speaker = self.table_model.data(speaker_index, Qt.ItemDataRole.DisplayRole)
        dialog = self.table_model.data(dialog_index, Qt.ItemDataRole.DisplayRole)
        if dialog:
            self.table_view.clearSelection()
            self.play_single_row(row, dialog, speaker)

    def show_context_menu(self, position):
        """显示右键菜单"""
        index = self.table_view.indexAt(position)
        if not index.isValid():
            return
            
        # 只在dialog列（第2列）显示菜单
        if index.column() != 2:
            return
            
        menu = QMenu(self)
        
        # 添加复制选项
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(lambda: self.copy_dialog_cell(index))
        menu.addAction(copy_action)
        
        # 添加编辑选项（会话模式与整合模式均可）
        edit_action = QAction("编辑", self)
        edit_action.triggered.connect(lambda: self.edit_dialog_cell(index))
        menu.addAction(edit_action)
        
        # 显示菜单
        menu.exec(self.table_view.mapToGlobal(position))
        
    def edit_dialog_cell(self, index):
        """编辑dialog单元格，编辑原始带特殊格式的文本"""
        if not index.isValid() or index.column() != 2:  # dialog现在是第2列
            return
            
        row = index.row()
        
        # 获取原始对话内容（带特殊格式）
        # 优先从original_dialog_content获取，如果没有则从_data中获取
        if self.original_dialog_content is not None and row < len(self.original_dialog_content):
            original_text = str(self.original_dialog_content.iloc[row])
        else:
            # 如果没有original_dialog_content，直接从_data中获取原始内容
            if (hasattr(self.table_model, '_data') and 
                self.table_model._data is not None and 
                row < len(self.table_model._data)):
                original_text = str(self.table_model._data.iloc[row, 2])  # dialog列现在是第2列
            else:
                # 最后的回退选项
                original_text = self.table_model.data(index, Qt.ItemDataRole.DisplayRole)
            
        # 创建编辑对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑对话内容")
        dialog.setModal(True)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout(dialog)
        
        # 添加说明标签
        info_label = QLabel("编辑原始对话内容（包含特殊格式）：")
        layout.addWidget(info_label)
        
        # 添加文本编辑框
        text_edit = QTextEdit()
        text_edit.setPlainText(original_text)
        layout.addWidget(text_edit)
        
        # 添加按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn:
            ok_btn.setText("保存")
        if cancel_btn:
            cancel_btn.setText("取消")
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = text_edit.toPlainText()
            
            # 更新原始对话内容
            if self.original_dialog_content is not None:
                self.original_dialog_content.iloc[row] = new_text
                
            # 同时更新表格模型中的_data
            self.table_model._data.iloc[row, 2] = new_text  # dialog列现在是第2列
            
            # 同时更新_original_data中对应列的数据
            if (hasattr(self.table_model, '_original_data') and 
                self.table_model._original_data is not None):
                # 在整合模式下，使用orig_row与orig_col映射保存到原文件
                orig_row = None
                orig_col = None
                try:
                    orig_row = self.table_model._data.iloc[row].get('orig_row')
                    orig_col = self.table_model._data.iloc[row].get('orig_col')
                except Exception:
                    orig_row = None
                    orig_col = None
                if orig_row is not None and orig_col and orig_col in self.table_model._original_data.columns:
                    self.table_model._original_data.loc[orig_row, orig_col] = new_text
                elif hasattr(self, 'current_column') and self.current_column in self.table_model._original_data.columns:
                    self.table_model._original_data.loc[row, self.current_column] = new_text
                
            # 重新提取特殊格式内容并更新显示
            self.extract_special_format_content()
            
            # 强制刷新表格显示
            self.table_model.beginResetModel()
            self.table_model.endResetModel()
            
            # 保存到原文件
            saved = False
            if hasattr(self, 'save_file'):
                saved = bool(self.save_file())
            if saved and hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_toast("修改已更新到原文件")
                    
    def copy_dialog_cell(self, index):
        """复制dialog单元格的加工后文本到剪贴板"""
        if not index.isValid() or index.column() != 2:  # dialog现在是第2列
            return
            
        # 获取加工后的文本（从表格模型的_data中获取，这里存储的是经过特殊格式替换后的内容）
        row = index.row()
        processed_text = self.table_model._data.iloc[row, 2]  # dialog列现在是第2列
        
        # 确保内容不为空
        if pd.isna(processed_text) or str(processed_text).lower() in ['nan', 'none', '']:
            processed_text = ""
        else:
            processed_text = str(processed_text)
        
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(processed_text)
        
        # 显示Toast提示
        if hasattr(self, 'toast_manager') and self.toast_manager:
            self.toast_manager.show_toast("已复制到剪贴板")
    
    def play_audio(self):
        """播放音频功能 - 从表格的dialog字段读取内容，逐行处理"""
        # 检查是否有数据
        if self.table_model.rowCount() == 0:
            QMessageBox.warning(self, "警告", "表格中没有数据，请先加载Excel文件")
            return
        
        # 停止当前播放（如果有的话），确保状态清理
        if hasattr(self, 'tts_player'):
            self.tts_player.stop()
        
        # 清除之前的高亮
        self.table_model.clear_highlight()
        
        # 收集所有dialog字段的内容
        self.texts = []
        self.speakers = []
        self.text_indices = []  # 存储每段文本对应的行索引
        
        skip_duoki = hasattr(self, 'skip_duoki_checkbox') and self.skip_duoki_checkbox.isChecked()
        for row in range(self.table_model.rowCount()):
            speaker_index = self.table_model.index(row, 1)  # speaker列现在是第1列
            dialog_index = self.table_model.index(row, 2)  # dialog列现在是第2列
            
            speaker = self.table_model.data(speaker_index, Qt.ItemDataRole.DisplayRole)
            text = self.table_model.data(dialog_index, Qt.ItemDataRole.DisplayRole)
            
            if text and text.strip():
                if skip_duoki and str(speaker).strip() == '多奇':
                    print(f"跳过多奇行 {row}")
                    continue
                self.texts.append(text.strip())
                self.speakers.append(speaker if speaker else "default")
                self.text_indices.append(row)
        
        if not self.texts:
            QMessageBox.warning(self, "警告", "表格的dialog字段没有有效内容")
            return
        
        try:
            self._open_btn_prev_enabled = self.open_file_btn.isEnabled()
            self.open_file_btn.setEnabled(False)
            
        except Exception:
            pass
        try:
            self._clear_image_memory()
        except Exception:
            pass
        # 锁定界面
        self.is_playing = True
        self.sidebar_list.setEnabled(False)
        self.skip_duoki_checkbox.setEnabled(False)
        
        # 切换按钮显示状态
        self.play_button.setVisible(False)
        self.stop_button.setVisible(True)
        
        # 显示图片容器
        self.image_container.setVisible(True)
        
        # 开始从第一行播放
        self.current_playing_index = 0
        print(f"开始播放，共 {len(self.texts)} 行对话")
        self.play_next_row()
    
    def play_single_row(self, row_index, text=None, speaker=None):
        """播放单行对话的通用方法"""
        # 停止当前播放（如果有的话），确保状态清理
        if hasattr(self, 'tts_player'):
            self.tts_player.stop()
        
        # 如果没有提供text和speaker，从数据中获取
        if text is None or speaker is None:
            if hasattr(self, 'table_model') and self.table_model._data is not None:
                if row_index < len(self.table_model._data):
                    if text is None:
                        text = self.table_model._data.iloc[row_index, 2]  # dialog列现在是第2列
                    if speaker is None:
                        speaker = self.table_model._data.iloc[row_index, 1]  # speaker列现在是第1列
                else:
                    print(f"行索引 {row_index} 超出范围")
                    return
            else:
                print("没有可用的数据")
                return
        
        print(f"播放单行: '{text}', speaker: {speaker}")
        self.current_speaker_name = speaker
        
        # 执行SceneGraph匹配逻辑
        images = self.match_scene_graph(row_index)
        image1, image2 = (images[0], images[1]) if images else ('', '')
        
        # 清除之前的高亮
        self.table_model.clear_highlight()
        
        # 高亮当前行
        self.table_model.highlight_row(row_index)
        # 滚动到高亮行
        self.table_view.scrollTo(self.table_model.index(row_index, 0))
        
        # 切换按钮显示状态（单行播放时也显示停止按钮）
        self.play_button.setVisible(False)
        self.stop_button.setVisible(True)
        
        # 执行SceneGraph匹配并显示图片
        self.image_container.setVisible(True)
        self.format_table.setVisible(False)
        def on_images_loaded(image_resources):
            pixmap1, pixmap2 = image_resources
            pixmaps = []
            if pixmap1 and not pixmap1.isNull():
                pixmaps.append(pixmap1)
            if pixmap2 and not pixmap2.isNull():
                pixmaps.append(pixmap2)
            self.display_image(pixmaps)
        self.load_images([image1, image2], on_images_loaded)
        
        # 播放当前行，设置播放完成后清除高亮和恢复按钮状态
        def on_single_row_finished():
            print(f"单行播放完成")
            self.table_model.clear_highlight()
            # 恢复按钮状态
            self.stop_button.setVisible(False)
            self.play_button.setVisible(True)
            # 隐藏图片容器
            self.image_container.setVisible(False)
            # 显示key-value列表
            self.format_table.setVisible(True)
            try:
                self.open_file_btn.setEnabled(getattr(self, '_open_btn_prev_enabled', True))
            except Exception:
                pass
        
        # 在播放开始时触发NPC立绘状态切换
        if hasattr(self, 'switch_npc_portrait_state'):
            self.switch_npc_portrait_state(speaker)
        
        self.tts_player.play_text_by_row(text, speaker, on_single_row_finished)

    def match_scene_graph(self, row_index):
        """匹配SceneGraph数据并返回image1数据"""
        # 首先尝试从_data中获取stage_name
        stage_name = None
        if (hasattr(self.table_model, '_data') and 
            self.table_model._data is not None and 
            row_index < len(self.table_model._data) and
            'stage_name' in self.table_model._data.columns):
            stage_name = self.table_model._data.iloc[row_index]['stage_name']
            print(f"从_data中获取stage_name: {stage_name}")
        
        # 如果_data中没有或为空，则从原始数据中获取
        if not stage_name:
            if (not hasattr(self.table_model, '_original_data') or 
                self.table_model._original_data is None or 
                row_index >= len(self.table_model._original_data)):
                print("无法获取原始数据或行索引超出范围")
                return None
            
            # 检查stage_name字段是否存在
            if 'stage_name' not in self.table_model._original_data.columns:
                print("原始数据中不存在stage_name字段")
                return None
            
            stage_name = self.table_model._original_data.iloc[row_index]['stage_name']
            print(f"从_original_data中获取stage_name: {stage_name}")
        
        # 若为show_image_npc，优先从ShowImageNpc中查找背景图
        if stage_name and str(stage_name) == 'show_image_npc':
            show_image_result = self._try_get_image_from_show_image_npc(row_index)
            if show_image_result:
                print("从ShowImageNpc中找到背景图")
                self._bg_from_show_image_npc = True
                return show_image_result
            stage_name = 'talk'

        # 获取当前文件名（不包括扩展名）
        if not hasattr(self, 'current_file_path') or not self.current_file_path:
            print("当前没有加载文件")
            return None
        base_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
        name_parts = base_name.split("-")
        file_name = "-".join(name_parts[:3]) if len(name_parts) >= 3 else base_name
        file_name = file_name.replace("_", "-")

        # 获取SceneGraph数据
        scene_graph_data = self.scene_graph_manager.get_scene_graph_data()
        if scene_graph_data is None or len(scene_graph_data) == 0:
            print("SceneGraph数据为空")
            return None
        
        # 执行匹配逻辑
        for _, row in scene_graph_data.iterrows():
            scene_id = row.get('scene_id', '')
            stage_type = row.get('stage_type', '')
            
            # 文件名和scene_id匹配逻辑
            file_match = False
            
            # 1. 完全匹配
            if file_name == scene_id:
                file_match = True
                print(f"文件名: {file_name} <-> scene_id: {scene_id} (完全匹配)")
            # 2. 如果scene_id的后缀为"通用"，则去掉后缀对比
            elif scene_id.endswith('-通用'):
                scene_id_without_suffix = scene_id.rsplit('-', 1)[0]
                file_name_without_suffix = file_name.rsplit('-', 1)[0] if '-' in file_name else file_name
                if file_name_without_suffix == scene_id_without_suffix:
                    file_match = True
                    print(f"文件名: {file_name} <-> scene_id: {scene_id} (通用后缀匹配)")
            
            # stage_name和stage_type匹配逻辑
            stage_match = False
            
            # 1. 完全匹配
            if stage_name == stage_type:
                stage_match = True
            
            # 如果两组匹配同时成立
            if file_match and stage_match:
                image1 = row.get('image1', '')
                image2 = row.get('image2', '')
                
                # 处理nan值
                if isinstance(image1, float) and math.isnan(image1):
                    image1 = ''
                if isinstance(image2, float) and math.isnan(image2):
                    image2 = ''
                
                # 如果image2为空，向上查找有值的image2
                if not image2:
                    image2 = self._find_image2_from_previous_rows(scene_graph_data, scene_id, stage_type)
                
                # 替换image1和image2中的{level}为1
                if image1:
                    image1 = image1.replace('{level}', '1')
                if image2:
                    image2 = image2.replace('{level}', '1')
                
                print(f"匹配成功！")
                print(f"文件名: {file_name} <-> scene_id: {scene_id}")
                print(f"stage_name: {stage_name} <-> stage_type: {stage_type}")
                print(f"image1: {image1}")
                print(f"image2: {image2}")
                self._bg_from_show_image_npc = False
                return [image1, image2]
        
        print("未找到匹配的SceneGraph数据")
        return None
    
    def _find_image2_from_previous_rows(self, scene_graph_data, target_scene_id, target_stage_type):
        """从SceneGraph表中向上查找有值的image2"""
        try:
            # 将DataFrame转换为列表以便按索引查找
            data_list = scene_graph_data.to_dict('records')
            
            # 找到当前匹配行的索引
            current_index = -1
            for i, row in enumerate(data_list):
                if (row.get('scene_id', '') == target_scene_id and 
                    row.get('stage_type', '') == target_stage_type):
                    current_index = i
                    break
            
            if current_index == -1:
                print("未找到当前匹配行")
                return ''
            
            # 从当前行向上查找有值的image2
            for i in range(current_index - 1, -1, -1):
                row = data_list[i]
                image2 = row.get('image2', '')
                
                # 处理nan值
                if isinstance(image2, float) and math.isnan(image2):
                    image2 = ''
                
                if image2:  # 找到有值的image2
                    print(f"在第{i}行找到image2: {image2}")
                    return image2
            
            print("向上查找未找到有值的image2")
            return ''
            
        except Exception as e:
            print(f"查找image2时发生错误: {str(e)}")
            return ''
    
    def _try_get_image_from_show_image_npc(self, row_index):
        """尝试从ShowImageNpc中获取背景图片"""
        try:
            template_type = None
            base_name = None
            if hasattr(self, 'current_file_path') and self.current_file_path:
                base_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
                parts = base_name.split('-')
                if len(parts) >= 2:
                    template_type = parts[1]
                    print(f"从文件名 {base_name} 提取template_type: {template_type}")
                else:
                    print(f"文件名 {base_name} 格式不符合要求，无法提取template_type")
            
            # 2. 获取stage_name作为stage_type参数
            stage_type = None
            if (hasattr(self.table_model, '_data') and 
                self.table_model._data is not None and 
                row_index < len(self.table_model._data) and
                'stage_name' in self.table_model._data.columns):
                stage_type = self.table_model._data.iloc[row_index]['stage_name']
                print(f"从_data中获取stage_type: {stage_type}")
            
            # 如果_data中没有或为空，则从原始数据中获取
            if not stage_type:
                if (hasattr(self.table_model, '_original_data') and 
                    self.table_model._original_data is not None and 
                    row_index < len(self.table_model._original_data) and
                    'stage_name' in self.table_model._original_data.columns):
                    stage_type = self.table_model._original_data.iloc[row_index]['stage_name']
                    print(f"从_original_data中获取stage_type: {stage_type}")
            
            # 3. 获取npc1_base_id和npc2_base_id
            npc1_base_id = getattr(self, 'npc1_base_id', None)
            npc2_base_id = getattr(self, 'npc2_base_id', None)
            print(f"获取npc1_base_id: {npc1_base_id}, npc2_base_id: {npc2_base_id}")
            
            if stage_type and str(stage_type) == 'show_image_npc':
                if not base_name or not all([npc1_base_id, npc2_base_id]):
                    print(f"ShowImageNpc查找参数不完整: npcSceneId源={base_name}, stage_type={stage_type}, npc1_base_id={npc1_base_id}, npc2_base_id={npc2_base_id}")
                    return None
                name_parts = base_name.split('-')
                npc_scene_id = '-'.join(name_parts[:3]) if len(name_parts) >= 3 else base_name
                image_url = self.show_image_npc_manager.get_url_image_by_scene(
                    npc_scene_id=npc_scene_id,
                    stage_type=str(stage_type),
                    npc1_base_id=npc1_base_id,
                    npc2_base_id=npc2_base_id
                )
            else:
                if not all([template_type, stage_type, npc1_base_id, npc2_base_id]):
                    print(f"ShowImageNpc查找参数不完整: template_type={template_type}, stage_type={stage_type}, npc1_base_id={npc1_base_id}, npc2_base_id={npc2_base_id}")
                    return None
                image_url = self.show_image_npc_manager.get_url_image(
                    template_type=template_type,
                    stage_type=stage_type,
                    npc1_base_id=npc1_base_id,
                    npc2_base_id=npc2_base_id
                )
            
            if image_url:
                print(f"从ShowImageNpc获取到图片URL: {image_url}")
                # 返回格式与SceneGraph保持一致：[image1, image2]
                return [image_url, '']
            else:
                print("ShowImageNpc中未找到匹配的图片")
                return None
                
        except Exception as e:
            print(f"从ShowImageNpc获取图片时发生错误: {str(e)}")
            return None
            


    def play_next_row(self):
        """播放下一行对话"""
        if self.current_playing_index >= len(self.texts):
            # 所有行都播放完成
            print("所有行播放完成")
            self.on_play_finished()
            return
        
        # 获取当前行的文本和speaker
        text = self.texts[self.current_playing_index]
        speaker = self.speakers[self.current_playing_index]
        row_index = self.text_indices[self.current_playing_index]
        
        print(f"播放第 {self.current_playing_index + 1}/{len(self.texts)} 行: '{text}', speaker: {speaker}")
        self.current_speaker_name = speaker
        
        # 高亮当前行
        self.table_model.highlight_row(row_index)
        # 滚动到高亮行
        self.table_view.scrollTo(self.table_model.index(row_index, 0))
        
        # 执行SceneGraph匹配并显示图片
        images = self.match_scene_graph(row_index)
        image1, image2 = (images[0], images[1]) if images else ('', '')
        
        # 显示图片容器并进行加载
        self.image_container.setVisible(True)
        self.format_table.setVisible(False)
        def on_images_loaded(image_resources):
            pixmap1, pixmap2 = image_resources
            pixmaps = []
            if pixmap1 and not pixmap1.isNull():
                pixmaps.append(pixmap1)
            if pixmap2 and not pixmap2.isNull():
                pixmaps.append(pixmap2)
            self.display_image(pixmaps)
        self.load_images([image1, image2], on_images_loaded)
        
        # 在播放开始时触发NPC立绘状态切换
        if hasattr(self, 'switch_npc_portrait_state'):
            self.switch_npc_portrait_state(speaker)
        
        # 播放当前行，并设置行播放完成回调（用于连续播放）
        self.tts_player.play_text_by_row(text, speaker, self.on_row_finished)
    
    def on_row_finished(self):
        """一行播放完成后的回调"""
        print(f"行 {self.current_playing_index + 1} 播放完成")
        # 移动到下一行
        self.current_playing_index += 1
        # 播放下一行
        self.play_next_row()
    
    def stop_audio(self):
        """停止音频播放"""
        self.tts_player.stop()
        self.unlock_interface()
        self.table_model.clear_highlight()
    
    def on_play_finished(self):
        """播放完成回调"""
        self.unlock_interface()
        self.table_model.clear_highlight()
        print("播放完成")
    
    def unlock_interface(self):
        """解锁界面"""
        self.is_playing = False
        self.sidebar_list.setEnabled(True)
        self.skip_duoki_checkbox.setEnabled(True)
        
        # 切换按钮显示状态
        self.stop_button.setVisible(False)
        self.play_button.setVisible(True)
        
        # 隐藏图片容器
        self.image_container.setVisible(False)
        
        # 显示format_table
        self.format_table.setVisible(True)
        
        # 重置inner_splitter的分割比例
        self.inner_splitter.setSizes([200, 100, 100])
        try:
            self.open_file_btn.setEnabled(getattr(self, '_open_btn_prev_enabled', True))
        except Exception:
            pass

    def _clear_image_memory(self):
        try:
            self.current_scene_pixmaps = []
        except Exception:
            pass
        try:
            if hasattr(self, 'image_container') and self.image_container:
                if getattr(self.image_container, 'current_movie', None):
                    try:
                        self.image_container.current_movie.stop()
                    except Exception:
                        pass
                    self.image_container.current_movie = None
                if hasattr(self.image_container, 'clearGif'):
                    self.image_container.clearGif()
                self.image_container.clear()
        except Exception:
            pass
        try:
            self.npc_portraits_cache = [{'image': None, 'talk': None}, {'image': None, 'talk': None}]
        except Exception:
            pass
    
    def open_file_dialog(self):
        """打开文件选择对话框"""
        # 获取主窗口实例
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'config_manager'):
            main_window = main_window.parent()
        
        # 获取上次打开路径（音频模块专用）
        start_dir = ""
        if main_window and hasattr(main_window, 'config_manager'):
            start_dir = main_window.config_manager.get_last_open_path('audio')
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Excel文件", start_dir, "Excel文件 (*.xlsx)"
        )
        
        if file_path:
            # 保存当前路径（音频模块专用）
            if main_window and hasattr(main_window, 'config_manager'):
                main_window.config_manager.set_last_open_path(file_path, 'audio')
            
            self.load_excel_file(file_path)
            
    def load_excel_file(self, file_path):
        """加载Excel文件"""
        try:
            # 读取Excel文件
            df = pd.read_excel(file_path)
            
            # 检查是否包含必要的列
            if 'speaker' not in df.columns or 'param1' not in df.columns:
                QMessageBox.warning(self, "格式错误", "表格数据不符合要求，缺少必要的列(speaker, param1)")
                return
            
            # 只有在文件格式正确后才更新UI状态
            # 存储当前文件路径
            self.current_file_path = file_path
            
            # 更新文件名标签（仅显示文件名）
            try:
                import os as _os
                self.file_label.setText(_os.path.basename(file_path))
            except Exception:
                self.file_label.setText(file_path)
            
            # 更新当前对话标签为当前选择（初始为param1或文件名）
            try:
                self.current_dialog_label.setText(self.current_column if getattr(self, 'current_column', None) else self.file_label.text())
            except Exception:
                pass
                
            # 加载数据到表格模型
            self.table_model.load_data(df)
            
            # 设置用户名到表格模型（使用固定值"贝贝"）
            self.table_model.username = "贝贝"
            
            # 清空侧边栏
            self.sidebar_list.clear()
            
            # 更新整合模式列表
            self.update_integration_list(df)
            
            # 首先添加param1列到侧边栏顶部
            if 'param1' in df.columns:
                self.sidebar_list.addItem('param1')
                # 初始选择param1并应用用户名替换
                self.sidebar_list.setCurrentRow(0)
                # 不直接调用on_sidebar_item_changed，而是通过信号触发
                # 或者手动处理param1列的显示
                column_name = 'param1'
                self.current_column = column_name
                
                # 获取用户昵称（使用固定值"贝贝"）
                self.table_model.username = "贝贝"
                
                # 对于param1列，不需要解析NPC名称
                self.table_model.npc1_name = ""
                self.table_model.npc2_name = ""
                
                # 创建空的speaker映射
                speaker_mapping = {}
                self.current_speaker_mapping = speaker_mapping
                
                # 更新表格显示
                self.table_model.update_display(column_name, speaker_mapping)
                
                # 提取并显示特殊格式内容（确保第一次加载时也能应用{user_name}替换）
                self.extract_special_format_content()
            
            # 然后添加包含"-"的列名
            for column in df.columns:
                if "-" in column:
                    self.sidebar_list.addItem(column)
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载文件时出错: {str(e)}")
    
    # 移除on_username_changed方法，因为不再需要用户昵称输入框
            # 不显示错误对话框，避免可能的循环崩溃
            # 仅记录错误
    
    def update_integration_list(self, df):
        """更新整合模式列表"""
        # 清空整合模式列表
        self.integration_list.clear()
        
        # 首先添加param1到顶部
        if 'param1' in df.columns:
            self.integration_list.addItem('param1')
        
        # 处理带有"-"的表头
        dash_columns = [col for col in df.columns if "-" in col]
        
        # 对带有"-"的列进行处理：split by "-"后取前两个元素并join by "-"后去重
        processed_columns = set()
        for column in dash_columns:
            parts = column.split("-")
            if len(parts) >= 2:
                # 取前两个元素并用"-"连接
                processed_name = "-".join(parts[:2])
                processed_columns.add(processed_name)
        
        # 将去重后的结果添加到整合模式列表
        for processed_name in sorted(processed_columns):
            self.integration_list.addItem(processed_name)

    def on_qa_tab_changed(self, index):
        try:
            if index == 1 and not getattr(self, '_knowledge_tab_initialized', False):
                self._knowledge_tab_initialized = True
                self.load_knowledge_mapping_table()
        except Exception:
            pass

    def _process_qc_compare_filename(self, filename):
        name = os.path.splitext(filename)[0]
        lower = name.lower()
        marker = "-english"
        idx = lower.find(marker)
        if idx >= 0:
            name = name[:idx]
        return name

    def on_qc_compare_open_directory_1(self):
        directory = QFileDialog.getExistingDirectory(self, "选择目录")
        if not directory:
            return
        self.qc_compare_before_dir = directory
        self.qc_compare_dir_label_1.setText(directory)
        print(f"[质检比对] 已选择目录1: {directory}")
        if self.qc_compare_open_dir_btn_2:
            self.qc_compare_open_dir_btn_2.setEnabled(True)
        self._refresh_qc_compare_file_list()

    def on_qc_compare_open_directory_2(self):
        if not getattr(self, "qc_compare_before_dir", ""):
            return
        directory = QFileDialog.getExistingDirectory(self, "选择目录")
        if not directory:
            return
        self.qc_compare_after_dir = directory
        self.qc_compare_dir_label_2.setText(directory)
        print(f"[质检比对] 已选择目录2: {directory}")
        self._compare_qc_directories()

    def _refresh_qc_compare_file_list(self):
        base_dir = getattr(self, "qc_compare_before_dir", "")
        self.qc_compare_file_list.clear()
        if not base_dir:
            return
        if not os.path.isdir(base_dir):
            return
        entries = sorted(os.listdir(base_dir))
        for name in entries:
            lower = name.lower()
            if lower.endswith(".xlsx") or lower.endswith(".xls"):
                full_path = os.path.join(base_dir, name)
                if os.path.isfile(full_path):
                    display = self._process_qc_compare_filename(name)
                    self.qc_compare_file_list.addItem(display)
                    item = self.qc_compare_file_list.item(self.qc_compare_file_list.count() - 1)
                    if item:
                        item.setData(Qt.ItemDataRole.UserRole, name)

    def _compare_qc_directories(self):
        before_dir = getattr(self, "qc_compare_before_dir", "")
        after_dir = getattr(self, "qc_compare_after_dir", "")
        if not before_dir or not after_dir:
            return
        if os.path.abspath(before_dir) == os.path.abspath(after_dir):
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.show_error("质检前后目录不能相同")
            else:
                QMessageBox.warning(self, "质检比对", "质检前后目录不能相同")
            return
        before_map = {}
        for i in range(self.qc_compare_file_list.count()):
            item = self.qc_compare_file_list.item(i)
            if not item:
                continue
            text = str(item.text() or "").strip()
            if not text:
                continue
            item.setForeground(QColor('black'))
            if text not in before_map:
                before_map[text] = []
            before_map[text].append(item)
        after_processed = set()
        extra_after = []
        if not os.path.isdir(after_dir):
            return
        entries = sorted(os.listdir(after_dir))
        for name in entries:
            lower = name.lower()
            if lower.endswith(".xlsx") or lower.endswith(".xls"):
                full_path = os.path.join(after_dir, name)
                if not os.path.isfile(full_path):
                    continue
                processed = self._process_qc_compare_filename(name)
                if not processed:
                    continue
                if processed in after_processed:
                    continue
                after_processed.add(processed)
                if processed in before_map:
                    for item in before_map[processed]:
                        item.setForeground(QColor('green'))
                else:
                    extra_after.append(processed)
        for key, items in before_map.items():
            if key not in after_processed:
                for item in items:
                    item.setForeground(QColor('red'))
        if extra_after:
            unique = sorted(set(extra_after))
            msg = "以下文件没有找到质检前版本:\n" + "\n".join(unique)
            QMessageBox.information(self, "质检比对", msg)

    def on_qc_compare_file_selected(self, row):
        if row is None or row < 0:
            return
        item = self.qc_compare_file_list.item(row)
        if not item:
            return
        brush = item.foreground()
        color = brush.color() if brush is not None else None
        is_green = bool(color and color == QColor('green'))
        if not is_green:
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.show_warning("缺少可对比的文件")
            else:
                QMessageBox.information(self, "质检比对", "缺少可对比的文件")
            return
        before_dir = getattr(self, "qc_compare_before_dir", "")
        after_dir = getattr(self, "qc_compare_after_dir", "")
        if not before_dir or not after_dir:
            return
        processed_name = str(item.text() or "").strip()
        if not processed_name:
            return
        original_before_name = item.data(Qt.ItemDataRole.UserRole) or ""
        before_path = ""
        if original_before_name:
            candidate = os.path.join(before_dir, original_before_name)
            if os.path.isfile(candidate):
                before_path = candidate
        if not before_path:
            before_path = self._find_qc_compare_file(before_dir, processed_name)
        after_path = self._find_qc_compare_file(after_dir, processed_name)
        if not before_path or not after_path:
            if hasattr(self, "toast_manager") and self.toast_manager:
                self.toast_manager.show_warning("缺少可对比的文件")
            else:
                QMessageBox.information(self, "质检比对", "缺少可对比的文件")
            return
        self._load_qc_compare_tables(before_path, after_path)

    def _find_qc_compare_file(self, base_dir, processed_name):
        if not base_dir or not processed_name:
            return ""
        if not os.path.isdir(base_dir):
            return ""
        entries = sorted(os.listdir(base_dir))
        for name in entries:
            lower = name.lower()
            if lower.endswith(".xlsx") or lower.endswith(".xls"):
                full_path = os.path.join(base_dir, name)
                if not os.path.isfile(full_path):
                    continue
                if self._process_qc_compare_filename(name) == processed_name:
                    return full_path
        return ""

    def _build_qc_compare_df(self, file_path):
        xls = pd.ExcelFile(file_path)
        sheet_names = xls.sheet_names
        if not sheet_names:
            return pd.DataFrame(columns=["key", "value"])
        df = pd.read_excel(xls, sheet_name=sheet_names[0])
        cols = list(df.columns)
        if "param1" not in cols:
            return pd.DataFrame(columns=["key", "value"])
        start_index = cols.index("param1") + 1
        if start_index >= len(cols):
            return pd.DataFrame(columns=["key", "value"])
        records = []
        for col in cols[start_index:]:
            series = df[col]
            for v in series:
                if pd.isna(v):
                    s = ""
                else:
                    s = str(v).strip()
                if s.lower() in {"nan", "none"}:
                    continue
                records.append({"key": col, "value": s})
        if not records:
            return pd.DataFrame(columns=["key", "value"])
        return pd.DataFrame(records, columns=["key", "value"])

    def _get_qc_selected_suffixes(self):
        suffixes = set()
        checkboxes = getattr(self, "qc_filter_checkboxes", [])
        if not checkboxes:
            return {"e0", "e1", "e2", "e3", "e4"}
        for cb in checkboxes:
            if cb.isChecked():
                text = str(cb.text() or "").strip()
                if text:
                    suffixes.add(text[-2:])
        return suffixes

    def _filter_qc_df_by_suffixes(self, df, suffixes):
        if df is None or df.empty:
            return pd.DataFrame(columns=["key", "value"])
        if not suffixes:
            return pd.DataFrame(columns=["key", "value"])
        keys = df["key"].astype(str)
        mask = keys.str[-2:].isin(suffixes)
        filtered = df[mask].reset_index(drop=True)
        return filtered

    def _apply_qc_filter_to_current_tables(self):
        before_df_full = getattr(self, "qc_compare_before_df_full", None)
        after_df_full = getattr(self, "qc_compare_after_df_full", None)
        if before_df_full is None or after_df_full is None:
            return
        suffixes = self._get_qc_selected_suffixes()
        before_df = self._filter_qc_df_by_suffixes(before_df_full, suffixes)
        after_df = self._filter_qc_df_by_suffixes(after_df_full, suffixes)
        before_model = self._set_qc_compare_table(self.qc_compare_dataform_1, before_df)
        after_model = self._set_qc_compare_table(self.qc_compare_dataform_2, after_df)
        self._compare_qc_tables(before_model, after_model)

    def _set_qc_compare_table(self, table, df):
        model = QStandardItemModel()
        model.setHorizontalHeaderLabels(["key", "value"])
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                key_item = QStandardItem(str(row.get("key", "")))
                value_item = QStandardItem(str(row.get("value", "")))
                model.appendRow([key_item, value_item])
        table.setModel(model)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        return model

    def _calculate_qc_diff_from_df(self, before_df, after_df):
        if before_df is None or after_df is None:
            return 0, 0
        rows_before = len(before_df.index)
        rows_after = len(after_df.index)
        if rows_before == 0 and rows_after == 0:
            return 0, 0
        if rows_before != rows_after:
            print("[质检比对] 表格结构不同，已跳过当前文件")
            return 0, 0
        diff_count = 0
        total = rows_after
        before_values = [str(v) .strip() for v in before_df["value"].tolist()]
        after_values = [str(v) .strip() for v in after_df["value"].tolist()]
        for v_before, v_after in zip(before_values, after_values):
            if v_before != v_after:
                diff_count += 1
        return diff_count, total

    def _load_qc_compare_tables(self, before_path, after_path):
        try:
            before_df = self._build_qc_compare_df(before_path)
            after_df = self._build_qc_compare_df(after_path)
        except Exception as e:
            QMessageBox.warning(self, "质检比对", f"读取文件失败：{e}")
            return
        self.qc_compare_before_df_full = before_df
        self.qc_compare_after_df_full = after_df
        self._apply_qc_filter_to_current_tables()

    def _compare_qc_tables(self, before_model, after_model):
        if before_model is None or after_model is None:
            return
        rows_before = before_model.rowCount()
        rows_after = after_model.rowCount()
        if rows_before == 0 and rows_after == 0:
            if hasattr(self, "qc_compare_diff_label"):
                self.qc_compare_diff_label.setText("修改内容：0/0")
            return
        if rows_before != rows_after:
            if hasattr(self, "qc_compare_diff_label"):
                self.qc_compare_diff_label.setText("修改内容：0/0")
            QMessageBox.information(self, "质检比对", "质检前后表格结构不同，无法比对")
            return
        diff_count = 0
        total = rows_after
        for row in range(rows_before):
            idx_before = before_model.index(row, 1)
            idx_after = after_model.index(row, 1)
            v_before = str(idx_before.data() or "").strip()
            v_after = str(idx_after.data() or "").strip()
            if v_before != v_after:
                diff_count += 1
                before_model.setData(idx_before, QColor("orange"), Qt.ItemDataRole.ForegroundRole)
                after_model.setData(idx_after, QColor("orange"), Qt.ItemDataRole.ForegroundRole)
        if hasattr(self, "qc_compare_diff_label"):
            self.qc_compare_diff_label.setText(f"修改内容：{diff_count}/{total}")

    def on_qc_compare_reset(self):
        self.qc_compare_file_list.clear()
        empty_df = pd.DataFrame(columns=["key", "value"])
        self._set_qc_compare_table(self.qc_compare_dataform_1, empty_df)
        self._set_qc_compare_table(self.qc_compare_dataform_2, empty_df)
        self.qc_compare_before_df_full = None
        self.qc_compare_after_df_full = None
        self.qc_compare_before_dir = ""
        self.qc_compare_after_dir = ""
        self.qc_compare_dir_label_1.setText("未选择目录")
        self.qc_compare_dir_label_2.setText("未选择目录")
        self.qc_compare_open_dir_btn_2.setEnabled(False)
        if hasattr(self, "qc_compare_diff_label"):
            self.qc_compare_diff_label.setText("修改内容：0/0")
        if hasattr(self, "qc_compare_stat_label"):
            self.qc_compare_stat_label.setText("修改量：0/0")
        if hasattr(self, "qc_filter_checkboxes"):
            for cb in self.qc_filter_checkboxes:
                cb.setChecked(True)
        print("[质检比对] 模块已重置")

    def on_qc_compare_stat(self):
        total_modified = 0
        total_cells = 0
        before_dir = getattr(self, "qc_compare_before_dir", "")
        after_dir = getattr(self, "qc_compare_after_dir", "")
        if not before_dir or not after_dir:
            if hasattr(self, "qc_compare_stat_label"):
                self.qc_compare_stat_label.setText("修改量：0/0")
            print("[质检比对] 统计失败，目录未选择完整")
            return
        for i in range(self.qc_compare_file_list.count()):
            item = self.qc_compare_file_list.item(i)
            if not item:
                continue
            brush = item.foreground()
            color = brush.color() if brush is not None else None
            if not color or color != QColor("green"):
                continue
            processed_name = str(item.text() or "").strip()
            if not processed_name:
                continue
            original_before_name = item.data(Qt.ItemDataRole.UserRole) or ""
            before_path = ""
            if original_before_name:
                candidate = os.path.join(before_dir, original_before_name)
                if os.path.isfile(candidate):
                    before_path = candidate
            if not before_path:
                before_path = self._find_qc_compare_file(before_dir, processed_name)
            after_path = self._find_qc_compare_file(after_dir, processed_name)
            if not before_path or not after_path:
                continue
            try:
                before_df = self._build_qc_compare_df(before_path)
                after_df = self._build_qc_compare_df(after_path)
            except Exception as e:
                print(f"[质检比对] 统计时读取文件失败: {processed_name}, 错误: {e}")
                continue
            suffixes = self._get_qc_selected_suffixes()
            before_filtered = self._filter_qc_df_by_suffixes(before_df, suffixes)
            after_filtered = self._filter_qc_df_by_suffixes(after_df, suffixes)
            modified, cells = self._calculate_qc_diff_from_df(before_filtered, after_filtered)
            total_modified += modified
            total_cells += cells
        if hasattr(self, "qc_compare_stat_label"):
            self.qc_compare_stat_label.setText(f"修改量：{total_modified}/{total_cells}")
        print(f"[质检比对] 统计完成: 修改量 {total_modified}/{total_cells}")

    def on_qc_filter_changed(self, state):
        self._apply_qc_filter_to_current_tables()

    def on_qc_compare_vertical_scroll_1(self, value):
        if getattr(self, "_qc_scroll_syncing", False):
            return
        self._qc_scroll_syncing = True
        self.qc_compare_dataform_2.verticalScrollBar().setValue(value)
        self._qc_scroll_syncing = False

    def on_qc_compare_vertical_scroll_2(self, value):
        if getattr(self, "_qc_scroll_syncing", False):
            return
        self._qc_scroll_syncing = True
        self.qc_compare_dataform_1.verticalScrollBar().setValue(value)
        self._qc_scroll_syncing = False

    def on_qc_compare_horizontal_scroll_1(self, value):
        if getattr(self, "_qc_hscroll_syncing", False):
            return
        self._qc_hscroll_syncing = True
        self.qc_compare_dataform_2.horizontalScrollBar().setValue(value)
        self._qc_hscroll_syncing = False

    def on_qc_compare_horizontal_scroll_2(self, value):
        if getattr(self, "_qc_hscroll_syncing", False):
            return
        self._qc_hscroll_syncing = True
        self.qc_compare_dataform_1.horizontalScrollBar().setValue(value)
        self._qc_hscroll_syncing = False

    def on_rd_sheet_changed(self, sheet_name):
        ids = self.template_config_manager.get_ids_by_sheet(sheet_name)
        self.rd_id_list.clear()
        for i in ids:
            self.rd_id_list.addItem(str(i))
        if self.rd_id_list.count() > 0:
            self.rd_id_list.setCurrentRow(0)
        self.update_rd_table()

    def on_rd_execute_debug(self):
        uid = str(self.rd_user_id_edit.text() or '').strip()
        it = self.rd_id_list.currentItem()
        tpl = str(it.text()).strip() if it else ''
        if not uid or not uid.isdigit():
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_warning('请输入数字UID')
            print('[真机调试] UID无效')
            return
        if not tpl:
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_warning('未选择模板ID')
            print('[真机调试] 未选择模板ID')
            return
        url = 'https://portal-test.qidianlingzhi.com:10199/server/sendGMCmd'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        cookie_header = ''
        if hasattr(self, 'auth_manager') and self.auth_manager:
            try:
                cookie_header = self.auth_manager.get_cookie_header()
            except Exception:
                cookie_header = ''
        if not cookie_header:
            try:
                cfg = ConfigManager()
                cookie_header = cfg.get('KEY', 'cookie', '')
            except Exception:
                cookie_header = ''
        if cookie_header:
            headers['Cookie'] = cookie_header
        cmd = f"online.level_game.stage+{uid}+{tpl}"
        data = {'serviceName': 'restaurant', 'command': cmd}
        print(f"[真机调试] 开始调用接口，command={cmd}")
        try:
            resp = requests.post(url, headers=headers, data=data, timeout=15, verify=False)
            status = resp.status_code
            text = resp.text or ''
            print(f"[真机调试] 状态码: {status}")
            msg = ''
            ctype = str(resp.headers.get('Content-Type') or '').lower()
            if 'application/json' in ctype:
                try:
                    j = resp.json()
                    msg = str(j.get('message') or '').strip()
                except Exception:
                    msg = text.strip()
            else:
                msg = text.strip()
            if hasattr(self, 'toast_manager') and self.toast_manager:
                if 200 <= status < 300:
                    success_text = '接口调用成功'
                    if msg:
                        success_text = f"{success_text}：{msg}"
                    self.toast_manager.show_success(success_text)
                else:
                    self.toast_manager.show_error(f"执行失败：{msg or ('HTTP ' + str(status))}")
            print('[真机调试] 接口调用完成')
            if text:
                print(text)
        except requests.exceptions.RequestException as e:
            err = str(e)
            if hasattr(self, 'toast_manager') and self.toast_manager:
                self.toast_manager.show_error(f"执行失败：{err}")
            print(f"[真机调试] 调用失败: {err}")

    def on_rd_search(self):
        q = self.rd_search_input.text().strip()
        print(f"[真机调试] 搜索关键字: '{q}'")
        if not q:
            return
        ql = q.lower()
        total = self.rd_id_list.count()
        for i in range(total):
            it = self.rd_id_list.item(i)
            if not it:
                continue
            t = it.text() or ''
            if ql in t.lower():
                self.rd_id_list.setCurrentRow(i)
                try:
                    self.rd_id_list.scrollToItem(it)
                except Exception:
                    pass
                print(f"[真机调试] 搜索命中索引: {i}, 值: {t}")
                return
        print("[真机调试] 未找到匹配项")

    def on_rd_id_changed(self, row):
        self.update_rd_table()

    def update_rd_table(self):
        sheet = self.rd_sheet_combo.currentText().strip()
        it = self.rd_id_list.currentItem()
        stage_id = str(it.text()).strip() if it else ''
        rows_out = []
        if stage_id:
            df_fmt = self.speech_manager.format_rows_by_id(stage_id, delimiter='|', sheet_name=sheet)
            npc_map2 = get_npc_id_map_2()
            tpl = self.template_config_manager.get_npcs_by_id(stage_id) or ('', '')
            npc1_char, npc2_char = tpl
            def _rev_lookup(val):
                v = str(val).strip()
                if not v:
                    return ''
                for k, vv in npc_map2.items():
                    if str(vv).strip() == v:
                        ks = str(k).strip()
                        return ks.split('_')[0] if '_' in ks else ks
                return ''
            npc1_name_key = _rev_lookup(npc1_char)
            npc2_name_key = _rev_lookup(npc2_char)
            for _, r in df_fmt.iterrows():
                stage_val = str(r.get('stage_type') or '').strip()
                spk = str(r.get('speaker') or '').strip().lower()
                if spk == 'npc1':
                    npc_val = npc1_name_key or str(npc1_char or '').strip()
                elif spk == 'npc2':
                    npc_val = npc2_name_key or str(npc2_char or '').strip()
                elif spk == 'duoki':
                    npc_val = '多奇'
                else:
                    npc_val = str(r.get('speaker') or '').strip()
                dialog = ''
                if 'param' in r.index:
                    dialog = str(r.get('param') or '').strip()
                else:
                    for c in ['param1', 'param2', 'param3', 'param4', 'param5']:
                        if c in r.index:
                            v = str(r.get(c) or '').strip()
                            if v:
                                dialog = v
                                break
                rows_out.append({'stage': stage_val, 'npc': npc_val, 'dialog': dialog})
        self.rd_table.setRowCount(len(rows_out))
        for i, rowi in enumerate(rows_out):
            self.rd_table.setItem(i, 0, QTableWidgetItem(rowi.get('stage', '')))
            self.rd_table.setItem(i, 1, QTableWidgetItem(rowi.get('npc', '')))
            self.rd_table.setItem(i, 2, QTableWidgetItem(rowi.get('dialog', '')))
        print(f"[真机调试] 表格已更新: {len(rows_out)} 行")

    def load_knowledge_mapping_table(self):
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            mapping_path = os.path.join(base_dir, 'resources', 'data', 'mapping', 'npc_voice_tts_mapping.xlsx')
            df = pd.read_excel(mapping_path)
            if 'change_voice_id' not in df.columns:
                df['change_voice_id'] = ''
            if 'speed_type' not in df.columns:
                df['speed_type'] = ''
            self.knowledge_mapping_df = df
            self.config_table.setRowCount(0)
            for _, row in df.iterrows():
                r = self.config_table.rowCount()
                self.config_table.insertRow(r)
                chk = QTableWidgetItem()
                chk.setFlags(chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Checked)
                self.config_table.setItem(r, 0, chk)
                try:
                    self.config_table.setItem(r, 1, QTableWidgetItem(str(row.iloc[0])))
                except Exception:
                    self.config_table.setItem(r, 1, QTableWidgetItem(""))
                try:
                    self.config_table.setItem(r, 2, QTableWidgetItem(str(row.iloc[1])))
                except Exception:
                    self.config_table.setItem(r, 2, QTableWidgetItem(""))
                try:
                    self.config_table.setItem(r, 3, QTableWidgetItem(str(row.iloc[2])))
                except Exception:
                    self.config_table.setItem(r, 3, QTableWidgetItem(""))
                try:
                    self.config_table.setItem(r, 4, QTableWidgetItem(str(row.iloc[3])))
                except Exception:
                    self.config_table.setItem(r, 4, QTableWidgetItem(""))
        except Exception:
            pass

    def on_open_knowledge_file(self):
        try:
            start_dir = self.config_manager.get_knowledge_last_open_path()
        except Exception:
            start_dir = "./"
        file_path, _ = QFileDialog.getOpenFileName(self, "选择Excel文件", start_dir, "Excel文件 (*.xlsx)")
        if not file_path:
            return
        try:
            df = pd.read_excel(file_path)
        except Exception:
            QMessageBox.warning(self, "格式错误", "无法读取xlsx文件")
            return
        cols = list(df.columns)
        if not cols or str(cols[0]).strip().lower() != 'knowledge':
            QMessageBox.warning(self, "格式错误", "第一列表头必须为 'knowledge'")
            return
        try:
            import os as _os
            self.kg_knowledge_file_label.setText(_os.path.basename(file_path))
        except Exception:
            self.kg_knowledge_file_label.setText(file_path)
        self._kg_clear_grid()
        # 构建knowledge frames
        series = df.iloc[:, 0]
        knowledges = []
        for val in series.tolist():
            s = str(val).strip()
            if s and s.lower() not in {'nan', 'none'}:
                knowledges.append(s)
        self._build_knowledge_seed_frames(knowledges)
        self._update_seed_frames_initial_status()
        self.config_manager.set_knowledge_last_open_path(file_path)

    def _on_seed_selected_knowledge(self, knowledge):
        if not knowledge:
            return
        self.kg_selected_word_label.setText(knowledge)
        self._kg_current_knowledge = knowledge
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        mapping = self._build_knowledge_mapping_by_speaker()
        self._kg_prepare_frames(mapping)
        self._kg_update_group_labels(knowledge)
        self._kg_mapping = mapping
        self._kg_update_frames_initial_status(knowledge)
        self._update_current_knowledge_label_color_by_completion()

    def _kg_update_frames_initial_status(self, knowledge):
        if not knowledge:
            return
        base_out = self.kg_output_dir_display.text().strip() or self.config_manager.ensure_knowledge_output_directory()
        safe_knowledge = knowledge.replace(' ', '_')
        finished = 0
        total = 0
        self._kg_finished_rows = set()
        for row, meta in (getattr(self, '_kg_speed_frames', {}) or {}).items():
            total += 1
            voice_name = str(meta.get('voice_name', '')).strip()
            speed_str = str(meta.get('speed', '')).strip() or '1'
            gender = str(meta.get('gender', '')).strip().lower()
            voice_override = self.male_voice_combo.currentText().strip() if gender == 'male' else self.female_voice_combo.currentText().strip()
            candidates = []
            if voice_override:
                candidates.append(voice_override)
            if voice_name:
                candidates.append(voice_name)
            # 去重同时保序
            seen = set()
            candidates = [c for c in candidates if not (c in seen or seen.add(c))]
            conv_path = os.path.join(base_out, f"{safe_knowledge}-{voice_name}-{speed_str}.mp3")
            conv_exists = os.path.exists(conv_path)
            if conv_exists:
                self._kg_set_speed_frame_status(row, 'success', conv_path=conv_path)
                self._mark_config_row_color(row, '#00AA00')
                item0 = self.config_table.item(row, 0)
                if item0:
                    item0.setCheckState(Qt.CheckState.Unchecked)
                finished += 1
                self._kg_finished_rows.add(row)
            else:
                self._kg_set_speed_frame_status(row, 'idle')
                # 重置行字色为原色并强制勾选
                cols = self.config_table.columnCount()
                for c in range(cols):
                    if c == 0:
                        continue
                    item = self.config_table.item(row, c)
                    if item:
                        item.setForeground(QColor('#FFFFFF'))
                item0 = self.config_table.item(row, 0)
                if item0:
                    item0.setCheckState(Qt.CheckState.Checked)
        # 更新统计
        self._kg_total_rows = total
        self._kg_set_label_progress(knowledge, finished, total)
        self._update_current_knowledge_label_color_by_completion()

    def _kg_set_label_progress(self, knowledge, finished, total):
        self.kg_selected_word_label.setText(f"<span style='font-weight:bold'>{knowledge}</span>（{finished}/{total}）")

    def _kg_update_progress_label(self):
        knowledge = str(getattr(self, '_kg_current_knowledge', '')).strip()
        if not knowledge:
            return
        finished = len(getattr(self, '_kg_finished_rows', set()))
        total = getattr(self, '_kg_total_rows', 0)
        self._kg_set_label_progress(knowledge, finished, total)
        self._update_current_knowledge_label_color_by_completion()

    def _update_current_knowledge_label_color_by_completion(self):
        k = str(getattr(self, '_kg_current_knowledge', '')).strip()
        if not k:
            return
        frames = getattr(self, '_seed_frames', {}) or {}
        meta = frames.get(k)
        if not meta:
            return
        finished = len(getattr(self, '_kg_finished_rows', set()))
        total = getattr(self, '_kg_total_rows', 0)
        if total and finished < total:
            meta['label'].setStyleSheet("color:#ff0000;")
        else:
            ss = meta['frame'].styleSheet() or ""
            if ('#88ff88' in ss) or ('#ff8888' in ss):
                meta['label'].setStyleSheet("color:#000000;")
            else:
                meta['label'].setStyleSheet("color:#ffffff;")

    def on_set_knowledge_output_directory(self):
        try:
            current_dir = self.kg_output_dir_display.text() or os.getcwd()
            directory = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
            if directory:
                self.kg_output_dir_display.setText(directory)
                try:
                    self.config_manager.set_knowledge_output_directory(directory)
                except Exception:
                    pass
        except Exception:
            pass

    def on_open_knowledge_output_directory(self):
        try:
            output_dir = self.kg_output_dir_display.text().strip()
            if not output_dir:
                try:
                    output_dir = self.config_manager.ensure_knowledge_output_directory()
                    self.kg_output_dir_display.setText(output_dir)
                except Exception:
                    return
            try:
                output_dir = os.path.abspath(output_dir)
            except Exception:
                return
            try:
                os.makedirs(output_dir, exist_ok=True)
                if os.name == 'nt':
                    os.startfile(output_dir)
                elif os.name == 'posix':
                    import subprocess
                    import platform
                    if platform.system() == "Darwin":
                        subprocess.run(["open", output_dir])
                    else:
                        subprocess.run(["xdg-open", output_dir])
            except Exception:
                pass
        except Exception:
            pass

    def on_tab_changed(self, index):
        """处理页签切换"""
        if index == 0:  # 会话模式
            # 更新当前对话标签显示为会话模式的当前项
            item = self.sidebar_list.currentItem()
            if item:
                self.current_dialog_label.setText(item.text())
            # 启用表格编辑功能
            self.table_view.setEditTriggers(QTableView.EditTrigger.DoubleClicked)
            # 如果有选中的项目，触发相应的处理
            current_item = self.sidebar_list.currentItem()
            if current_item:
                self.on_sidebar_item_changed(current_item, None)
            else:
                # 如果没有选中项目，从当前表格数据中提取特殊格式
                self.extract_special_format_content()
        elif index == 1:  # 整合模式
            # 更新当前对话标签显示为整合模式的当前项
            item = self.integration_list.currentItem()
            if item:
                self.current_dialog_label.setText(item.text())
            # 禁用表格编辑功能
            self.table_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
            # 如果有选中的项目，触发相应的处理
            current_item = self.integration_list.currentItem()
            if current_item:
                self.on_integration_item_changed(current_item, None)
            else:
                # 如果没有选中项目，从当前表格数据中提取特殊格式
                self.extract_special_format_content()
        
    
    def on_integration_item_changed(self, current, previous):
        """处理整合模式列表选项变化"""
        if not current:
            return
            
        selected_item = current.text()
        self.current_column = selected_item  # 保存当前选择的项
        try:
            self.current_dialog_label.setText(selected_item)
        except Exception:
            pass
        
        # 在整合模式下，需要找出所有包含选中项名字的表头并合并数据
        if hasattr(self, 'table_model') and self.table_model._original_data is not None:
            self.merge_matching_columns(selected_item)
        else:
            # 如果没有数据，调用原有逻辑
            self.on_sidebar_item_changed(current, previous)

    def on_sidebar_item_changed(self, current, previous):
        """处理侧边栏选项变化"""
        if not current:
            return
            
        column_name = current.text()
        self.current_column = column_name  # 保存当前选择的列
        try:
            self.current_dialog_label.setText(column_name)
        except Exception:
            pass

        # 获取用户昵称（使用固定值"贝贝"）
        self.table_model.username = "贝贝"
        
        # 解析NPC名称
        npc1_name = ""
        npc2_name = ""
        
        # 初始化parts变量，避免后面使用时出错
        parts = []
        
        if column_name != 'param1':
            # 解析列名，通常会得到一个包含NPC名称的数组
            parts = column_name.split("-")
            
            if len(parts) >= 1:
                npc1_name = parts[0].strip()
            if len(parts) >= 2:
                npc2_name = parts[1].strip()
                
            # 处理当前表头，提取前两个元素并获取base_id
            if "-" in column_name:
                try:
                    header_parts = column_name.split("-")
                    if len(header_parts) >= 2:
                        element1 = header_parts[0].strip()
                        element2 = header_parts[1].strip()
                        
                        # 使用第一个和第二个元素作为speaker名称获取base_id
                        npc1_base_id = self.character_table_manager.get_base_id_by_speaker(element1)
                        npc2_base_id = self.character_table_manager.get_base_id_by_speaker(element2)
                        
                        # 保存base_id供后续使用
                        self.npc1_base_id = npc1_base_id
                        self.npc2_base_id = npc2_base_id
                        
                        print(f"当前表头处理: '{column_name}' -> 元素1: '{element1}' (base_id: {npc1_base_id}), 元素2: '{element2}' (base_id: {npc2_base_id})")
                except Exception as e:
                    print(f"处理当前表头 '{column_name}' 时出错: {e}")
                    self.npc1_base_id = None
                    self.npc2_base_id = None
            else:
                # 如果不包含"-"，清空base_id
                self.npc1_base_id = None
                self.npc2_base_id = None
        else:
            # 如果不包含"-"，清空base_id
            self.npc1_base_id = None
            self.npc2_base_id = None
        
        # 设置表格模型的NPC名称
        self.table_model.npc1_name = npc1_name
        self.table_model.npc2_name = npc2_name
        
        # 同时设置AudioInspector实例的NPC名称，供立绘切换使用
        self.npc1_name = npc1_name
        self.npc2_name = npc2_name

        # 创建speaker映射
        speaker_mapping = {}
        if len(parts) >= 1:
            speaker_mapping["npc1"] = parts[0]
        if len(parts) >= 2:
            speaker_mapping["npc2"] = parts[1]
            
        # 保存当前的speaker映射
        self.current_speaker_mapping = speaker_mapping

        # 更新表格显示
        self.table_model.update_display(column_name, speaker_mapping)

        # 重置original_dialog_content，让它重新从新的_data中获取
        self.original_dialog_content = None

        # 提取并显示特殊格式内容
        self.extract_special_format_content()

    def merge_matching_columns(self, selected_item):
        """合并所有包含选中项名字的表头数据，每个匹配列的数据作为独立行显示"""
        if not hasattr(self, 'table_model') or self.table_model._original_data is None:
            return
            
        original_data = self.table_model._original_data
        
        # 找出所有包含选中项名字的表头
        matching_columns = []
        for column in original_data.columns:
            if column != 'speaker' and selected_item in column:
                matching_columns.append(column)
        
        print(f"选中项: '{selected_item}', 匹配的表头: {matching_columns}")
        
        if not matching_columns:
            # 如果没有匹配的列，显示空数据
            self.table_model.beginResetModel()
            self.table_model._data = pd.DataFrame(columns=['speaker', 'dialog'])
            self.table_model.endResetModel()
            return
        
        # 为每个匹配列的每行数据创建独立的行
        merged_data = []
        
        for idx, row in original_data.iterrows():
            speaker = row['speaker']
            stage_name = row.get('stage_name', '')  # 获取stage_name，如果不存在则为空字符串
            
            # 为每个匹配列创建独立的行
            for col in matching_columns:
                if pd.notna(row[col]) and str(row[col]).strip():
                    dialog_content = str(row[col]).strip()
                    merged_data.append({
                        'speaker': speaker, 
                        'dialog': dialog_content,
                        'stage_name': stage_name,
                        'orig_row': idx,
                        'orig_col': col
                    })
        
        # 创建合并后的DataFrame
        if merged_data:
            merged_df = pd.DataFrame(merged_data)
        else:
            merged_df = pd.DataFrame(columns=['speaker', 'dialog', 'stage_name'])
        
        # 处理speaker映射和NPC名称替换
        self.process_merged_data(merged_df, selected_item)

    def process_merged_data(self, merged_df, selected_item):
        """处理合并后的数据，应用speaker映射和NPC名称替换"""
        # 解析选中项获取NPC名称
        npc1_name = ""
        npc2_name = ""
        speaker_mapping = {}
        
        if selected_item != 'param1' and '-' in selected_item:
            parts = selected_item.split("-")
            if len(parts) >= 1:
                npc1_name = parts[0].strip()
                speaker_mapping["npc1"] = parts[0]
            if len(parts) >= 2:
                npc2_name = parts[1].strip()
                speaker_mapping["npc2"] = parts[1]
        
        # 设置表格模型的NPC名称
        self.table_model.npc1_name = npc1_name
        self.table_model.npc2_name = npc2_name
        
        # 同时设置AudioInspector实例的NPC名称
        self.npc1_name = npc1_name
        self.npc2_name = npc2_name
        
        # 保存当前的speaker映射
        self.current_speaker_mapping = speaker_mapping
        
        # 应用speaker映射
        if not merged_df.empty:
            # 重新排列列的顺序为：stage_name, speaker, dialog
            ordered_df = pd.DataFrame()
            
            # 第0列：stage_name
            if 'stage_name' in merged_df.columns:
                ordered_df['stage_name'] = merged_df['stage_name'].copy()
            else:
                ordered_df['stage_name'] = ''
            
            # 第1列：speaker（应用映射）
            speakers = merged_df['speaker'].copy()
            for old_val, new_val in speaker_mapping.items():
                speakers = speakers.replace(old_val, new_val)
            
            # 将speaker字段中的"duoki"替换为"多奇"
            speakers = speakers.replace('duoki', '多奇')
            ordered_df['speaker'] = speakers
            
            # 第2列：dialog（应用NPC名称替换）
            dialog_content = merged_df['dialog'].copy()
            if npc1_name:
                dialog_content = dialog_content.str.replace('{npc1_name}', npc1_name)
                dialog_content = dialog_content.str.replace('{npc1_name_origin}', npc1_name)
            
            if npc2_name:
                dialog_content = dialog_content.str.replace('{npc2_name}', npc2_name)
                dialog_content = dialog_content.str.replace('{npc2_name_origin}', npc2_name)
            
            ordered_df['dialog'] = dialog_content
            # 保留原始映射信息
            if 'orig_row' in merged_df.columns:
                ordered_df['orig_row'] = merged_df['orig_row'].copy()
            if 'orig_col' in merged_df.columns:
                ordered_df['orig_col'] = merged_df['orig_col'].copy()
            
            merged_df = ordered_df
        
        # 更新表格模型数据
        self.table_model.beginResetModel()
        self.table_model._data = merged_df
        self.table_model.endResetModel()
        
        # 获取用户昵称
        self.table_model.username = "贝贝"
        
        # 处理base_id
        if selected_item != 'param1' and '-' in selected_item:
            try:
                header_parts = selected_item.split("-")
                if len(header_parts) >= 2:
                    element1 = header_parts[0].strip()
                    element2 = header_parts[1].strip()
                    
                    # 使用第一个和第二个元素作为speaker名称获取base_id
                    npc1_base_id = self.character_table_manager.get_base_id_by_speaker(element1)
                    npc2_base_id = self.character_table_manager.get_base_id_by_speaker(element2)
                    
                    # 保存base_id供后续使用
                    self.npc1_base_id = npc1_base_id
                    self.npc2_base_id = npc2_base_id
                    
                    print(f"整合模式处理: '{selected_item}' -> 元素1: '{element1}' (base_id: {npc1_base_id}), 元素2: '{element2}' (base_id: {npc2_base_id})")
            except Exception as e:
                print(f"处理整合模式选中项 '{selected_item}' 时出错: {e}")
                self.npc1_base_id = None
                self.npc2_base_id = None
        else:
            self.npc1_base_id = None
            self.npc2_base_id = None
        
        # 重置original_dialog_content，让它重新从新的_data中获取
        self.original_dialog_content = None
        
        # 提取并显示特殊格式内容
        self.extract_special_format_content()

    def save_file(self):
        """保存文件功能，将_original_data保存到原xlsx文件"""
        if not hasattr(self.table_model, '_original_data') or self.table_model._original_data is None:
            print("[保存] 失败：没有可保存的数据")
            QMessageBox.warning(self, "警告", "没有可保存的数据")
            return False
            
        if not self.current_file_path:
            print("[保存] 失败：没有指定保存路径")
            QMessageBox.warning(self, "警告", "没有指定保存路径")
            return False
            
        try:
            # 将_original_data保存到原xlsx文件
            self.table_model._original_data.to_excel(self.current_file_path, index=False)
            
            print(f"[保存] 成功: {self.current_file_path}")
            return True
                
        except Exception as e:
            print(f"[保存] 失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"保存文件时出错: {str(e)}")
            return False

    def resizeEvent(self, event):
        """窗口大小改变事件"""
        super().resizeEvent(event)
        # 调整固定列宽度
        if hasattr(self, 'table_view'):
            self.table_view.setColumnWidth(0, 100)  # stage_name列宽度
            self.table_view.setColumnWidth(1, 80)   # speaker列宽度



    def extract_special_format_content(self):
        """从当前对话中提取特殊格式内容"""
        # 清空特殊格式内容表格
        self.format_table.setRowCount(0)
        self.special_format_items = {}
        
        # 永久添加 {user_name} 键值对，置顶显示
        self.special_format_items['{user_name}'] = '贝贝'
        
        # 检查是否有数据
        if self.table_model.rowCount() == 0:
            # 即使没有数据，也要显示user_name
            self.update_format_table()
            return
            
        # 保存原始对话内容（只在第一次或没有原始内容时保存）
        if self.original_dialog_content is None:
            if hasattr(self.table_model, '_original_data') and self.table_model._original_data is not None:
                col = self.current_column if self.current_column in self.table_model._original_data.columns else 'param1'
                self.original_dialog_content = self.table_model._original_data[col].copy()
            else:
                self.original_dialog_content = self.table_model._data['dialog'].copy()
            
        # 收集所有dialog字段的内容
        import re
        
        # 正则表达式模式
        pattern1 = r'\{([^{}]+)\}'  # 匹配 {xxx}
        pattern2 = r'\[([^\[\]]+\|[^\[\]]+(?:\|[^\[\]]+)*)\]'  # 匹配 [xxx|xxx|xxx]
        
        print("开始提取特殊格式内容...")
        
        for row in range(self.table_model.rowCount()):
            # 优先使用原始内容进行提取，确保保存后再次提取仍能识别占位符
            text = None
            if self.original_dialog_content is not None and row < len(self.original_dialog_content):
                text = str(self.original_dialog_content.iloc[row])
            elif hasattr(self.table_model, '_original_data') and self.table_model._original_data is not None:
                col = self.current_column if self.current_column in self.table_model._original_data.columns else 'param1'
                if row < len(self.table_model._original_data) and col in self.table_model._original_data.columns:
                    text = str(self.table_model._original_data.iloc[row][col])
                else:
                    text = None
            if not text:
                dialog_index = self.table_model.index(row, 2)
                text = self.table_model.data(dialog_index, Qt.ItemDataRole.DisplayRole)
            
            if text and text.strip():
                # 查找所有匹配的特殊格式内容
                matches1 = re.findall(pattern1, text)
                matches2 = re.findall(pattern2, text)
                
                # 处理 {xxx} 格式
                for match in matches1:
                    key = '{' + match + '}'
                    # 检查是否有保存的值
                    if key in self.saved_values:
                        self.special_format_items[key] = self.saved_values[key]
                    elif key not in self.special_format_items:
                        # 只有当key不存在时才设置为空，避免覆盖已设置的默认值
                        self.special_format_items[key] = ""
                
                # 处理 [xxx|xxx|xxx] 格式
                for match in matches2:
                    key = '[' + match + ']'
                    # 检查是否有保存的值
                    if key in self.saved_values:
                        self.special_format_items[key] = self.saved_values[key]
                    elif key not in self.special_format_items:
                        # 只有当key不存在时才设置为空，避免覆盖已设置的默认值
                        self.special_format_items[key] = ""
        
        print(f"共提取到 {len(self.special_format_items)} 个特殊格式内容")
        
        # 自动应用 {user_name} 的替换规则
        if '{user_name}' in self.special_format_items:
            self.update_dialog_content('{user_name}', self.special_format_items['{user_name}'])
        
        # 更新特殊格式内容表格
        self.update_format_table()
    
    def update_format_table(self):
        """更新特殊格式内容表格"""
        # 断开信号连接，避免在批量更新时触发cellChanged事件
        self.format_table.blockSignals(True)
        
        # 设置表格行数
        self.format_table.setRowCount(len(self.special_format_items))
        
        # 填充表格
        for i, (key, value) in enumerate(self.special_format_items.items()):
            # 检查是否有保存的值
            if key in self.saved_values:
                value = self.saved_values[key]
                # 同时更新special_format_items
                self.special_format_items[key] = value
                # 如果有保存的值，直接更新对话内容
                self.update_dialog_content(key, value)
            
            # 设置key（不可编辑）
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            key_item.setToolTip(key)
            self.format_table.setItem(i, 0, key_item)
            
            # 设置value（可编辑）
            value_item = QTableWidgetItem(value)
            self.format_table.setItem(i, 1, value_item)
        
        # 恢复信号连接
        self.format_table.blockSignals(False)
    
    def on_format_value_changed(self, row, column):
        """处理特殊格式内容表格的值变化"""
        # 只处理value列的变化
        if column != 1:
            return
            
        # 获取变化的key和value
        key_item = self.format_table.item(row, 0)
        value_item = self.format_table.item(row, 1)
        
        if key_item and value_item:
            key = key_item.text()
            value = value_item.text()
            
            # 更新特殊格式内容字典
            self.special_format_items[key] = value
            
            # 保存value以便在其他表单中使用
            self.saved_values[key] = value
            print(f"保存值: {key} = {value}")
            
            # 更新对话内容
            self.update_dialog_content(key, value)
            
            # 显示Toast提示
            self._show_toast_with_debounce("会话内容已更新")
    
    def update_dialog_content(self, key, value):
        """更新对话内容中的特殊格式内容 - 只在view层进行更新，不修改_data"""
        # 检查是否有数据
        if self.table_model.rowCount() == 0 or self.original_dialog_content is None:
            return
            
        # 创建一个临时的显示数据副本
        temp_display_data = self.table_model._data.copy()
        
        # 为每个key创建使用计数器字典
        key_usage_counters = {}
        
        # 替换特殊格式内容
        for row in range(len(temp_display_data)):
            # 从原始内容开始
            original_dialog = self.original_dialog_content.iloc[row]
            
            # 使用抽象的替换方法，支持顺序值替换
            dialog = self._replace_special_format_core(
                original_dialog, 
                key_usage_counters=key_usage_counters, 
                use_sequential_values=True
            )
                
            # 更新临时显示数据的对话内容
            temp_display_data.iloc[row, 2] = dialog  # dialog列现在是第2列
        
        # 更新表格模型中的数据用于显示
        self.table_model.beginResetModel()
        self.table_model._data = temp_display_data
        self.table_model.endResetModel()

    def on_tts_error(self, error_message):
        """处理TTS错误的槽函数"""
        print(f"TTS错误: {error_message}")
        # 显示错误提示给用户
        self._show_toast_with_debounce(f"TTS错误: {error_message}")
        # 解锁界面，允许用户继续操作
        self.unlock_interface()

    def _show_toast_with_debounce(self, message):
        """防重复显示Toast提示的方法"""
        from PyQt6.QtCore import QTimer
        
        # 如果已有定时器在运行，先停止它
        if self._toast_timer and self._toast_timer.isActive():
            return  # 忽略重复的Toast请求
            
        # 显示Toast
        if hasattr(self, 'toast_manager') and self.toast_manager:
            self.toast_manager.show_toast(message)
            
        # 创建定时器，防止短时间内重复显示
        self._toast_timer = QTimer()
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: None)  # 空操作，只是为了重置状态
        self._toast_timer.start(1000)  # 1秒内不允许重复显示Toast

    def get_cached_image_path(self, image_name):
        """获取缓存图片的本地路径"""
        if not image_name:
            return None
        
        # 支持目录层级，如 scenegraph/zoo/game_ui/zoo_main_top_{level}.jpg
        # 将路径分隔符统一为当前系统的分隔符
        normalized_image_name = image_name.replace('/', os.sep).replace('\\', os.sep)
        cached_path = os.path.join(self.cache_dir, normalized_image_name)
        
        # 确保目录存在
        cached_dir = os.path.dirname(cached_path)
        os.makedirs(cached_dir, exist_ok=True)
        
        return cached_path

    def is_image_cached(self, image_name):
        """检查图片是否已缓存"""
        if not image_name:
            return False
        cached_path = self.get_cached_image_path(image_name)
        return os.path.exists(cached_path)

    def download_image(self, image_name, callback=None, return_pixmap=False):
        """下载图片并缓存到本地，可选择返回图片资源"""
        if not image_name:
            if callback:
                callback(None)
            if return_pixmap:
                return None
            return
        
        # 构建完整的URL
        base_url = "https://portal-test.qidianlingzhi.com:10199/client_resources/getFile?path=client/restaurant/image/"
        full_url = base_url + image_name
        
        def download_worker():
            try:
                print(f"开始下载图片: {full_url}")
                # 设置请求头和cookie
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                # 从认证管理器获取cookie
                cookie_header = self.auth_manager.get_cookie_header()
                if cookie_header:
                    headers['Cookie'] = cookie_header
                response = requests.get(full_url, timeout=10, headers=headers, verify=False)
                response.raise_for_status()
                
                # 保存到缓存目录（支持目录层级）
                cached_path = self.get_cached_image_path(image_name)
                with open(cached_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"图片下载成功: {cached_path}")
                
                # 如果需要返回图片资源，加载并返回
                pixmap = None
                if return_pixmap:
                    pixmap = self.get_image_from_path(cached_path)
                
                if callback:
                    if return_pixmap:
                        callback(cached_path, pixmap)
                    else:
                        callback(cached_path)
                    
            except Exception as e:
                print(f"图片下载失败: {str(e)}")
                if callback:
                    if return_pixmap:
                        callback(None, None)
                    else:
                        callback(None)
        
        # 在后台线程中下载
        thread = threading.Thread(target=download_worker)
        thread.daemon = True
        thread.start()

    def download_npc_portraits(self, base_id, callback=None, return_pixmaps=False):
        """下载NPC的两张立绘图片（静态和说话状态）并缓存到本地
        Args:
            base_id: NPC的base_id
            callback: 回调函数，接收 (image_pixmap, talk_pixmap) 或 (image_path, talk_path)
            return_pixmaps: 是否返回QPixmap对象
        """
        if not base_id:
            if callback:
                callback(None, None)
            return
        
        # 构建立绘图片名称
        image_name = f"{base_id}-image.png"
        talk_name = f"{base_id}-talk.gif"
        
        # 构建完整的URL
        base_url = "https://portal-test.qidianlingzhi.com:10199/client_resources/getFile?path=client/common/image/unit/"
        image_url = base_url + image_name
        talk_url = base_url + talk_name
        
        def download_worker():
            try:
                image_pixmap = None
                talk_pixmap = None
                image_path = None
                talk_path = None
                
                # 设置请求头和cookie
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                # 从认证管理器获取cookie
                cookie_header = self.auth_manager.get_cookie_header()
                
                # 下载静态立绘
                print(f"开始下载NPC静态立绘: {image_url}")
                if cookie_header:
                    headers['Cookie'] = cookie_header
                response = requests.get(image_url, timeout=10, headers=headers, verify=False)
                response.raise_for_status()
                
                image_path = self.get_cached_image_path(image_name)
                with open(image_path, 'wb') as f:
                    f.write(response.content)
                print(f"NPC静态立绘下载成功: {image_path}")
                
                if return_pixmaps:
                    image_pixmap = self.get_image_from_path(image_path)
                
                # 下载说话立绘
                print(f"开始下载NPC说话立绘: {talk_url}")
                response = requests.get(talk_url, timeout=10, headers=headers, verify=False)
                response.raise_for_status()
                
                talk_path = self.get_cached_image_path(talk_name)
                with open(talk_path, 'wb') as f:
                    f.write(response.content)
                print(f"NPC说话立绘下载成功: {talk_path}")
                
                if return_pixmaps:
                    talk_pixmap = self.get_image_from_path(talk_path)
                
                if callback:
                    if return_pixmaps:
                        callback(image_pixmap, talk_pixmap)
                    else:
                        callback(image_path, talk_path)
                        
            except Exception as e:
                print(f"NPC立绘下载失败: {str(e)}")
                if callback:
                    callback(None, None)
        
        # 在后台线程中下载
        thread = threading.Thread(target=download_worker)
        thread.daemon = True
        thread.start()

    def download_npc_portrait(self, base_id, callback=None, return_pixmap=False):
        """下载NPC立绘图片并缓存到本地（保持向后兼容）
        Args:
            base_id: NPC的base_id
            callback: 回调函数
            return_pixmap: 是否返回QPixmap对象
        """
        if not base_id:
            if callback:
                callback(None)
            if return_pixmap:
                return None
            return
        
        # 构建立绘图片名称
        portrait_name = f"{base_id}-image.png"
        
        # 构建完整的URL
        base_url = "https://portal-test.qidianlingzhi.com:10199/client_resources/getFile?path=client/common/image/"
        full_url = base_url + portrait_name
        
        def download_worker():
            try:
                print(f"开始下载NPC立绘: {full_url}")
                # 设置请求头和cookie
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                # 从认证管理器获取cookie
                cookie_header = self.auth_manager.get_cookie_header()
                
                if cookie_header:
                    headers['Cookie'] = cookie_header
                response = requests.get(full_url, timeout=10, headers=headers, verify=False)
                response.raise_for_status()
                
                # 保存到缓存目录
                cached_path = self.get_cached_image_path(portrait_name)
                with open(cached_path, 'wb') as f:
                    f.write(response.content)
                
                print(f"NPC立绘下载成功: {cached_path}")
                
                # 如果需要返回图片资源，加载并返回
                pixmap = None
                if return_pixmap:
                    pixmap = self.get_image_from_path(cached_path)
                
                if callback:
                    if return_pixmap:
                        callback(cached_path, pixmap)
                    else:
                        callback(cached_path)
                    
            except Exception as e:
                print(f"NPC立绘下载失败: {str(e)}")
                if callback:
                    if return_pixmap:
                        callback(None, None)
                    else:
                        callback(None)
        
        # 在后台线程中下载
        thread = threading.Thread(target=download_worker)
        thread.daemon = True
        thread.start()

    def are_npc_portraits_cached(self, base_id):
        """检查NPC的两张立绘是否都已缓存"""
        if not base_id:
            return False
        image_name = f"{base_id}-image.png"
        talk_name = f"{base_id}-talk.gif"
        return self.is_image_cached(image_name) and self.is_image_cached(talk_name)

    def is_npc_portrait_cached(self, base_id):
        """检查NPC立绘是否已缓存（保持向后兼容）"""
        if not base_id:
            return False
        portrait_name = f"{base_id}-image.png"
        return self.is_image_cached(portrait_name)

    def get_cached_npc_portrait_paths(self, base_id):
        """获取缓存的NPC两张立绘路径
        Returns:
            tuple: (image_path, talk_path)
        """
        if not base_id:
            return None, None
        image_name = f"{base_id}-image.png"
        talk_name = f"{base_id}-talk.gif"
        return self.get_cached_image_path(image_name), self.get_cached_image_path(talk_name)

    def get_cached_npc_portrait_path(self, base_id):
        """获取缓存的NPC立绘路径（保持向后兼容）"""
        if not base_id:
            return None
        portrait_name = f"{base_id}-image.png"
        return self.get_cached_image_path(portrait_name)

    def load_images(self, image_names, callback=None):
        """加载多个图片并返回图片资源数组
        Args:
            image_names: 图片名称数组 [image1, image2]
            callback: 回调函数，接收图片资源数组 [pixmap1, pixmap2]
        Returns:
            None (异步操作通过callback返回结果)
        """
        if not image_names or len(image_names) == 0:
            if callback:
                callback([None, None])
            return
        
        # 确保数组长度为2
        while len(image_names) < 2:
            image_names.append(None)
        
        image1_name = image_names[0]
        image2_name = image_names[1] if len(image_names) > 1 else None
        
        # 结果数组
        results = [None, None]
        completed_count = 0
        
        def check_completion():
            nonlocal completed_count
            completed_count += 1
            if callback:
                callback(results)
        
        def load_image1():
            if not image1_name:
                results[0] = None
                check_completion()
                return
            
            # 检查是否已缓存
            if self.is_image_cached(image1_name):
                cached_path = self.get_cached_image_path(image1_name)
                results[0] = self.get_image_from_path(cached_path)
                check_completion()
            else:
                # 下载图片
                def on_image1_downloaded(path, pixmap):
                    results[0] = pixmap
                    check_completion()
                self.download_image(image1_name, on_image1_downloaded, return_pixmap=True)
        
        def load_image2():
            if not image2_name:
                results[1] = None
                check_completion()
                return
            
            # 检查是否已缓存
            if self.is_image_cached(image2_name):
                cached_path = self.get_cached_image_path(image2_name)
                results[1] = self.get_image_from_path(cached_path)
                check_completion()
            else:
                # 下载图片
                def on_image2_downloaded(path, pixmap):
                    results[1] = pixmap
                    check_completion()
                self.download_image(image2_name, on_image2_downloaded, return_pixmap=True)
        
        # 并行加载两个图片
        load_image1()
        load_image2()

    def load_and_display_image(self, image_name):
        """加载并显示单个图片（保留原方法以兼容现有代码）"""
        if not image_name:
            self.image_container.clear()
            self.image_container.setText("无图片")
            return
        
        # 检查是否已缓存
        if self.is_image_cached(image_name):
            cached_path = self.get_cached_image_path(image_name)
            self.display_image_from_path(cached_path)
        else:
            # 显示加载中状态
            self.image_container.clear()
            self.image_container.setText("图片加载中...")
            # 下载图片
            self.download_image(image_name, self.on_image_downloaded)

    def get_image_from_path(self, image_path):
        """从路径获取图片资源"""
        if not image_path or not os.path.exists(image_path):
            return None
        
        try:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                print(f"无法加载图片: {image_path}")
                return None
            return pixmap
        except Exception as e:
            print(f"加载图片时出错: {str(e)}")
            return None
    
    def _scale_image_to_width(self, pixmap, target_width):
        """将图片按宽度缩放，高度按比例计算
        
        Args:
            pixmap: 要缩放的QPixmap
            target_width: 目标宽度
            
        Returns:
            tuple: (scaled_pixmap, scaled_height)
        """
        original_width = pixmap.width()
        original_height = pixmap.height()
        
        # 计算缩放比例和目标高度
        scale = target_width / original_width
        scaled_height = int(original_height * scale)
        
        # 缩放图片
        scaled_pixmap = pixmap.scaled(
            target_width, scaled_height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        return scaled_pixmap, scaled_height

    def _create_canvas_with_painter(self, width, height):
        """创建画布和画笔
        
        Args:
            width: 画布宽度
            height: 画布高度
            
        Returns:
            tuple: (canvas_pixmap, painter)
        """
        from PyQt6.QtGui import QPainter
        
        canvas = QPixmap(width, height)
        canvas.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        return canvas, painter
    
    def _draw_image_at_position(self, painter, pixmap, x, y):
        """在指定位置绘制图片
        
        Args:
            painter: QPainter对象
            pixmap: 要绘制的QPixmap
            x: x坐标
            y: y坐标
        """
        painter.drawPixmap(x, y, pixmap)

    def display_image(self, pixmaps):
        """显示图片到容器中
        Args:
            pixmaps: 单个QPixmap或QPixmap数组
        """
        # 处理单个图片的情况（向后兼容）
        if isinstance(pixmaps, QPixmap):
            pixmaps = [pixmaps]
        elif not isinstance(pixmaps, list):
            pixmaps = [pixmaps] if pixmaps else []
        
        # 过滤掉None和无效的pixmap
        valid_pixmaps = [p for p in pixmaps if p and not p.isNull()]
        
        if not valid_pixmaps:
            pass
        
        # 获取容器大小
        container_size = self.image_container.size()
        container_width = container_size.width()
        container_height = container_size.height()
        
        # 如果容器太小，使用默认大小
        if container_width < 100 or container_height < 100:
            container_width = 400
            container_height = 400
        
        # 异步加载NPC立绘，然后统一显示
        self._load_and_display_all_images(valid_pixmaps, container_width, container_height)

    def _render_on_ui(self, scene_pixmaps, container_width, container_height, display_portraits):
        self._display_multiple_images(scene_pixmaps, container_width, container_height, display_portraits)
    
    def switch_npc_portrait_state(self, speaker_name):
        """根据说话人切换NPC立绘状态
        Args:
            speaker_name: 当前说话人的名字
        """
        if not hasattr(self, 'npc_portraits_cache') or not self.npc_portraits_cache:
            return
        
        # 获取NPC名字
        npc1_name = getattr(self, 'npc1_name', None)
        npc2_name = getattr(self, 'npc2_name', None)
        
        if not npc1_name and not npc2_name:
            return
        
        # 确定当前说话的NPC和静默的NPC
        talking_npc_index = None
        if speaker_name == npc1_name:
            talking_npc_index = 0
        elif speaker_name == npc2_name:
            talking_npc_index = 1
        # 如果speaker不是npc1也不是npc2，talking_npc_index保持为None
        
        # 构建显示的立绘列表
        display_portraits = [None, None]
        
        for i in range(2):
            if i < len(self.npc_portraits_cache) and self.npc_portraits_cache[i]:
                if talking_npc_index is not None and i == talking_npc_index:
                    # 说话的NPC显示talk状态
                    display_portraits[i] = self.npc_portraits_cache[i]['talk']
                else:
                    # 其他NPC显示静态状态（包括当speaker不是npc1也不是npc2的情况）
                    display_portraits[i] = self.npc_portraits_cache[i]['image']

        # 获取当前场景图片
        scene_pixmaps = []
        if hasattr(self, 'current_scene_pixmaps') and self.current_scene_pixmaps:
            scene_pixmaps = self.current_scene_pixmaps
        
        # 获取容器尺寸
        container_width = self.image_container.width()
        container_height = self.image_container.height()
        
        # 更新显示
        print(f"切换NPC立绘状态: 说话人={speaker_name}, 说话NPC索引={talking_npc_index}")
        self.render_request.emit(scene_pixmaps, container_width, container_height, display_portraits)

    def _load_and_display_all_images(self, scene_pixmaps, container_width, container_height):
        """异步加载NPC立绘，然后统一显示所有图片
        Args:
            scene_pixmaps: 已加载的场景图片列表
            container_width: 容器宽度
            container_height: 容器高度
        """
        # 存储当前场景图片，供后续切换使用
        self.current_scene_pixmaps = scene_pixmaps
        
        self.render_request.emit(scene_pixmaps, container_width, container_height, None)
        
        # 检查是否有有效的base_id
        if not hasattr(self, 'npc1_base_id') or not hasattr(self, 'npc2_base_id'):
            return
        
        if not self.npc1_base_id and not self.npc2_base_id:
            return
        
        # 异步加载NPC立绘
        npc_portraits = [{'image': None, 'talk': None}, {'image': None, 'talk': None}]
        completed_count = 0
        total_count = 0
        
        # 计算需要加载的NPC立绘数量
        if self.npc1_base_id:
            total_count += 1
        if self.npc2_base_id:
            total_count += 1
        
        if total_count == 0:
            self.render_request.emit(scene_pixmaps, container_width, container_height, None)
            return
        
        def check_completion():
            nonlocal completed_count
            completed_count += 1
            # 每次有新的立绘就尝试即时渲染，避免等待切句子
            self._trigger_immediate_render(container_width, container_height)
        
        # 加载NPC1立绘
        if self.npc1_base_id:
            def on_npc1_loaded(image_pixmap, talk_pixmap):
                npc_portraits[0]['image'] = image_pixmap
                npc_portraits[0]['talk'] = talk_pixmap
                self.npc_portraits_cache = npc_portraits
                check_completion()
            self._load_npc_portraits_async(self.npc1_base_id, on_npc1_loaded)
        
        # 加载NPC2立绘
        if self.npc2_base_id:
            def on_npc2_loaded(image_pixmap, talk_pixmap):
                npc_portraits[1]['image'] = image_pixmap
                npc_portraits[1]['talk'] = talk_pixmap
                self.npc_portraits_cache = npc_portraits
                check_completion()
            self._load_npc_portraits_async(self.npc2_base_id, on_npc2_loaded)
        
        # 存储NPC立绘状态
        self.npc_portraits_cache = npc_portraits

    def _trigger_immediate_render(self, container_width, container_height):
        scene_pixmaps = self.current_scene_pixmaps if hasattr(self, 'current_scene_pixmaps') else []
        # 构建显示立绘：优先根据当前说话人使用talk，否则使用image
        display_portraits = [None, None]
        if hasattr(self, 'npc_portraits_cache') and self.npc_portraits_cache:
            npc1_name = getattr(self, 'npc1_name', None)
            npc2_name = getattr(self, 'npc2_name', None)
            for i in range(2):
                cache = self.npc_portraits_cache[i] if i < len(self.npc_portraits_cache) else None
                if not cache:
                    continue
                if self.current_speaker_name and ((i == 0 and self.current_speaker_name == npc1_name) or (i == 1 and self.current_speaker_name == npc2_name)):
                    display_portraits[i] = cache['talk']
                else:
                    display_portraits[i] = cache['image']
        self.render_request.emit(scene_pixmaps, container_width, container_height, display_portraits)
    
    def _load_npc_portraits_async(self, base_id, callback):
        """异步加载单个NPC的两张立绘图片
        Args:
            base_id: NPC的base_id
            callback: 回调函数，接收 (image_pixmap, talk_pixmap) 参数
        """
        if not base_id:
            callback(None, None)
            return
        
        # 检查缓存
        if self.are_npc_portraits_cached(base_id):
            image_path, talk_path = self.get_cached_npc_portrait_paths(base_id)
            if os.path.exists(image_path) and os.path.exists(talk_path):
                image_pixmap = QPixmap(image_path)
                talk_pixmap = QPixmap(talk_path)
                if not image_pixmap.isNull() and not talk_pixmap.isNull():
                    print(f"从缓存加载NPC立绘: {base_id} -> {image_path}, {talk_path}")
                    callback(image_pixmap, talk_pixmap)
                    return
        
        # 下载图片
        def on_download_complete(image_pixmap, talk_pixmap):
            if image_pixmap and talk_pixmap and not image_pixmap.isNull() and not talk_pixmap.isNull():
                print(f"成功下载NPC立绘: {base_id}")
                callback(image_pixmap, talk_pixmap)
            else:
                print(f"下载NPC立绘失败: {base_id}")
                callback(None, None)
        
        try:
            print(f"开始下载NPC立绘: {base_id}")
            self.download_npc_portraits(base_id, on_download_complete, return_pixmaps=True)
        except Exception as e:
            print(f"下载NPC立绘异常: {base_id}, 错误: {e}")
            callback(None, None)

    def _load_npc_portrait_async(self, base_id, callback):
        """异步加载单个NPC立绘图片（保持向后兼容）
        Args:
            base_id: NPC的base_id
            callback: 回调函数，接收QPixmap参数
        """
        if not base_id:
            callback(None)
            return
        
        # 检查缓存
        if self.is_npc_portrait_cached(base_id):
            cached_path = self.get_cached_npc_portrait_path(base_id)
            if os.path.exists(cached_path):
                pixmap = QPixmap(cached_path)
                if not pixmap.isNull():
                    print(f"从缓存加载NPC立绘: {base_id} -> {cached_path}")
                    callback(pixmap)
                    return
        
        # 下载图片
        def on_download_complete(path, pixmap):
            if pixmap and not pixmap.isNull():
                print(f"成功下载NPC立绘: {base_id}")
                callback(pixmap)
            else:
                print(f"下载NPC立绘失败: {base_id}")
                callback(None)
        
        try:
            print(f"开始下载NPC立绘: {base_id}")
            self.download_npc_portrait(base_id, on_download_complete, return_pixmap=True)
        except Exception as e:
            print(f"下载NPC立绘异常: {base_id}, 错误: {e}")
            callback(None)
    
    def _display_multiple_images(self, pixmaps, container_width, container_height, npc_portraits=None):
        """显示多张图片，image1撑满宽度，image2紧贴底边并撑满宽度，npc立绘显示在左右两侧
        Args:
            pixmaps: 场景图片列表 [image1, image2]
            container_width: 容器宽度
            container_height: 容器高度
            npc_portraits: NPC立绘图片列表 [npc1_portrait, npc2_portrait]
        """
        # 检查是否有GIF动画需要播放
        has_gif = False
        gif_path = None
        
        if npc_portraits:
            for i, portrait in enumerate(npc_portraits):
                if portrait and hasattr(self, 'npc_portraits_cache') and self.npc_portraits_cache:
                    # 检查当前立绘是否是talk状态（GIF动画）
                    if i < len(self.npc_portraits_cache) and self.npc_portraits_cache[i]:
                        talk_portrait = self.npc_portraits_cache[i]['talk']
                        if portrait == talk_portrait:
                            # 这是talk状态的立绘，需要播放GIF
                            # 获取对应的GIF文件路径
                            npc_base_id = getattr(self, f'npc{i+1}_base_id', None)
                            if npc_base_id:
                                gif_path = self.get_cached_image_path(f"{npc_base_id}-talk.gif")
                                if gif_path and os.path.exists(gif_path):
                                    has_gif = True
                                    break
        
        if has_gif and gif_path:
            # 有GIF动画，使用QMovie播放
            self._display_images_with_gif_animation(pixmaps, container_width, container_height, npc_portraits, gif_path)
        else:
            if hasattr(self.image_container, 'current_movie') and self.image_container.current_movie:
                self.image_container.current_movie.stop()
                self.image_container.current_movie = None
            if hasattr(self.image_container, 'clearGif'):
                self.image_container.clearGif()
            self._display_static_images(pixmaps, container_width, container_height, npc_portraits)
    
    def _display_images_with_gif_animation(self, pixmaps, container_width, container_height, npc_portraits, gif_path):
        """显示包含GIF动画的图片
        Args:
            pixmaps: 场景图片列表
            container_width: 容器宽度
            container_height: 容器高度
            npc_portraits: NPC立绘图片列表
            gif_path: GIF文件路径
        """
        print(f"尝试播放GIF动画: {gif_path}")
        
        # 首先绘制背景图片（场景图片）
        combined_pixmap, painter = self._create_canvas_with_painter(container_width, container_height)
        
        # 处理第一张图片（image1）- 撑满宽度，位于上半部分
        if len(pixmaps) >= 1:
            pixmap1 = pixmaps[0]
            scaled_pixmap1, scaled_height1 = self._scale_image_to_width(pixmap1, container_width)
            if self._bg_from_show_image_npc:
                scaled_pixmap1 = self._desaturate_pixmap(scaled_pixmap1)
            self._draw_image_at_position(painter, scaled_pixmap1, 0, 0)
        
        # 处理第二张图片（image2）- 撑满宽度，紧贴image1底部
        if len(pixmaps) >= 2:
            pixmap2 = pixmaps[1]
            scaled_pixmap2, scaled_height2 = self._scale_image_to_width(pixmap2, container_width)
            
            # 计算image2的y坐标（紧贴image1底部）
            if len(pixmaps) >= 1:
                _, scaled_height1 = self._scale_image_to_width(pixmaps[0], container_width)
                y2 = scaled_height1
            else:
                y2 = 0
            
            self._draw_image_at_position(painter, scaled_pixmap2, 0, y2)
        
        # 处理静态NPC立绘（非GIF的立绘）
        gif_npc_index = -1
        gif_x = 0
        gif_y = 0
        
        if npc_portraits:
            npc_max_width = container_width // 3
            
            # 计算背景图的缩放比例
            background_scale = 1.0
            if len(pixmaps) >= 1:
                original_width = pixmaps[0].width()
                background_scale = container_width / original_width
            
            # 找出哪个NPC是GIF动画
            for i, portrait in enumerate(npc_portraits):
                if portrait and hasattr(self, 'npc_portraits_cache') and self.npc_portraits_cache:
                    if i < len(self.npc_portraits_cache) and self.npc_portraits_cache[i]:
                        talk_portrait = self.npc_portraits_cache[i]['talk']
                        if portrait == talk_portrait:
                            gif_npc_index = i
                            break
            
            # 绘制静态NPC立绘并计算GIF位置
            for i, portrait in enumerate(npc_portraits):
                if portrait:
                    npc_scaled = self._scale_npc_portrait(portrait, npc_max_width, container_height)
                    if npc_scaled:
                        if i == 0:  # NPC1 (左侧)
                            npc_x = 10
                        else:  # NPC2 (右侧)
                            npc_x = container_width - npc_scaled.width() - 10
                        # 立绘底边位于y=540*背景图scale的位置，所以y坐标=540*背景图scale-立绘高度
                        npc_y = int(540 * background_scale - npc_scaled.height()) if len(pixmaps) >= 2 else (container_height - npc_scaled.height())
                        
                        if i == gif_npc_index:
                            # 这是GIF动画的位置，记录位置但不绘制静态图片
                            gif_x = npc_x
                            gif_y = npc_y
                        else:
                            # 绘制静态NPC立绘
                            self._draw_image_at_position(painter, npc_scaled, npc_x, npc_y)
        
        painter.end()
        
        # 创建并播放GIF动画
        if os.path.exists(gif_path):
            movie = QMovie(gif_path)
            if movie.isValid():
                # 计算GIF动画的大小
                npc_max_width = container_width // 3
                
                # 使用新的方法设置背景和GIF动画
                try:
                    movie.setCacheMode(QMovie.CacheMode.CacheAll)
                    movie.jumpToFrame(0)
                except Exception:
                    pass
                self.image_container.setBackgroundWithGif(
                    combined_pixmap, movie, gif_x, gif_y, npc_max_width, npc_max_width
                )
                self.image_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
                
                print(f"开始播放GIF动画: {gif_path}, 位置: ({gif_x}, {gif_y}), 大小: {npc_max_width}x{npc_max_width}")
            else:
                print(f"无效的GIF文件: {gif_path}")
                # 回退到静态显示
                self._display_static_images(pixmaps, container_width, container_height, npc_portraits)
        else:
            print(f"GIF文件不存在: {gif_path}")
            # 回退到静态显示
            self._display_static_images(pixmaps, container_width, container_height, npc_portraits)
    
    def _display_static_images(self, pixmaps, container_width, container_height, npc_portraits=None):
        """显示静态图片（原来的_display_multiple_images逻辑）
        Args:
            pixmaps: 场景图片列表 [image1, image2]
            container_width: 容器宽度
            container_height: 容器高度
            npc_portraits: NPC立绘图片列表 [npc1_portrait, npc2_portrait]
        """
        # 创建画布和画笔
        combined_pixmap, painter = self._create_canvas_with_painter(container_width, container_height)
        
        # 处理第一张图片（image1）- 撑满宽度，位于上半部分
        if len(pixmaps) >= 1:
            pixmap1 = pixmaps[0]
            scaled_pixmap1, scaled_height1 = self._scale_image_to_width(pixmap1, container_width)
            if self._bg_from_show_image_npc:
                scaled_pixmap1 = self._desaturate_pixmap(scaled_pixmap1)
            self._draw_image_at_position(painter, scaled_pixmap1, 0, 0)
        
        # 处理第二张图片（image2）- 撑满宽度，紧贴image1底部
        if len(pixmaps) >= 2:
            pixmap2 = pixmaps[1]
            
            # 缩放第二张图片
            scaled_pixmap2, scaled_height2 = self._scale_image_to_width(pixmap2, container_width)
            
            # 计算image2的y坐标（紧贴image1底部）
            if len(pixmaps) >= 1:
                # 获取第一张图片的缩放高度
                _, scaled_height1 = self._scale_image_to_width(pixmaps[0], container_width)
                y2 = scaled_height1  # 紧贴image1底部
            else:
                y2 = 0  # 如果没有image1，从顶部开始
            
            # 绘制第二张图片
            self._draw_image_at_position(painter, scaled_pixmap2, 0, y2)
        
        # 处理NPC立绘 - 显示在左右两侧，底边位于540*背景图scale的位置
        if npc_portraits:
            # NPC立绘的最大宽度（容器宽度的1/4）
            npc_max_width = container_width // 3
            
            # 计算背景图的缩放比例
            background_scale = 1.0
            if len(pixmaps) >= 1:
                original_width = pixmaps[0].width()
                background_scale = container_width / original_width
            
            # 处理NPC1立绘（左侧）
            if len(npc_portraits) >= 1 and npc_portraits[0]:
                npc1_pixmap = npc_portraits[0]
                # 按比例缩放NPC1立绘，限制最大宽度
                npc1_scaled = self._scale_npc_portrait(npc1_pixmap, npc_max_width, container_height)
                if npc1_scaled:
                    # 计算左侧位置
                    npc1_x = 10  # 左边距
                    # 立绘底边位于y=540*背景图scale的位置，所以y坐标=540*背景图scale-立绘高度
                    npc1_y = int(540 * background_scale - npc1_scaled.height())
                    self._draw_image_at_position(painter, npc1_scaled, npc1_x, npc1_y)
            # 处理NPC2立绘（右侧）
            if len(npc_portraits) >= 2 and npc_portraits[1]:
                npc2_pixmap = npc_portraits[1]
                # 按比例缩放NPC2立绘，限制最大宽度
                npc2_scaled = self._scale_npc_portrait(npc2_pixmap, npc_max_width, container_height)
                if npc2_scaled:
                    # 计算右侧位置
                    npc2_x = container_width - npc2_scaled.width() - 10  # 右边距
                    # 立绘底边位于y=540*背景图scale的位置，所以y坐标=540*背景图scale-立绘高度
                    npc2_y = int(540 * background_scale - npc2_scaled.height())
                    self._draw_image_at_position(painter, npc2_scaled, npc2_x, npc2_y)
        
        painter.end()
        
        # 显示组合后的图片
        self.image_container.setPixmap(combined_pixmap)
        self.image_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _scale_npc_portrait(self, pixmap, max_width, max_height):
        """缩放NPC立绘，保持宽高比，限制最大尺寸
        Args:
            pixmap: 原始图片
            max_width: 最大宽度
            max_height: 最大高度
        Returns:
            缩放后的QPixmap
        """
        if not pixmap or pixmap.isNull():
            return None
        
        original_width = pixmap.width()
        original_height = pixmap.height()
        
        # 计算缩放比例，保持宽高比
        width_scale = max_width / original_width
        height_scale = max_height / original_height
        scale = min(width_scale, height_scale, 1.0)  # 不放大，只缩小
        
        # 计算目标尺寸
        target_width = int(original_width * scale)
        target_height = int(original_height * scale)
        
        # 缩放图片
        scaled_pixmap = pixmap.scaled(
            target_width, target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        return scaled_pixmap

    def _desaturate_pixmap(self, pixmap, factor=1):
        # 临时覆盖：仅在show_image_npc背景时使用滑动条值
        override = self._saturation_factor_override
        if override is None:
            factor = self.config_manager.get_image_npc_desaturate()
        else:
            factor = max(0.0, min(1.0, float(override)))
        if factor == 1:
            return pixmap
        img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        w = img.width()
        h = img.height()
        for y in range(h):
            for x in range(w):
                c = QColor.fromRgb(img.pixel(x, y))
                h_ = c.hslHue()
                s = c.hslSaturation()
                l = c.lightness()
                a = c.alpha()
                s = int(s * factor)
                c.setHsl(h_, s, l, a)
                img.setPixel(x, y, c.rgba())
        return QPixmap.fromImage(img)

    def on_saturation_changed(self, value):
        factor = max(0.0, min(1.0, float(value) / 100.0))
        self._saturation_factor_override = factor
        print(f"饱和度调整: factor={factor}")
        if hasattr(self, 'saturation_value_label') and self.saturation_value_label:
            self.saturation_value_label.setText(f"{factor:.2f}")
        # 仅当当前背景来自show_image_npc时重渲染
        if self._bg_from_show_image_npc:
            cw = self.image_container.width()
            ch = self.image_container.height()
            self._trigger_immediate_render(cw, ch)

    def display_image_from_path(self, image_path):
        """从路径显示图片（保留原方法以兼容现有代码）"""
        pixmap = self.get_image_from_path(image_path)
        self.display_image(pixmap)

    def on_image_downloaded(self, image_path):
        """图片下载完成的回调"""
        if image_path:
            self.display_image_from_path(image_path)
        else:
            self.image_container.setText("图片下载失败")

class FormatItemDelegate(QStyledItemDelegate):
    """自定义委托，用于处理不同类型的编辑控件"""
    def createEditor(self, parent, option, index):
        # 只处理第二列（value列）
        if index.column() != 1:
            return super().createEditor(parent, option, index)
            
        # 获取当前行的key
        key = index.model().item(index.row(), 0).text() if hasattr(index.model(), 'item') else index.sibling(index.row(), 0).data()
        
        # 检查是否是需要下拉列表的格式
        if ('|' in key) and (key.startswith('[') or key.startswith('{')):
            # 创建下拉列表
            combo = QComboBox(parent)
            combo.setStyleSheet("background-color: white; color: black;")  # 设置不透明背景和黑色文字
            # 去掉括号，然后按|分割
            content = key.strip('[]{}')
            options = content.split('|')
            for option in options:
                combo.addItem(option.strip())
            # 设置下拉框在获得焦点时自动展开
            combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            
            # 重写focusInEvent方法来自动展开下拉列表
            original_focus_in_event = combo.focusInEvent
            def custom_focus_in_event(event):
                original_focus_in_event(event)
                combo.showPopup()
            combo.focusInEvent = custom_focus_in_event
            
            return combo
        else:
            # 创建普通文本输入框
            editor = QLineEdit(parent)
            editor.setStyleSheet("background-color: white; color: black;")  # 设置不透明背景和黑色文字
            # 安装事件过滤器来处理回车键
            editor.installEventFilter(self)
            return editor
    
    def eventFilter(self, obj, event):
        """处理编辑器的事件，特别是回车键"""
        if isinstance(obj, QLineEdit) and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                # 提交当前编辑
                self.commitData.emit(obj)
                self.closeEditor.emit(obj)
                
                # 获取表格视图
                table = obj.parent()
                while table and not isinstance(table, QTableWidget):
                    table = table.parent()
                
                if table:
                    # 获取当前行
                    current_row = table.currentRow()
                    # 移动到下一行的value列
                    next_row = current_row + 1
                    if next_row < table.rowCount():
                        table.setCurrentCell(next_row, 1)  # 设置到下一行的value列
                        table.edit(table.currentIndex())  # 开始编辑
                
                return True
        
        return super().eventFilter(obj, event)
            
    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.DisplayRole)
        if isinstance(editor, QComboBox):
            # 如果当前值在选项中，则选中它
            current_index = editor.findText(value)
            if current_index >= 0:
                editor.setCurrentIndex(current_index)
        else:
            editor.setText(str(value) if value is not None else "")
            
    def setModelData(self, editor, model, index):
        if isinstance(editor, QComboBox):
            value = editor.currentText()
        else:
            value = editor.text()
        model.setData(index, value, Qt.ItemDataRole.EditRole)
        
        # 获取当前行和列
        row = index.row()
        column = index.column()
        
        # 只处理value列的变化
        if column == 1:
            # 获取对应的key
            key_index = index.sibling(row, 0)
            key = model.data(key_index, Qt.ItemDataRole.DisplayRole)
            
            # 获取AudioInspector实例并更新对话内容
            parent = editor.parent()
            while parent and not isinstance(parent, AudioInspector):
                parent = parent.parent()
                
            if parent and isinstance(parent, AudioInspector):
                parent.special_format_items[key] = value
                # 同时更新saved_values字典
                parent.saved_values[key] = value
                print(f"委托中保存值: {key} = {value}")
                parent.update_dialog_content(key, value)
                
                # 显示Toast提示
                parent._show_toast_with_debounce("会话内容已更新")
        try:
            self._open_btn_prev_enabled = self.open_file_btn.isEnabled()
            self.open_file_btn.setEnabled(False)
        except Exception:
            pass
        try:
            self._clear_image_memory()
        except Exception:
            pass
