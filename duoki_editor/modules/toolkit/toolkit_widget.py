from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QFileDialog, QTextEdit, QLabel, QStackedWidget, QComboBox, QMessageBox, QDoubleSpinBox, QSizePolicy, QCheckBox, QRadioButton, QListWidget, QListWidgetItem
from PyQt6.QtCore import Qt, QUrl, QSize, QThread, pyqtSignal, QRegularExpression
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QPixmap, QSyntaxHighlighter, QTextCharFormat, QColor, QFont
import os
import sys
import time
import json
import subprocess
import locale
import requests
import pandas as pd
from duoki_editor.utils.config_manager import ConfigManager
from duoki_editor.ui.toast import ToastManager
from duoki_editor.utils.mp3format import convert_all_mp3_in_directory
from duoki_editor.modules.ai_image_generator.ai_image_generator import CARTOON_STYLE_SUFFIX
from duoki_editor.modules.content_generator.coze_client import CozeAPIClient, CozeWorkerThread


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []

        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569CD6"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "and", "as", "assert", "break", "class", "continue", "def", "del",
            "elif", "else", "except", "False", "finally", "for", "from",
            "global", "if", "import", "in", "is", "lambda", "None", "nonlocal",
            "not", "or", "pass", "raise", "return", "True", "try", "while",
            "with", "yield"
        ]
        for word in keywords:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self.highlighting_rules.append((pattern, keyword_format))

        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#4EC9B0"))
        builtins = [
            "abs", "all", "any", "bool", "bytes", "dict", "dir", "enumerate",
            "float", "int", "len", "list", "map", "max", "min", "object",
            "print", "range", "set", "str", "sum", "tuple", "zip"
        ]
        for word in builtins:
            pattern = QRegularExpression(r"\b" + word + r"\b")
            self.highlighting_rules.append((pattern, builtin_format))

        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))
        number_pattern = QRegularExpression(r"\b[0-9]+(\.[0-9]+)?\b")
        self.highlighting_rules.append((number_pattern, number_format))

        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178"))
        single_quoted = QRegularExpression(r"'[^'\n]*'")
        double_quoted = QRegularExpression(r'"[^"\n]*"')
        self.highlighting_rules.append((single_quoted, string_format))
        self.highlighting_rules.append((double_quoted, string_format))

        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))
        comment_pattern = QRegularExpression(r"#.*$")
        self.highlighting_rules.append((comment_pattern, comment_format))

        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor("#C586C0"))
        decorator_pattern = QRegularExpression(r"@[A-Za-z_][A-Za-z0-9_]*")
        self.highlighting_rules.append((decorator_pattern, decorator_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                start = match.capturedStart()
                length = match.capturedLength()
                if length > 0:
                    self.setFormat(start, length, fmt)

class SquareImageContainer(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #080808; border: 1px solid #0F0F0F;")

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return width

class LocalImageApiThread(QThread):
    
    success = pyqtSignal(object, int, object)
    error = pyqtSignal(str, int, str)

    def __init__(self, prompt: str, steps: int, size_type: str, use_cartoon_suffix: bool, parent=None):
        super().__init__(parent)
        URL_FAST = 'https://u216911-8e22-ad85fcd4.westd.seetacloud.com:8443/'  # z-image-turbo test
        self.url = URL_FAST + 'generate/'
        base_prompt = str(prompt or '').strip()
        if use_cartoon_suffix:
            base_prompt = (base_prompt + ' ' + str(CARTOON_STYLE_SUFFIX or '').strip()).strip()
        self.prompt = base_prompt
        self.steps = steps
        self.size_type = size_type

    def _call_image_api(self, url, prompt, steps, size_type='normal'):
        payload = {"prompt": prompt, "num_inference_steps": steps, "size_type": size_type}
        return requests.post(url, json=payload)

    def run(self):
        print(f"本地生图调用开始: url={self.url}, steps={self.steps}, size_type={self.size_type}, prompt={self.prompt}")
        try:
            resp = self._call_image_api(self.url, self.prompt, self.steps, self.size_type)
            ct = resp.headers.get('content-type', '')
            if resp.status_code == 200:
                self.success.emit(resp.content, resp.status_code, resp.headers)
            else:
                err_msg = ""
                try:
                    err_msg = str(resp.json())
                except Exception:
                    err_msg = resp.text or f"status={resp.status_code}"
                self.error.emit(err_msg, resp.status_code, resp.text or "")
        except Exception as e:
            self.error.emit(str(e), -1, "")


class ToolkitWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.toast_manager = None
        self.config_manager = ConfigManager()

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        materials_tab = QWidget()
        materials_layout = QVBoxLayout(materials_tab)
        materials_row = QHBoxLayout()
        materials_layout.addLayout(materials_row)
        left_materials_col = QVBoxLayout()
        right_materials_col = QVBoxLayout()
        materials_row.addLayout(left_materials_col)
        materials_row.addLayout(right_materials_col)
        materials_row.addStretch(1)

        self.single_group = QGroupBox("")
        self.single_group.setFixedWidth(600)
        single_layout = QVBoxLayout(self.single_group)
        single_title = QLabel("单句生成")
        single_layout.addWidget(single_title, alignment=Qt.AlignmentFlag.AlignLeft)

        s_row_text = QVBoxLayout()
        self.single_text_input = QTextEdit()
        self.single_text_input.setPlaceholderText("请输入要生成语音的文本...")
        try:
            s_line_height = self.single_text_input.fontMetrics().height()
            self.single_text_input.setFixedHeight(s_line_height * 6 + 12)
        except Exception:
            self.single_text_input.setFixedHeight(132)
        s_row_text.addWidget(self.single_text_input)
        single_layout.addLayout(s_row_text)

        s_row_char = QHBoxLayout()
        s_row_char.addWidget(QLabel("角色:"))
        self.character_combo = QComboBox()
        self.character_combo.setFixedWidth(140)
        s_row_char.addWidget(self.character_combo)
        s_row_char.addStretch()
        self.single_engine_combo = QComboBox()
        self.single_engine_combo.addItems(["custom"])
        self.single_engine_combo.setCurrentText("custom")
        self.single_engine_combo.setFixedWidth(100)
        s_row_char.addWidget(self.single_engine_combo)
        single_layout.addLayout(s_row_char)

        s_row_voice = QHBoxLayout()
        self.voice_type_label = QLabel("音色：")
        s_row_voice.addWidget(self.voice_type_label)
        s_row_voice.addStretch()
        self.speed_label = QLabel("速度:")
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setDecimals(2)
        self.speed_spin.setSingleStep(0.01)
        self.speed_spin.setRange(0.1, 2.0)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setFixedWidth(50)
        s_row_voice.addWidget(self.speed_label)
        s_row_voice.addWidget(self.speed_spin)
        self.emotion_label = QLabel("情绪:")
        self.emotion_combo = QComboBox()
        self.emotion_combo.setFixedWidth(80)
        s_row_voice.addWidget(self.emotion_label)
        s_row_voice.addWidget(self.emotion_combo)
        single_layout.addLayout(s_row_voice)

        s_row_out = QHBoxLayout()
        self.single_output_dir_btn = QPushButton("设置输出目录")
        self.single_open_output_dir_btn = QPushButton("打开目录")
        self.single_output_dir_display = QLineEdit()
        self.single_output_dir_display.setReadOnly(True)
        self.single_output_dir_btn.clicked.connect(self.on_select_single_output_directory)
        self.single_open_output_dir_btn.clicked.connect(self.on_open_single_output_directory)
        s_row_out.addWidget(self.single_output_dir_btn)
        s_row_out.addWidget(self.single_output_dir_display, stretch=1)
        s_row_out.addWidget(self.single_open_output_dir_btn)
        single_layout.addLayout(s_row_out)

        self.single_generate_btn = QPushButton("生成语音")
        self.single_generate_btn.clicked.connect(self.on_generate_single_voice)
        single_layout.addWidget(self.single_generate_btn)

        s_row_play = QHBoxLayout()
        self.single_generated_filename_display = QLineEdit()
        self.single_generated_filename_display.setReadOnly(True)
        self.single_play_btn = QPushButton("播放")
        self.single_stop_btn = QPushButton("停止")
        self.single_play_btn.setEnabled(False)
        self.single_stop_btn.setEnabled(False)
        self.single_play_btn.clicked.connect(self.on_play_single)
        self.single_stop_btn.clicked.connect(self.on_stop_single)
        self.single_play_stop_stack = QStackedWidget()
        self.single_play_stop_stack.addWidget(self.single_play_btn)
        self.single_play_stop_stack.addWidget(self.single_stop_btn)
        self.single_play_stop_stack.setCurrentWidget(self.single_play_btn)
        s_row_play.addWidget(self.single_generated_filename_display, stretch=4)
        s_row_play.addWidget(self.single_play_stop_stack, stretch=1)
        single_layout.addLayout(s_row_play)

        left_materials_col.addWidget(self.single_group, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.sfx_group = QGroupBox("")
        self.sfx_group.setFixedWidth(600)

        group_layout = QVBoxLayout(self.sfx_group)
        title_label = QLabel("音效生成（ElevenLabs）")
        group_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignLeft)

        row1 = QHBoxLayout()
        self.set_output_dir_btn = QPushButton("设置输出目录")
        self.open_output_dir_btn = QPushButton("打开目录")
        self.output_dir_display = QLineEdit()
        self.output_dir_display.setReadOnly(True)
        self.set_output_dir_btn.clicked.connect(self.on_set_output_directory)
        self.open_output_dir_btn.clicked.connect(self.on_open_output_directory)
        row1.addWidget(self.set_output_dir_btn)
        row1.addWidget(self.output_dir_display, stretch=1)
        row1.addWidget(self.open_output_dir_btn)
        group_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("请输入单个提示词")
        try:
            line_height = self.prompt_input.fontMetrics().height()
            self.prompt_input.setFixedHeight(line_height * 3 + 12)
        except Exception:
            self.prompt_input.setFixedHeight(72)
        row2.addWidget(self.prompt_input, stretch=1)
        group_layout.addLayout(row2)

        self.generate_btn = QPushButton("生成音效")
        self.generate_btn.clicked.connect(self.on_generate_sfx)
        group_layout.addWidget(self.generate_btn)

        row4 = QHBoxLayout()
        self.generated_name_display = QLineEdit()
        self.generated_name_display.setReadOnly(True)
        self.play_btn = QPushButton("播放")
        self.stop_btn = QPushButton("停止")
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.play_btn.clicked.connect(self.on_play)
        self.stop_btn.clicked.connect(self.on_stop)
        self.play_stop_stack = QStackedWidget()
        self.play_stop_stack.addWidget(self.play_btn)
        self.play_stop_stack.addWidget(self.stop_btn)
        self.play_stop_stack.setCurrentWidget(self.play_btn)
        row4.addWidget(self.generated_name_display, stretch=4)
        row4.addWidget(self.play_stop_stack, stretch=1)
        group_layout.addLayout(row4)

        left_materials_col.addWidget(self.sfx_group, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.tts_group = QGroupBox("")
        self.tts_group.setFixedWidth(600)
        tts_layout = QVBoxLayout(self.tts_group)
        tts_title = QLabel("真人音色（ElevenLabs）")
        tts_layout.addWidget(tts_title, alignment=Qt.AlignmentFlag.AlignLeft)

        tts_row1 = QHBoxLayout()
        self.tts_set_output_dir_btn = QPushButton("设置输出目录")
        self.tts_open_output_dir_btn = QPushButton("打开目录")
        self.tts_output_dir_display = QLineEdit()
        self.tts_output_dir_display.setReadOnly(True)
        self.tts_set_output_dir_btn.clicked.connect(self.on_set_tts_output_directory)
        self.tts_open_output_dir_btn.clicked.connect(self.on_open_tts_output_directory)
        tts_row1.addWidget(self.tts_set_output_dir_btn)
        tts_row1.addWidget(self.tts_output_dir_display, stretch=1)
        tts_row1.addWidget(self.tts_open_output_dir_btn)
        tts_layout.addLayout(tts_row1)

        tts_row2 = QHBoxLayout()
        self.tts_prompt_input = QTextEdit()
        self.tts_prompt_input.setPlaceholderText("请输入单个提示词")
        try:
            t_line_height = self.tts_prompt_input.fontMetrics().height()
            self.tts_prompt_input.setFixedHeight(t_line_height * 3 + 12)
        except Exception:
            self.tts_prompt_input.setFixedHeight(72)
        tts_row2.addWidget(self.tts_prompt_input, stretch=1)
        tts_layout.addLayout(tts_row2)

        tts_row3 = QHBoxLayout()
        self.tts_speed_label = QLabel("速度:")
        self.tts_speed_spin = QDoubleSpinBox()
        self.tts_speed_spin.setDecimals(2)
        self.tts_speed_spin.setSingleStep(0.01)
        self.tts_speed_spin.setRange(0.02, 2.0)
        self.tts_speed_spin.setValue(1.0)
        tts_row3.addWidget(self.tts_speed_label)
        tts_row3.addWidget(self.tts_speed_spin)
        self.tts_stability_label = QLabel("稳定性:")
        self.tts_stability_spin = QDoubleSpinBox()
        self.tts_stability_spin.setDecimals(2)
        self.tts_stability_spin.setSingleStep(0.1)
        self.tts_stability_spin.setRange(0.0, 1.0)
        self.tts_stability_spin.setValue(1.0)
        tts_row3.addWidget(self.tts_stability_label)
        tts_row3.addWidget(self.tts_stability_spin)
        self.tts_generate_btn = QPushButton("生成语音")
        self.tts_generate_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tts_generate_btn.clicked.connect(self.on_generate_tts)
        tts_row3.addWidget(self.tts_generate_btn, stretch=1)
        tts_layout.addLayout(tts_row3)

        tts_row4 = QHBoxLayout()
        self.tts_generated_name_display = QLineEdit()
        self.tts_generated_name_display.setReadOnly(True)
        self.tts_play_btn = QPushButton("播放")
        self.tts_stop_btn = QPushButton("停止")
        self.tts_play_btn.setEnabled(False)
        self.tts_stop_btn.setEnabled(False)
        self.tts_play_btn.clicked.connect(self.on_play_tts)
        self.tts_stop_btn.clicked.connect(self.on_stop_tts)
        self.tts_play_stop_stack = QStackedWidget()
        self.tts_play_stop_stack.addWidget(self.tts_play_btn)
        self.tts_play_stop_stack.addWidget(self.tts_stop_btn)
        self.tts_play_stop_stack.setCurrentWidget(self.tts_play_btn)
        tts_row4.addWidget(self.tts_generated_name_display, stretch=4)
        tts_row4.addWidget(self.tts_play_stop_stack, stretch=1)
        tts_layout.addLayout(tts_row4)

        left_materials_col.addWidget(self.tts_group, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        left_materials_col.addStretch(1)

        self.local_image_group = QGroupBox("")
        self.local_image_group.setFixedWidth(600)
        li_layout = QVBoxLayout(self.local_image_group)
        li_title = QLabel("本地生图")
        li_layout.addWidget(li_title, alignment=Qt.AlignmentFlag.AlignLeft)

        li_row2 = QHBoxLayout()
        self.local_image_prompt_input = QTextEdit()
        self.local_image_prompt_input.setPlaceholderText("请输入生图提示词...")
        self.local_image_prompt_input.setFixedHeight(72)
        li_row2.addWidget(self.local_image_prompt_input, stretch=1)
        li_layout.addLayout(li_row2)

        li_row3 = QHBoxLayout()
        li_size_label = QLabel("尺寸")
        self.local_size_full_radio = QRadioButton("full")
        self.local_size_normal_radio = QRadioButton("normal")
        self.local_cartoon_checkbox = QCheckBox("卡通风格")
        self.local_cartoon_checkbox.setChecked(True)
        self.local_cartoon_words_label = QLabel("{words}")
        self.local_cartoon_words_input = QLineEdit()
        self.local_cartoon_words_input.setPlaceholderText("")
        self.local_cartoon_words_input.setFixedWidth(160)
        self.local_size_full_radio.setChecked(True)
        self.local_image_start_btn = QPushButton("开始生成")
        self.local_image_start_btn.clicked.connect(self.on_local_image_start)
        li_row3.addWidget(li_size_label)
        li_row3.addWidget(self.local_size_full_radio)
        li_row3.addWidget(self.local_size_normal_radio)
        li_row3.addWidget(self.local_cartoon_checkbox)
        li_row3.addWidget(self.local_cartoon_words_label)
        li_row3.addWidget(self.local_cartoon_words_input)
        li_row3.addStretch(1)
        li_row3.addWidget(self.local_image_start_btn)
        li_layout.addLayout(li_row3)

        self.local_image_preview = SquareImageContainer()
        li_layout.addWidget(self.local_image_preview)

        right_materials_col.addWidget(self.local_image_group, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        right_materials_col.addStretch(1)

        tabs.addTab(materials_tab, "素材生产")

        batch_tab = QWidget()
        batch_layout = QVBoxLayout(batch_tab)
        batch_row = QHBoxLayout()
        batch_layout.addLayout(batch_row)
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        batch_row.addLayout(left_col)
        batch_row.addLayout(right_col)
        batch_row.addStretch(1)

        self.transcode_group = QGroupBox("")
        self.transcode_group.setFixedWidth(600)
        tg_layout = QVBoxLayout(self.transcode_group)
        tg_title = QLabel("音频压缩（仅限windows系统）")
        tg_layout.addWidget(tg_title, alignment=Qt.AlignmentFlag.AlignLeft)

        tg_row1 = QHBoxLayout()
        self.transcode_input_btn = QPushButton("选择输入目录")
        self.transcode_input_btn.clicked.connect(self.on_select_transcode_input_dir)
        self.transcode_input_display = QLineEdit()
        self.transcode_input_display.setReadOnly(True)
        self.transcode_recursive_checkbox = QCheckBox("下钻子目录")
        self.transcode_recursive_checkbox.setChecked(True)
        self.transcode_recursive_checkbox.toggled.connect(self._on_transcode_recursive_changed)
        tg_row1.addWidget(self.transcode_input_btn)
        tg_row1.addWidget(self.transcode_input_display, stretch=1)
        tg_row1.addWidget(self.transcode_recursive_checkbox)
        tg_layout.addLayout(tg_row1)

        tg_row2 = QHBoxLayout()
        self.transcode_output_btn = QPushButton("选择输出目录")
        self.transcode_output_btn.clicked.connect(self.on_select_transcode_output_dir)
        self.transcode_output_display = QLineEdit()
        self.transcode_output_display.setReadOnly(True)
        self.transcode_open_output_btn = QPushButton("打开目录")
        self.transcode_open_output_btn.setEnabled(False)
        self.transcode_open_output_btn.clicked.connect(self.on_open_transcode_output_dir)
        tg_row2.addWidget(self.transcode_output_btn)
        tg_row2.addWidget(self.transcode_output_display, stretch=1)
        tg_row2.addWidget(self.transcode_open_output_btn)
        tg_layout.addLayout(tg_row2)

        tg_row3 = QHBoxLayout()
        self.transcode_format_mp3_radio = QRadioButton("mp3")
        self.transcode_format_wav_radio = QRadioButton("wav")
        self.transcode_format_mp3_radio.setChecked(True)
        self.transcode_output_format = "mp3"
        self.transcode_format_mp3_radio.toggled.connect(lambda checked: self._on_transcode_format_changed("mp3", checked))
        self.transcode_format_wav_radio.toggled.connect(lambda checked: self._on_transcode_format_changed("wav", checked))
        tg_row3.addWidget(self.transcode_format_mp3_radio)
        tg_row3.addWidget(self.transcode_format_wav_radio)
        self.transcode_start_btn = QPushButton("开始压缩")
        self.transcode_start_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tg_row3.addWidget(self.transcode_start_btn, 1)
        self.transcode_progress_label = QLabel("完成进度：0/0")
        tg_row3.addWidget(self.transcode_progress_label)
        tg_layout.addLayout(tg_row3)
        left_col.addWidget(self.transcode_group, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.rename_group = QGroupBox("")
        self.rename_group.setFixedWidth(600)
        rg_layout = QVBoxLayout(self.rename_group)
        rg_title = QLabel("批量改名")
        rg_layout.addWidget(rg_title, alignment=Qt.AlignmentFlag.AlignLeft)

        rg_row1 = QHBoxLayout()
        self.rename_select_folder_btn = QPushButton("选择文件夹")
        try:
            self.rename_select_folder_btn.setFixedWidth(90)
        except Exception:
            pass
        self.rename_folder_display = QLineEdit()
        self.rename_folder_display.setReadOnly(True)
        self.rename_ext_combo = QComboBox()
        self.rename_ext_combo.addItems(["jpg", "png", "xlsx", "mp3", "wav"])
        try:
            self.rename_ext_combo.setCurrentText("jpg")
        except Exception:
            pass
        self.rename_select_folder_btn.clicked.connect(self.on_select_rename_folder)
        self.rename_ext_combo.currentTextChanged.connect(self.on_ext_changed)
        rg_row1.addWidget(self.rename_select_folder_btn)
        rg_row1.addWidget(self.rename_folder_display, stretch=1)
        rg_row1.addWidget(self.rename_ext_combo)
        rg_layout.addLayout(rg_row1)

        rg_row2 = QHBoxLayout()
        self.rename_left_text = QTextEdit()
        self.rename_left_text.setReadOnly(True)
        self.rename_right_text = QTextEdit()
        mid_label = QLabel(">")
        mid_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rename_left_text.setFixedHeight(600)
        self.rename_right_text.setFixedHeight(600)
        rg_row2.addWidget(self.rename_left_text, stretch=1)
        rg_row2.addWidget(mid_label)
        rg_row2.addWidget(self.rename_right_text, stretch=1)
        rg_layout.addLayout(rg_row2)

        rg_row3 = QHBoxLayout()
        self.rename_check_btn = QPushButton("检查")
        self.rename_start_btn = QPushButton("开始改名")
        self.rename_start_btn.setEnabled(False)
        self.rename_check_btn.clicked.connect(self.on_rename_check)
        self.rename_start_btn.clicked.connect(self.on_rename_start)
        rg_row3.addWidget(self.rename_check_btn, 1)
        rg_row3.addWidget(self.rename_start_btn, 2)
        rg_layout.addLayout(rg_row3)

        left_col.addWidget(self.rename_group, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        left_col.addStretch(1)

        self.template_clean_group = QGroupBox("")
        self.template_clean_group.setFixedWidth(600)
        tc_layout = QVBoxLayout(self.template_clean_group)
        tc_title = QLabel("模板清洗")
        tc_layout.addWidget(tc_title, alignment=Qt.AlignmentFlag.AlignLeft)

        tc_row1 = QHBoxLayout()
        self.tpl_select_files_btn = QPushButton("选择文件")
        self.tpl_select_files_btn.clicked.connect(self.on_tpl_select_files)
        self.tpl_clean_status_label = QLabel("")
        self.tpl_clean_status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        tc_row1.addWidget(self.tpl_select_files_btn)
        tc_row1.addStretch(1)
        tc_row1.addWidget(self.tpl_clean_status_label)
        tc_layout.addLayout(tc_row1)

        self.tpl_file_list = QListWidget()
        try:
            self.tpl_file_list.setMinimumHeight(420)
        except Exception:
            pass
        tc_layout.addWidget(self.tpl_file_list)

        tc_row3 = QHBoxLayout()
        self.tpl_select_output_dir_btn = QPushButton("选择输出目录")
        self.tpl_select_output_dir_btn.clicked.connect(self.on_tpl_select_output_dir)
        self.tpl_output_dir_display = QLineEdit()
        self.tpl_output_dir_display.setReadOnly(True)
        self.tpl_start_clean_btn = QPushButton("开始清洗")
        self.tpl_start_clean_btn.clicked.connect(self.on_tpl_start_clean)
        try:
            self.tpl_start_clean_btn.setEnabled(False)
        except Exception:
            pass
        tc_row3.addWidget(self.tpl_select_output_dir_btn)
        tc_row3.addWidget(self.tpl_output_dir_display, stretch=1)
        tc_row3.addWidget(self.tpl_start_clean_btn)
        tc_layout.addLayout(tc_row3)

        right_col.addWidget(self.template_clean_group, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        tabs.addTab(batch_tab, "批处理")

        other_tab = QWidget()
        other_layout = QVBoxLayout(other_tab)

        self.script_generator_group = QGroupBox("")
        self.script_generator_group.setFixedWidth(600)
        self.script_generator_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sg_layout = QVBoxLayout(self.script_generator_group)

        sg_title = QLabel("表格批处理机器人")
        sg_layout.addWidget(sg_title, alignment=Qt.AlignmentFlag.AlignLeft)

        sg_row = QHBoxLayout()
        sg_left_col = QVBoxLayout()
        sg_right_col = QVBoxLayout()
        sg_row.addLayout(sg_left_col, 1)
        sg_row.addLayout(sg_right_col, 1)
        sg_layout.addLayout(sg_row)

        self.script_generator_input = QTextEdit()
        self.script_generator_input.setAcceptRichText(False)
        self.script_generator_input.setPlaceholderText("请描述您的表格批处理方面的需求…")
        self.script_generator_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sg_left_col.addWidget(self.script_generator_input, 1)

        self.script_generator_send_btn = QPushButton("发送")
        self.script_generator_send_btn.clicked.connect(self.on_send_script_prompt)
        self.script_generator_send_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sg_left_col.addWidget(self.script_generator_send_btn)

        self.script_generator_output = QTextEdit()
        self.script_generator_output.setReadOnly(False)
        font = self.script_generator_output.font()
        font.setFamily("Consolas")
        self.script_generator_output.setFont(font)
        self.script_generator_output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.script_generator_highlighter = PythonSyntaxHighlighter(self.script_generator_output.document())
        sg_right_col.addWidget(self.script_generator_output, 1)

        self.script_generator_save_btn = QPushButton("脚本另存为")
        self.script_generator_save_btn.clicked.connect(self.on_save_generated_script)
        self.script_generator_save_btn.setEnabled(False)
        self.script_generator_save_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sg_right_col.addWidget(self.script_generator_save_btn)

        cs_row2 = QHBoxLayout()
        self.custom_script_file_display = QLineEdit()
        self.custom_script_file_display.setReadOnly(True)
        cs_row2.addWidget(self.custom_script_file_display, stretch=1)
        sg_layout.addLayout(cs_row2)

        cs_row3 = QHBoxLayout()
        self.custom_script_input_dir_btn = QPushButton("选择输入目录")
        self.custom_script_input_dir_btn.setFixedWidth(120)
        self.custom_script_input_dir_display = QLineEdit()
        self.custom_script_input_dir_display.setReadOnly(True)
        self.custom_script_input_dir_btn.clicked.connect(self.on_select_custom_script_input_dir)
        self.custom_script_open_input_dir_btn = QPushButton("打开目录")
        self.custom_script_open_input_dir_btn.setFixedWidth(80)
        self.custom_script_open_input_dir_btn.clicked.connect(self.on_open_custom_script_input_dir)
        cs_row3.addWidget(self.custom_script_input_dir_btn)
        cs_row3.addWidget(self.custom_script_input_dir_display, stretch=1)
        cs_row3.addWidget(self.custom_script_open_input_dir_btn)
        sg_layout.addLayout(cs_row3)

        cs_row4 = QHBoxLayout()
        self.custom_script_output_dir_btn = QPushButton("选择输出目录")
        self.custom_script_output_dir_btn.setFixedWidth(120)
        self.custom_script_output_dir_display = QLineEdit()
        self.custom_script_output_dir_display.setReadOnly(True)
        self.custom_script_output_dir_btn.clicked.connect(self.on_select_custom_script_output_dir)
        self.custom_script_open_output_dir_btn = QPushButton("打开目录")
        self.custom_script_open_output_dir_btn.setFixedWidth(80)
        self.custom_script_open_output_dir_btn.clicked.connect(self.on_open_custom_script_output_dir)
        cs_row4.addWidget(self.custom_script_output_dir_btn)
        cs_row4.addWidget(self.custom_script_output_dir_display, stretch=1)
        cs_row4.addWidget(self.custom_script_open_output_dir_btn)
        sg_layout.addLayout(cs_row4)

        self.custom_script_run_btn = QPushButton("运行")
        self.custom_script_run_btn.clicked.connect(self.on_run_custom_script)
        sg_layout.addWidget(self.custom_script_run_btn)

        other_layout.addWidget(self.script_generator_group, 1)

        tabs.addTab(other_tab, "其它")

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.generated_file_path = None
        self.single_player = QMediaPlayer()
        self.single_audio_output = QAudioOutput()
        self.single_player.setAudioOutput(self.single_audio_output)

        self.single_player.mediaStatusChanged.connect(self._on_single_media_status_changed)
        self.single_player.playbackStateChanged.connect(self._on_single_playback_state_changed)

        self.tts_player = QMediaPlayer()
        self.tts_audio_output = QAudioOutput()
        self.tts_player.setAudioOutput(self.tts_audio_output)
        self.tts_player.mediaStatusChanged.connect(self._on_tts_media_status_changed)
        self.tts_player.playbackStateChanged.connect(self._on_tts_playback_state_changed)
        self.tts_generated_file_path = None
        self._scroll_syncing = False
        self._rename_ready = False
        self._rename_pairs = []
        self.transcode_total_count = 0
        self.transcode_converted_count = 0
        self.transcode_start_btn.clicked.connect(self.on_transcode_start)
        try:
            self.rename_left_text.verticalScrollBar().valueChanged.connect(self._on_left_scroll)
            self.rename_right_text.verticalScrollBar().valueChanged.connect(self._on_right_scroll)
            self.rename_right_text.textChanged.connect(self._on_right_text_changed)
        except Exception:
            pass
        self._init_values()
        self._init_single_values()
        self._init_single_generation_controls()

    def on_select_transcode_input_dir(self):
        current_dir = os.getcwd()
        directory = QFileDialog.getExistingDirectory(self, "选择输入目录", current_dir)
        if directory:
            absdir = os.path.abspath(directory)
            self.transcode_input_display.setText(absdir)
            recursive = True
            if hasattr(self, 'transcode_recursive_checkbox') and self.transcode_recursive_checkbox:
                recursive = self.transcode_recursive_checkbox.isChecked()
            count = self._count_mp3_files_in_dir(absdir, recursive=recursive)
            self.transcode_total_count = count
            self.transcode_converted_count = 0
            if hasattr(self, 'transcode_progress_label') and self.transcode_progress_label:
                self.transcode_progress_label.setText(f"完成进度：{self.transcode_converted_count}/{self.transcode_total_count}")
            print(f"音频转码输入目录: {absdir}, 有效音频: {count}")

    def on_select_transcode_output_dir(self):
        current_dir = os.getcwd()
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
        if directory:
            absdir = os.path.abspath(directory)
            self.transcode_output_dir = absdir
            try:
                self.transcode_output_display.setText(absdir)
            except Exception:
                pass
            if hasattr(self, 'transcode_open_output_btn') and self.transcode_open_output_btn:
                self.transcode_open_output_btn.setEnabled(True)

            print(f"音频转码输出目录: {absdir}")

    def on_transcode_start(self):
        input_dir = self.transcode_input_display.text().strip()
        if not input_dir:
            if self.toast_manager:
                self.toast_manager.show_warning("请选择音频目录")
            return
        recursive = True
        if hasattr(self, 'transcode_recursive_checkbox') and self.transcode_recursive_checkbox:
            recursive = self.transcode_recursive_checkbox.isChecked()
        total = self._count_mp3_files_in_dir(input_dir, recursive=recursive)
        if total <= 0:
            if self.toast_manager:
                self.toast_manager.show_info("无可转换文件")
            return
        output_dir = getattr(self, 'transcode_output_dir', '') or self.transcode_output_display.text().strip()
        if not output_dir:
            if self.toast_manager:
                self.toast_manager.show_warning("请选择输出目录")
            return
        fmt = getattr(self, 'transcode_output_format', 'mp3')
        print(f"开始批量转码: 输入={input_dir}, 输出={output_dir}, 文件数={total}, 输出格式={fmt}")
        self.transcode_total_count = total
        self.transcode_converted_count = 0
        self.transcode_progress_label.setText(f"完成进度：0/{self.transcode_total_count}")
        self.transcode_start_btn.setEnabled(False)
        self.transcode_thread = TranscodeThread(input_dir, output_dir, recursive, fmt)
        def on_done(converted, counted):
            self.transcode_total_count = counted
            self.transcode_converted_count = converted
            self.transcode_progress_label.setText(f"完成进度：{self.transcode_converted_count}/{self.transcode_total_count}")
            self.transcode_start_btn.setEnabled(True)
            print(f"批量转码完成: 已转换 {converted} / 总数 {counted}")
        def on_progress(converted, counted):
            self.transcode_converted_count = converted
            self.transcode_progress_label.setText(f"完成进度：{self.transcode_converted_count}/{self.transcode_total_count}")
            #print(f"完成进度: {converted}/{counted}")
        self.transcode_thread.done.connect(on_done)
        self.transcode_thread.progress.connect(on_progress)
        self.transcode_thread.start()

    def _on_transcode_recursive_changed(self, checked):
        input_dir = self.transcode_input_display.text().strip()
        if input_dir:
            count = self._count_mp3_files_in_dir(input_dir, recursive=bool(checked))
            self.transcode_total_count = count
            self.transcode_converted_count = 0
            self.transcode_progress_label.setText(f"完成进度：{self.transcode_converted_count}/{self.transcode_total_count}")

    def _on_transcode_format_changed(self, fmt, checked):
        if checked:
            self.transcode_output_format = fmt

    def _count_mp3_files_in_dir(self, directory, recursive=True):
        total = 0
        if recursive:
            for root, dirs, files in os.walk(directory):
                for name in files:
                    if str(name).lower().endswith('.mp3'):
                        total += 1
        else:
            for name in os.listdir(directory):
                p = os.path.join(directory, name)
                if os.path.isfile(p) and str(name).lower().endswith('.mp3'):
                    total += 1
        return total

    def on_send_script_prompt(self):
        if getattr(self, "_script_generating", False):
            return
        text = self.script_generator_input.toPlainText().strip()
        if not text:
            if self.toast_manager:
                self.toast_manager.show_warning("请输入表格批处理需求描述")
            return
        api_base = self.config_manager.get_coze_api()
        token = self.config_manager.get_coze_token()
        bot_id = self.config_manager.get_coze_duoki_script_bot_id()
        if not all([api_base, token, bot_id]):
            QMessageBox.warning(self, "配置错误", "请检查Coze脚本生成器配置")
            return
        print("开始调用Coze脚本生成器")
        self.script_generator_output.clear()
        self._script_generating = True
        self.script_generator_send_btn.setEnabled(False)
        self.script_generator_send_btn.setText("生成中...")
        self._script_api_base = api_base
        self._script_token = token
        self._script_bot_id = bot_id
        self._script_pending_message = text
        conv_id = self.config_manager.get_coze_script_conversation_dialog_id()
        if not conv_id:
            legacy_conv_id = self.config_manager.get_coze_image_conversation_dialog_id()
            if legacy_conv_id:
                conv_id = legacy_conv_id
                self.config_manager.set_coze_script_conversation_dialog_id(conv_id)
        if conv_id:
            self._start_script_generation(conv_id, text)
            return
        self._script_coze_client = CozeAPIClient(api_base, token)
        self._script_conv_worker = CozeWorkerThread(self._script_coze_client, "create_conversation")
        self._script_conv_worker.conversation_created.connect(self._on_script_conversation_created)
        self._script_conv_worker.conversation_failed.connect(self._on_script_conversation_failed)
        self._script_conv_worker.start()

    def _start_script_generation(self, conversation_id, message):
        api_base = getattr(self, "_script_api_base", None) or self.config_manager.get_coze_api()
        token = getattr(self, "_script_token", None) or self.config_manager.get_coze_token()
        bot_id = getattr(self, "_script_bot_id", None) or self.config_manager.get_coze_duoki_script_bot_id()
        self._script_coze_client = CozeAPIClient(api_base, token)
        self._script_worker = CozeWorkerThread(
            self._script_coze_client,
            "send_message",
            bot_id=bot_id,
            conversation_id=conversation_id,
            user_name="toolkit_script",
            message=message,
            stream=True
        )
        self._script_worker.message_received.connect(self._on_script_message_received)
        self._script_worker.chat_finished.connect(self._on_script_chat_finished)
        self._script_worker.chat_failed.connect(self._on_script_chat_failed)
        self._script_worker.start()

    def _on_script_conversation_created(self, conversation_id: str):
        print(f"脚本生成会话ID创建成功: {conversation_id}")
        self.config_manager.set_coze_script_conversation_dialog_id(conversation_id)
        msg = getattr(self, "_script_pending_message", "").strip()
        if not msg:
            self._script_generating = False
            self.script_generator_send_btn.setEnabled(True)
            self.script_generator_send_btn.setText("发送")
            return
        self._start_script_generation(conversation_id, msg)

    def _on_script_conversation_failed(self, error_msg: str):
        print(f"脚本生成会话创建失败: {error_msg}")
        self._script_generating = False
        self.script_generator_send_btn.setEnabled(True)
        self.script_generator_send_btn.setText("发送")
        QMessageBox.critical(self, "会话创建失败", error_msg)

    def _on_script_message_received(self, content: str):
        cursor = self.script_generator_output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.script_generator_output.setTextCursor(cursor)
        self.script_generator_output.insertPlainText(content)

    def _process_generated_script_text(self, text: str) -> str:
        if not text:
            return ""
        lines = text.splitlines()
        if lines and str(lines[0]).lstrip().startswith("```"):
            lines = lines[1:]
        if lines and str(lines[-1]).lstrip().startswith("```"):
            lines = lines[:-1]
        start_idx = 0
        found_import = False
        for i, line in enumerate(lines):
            if str(line).lstrip().startswith("import"):
                start_idx = i
                found_import = True
                break
        if found_import:
            lines = lines[start_idx:]
        end_idx = len(lines)
        for i, line in enumerate(lines):
            if "raise SystemExit(main())" in str(line):
                end_idx = i + 1
                break
        lines = lines[:end_idx]
        return "\n".join(lines)

    def _on_script_chat_finished(self, chat_data: dict):
        print("Coze脚本生成完成")
        self._script_generating = False
        self.script_generator_send_btn.setEnabled(True)
        self.script_generator_send_btn.setText("发送")
        full = str(chat_data.get("full_content", "")).strip()
        if full:
            if not self.script_generator_output.toPlainText().strip():
                self.script_generator_output.setPlainText(full)
        text = self.script_generator_output.toPlainText()
        if text.strip():
            text_to_save = self._process_generated_script_text(text)
            if not text_to_save.strip():
                print("脚本内容为空，未自动保存")
                return
            script_dir = self.config_manager.ensure_script_output_directory()
            ts = time.strftime("%Y%m%d%H%M%S", time.localtime())
            file_path = os.path.join(script_dir, f"script_{ts}.py")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text_to_save)
            abs_path = os.path.abspath(file_path)
            self.custom_script_file_display.setText(abs_path)
            print(f"脚本已自动保存: {abs_path}")
            if self.toast_manager:
                self.toast_manager.show_info("脚本已生成并自动保存")
            self.script_generator_save_btn.setEnabled(True)

    def _on_script_chat_failed(self, error_msg: str):
        print(f"Coze脚本生成失败: {error_msg}")
        self._script_generating = False
        self.script_generator_send_btn.setEnabled(True)
        self.script_generator_send_btn.setText("发送")
        QMessageBox.critical(self, "脚本生成失败", error_msg)

    def on_save_generated_script(self):
        text = self.script_generator_output.toPlainText()
        if not text.strip():
            if self.toast_manager:
                self.toast_manager.show_warning("暂无可保存的脚本内容")
            return
        text_to_save = self._process_generated_script_text(text)
        if not text_to_save.strip():
            if self.toast_manager:
                self.toast_manager.show_warning("脚本内容为空，无法保存")
            print("脚本内容为空，未另存为")
            return
        default_path = os.getcwd()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存脚本",
            os.path.join(default_path, "script.py"),
            "Python Files (*.py)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text_to_save)
        except Exception as e:
            msg = f"保存脚本失败: {e}"
            print(msg)
            if self.toast_manager:
                self.toast_manager.show_warning(msg)
            return
        print(f"脚本已另存为: {file_path}")
        if self.toast_manager:
            self.toast_manager.show_info("脚本已另存为")

    def on_select_custom_script_file(self):
        current_dir = os.getcwd()
        file_path, _ = QFileDialog.getOpenFileName(self, "选择脚本文件", current_dir, "Python Files (*.py)")
        if file_path:
            abs_path = os.path.abspath(file_path)
            self.custom_script_file_display.setText(abs_path)
            print(f"自定义脚本文件已选择: {abs_path}")

    def on_select_custom_script_input_dir(self):
        current_dir = os.getcwd()
        directory = QFileDialog.getExistingDirectory(self, "选择输入目录", current_dir)
        if directory:
            absdir = os.path.abspath(directory)
            self.custom_script_input_dir_display.setText(absdir)
            print(f"自定义脚本输入目录已选择: {absdir}")

    def on_open_custom_script_input_dir(self):
        path = self.custom_script_input_dir_display.text().strip()
        if not path:
            if self.toast_manager:
                self.toast_manager.show_warning("请先选择输入目录")
            return
        try:
            path = os.path.abspath(path)
        except Exception:
            if self.toast_manager:
                self.toast_manager.show_warning("输入目录路径格式错误")
            return
        try:
            os.makedirs(path, exist_ok=True)
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                import subprocess
                import platform
                if platform.system() == "Darwin":
                    subprocess.run(["open", path])
                else:
                    subprocess.run(["xdg-open", path])
        except Exception:
            if self.toast_manager:
                self.toast_manager.show_warning("无法打开输入目录")

    def on_select_custom_script_output_dir(self):
        current_dir = os.getcwd()
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
        if directory:
            absdir = os.path.abspath(directory)
            self.custom_script_output_dir_display.setText(absdir)
            print(f"自定义脚本输出目录已选择: {absdir}")

    def on_open_custom_script_output_dir(self):
        path = self.custom_script_output_dir_display.text().strip()
        if not path:
            if self.toast_manager:
                self.toast_manager.show_warning("请先选择输出目录")
            return
        try:
            path = os.path.abspath(path)
        except Exception:
            if self.toast_manager:
                self.toast_manager.show_warning("输出目录路径格式错误")
            return
        try:
            os.makedirs(path, exist_ok=True)
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix':
                import subprocess
                import platform
                if platform.system() == "Darwin":
                    subprocess.run(["open", path])
                else:
                    subprocess.run(["xdg-open", path])
        except Exception:
            if self.toast_manager:
                self.toast_manager.show_warning("无法打开输出目录")

    def on_run_custom_script(self):
        script_path = self.custom_script_file_display.text().strip()
        input_dir = self.custom_script_input_dir_display.text().strip()
        output_dir = self.custom_script_output_dir_display.text().strip()
        if not script_path:
            if self.toast_manager:
                self.toast_manager.show_warning("请先生成脚本")
            return
        if not os.path.isfile(script_path):
            msg = "脚本文件不存在，请重新选择"
            print(f"自定义脚本运行失败: {msg}, path={script_path}")
            if self.toast_manager:
                self.toast_manager.show_warning(msg)
            return
        if not input_dir:
            if self.toast_manager:
                self.toast_manager.show_warning("请选择输入目录")
            return
        if not os.path.isdir(input_dir):
            msg = "输入目录不存在，请重新选择"
            print(f"自定义脚本运行失败: {msg}, input_dir={input_dir}")
            if self.toast_manager:
                self.toast_manager.show_warning(msg)
            return
        if not output_dir:
            if self.toast_manager:
                self.toast_manager.show_warning("请选择输出目录")
            return
        if not os.path.isdir(output_dir):
            msg = "输出目录不存在，请重新选择"
            print(f"自定义脚本运行失败: {msg}, output_dir={output_dir}")
            if self.toast_manager:
                self.toast_manager.show_warning(msg)
            return

        print(f"自定义脚本开始运行: 脚本={script_path}, 输入目录={input_dir}, 输出目录={output_dir}")

        cmd = [sys.executable, script_path, input_dir, output_dir]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            msg = f"脚本执行失败: {e}"
            print(f"自定义脚本运行异常: {msg}")
            if self.toast_manager:
                self.toast_manager.show_warning(msg)
            return

        enc = locale.getpreferredencoding(False) or "utf-8"
        stdout = (result.stdout or b"").decode(enc, errors="replace").strip()
        stderr = (result.stderr or b"").decode(enc, errors="replace").strip()

        code = 500
        message = ""

        if stdout:
            try:
                data = json.loads(stdout)
                if isinstance(data, dict):
                    c = data.get("code")
                    if c is not None:
                        try:
                            code = int(c)
                        except Exception:
                            code = 500
                    message = str(data.get("message") or data.get("msg") or "")
            except Exception:
                message = stdout

        if code == 200 and result.returncode == 0:
            print("自定义脚本执行成功: 脚本运行成功")
            if self.toast_manager:
                self.toast_manager.show_info("脚本运行成功")
        else:
            if not message:
                if stderr:
                    message = stderr
                else:
                    message = f"脚本执行失败, 返回码={result.returncode}"
            print(f"自定义脚本执行失败: code={code}, message={message}")
            QMessageBox.critical(self, "脚本运行失败", message)

    def _init_values(self):
        sfx_dir = self.config_manager.get_sfx_output_directory()
        self.output_dir_display.setText(os.path.abspath(sfx_dir))
        voice_dir = self.config_manager.get_voice_output_directory()
        self.tts_output_dir_display.setText(os.path.abspath(voice_dir))

    def _init_single_values(self):
        d = self.config_manager.get_voice_output_directory()
        try:
            self.single_output_dir_display.setText(os.path.abspath(d))
        except Exception:
            self.single_output_dir_display.setText(d)

    def _init_single_generation_controls(self):
        from duoki_editor.utils.constants_loader import ConstantsLoader
        from duoki_editor.core.speech_parameters_manager import SpeechParametersManager
        self._current_tts_engine = 'custom'
        self.constants_loader = ConstantsLoader()
        self._update_tts_controls()
        self.character_combo.currentTextChanged.connect(self._on_character_changed)
        self.single_engine_combo.currentTextChanged.connect(self._on_single_engine_changed)

        npc_id_map_2 = self.constants_loader.get_npc_id_map_2()
        self.character_combo.clear()
        self.character_combo.addItem("请选择角色", "")
        character_names = set()
        engine_prefix_map = {}
        speech_manager = SpeechParametersManager()
        for key, value in npc_id_map_2.items():
            if '_' in key:
                n = key.split('_')[0]
            else:
                n = key
            character_names.add(n)
            try:
                numeric_id = int(value)
            except Exception:
                numeric_id = None
            if numeric_id is not None:
                vt = speech_manager.get_voice_type_by_id(numeric_id, with_prefix=True)
                if isinstance(vt, str) and vt:
                    engine = vt.split('_')[0] if '_' in vt else vt
                    if n not in engine_prefix_map:
                        engine_prefix_map[n] = engine
        for n in sorted(character_names):
            eng = engine_prefix_map.get(n)
            display = f"{n} [{eng}]" if eng else n
            self.character_combo.addItem(display, n)

    def _update_tts_controls(self):
        eng = self._current_tts_engine
        show_speed = eng != 'custom'
        self.speed_label.setVisible(show_speed)
        self.speed_spin.setVisible(show_speed)
        show_emotion = eng in ['minimax', 'volcano']
        self.emotion_label.setVisible(show_emotion)
        self.emotion_combo.setVisible(show_emotion)
        if show_emotion:
            items = self.constants_loader.get_tts_emotions(eng) or []
            current = self.emotion_combo.currentText()
            self.emotion_combo.clear()
            for it in items:
                self.emotion_combo.addItem(str(it))
            if current:
                idx = self.emotion_combo.findText(current)
                if idx >= 0:
                    self.emotion_combo.setCurrentIndex(idx)

    def _update_single_engine_options(self, vt):
        options = ["custom"]
        if isinstance(vt, str) and vt:
            prefix = vt.split('_')[0] if '_' in vt else vt
            if prefix == 'minimax':
                options.append('minimax')
            elif prefix == 'volcano':
                options.append('volcano')
        self.single_engine_combo.clear()
        for o in options:
            self.single_engine_combo.addItem(o)
        self.single_engine_combo.setCurrentText('custom')
        self._current_tts_engine = 'custom'
        self._update_tts_controls()

    def _on_character_changed(self, character_name):
        if character_name == "请选择角色":
            self.voice_type_label.setText("音色：")
            self._update_single_engine_options(None)
            return
        try:
            from duoki_editor.core.speech_parameters_manager import SpeechParametersManager
            sm = SpeechParametersManager()
            speaker = self.character_combo.currentData()
            vt = sm.get_voice_id_from_speaker(speaker or character_name.split('[')[0].strip(), with_prefix=True)
            if vt:
                self.voice_type_label.setText(f"音色：{vt}")
                self._update_single_engine_options(vt)
            else:
                self.voice_type_label.setText("音色：未找到")
            sp = sm.get_speech_parameters(speaker or character_name.split('[')[0].strip())
            if isinstance(sp, dict) and 'speed' in sp:
                try:
                    self.speed_spin.setValue(float(sp['speed']))
                except Exception:
                    pass
        except Exception:
            self.voice_type_label.setText("音色：获取失败")

    def _on_single_engine_changed(self, value):
        if isinstance(value, str) and value:
            self._current_tts_engine = value.strip().lower()
            self._update_tts_controls()

    def on_select_single_output_directory(self):
        current_dir = self.single_output_dir_display.text() or self.config_manager.get_voice_output_directory()
        directory = QFileDialog.getExistingDirectory(self, "选择语音输出目录", current_dir)
        if directory:
            self.single_output_dir_display.setText(directory)
            self.config_manager.set_voice_output_directory(directory)

    def on_open_single_output_directory(self):
        output_dir = self.single_output_dir_display.text().strip() or self.config_manager.get_voice_output_directory()
        try:
            output_dir = os.path.abspath(output_dir)
        except Exception:
            if self.toast_manager:
                self.toast_manager.show_toast("路径格式错误")
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
        except Exception as e:
            if self.toast_manager:
                self.toast_manager.show_toast("无法打开目录")

    def _replace_special_format_core(self, text):
        if not isinstance(text, str):
            text = str(text)
        items = getattr(self, 'special_format_items', None)
        if items is None:
            self.special_format_items = {'{user_name}': '贝贝'}
            items = self.special_format_items
        for k, v in items.items():
            if not v:
                continue
            ks = str(k)
            vs = str(v)
            if ks in text:
                if '|' in vs:
                    arr = [val.strip() for val in vs.split('|') if val.strip()]
                    if len(arr) >= 1:
                        text = text.replace(ks, arr[0])
                else:
                    text = text.replace(ks, vs)
        return text

    def replace_special_format_in_text(self, text):
        return self._replace_special_format_core(text)

    def on_generate_single_voice(self):
        try:
            text = self.single_text_input.toPlainText().strip()
        except Exception:
            text = str(self.single_text_input.text()).strip()
        if not text:
            QMessageBox.warning(self, "警告", "请输入要生成语音的文本")
            return
        text = self.replace_special_format_in_text(text)
        speaker = self.character_combo.currentData() or self.character_combo.currentText()
        if isinstance(speaker, str) and '[' in speaker:
            speaker = speaker.split('[')[0].strip()
        if speaker == "请选择角色":
            QMessageBox.warning(self, "警告", "请选择角色")
            return
        output_dir = (self.single_output_dir_display.text() or '').strip()
        if not output_dir:
            QMessageBox.warning(self, "警告", "请设置输出目录")
            return
        os.makedirs(output_dir, exist_ok=True)
        try:
            from duoki_editor.tts.tts_cache import TTSCache
            tts_cache = TTSCache()
            eng = self._current_tts_engine
            speed_override = None if eng == 'custom' else float(self.speed_spin.value())
            emotion_override = None
            if eng in ['minimax', 'volcano'] and self.emotion_combo.isVisible():
                e_text = self.emotion_combo.currentText().strip()
                if e_text:
                    emotion_override = e_text
            result = tts_cache.call_tts_api(text, speaker=speaker, speed=speed_override, emotion=emotion_override, engine=self._current_tts_engine)
            if 'error' in result:
                err = str(result['error'])
                print(f"语音生成失败: {err}")
                QMessageBox.critical(self, "错误", f"语音生成失败: {err}")
                return
            api_type = tts_cache.current_tts_api_type
            audio_format = tts_cache.current_audio_format or "mp3"
            import re
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
            safe_text = ''.join(chinese_chars[:40])
            if not safe_text:
                safe_text = "".join(c for c in text if c.isalnum())
            safe_text = self._sanitize_filename_component(safe_text, default='voice', max_len=20)
            audio_path = None
            if 'audio_path' in result:
                source_path = result['audio_path']
                if audio_format == "wav":
                    filename = f"{self._sanitize_filename_component(str(speaker), default='speaker')}_{safe_text}.wav"
                else:
                    filename = f"{self._sanitize_filename_component(str(speaker), default='speaker')}_{safe_text}.mp3"
                audio_path = os.path.join(output_dir, filename)
                import shutil
                try:
                    shutil.copy2(source_path, audio_path)
                    print(f"语音文件已保存: {audio_path} (源: {source_path}, 格式: {audio_format}, API: {api_type})")
                except Exception as e:
                    print(f"保存语音文件失败: {str(e)} (源: {source_path})")
            if audio_path and os.path.exists(audio_path):
                self.single_generated_filename_display.setText(os.path.basename(audio_path))
                self.single_generated_file_path = audio_path
                self.single_play_btn.setEnabled(True)
                self.single_stop_btn.setEnabled(True)
                if self.toast_manager:
                    self.toast_manager.show_success("语音生成成功")
                self.single_player.setSource(QUrl.fromLocalFile(audio_path))
                self.single_player.play()
                self.single_play_stop_stack.setCurrentWidget(self.single_stop_btn)
            else:
                print("生成失败: 未生成目标文件")
                QMessageBox.critical(self, "错误", "生成失败，请检查TTS设置")
        except Exception as e:
            print(f"语音生成过程中发生错误: {str(e)}")
            QMessageBox.critical(self, "错误", f"语音生成过程中发生错误: {str(e)}")

    def on_play_single(self):
        p = getattr(self, 'single_generated_file_path', None)
        if not p or not os.path.exists(p):
            return
        self.single_player.setSource(QUrl.fromLocalFile(p))
        self.single_player.play()
        try:
            self.single_play_stop_stack.setCurrentWidget(self.single_stop_btn)
        except Exception:
            pass

    def on_stop_single(self):
        try:
            self.single_player.stop()
        except Exception:
            pass
        try:
            self.single_play_stop_stack.setCurrentWidget(self.single_play_btn)
        except Exception:
            pass

    def _on_single_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.single_play_stop_stack.setCurrentWidget(self.single_play_btn)

    def _on_single_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.single_play_stop_stack.setCurrentWidget(self.single_play_btn)

    def _on_tts_media_status_changed(self, status):
        from PyQt6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.tts_play_stop_stack.setCurrentWidget(self.tts_play_btn)

    def _on_tts_playback_state_changed(self, state):
        from PyQt6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.tts_play_stop_stack.setCurrentWidget(self.tts_stop_btn)
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            self.tts_play_stop_stack.setCurrentWidget(self.tts_play_btn)

    def on_set_output_directory(self):
        current_dir = self.output_dir_display.text() or self.config_manager.get_sfx_output_directory()
        directory = QFileDialog.getExistingDirectory(self, "选择音效输出目录", current_dir)
        if directory:
            self.config_manager.set_sfx_output_directory(directory)
            self.output_dir_display.setText(os.path.abspath(directory))

    def on_open_output_directory(self):
        directory = self.output_dir_display.text() or self.config_manager.get_sfx_output_directory()
        try:
            directory = os.path.abspath(directory)
            os.makedirs(directory, exist_ok=True)
            if os.name == 'nt':
                os.startfile(directory)
            elif os.name == 'posix':
                import subprocess
                import platform
                if platform.system() == "Darwin":
                    subprocess.run(["open", directory])
                else:
                    subprocess.run(["xdg-open", directory])
        except Exception as e:
            if self.toast_manager:
                self.toast_manager.show_error(f"无法打开目录: {str(e)}")

    def on_open_transcode_output_dir(self):
        directory = self.transcode_output_display.text().strip()
        if not directory:
            return
        try:
            directory = os.path.abspath(directory)
            os.makedirs(directory, exist_ok=True)
            if os.name == 'nt':
                os.startfile(directory)
            elif os.name == 'posix':
                import subprocess
                import platform
                if platform.system() == "Darwin":
                    subprocess.run(["open", directory])
                else:
                    subprocess.run(["xdg-open", directory])
            if self.toast_manager:
                self.toast_manager.show_success("已打开输出目录")
        except Exception as e:
            if self.toast_manager:
                self.toast_manager.show_error(f"无法打开目录: {str(e)}")

    def on_tpl_select_files(self):
        current_dir = os.getcwd()
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", current_dir, "Excel文件 (*.xlsx)")
        if files:
            self.tpl_selected_files = [os.path.abspath(f) for f in files if isinstance(f, str) and f.lower().endswith('.xlsx')]
            validity = {}
            invalid_count = 0
            for p in self.tpl_selected_files:
                ok = self._validate_template_file(p)
                validity[p] = ok
                if not ok:
                    invalid_count += 1
            self.tpl_file_list.clear()
            for p in self.tpl_selected_files:
                name = os.path.basename(p)
                it = QListWidgetItem(name)
                if validity.get(p, False):
                    it.setForeground(Qt.GlobalColor.green)
                else:
                    it.setForeground(Qt.GlobalColor.red)
                self.tpl_file_list.addItem(it)
            if invalid_count == 0 and len(self.tpl_selected_files) > 0:
                self.tpl_clean_status_label.setText(f"待清洗模板{len(self.tpl_selected_files)}个")
                self.tpl_clean_status_label.setStyleSheet("color: green;")
                try:
                    self.tpl_start_clean_btn.setEnabled(True)
                except Exception:
                    pass
            else:
                self.tpl_clean_status_label.setText(f"有{invalid_count}个文件格式有误")
                self.tpl_clean_status_label.setStyleSheet("color: red;")
                try:
                    self.tpl_start_clean_btn.setEnabled(False)
                except Exception:
                    pass
            self.tpl_valid_files = [p for p in self.tpl_selected_files if validity.get(p)]
            print(f"模板清洗文件选择: 总数={len(self.tpl_selected_files)}, 合法={len(self.tpl_valid_files)}, 非法={invalid_count}")

    def _validate_template_file(self, file_path: str) -> bool:
        try:
            sheets = pd.read_excel(file_path, sheet_name=None)
        except Exception as e:
            print(f"模板清洗读取失败: {file_path}, 错误={str(e)}")
            return False
        required = {"stage_id", "stage_name", "step_name", "speaker", "param1"}
        base = os.path.splitext(os.path.basename(file_path))[0]
        any_valid = False
        for _, df in sheets.items():
            if not hasattr(df, 'columns'):
                continue
            cols = {str(c).strip() for c in df.columns}
            if not required.issubset(cols):
                continue
            rows = df.dropna(how='all')
            if rows is None or rows.empty:
                continue
            ok = True
            for _, row in rows.iterrows():
                sid = str(row.get('stage_id') or '').strip()
                sname = str(row.get('stage_name') or '').strip()
                step = str(row.get('step_name') or '').strip()
                spk = str(row.get('speaker') or '').strip()
                p1 = str(row.get('param1') or '').strip()
                if not sid or not sname or not step or not spk or not p1:
                    ok = False
                    break
                if sid not in base:
                    ok = False
                    break
            if ok:
                any_valid = True
                break
        return any_valid

    def on_tpl_select_output_dir(self):
        current_dir = os.getcwd()
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
        if directory:
            absdir = os.path.abspath(directory)
            self.tpl_output_dir_display.setText(absdir)
            print(f"模板清洗输出目录: {absdir}")

    def on_tpl_start_clean(self):
        selected = getattr(self, 'tpl_selected_files', []) or []
        valid = getattr(self, 'tpl_valid_files', []) or []
        print(f"模板清洗启动: 已选={len(selected)}, 合法={len(valid)}")
        out_dir = self.tpl_output_dir_display.text().strip()
        if not out_dir:
            if self.toast_manager:
                self.toast_manager.show_warning("请选择输出目录")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            print(f"模板清洗创建输出目录失败: {str(e)}")
            if self.toast_manager:
                self.toast_manager.show_error("输出目录不可用")
            return
        required_cols = ["stage_id", "stage_name", "step_name", "speaker", "param1"]
        processed = 0
        for p in selected:
            base = os.path.splitext(os.path.basename(p))[0]
            out_name = f"{base.split('-english')[0]}-blank.xlsx"
            out_path = os.path.join(out_dir, out_name)
            try:
                sheets = pd.read_excel(p, sheet_name=None)
            except Exception as e:
                print(f"模板清洗读取失败: {p}, 错误={str(e)}")
                continue
            saved_sheets = 0
            try:
                with pd.ExcelWriter(out_path) as writer:
                    for sname, df in sheets.items():
                        cols = [str(c).strip() for c in getattr(df, 'columns', [])]
                        if all(c in cols for c in required_cols):
                            df_out = df[required_cols].copy()
                            df_out.to_excel(writer, sheet_name=str(sname), index=False)
                            saved_sheets += 1
                if saved_sheets > 0:
                    processed += 1
                    print(f"模板清洗完成: 输入={p}, 输出={out_path}, 保存sheet={saved_sheets}")
                else:
                    print(f"模板清洗跳过(无有效sheet): 输入={p}")
            except Exception as e:
                print(f"模板清洗写出失败: {out_path}, 错误={str(e)}")
                continue
        print(f"模板清洗总计完成: {processed}/{len(selected)} 个文件")
        QMessageBox.information(self, "完成", f"已完成{processed}个文件的清洗")

    def on_generate_sfx(self):
        try:
            text = self.prompt_input.toPlainText().strip()
        except Exception:
            text = str(self.prompt_input.text()).strip()
        if not text:
            if self.toast_manager:
                self.toast_manager.show_warning("请输入提示词")
            return
        api_key = self.config_manager.get_elevenlabs_api_key()
        url = "https://api.elevenlabs.io/v1/sound-generation"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        payload = {"text": text}
        try:
            masked = (api_key[:4] + "..." + api_key[-4:]) if isinstance(api_key, str) and len(api_key) >= 8 else "***"
            print(f"SFX 请求: url={url}, key={masked}, payload_text_len={len(text)}")
            print(f"SFX 目录: {self.output_dir_display.text() or './output/sfx'}")
            safe_prompt = ''.join(text.split())
            base_name = self._sanitize_filename_component(safe_prompt, default='sfx', max_len=20)
            ts = time.strftime('%Y%m%d%H%M%S')
            print(f"SFX 命名: prefix={base_name}, ts={ts}")
            response = requests.post(url, headers=headers, json=payload, timeout=(10, 30))
            print(f"SFX 响应: status={response.status_code}, content_type={response.headers.get('content-type','')}, bytes={len(response.content)}")
            content_type = response.headers.get('content-type', '')
            directory = self.output_dir_display.text() or './output/sfx'
            os.makedirs(directory, exist_ok=True)
            if 'audio' in content_type or 'mpeg' in content_type or 'mp3' in content_type:
                ext = 'mp3'
                filename = f"{base_name}_{ts}.{ext}"
                file_path = os.path.join(directory, filename)
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                print(f"SFX 保存: path={file_path}, bytes={len(response.content)}")
            elif 'wav' in content_type:
                ext = 'wav'
                filename = f"{base_name}_{ts}.{ext}"
                file_path = os.path.join(directory, filename)
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                print(f"SFX 保存: path={file_path}, bytes={len(response.content)}")
            else:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                audio_url = None
                if isinstance(data, dict):
                    audio_url = data.get('audio') or data.get('data', {}).get('audio') or data.get('audio_url')
                print(f"SFX JSON: keys={list(data.keys()) if isinstance(data, dict) else 'n/a'}, audio_url={audio_url}")
                if audio_url:
                    print(f"SFX 下载: url={audio_url}")
                    audio_resp = requests.get(audio_url, timeout=(10, 30))
                    audio_ct = audio_resp.headers.get('content-type', '')
                    print(f"SFX 下载响应: status={audio_resp.status_code}, content_type={audio_ct}, bytes={len(audio_resp.content)}")
                    ext = 'mp3'
                    if 'wav' in audio_ct:
                        ext = 'wav'
                    filename = f"{base_name}_{ts}.{ext}"
                    file_path = os.path.join(directory, filename)
                    with open(file_path, 'wb') as f:
                        f.write(audio_resp.content)
                    print(f"SFX 保存: path={file_path}, bytes={len(audio_resp.content)}")
                else:
                    if self.toast_manager:
                        self.toast_manager.show_error("生成失败")
                    return
            self.generated_file_path = file_path
            self.generated_name_display.setText(os.path.basename(file_path))
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            if self.toast_manager:
                self.toast_manager.show_success("音效生成成功")
            print(f"SFX 完成: file={self.generated_file_path}")
        except Exception as e:
            if self.toast_manager:
                self.toast_manager.show_error(f"生成失败: {str(e)}")
            print(f"SFX 异常: {str(e)}")

    def on_set_tts_output_directory(self):
        current_dir = self.tts_output_dir_display.text() or self.config_manager.get_voice_output_directory()
        directory = QFileDialog.getExistingDirectory(self, "选择音效输出目录", current_dir)
        if directory:
            self.config_manager.set_voice_output_directory(directory)
            self.tts_output_dir_display.setText(os.path.abspath(directory))

    def on_open_tts_output_directory(self):
        directory = self.tts_output_dir_display.text() or self.config_manager.get_voice_output_directory()
        try:
            directory = os.path.abspath(directory)
            os.makedirs(directory, exist_ok=True)
            if os.name == 'nt':
                os.startfile(directory)
            elif os.name == 'posix':
                import subprocess
                import platform
                if platform.system() == "Darwin":
                    subprocess.run(["open", directory])
                else:
                    subprocess.run(["xdg-open", directory])
        except Exception as e:
            if self.toast_manager:
                self.toast_manager.show_error(f"无法打开目录: {str(e)}")

    def on_generate_tts(self):
        try:
            text = self.tts_prompt_input.toPlainText().strip()
        except Exception:
            text = str(self.tts_prompt_input.text()).strip()
        if not text:
            if self.toast_manager:
                self.toast_manager.show_warning("请输入提示词")
            return
        try:
            from duoki_editor.tts.tts_cache import TTSCache
            tts_cache = TTSCache()
            voice_id = "KfcOXyYXfJ51vqufTZxR"
            print(f"TTS 请求: voice_id={voice_id}, text_len={len(text)}")
            result = tts_cache.call_elevenlabs_tts(text, voice_id=voice_id, model_id="eleven_multilingual_v2", speed=float(self.tts_speed_spin.value()), stability=float(self.tts_stability_spin.value()))
            directory = self.tts_output_dir_display.text() or './output/voice'
            os.makedirs(directory, exist_ok=True)
            if 'error' in result:
                if self.toast_manager:
                    self.toast_manager.show_error("生成失败")
                return
            source_path = result.get('audio_path')
            if not source_path or not os.path.exists(source_path):
                if self.toast_manager:
                    self.toast_manager.show_error("生成失败")
                return
            import re
            safe_prompt = ''.join(text.split())
            base_name = self._sanitize_filename_component(safe_prompt, default='tts', max_len=20)
            ts = time.strftime('%Y%m%d%H%M%S')
            ext = os.path.splitext(source_path)[1].lstrip('.') or 'mp3'
            filename = f"{base_name}_{ts}.{ext}"
            file_path = os.path.join(directory, filename)
            import shutil
            shutil.copy2(source_path, file_path)
            self.tts_generated_file_path = file_path
            self.tts_generated_name_display.setText(os.path.basename(file_path))
            self.tts_play_btn.setEnabled(True)
            self.tts_stop_btn.setEnabled(True)
            if self.toast_manager:
                self.toast_manager.show_success("真人音色生成成功")
            print(f"TTS 完成: file={self.tts_generated_file_path}")
        except Exception as e:
            if self.toast_manager:
                self.toast_manager.show_error(f"生成失败: {str(e)}")
            print(f"TTS 异常: {str(e)}")

    def on_play_tts(self):
        if not self.tts_generated_file_path or not os.path.exists(self.tts_generated_file_path):
            return
        self.tts_player.setSource(QUrl.fromLocalFile(self.tts_generated_file_path))
        self.tts_player.play()
        self.tts_play_stop_stack.setCurrentWidget(self.tts_stop_btn)

    def on_stop_tts(self):
        self.tts_player.stop()
        self.tts_play_stop_stack.setCurrentWidget(self.tts_play_btn)

    def on_play(self):
        if not self.generated_file_path or not os.path.exists(self.generated_file_path):
            return
        self.player.setSource(QUrl.fromLocalFile(self.generated_file_path))
        self.player.play()
        self.play_stop_stack.setCurrentWidget(self.stop_btn)

    def on_stop(self):
        self.player.stop()
        self.play_stop_stack.setCurrentWidget(self.play_btn)

    def _on_playback_state_changed(self, state):
        from PyQt6.QtMultimedia import QMediaPlayer
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_stop_stack.setCurrentWidget(self.stop_btn)
        else:
            self.play_stop_stack.setCurrentWidget(self.play_btn)

    def on_select_rename_folder(self):
        try:
            current_dir = os.getcwd()
            directory = QFileDialog.getExistingDirectory(self, "选择文件夹", current_dir)
            if directory:
                self.rename_selected_dir = os.path.abspath(directory)
                self.rename_folder_display.setText(self.rename_selected_dir)
                self._refresh_rename_list()
        except Exception:
            pass

    def on_ext_changed(self, value):
        try:
            if getattr(self, "rename_selected_dir", None):
                self._refresh_rename_list()
        except Exception:
            pass

    def _refresh_rename_list(self):
        try:
            directory = getattr(self, "rename_selected_dir", None)
            if not directory:
                return
            ext = "." + str(self.rename_ext_combo.currentText()).lower()
            names = []
            for entry in os.listdir(directory):
                p = os.path.join(directory, entry)
                if not os.path.isfile(p):
                    continue
                e = os.path.splitext(entry)[1].lower()
                if e == ext:
                    names.append(os.path.splitext(entry)[0])
            self.rename_left_text.setPlainText("\n".join(names))
        except Exception:
            pass

    def _on_left_scroll(self, value):
        if getattr(self, "_scroll_syncing", False):
            return
        self._scroll_syncing = True
        try:
            ls = self.rename_left_text.verticalScrollBar()
            rs = self.rename_right_text.verticalScrollBar()
            lmin, lmax = ls.minimum(), ls.maximum()
            rmin, rmax = rs.minimum(), rs.maximum()
            frac = 0 if (lmax - lmin) <= 0 else (value - lmin) / (lmax - lmin)
            rvalue = int(round(rmin + frac * (rmax - rmin)))
            rs.setValue(rvalue)
        except Exception:
            pass
        self._scroll_syncing = False

    def _on_right_scroll(self, value):
        if getattr(self, "_scroll_syncing", False):
            return
        self._scroll_syncing = True
        try:
            rs = self.rename_right_text.verticalScrollBar()
            ls = self.rename_left_text.verticalScrollBar()
            rmin, rmax = rs.minimum(), rs.maximum()
            lmin, lmax = ls.minimum(), ls.maximum()
            frac = 0 if (rmax - rmin) <= 0 else (value - rmin) / (rmax - rmin)
            lvalue = int(round(lmin + frac * (lmax - lmin)))
            ls.setValue(lvalue)
        except Exception:
            pass
        self._scroll_syncing = False

    def _on_right_text_changed(self):
        try:
            self._rename_ready = False
            self.rename_start_btn.setEnabled(False)
        except Exception:
            pass

    def on_rename_check(self):
        try:
            left_lines = [ln.strip() for ln in self.rename_left_text.toPlainText().splitlines()]
            right_raw = [ln for ln in self.rename_right_text.toPlainText().splitlines()]
            right_lines = [ln.strip() for ln in right_raw if ln.strip()]
            max_pairs = min(len(left_lines), len(right_lines))
            filtered_left = []
            filtered_right = []
            for i in range(max_pairs):
                if left_lines[i] != right_lines[i]:
                    filtered_left.append(left_lines[i])
                    filtered_right.append(right_lines[i])
            if len(filtered_left) == 0 and len(filtered_right) == 0:
                if self.toast_manager:
                    self.toast_manager.show_info("没有文件需要改名")
                self._rename_ready = False
                self.rename_start_btn.setEnabled(False)
                return
            if len(filtered_left) != len(filtered_right):
                if self.toast_manager:
                    self.toast_manager.show_error("输入的行数不匹配")
                self._rename_ready = False
                self.rename_start_btn.setEnabled(False)
                return
            invalid = []
            for name in filtered_right:
                if not self._is_valid_filename(name):
                    invalid.append(name)
            if invalid:
                QMessageBox.critical(self, "错误", "以下名称不合规范：\n" + "\n".join(invalid))
                self._rename_ready = False
                self.rename_start_btn.setEnabled(False)
                return
            seen = set()
            dups = []
            for name in filtered_right:
                if name in seen and name not in dups:
                    dups.append(name)
                seen.add(name)
            if dups:
                QMessageBox.critical(self, "错误", "以下名称存在重复：\n" + "\n".join(dups))
                self._rename_ready = False
                self.rename_start_btn.setEnabled(False)
                return
            self._rename_pairs = list(zip(filtered_left, filtered_right))
            self._rename_ready = True
            self.rename_start_btn.setEnabled(True)
            if self.toast_manager:
                self.toast_manager.show_success("质检通过，可以改名")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"检查失败: {str(e)}")
            self._rename_ready = False
            self.rename_start_btn.setEnabled(False)

    def on_rename_start(self):
        try:
            if not self._rename_ready:
                if self.toast_manager:
                    self.toast_manager.show_warning("请先检查")
                return
            directory = getattr(self, "rename_selected_dir", None)
            if not directory:
                QMessageBox.critical(self, "错误", "未选择文件夹")
                return
            ext = "." + str(self.rename_ext_combo.currentText()).lower()
            for src, dst in self._rename_pairs:
                src_path = os.path.join(directory, src + ext)
                dst_path = os.path.join(directory, dst + ext)
                os.rename(src_path, dst_path)
            if self.toast_manager:
                self.toast_manager.show_success("批量改名完成")
            self._refresh_rename_list()
            self._rename_ready = False
            self.rename_start_btn.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"改名失败: {str(e)}")
            self._rename_ready = False
            self.rename_start_btn.setEnabled(False)

    def _is_valid_filename(self, name: str) -> bool:
        try:
            if not name or name in {'.', '..'}:
                return False
            forbidden = set('\\/:*?"<>|')
            if any(ch in forbidden for ch in name):
                return False
            if any(ord(ch) < 32 for ch in name):
                return False
            if name[-1] in {' ', '.'}:
                return False
            win_reserved = {"CON","PRN","AUX","NUL"} | {f"COM{i}" for i in range(1,10)} | {f"LPT{i}" for i in range(1,10)}
            if name.upper() in win_reserved:
                return False
            return True
        except Exception:
            return False

    def _sanitize_filename_component(self, name: str, default: str = 'file', max_len: int | None = None) -> str:
        try:
            s = str(name or '').strip()
            if not s:
                s = default
            forbidden = set('\\/:*?"<>|')
            s = ''.join(ch for ch in s if (ord(ch) >= 32 and ch not in forbidden))
            s = s.strip(' .')
            if not s:
                s = default
            if max_len and max_len > 0:
                s = s[:max_len]
            return s
        except Exception:
            return default

    def on_local_image_start(self):
        try:
            prompt = self.local_image_prompt_input.toPlainText().strip()
        except Exception:
            prompt = str(self.local_image_prompt_input.text()).strip()
        if hasattr(self, "local_cartoon_words_input") and self.local_cartoon_words_input:
            words = str(self.local_cartoon_words_input.text() or "").strip()
            if "{words}" in prompt:
                prompt = prompt.replace("{words}", words)
        if not prompt:
            if self.toast_manager:
                self.toast_manager.show_warning("请输入提示词")
            return
        size_type = "full" if self.local_size_full_radio.isChecked() else "normal"
        use_cartoon_suffix = True
        try:
            use_cartoon_suffix = self.local_cartoon_checkbox.isChecked()
        except Exception:
            pass
        steps = 9
        print(f"本地生图开始: size_type={size_type}, steps={steps}")
        self.local_image_preview.setText("加载中...")
        t = LocalImageApiThread(prompt, steps, size_type, use_cartoon_suffix)
        t.success.connect(self.on_local_image_api_success)
        t.error.connect(self.on_local_image_api_error)
        self._local_image_thread = t
        t.start()

    def on_local_image_api_success(self, content, status_code, headers):
        ct = ""
        try:
            ct = headers.get('content-type', '')
        except Exception:
            ct = ''
        print(f"本地生图成功: status={status_code}, content_type={ct}, bytes={len(content)}")
        pix = QPixmap()
        loaded = pix.loadFromData(content)
        if loaded and not pix.isNull():
            w = self.local_image_preview.width()
            h = self.local_image_preview.heightForWidth(w)
            scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.local_image_preview.setPixmap(scaled)
            if self.toast_manager:
                self.toast_manager.show_success("生图接口返回图片")
        else:
            try:
                text_preview = content.decode('utf-8', errors='ignore')[:500]
            except Exception:
                text_preview = f"bytes={len(content)}"
            self.local_image_preview.setText(text_preview or f"bytes={len(content)}")
            if self.toast_manager:
                self.toast_manager.show_info("接口返回非图片内容")

    def on_local_image_api_error(self, error_msg, status_code, body_text):
        print(f"本地生图失败: status={status_code}, 错误={error_msg}")
        if body_text:
            print(f"本地生图失败响应体: {body_text[:500]}")
        self.local_image_preview.setText("生成失败")
        if self.toast_manager:
            self.toast_manager.show_error("生图接口调用失败")


class TranscodeThread(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(int, int)
    def __init__(self, input_dir, output_dir, recursive, output_format="mp3"):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.recursive = recursive
        self.output_format = output_format
    def run(self):
        def cb(converted, total):
            self.progress.emit(converted, total)
        converted, total = convert_all_mp3_in_directory(self.input_dir, self.output_dir, self.recursive, cb, self.output_format)
        self.done.emit(converted, total)

    
    
