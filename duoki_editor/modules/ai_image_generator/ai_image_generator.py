import os
import sys
import re
import json
import base64
import logging
import io
from io import BytesIO
import shutil
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

import requests
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QTextEdit, QSpinBox, QComboBox, QProgressBar, QScrollArea, QFrame,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QMessageBox, QGroupBox, QGridLayout, QMenu, QMenuBar, QApplication, QDialog, QCheckBox,
    QPlainTextEdit, QSizePolicy, QAbstractSpinBox, QRadioButton, QTabWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QFont, QColor, QFontMetrics, QPalette

from duoki_editor.utils.config_manager import ConfigManager
from duoki_editor.modules.online_data.online_data_viewer import ImagePreviewDialog
from duoki_editor.utils.constants_loader import ConstantsLoader
from duoki_editor.ui.toast import Toast
from duoki_editor.utils.worker_thread import ThreadPoolRunner

# 获取logger
logger = logging.getLogger(__name__)

# 提升为常量：卡通风格后缀
CARTOON_STYLE_SUFFIX = "cartoon style，扁平风格，无轮廓，禁用渐变/体积感，明快配色。"
BATCH_CREATE_STORY_PROMPT = "创意参数拉满到1.0，无参考图的角色使用Q版风格，主角要靠近画面中心，不要太贴近边缘，姿势要尽量灵动，如果主要角色没有穿衣服，可以根据实际情境选择是否给主要角色添加服装，所有人类角色和拟人角色的个体大小要相对一致，不要有太大差别，如果前面没有提到具体的场景设定，可以根据情境设计一个场景作为背景，画面中不要出现中文，图片尺寸为1024x1024"
BATCH_CREATE_COMMON_PROMPT = "创意参数0.8，画面中不要出现中文，图片尺寸为1536x1024"
BATCH_CREATE_IMAGE_TO_IMAGE = "将这张图调整为下面的风格：cartoon style，扁平风格，无轮廓，可在保持扁平风格的前提下少量增加阴影提升立体感。"
BATCH_CREATE_AVATAR_IMAGE = "给附件中的角色换成{cosplay}的服装，{addons}，除此之外不要改变角色的身材、五官、动作等，保持半身像。不要添加原图中不存在的部分，此外身体、头部、五官的大小和相对位置都要保持跟原图一致，可以完全重叠，风格同原图保持一致，白色背景，图片内宽1024，高1024，cartoon style，扁平风格，无轮廓，明快配色。"

def add_watermark(img_bytes):
    """在图片下方添加一行白色文字: "AI 生成图片"
    字体固定使用 duoki_editor/resources/font/DOUYUFont.ttf，不再从系统字体中查找。
    """
    try:
        with Image.open(io.BytesIO(img_bytes)) as base_image:
            original_format = (base_image.format or 'PNG').upper()
            original_icc = base_image.info.get('icc_profile')
            original_exif = base_image.info.get('exif')
            has_alpha = 'A' in base_image.getbands() or 'transparency' in base_image.info
            supports_alpha = original_format in {'PNG', 'WEBP'}

            image = base_image.copy() if base_image.mode == 'RGBA' else base_image.convert('RGBA')
            width, height = image.size

            watermark_text = "AI 生成图片"

            # 根据图片高度调整字体大小
            font_size = int(height * 0.03)
            if font_size < 12:
                font_size = 12

            # 根据字体大小调整边距
            margin = int(font_size * 1.5)
            draw = ImageDraw.Draw(image)
            rect_height = margin
            rect_y0 = height - rect_height

            # 固定使用项目内置字体 DOUYUFont.ttf
            # 兼容开发环境、Windows/Mac 打包环境（onefile/onefolder）
            font = None
            font_candidates = []

            try:
                dev_base = Path(__file__).resolve().parents[2]  # duoki_editor 目录
                # 开发环境（源码路径）
                font_candidates.append(str(dev_base / 'resources' / 'font' / 'DOUYUFont.ttf'))
                if getattr(sys, 'frozen', False):
                    # PyInstaller 环境（统一打包到 duoki_editor/resources）
                    meipass = getattr(sys, '_MEIPASS', None)
                    if meipass:
                        font_candidates.append(os.path.join(meipass, 'duoki_editor', 'resources', 'font', 'DOUYUFont.ttf'))
                        font_candidates.append(os.path.join(meipass, 'resources', 'font', 'DOUYUFont.ttf'))
                    # onefolder/普通可执行目录
                    exe_dir = os.path.dirname(sys.executable)
                    font_candidates.append(os.path.join(exe_dir, 'duoki_editor', 'resources', 'font', 'DOUYUFont.ttf'))
                    font_candidates.append(os.path.join(exe_dir, 'resources', 'font', 'DOUYUFont.ttf'))
                    # macOS .app 结构: Contents/MacOS -> Contents/Resources/duoki_editor/resources
                    try:
                        contents_dir = Path(sys.executable).resolve().parents[1]
                        font_candidates.append(str(contents_dir / 'Resources' / 'duoki_editor' / 'resources' / 'font' / 'DOUYUFont.ttf'))
                        font_candidates.append(str(contents_dir / 'Resources' / 'resources' / 'font' / 'DOUYUFont.ttf'))
                    except Exception:
                        pass
            except Exception:
                pass

            # 选取首个存在的字体路径
            font_path = None
            for p in font_candidates:
                if p and os.path.exists(p):
                    font_path = p
                    break

            try:
                if font_path:
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    raise IOError('DOUYUFont.ttf not found')
            except Exception:
                # 回退到默认字体，避免处理失败
                try:
                    font = ImageFont.load_default()
                except Exception:
                    logger.error("Cannot load default font for watermark.")
                    return img_bytes

            # 使用 getbbox 来计算文本尺寸
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(watermark_text)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            else:
                text_width, text_height = draw.textsize(watermark_text, font=font)

            text_x = (width - text_width) / 2
            text_y = rect_y0 + (rect_height - text_height) / 2

            draw.text(
                (text_x, text_y), watermark_text, font=font, fill=(255, 255, 255, 255),
                # stroke_width=1, stroke_fill=(0, 0, 0, 255) # 增加黑色描边
            )

            # 维持原始格式保存，避免额外的颜色配置
            if supports_alpha and has_alpha:
                final_image = image
            else:
                final_image = image.convert('RGB')

            img_byte_arr = io.BytesIO()
            save_kwargs = {}
            if original_icc:
                save_kwargs['icc_profile'] = original_icc
            if original_exif:
                save_kwargs['exif'] = original_exif

            final_image.info.pop('icc_profile', None)

            if original_format in {'JPEG', 'JPG'}:
                final_image.save(img_byte_arr, format='JPEG', quality=90, **save_kwargs)
            elif original_format == 'PNG':
                final_image.save(img_byte_arr, format='PNG', **save_kwargs)
            elif original_format == 'WEBP':
                final_image.save(img_byte_arr, format='WEBP', **save_kwargs)
            else:
                final_image.save(img_byte_arr, format=original_format, **save_kwargs)

            return img_byte_arr.getvalue()
    except Exception as e:
        print(f"Failed to add watermark: {e}")
        return img_bytes


class GeneratedImagePreviewDialog(QDialog):
    """生成图片预览弹窗（支持上一张/下一张循环浏览和计数标签）"""
    
    def __init__(self, images_ref, start_index=0, parent=None):
        super().__init__(parent)
        # 引用图片列表（元素包含 'image_data' 等），新图片追加后即可被预览循环访问
        self.images_ref = images_ref
        self.current_index = max(0, int(start_index))
        self.gen_pixmap = None
        self.orig_pixmap = None
        self.counter_label = None
        self.prev_btn = None
        self.next_btn = None
        parent_widget = self.parent()
        page = getattr(parent_widget, 'parent_widget', None)
        try:
            self._show_orig_panel = isinstance(page, Img2ImgPage)
        except Exception:
            self._show_orig_panel = False
        self.init_ui()
        self._render_current()
        # 定时刷新总数，保证新生成图片加入循环并更新计数
        try:
            self._counter_timer = QTimer(self)
            self._counter_timer.setInterval(1000)
            self._counter_timer.timeout.connect(self._refresh_counter_only)
            self._counter_timer.start()
        except Exception:
            pass

    def init_ui(self):
        """初始化多图预览对话框UI"""
        self.setWindowTitle("图片预览")
        self.setModal(True)
        self.resize(800, 700)

        layout = QVBoxLayout()

        # 菜单栏：文件 -> 另存为
        try:
            self.menu_bar = QMenuBar(self)
            file_menu = self.menu_bar.addMenu("文件")
            save_as_action = file_menu.addAction("另存为")
            save_as_action.triggered.connect(self._on_save_as)
            # 审核菜单 -> 打回（仅对 XLSX 批量生成的图片显示）
            self.review_menu = self.menu_bar.addMenu("审核")
            self.reject_action = self.review_menu.addAction("打回")
            self.reject_action.triggered.connect(self._on_reject_current)
            # 默认隐藏，后续根据当前图片来源动态显示
            self.review_menu.menuAction().setVisible(False)
            layout.setMenuBar(self.menu_bar)
        except Exception:
            pass

        # 上方固定空间用于图片（随窗口变化），与图片内容大小无关
        self.image_container = QWidget()
        self.image_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container_layout = QVBoxLayout(self.image_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # 水平并列显示：左原图 + 右生成图
        images_row = QHBoxLayout()
        images_row.setContentsMargins(0, 0, 0, 0)
        images_row.setSpacing(6)
        self.orig_image_label = QLabel()
        self.orig_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orig_image_label.setStyleSheet("border: 1px solid gray; background: #111;")
        self.orig_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.orig_image_label.setMinimumSize(200, 150)
        self.orig_image_label.setText("原图加载中...")

        self.gen_image_label = QLabel()
        self.gen_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gen_image_label.setStyleSheet("border: 1px solid gray; background: #111;")
        self.gen_image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.gen_image_label.setMinimumSize(200, 150)
        self.gen_image_label.setText("生成图加载中...")

        images_row.addWidget(self.orig_image_label)
        images_row.addWidget(self.gen_image_label)
        container_layout.addLayout(images_row)
        self.orig_image_label.setVisible(bool(self._show_orig_panel))

        layout.addWidget(self.image_container, stretch=1)

        # 图片下方：完整提示词显示区域（包含prompt + style/common）
        self.full_prompt_view = QPlainTextEdit()
        self.full_prompt_view.setReadOnly(True)
        self.full_prompt_view.setFixedHeight(80)
        layout.addWidget(self.full_prompt_view, stretch=0)

        # 底部控制区：上一张 [计数] 下一张，整体居中；固定为一行空间
        ctrl_widget = QWidget()
        ctrl_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        ctrl = QHBoxLayout(ctrl_widget)
        ctrl.setContentsMargins(0, 6, 0, 6)
        ctrl.setSpacing(12)
        ctrl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev_btn = QPushButton("上一张")
        self.next_btn = QPushButton("下一张")
        self.counter_label = QLabel("0/0")
        self.counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ctrl.addWidget(self.prev_btn)
        ctrl.addWidget(self.counter_label)
        ctrl.addWidget(self.next_btn)
        layout.addWidget(ctrl_widget, stretch=0)

        # 事件连接
        self.prev_btn.clicked.connect(self._on_prev)
        self.next_btn.clicked.connect(self._on_next)

        self.setLayout(layout)

    def _on_save_as(self):
        """菜单栏的另存为：复用父组件的另存为逻辑"""
        try:
            total = self._current_total()
            if total <= 0:
                return
            idx = self.current_index % total
            item = self.images_ref[idx]
            image_data = item.get('image_data') if isinstance(item, dict) else None
            data_dict = item.get('data_dict') if isinstance(item, dict) else None
            parent = self.parent()
            if parent and hasattr(parent, 'save_image_as') and image_data:
                parent.save_image_as(image_data, data_dict or {})
        except Exception:
            pass

    def _on_reject_current(self):
        """审核菜单中的打回：联动父组件删除当前图片并标记失败"""
        total = self._current_total()
        if total <= 0:
            return
        idx = self.current_index % total
        item = self.images_ref[idx] if isinstance(self.images_ref, list) else None
        if not isinstance(item, dict):
            return
        frame = item.get('frame')
        data_dict = item.get('data_dict') or {}
        parent = self.parent()
        # 调用父组件的打回逻辑，移除缩略图并联动左侧失败标记
        if parent and hasattr(parent, '_reject_frame') and frame is not None:
            parent._reject_frame(frame, data_dict)
            # 更新当前索引与界面（列表可能已缩短或为空）
            new_total = self._current_total()
            if new_total <= 0:
                self.close()
                return
            self.current_index = self.current_index % new_total
            self._render_current()

    def _current_total(self) -> int:
        try:
            return len(self.images_ref) if self.images_ref is not None else 0
        except Exception:
            return 0

    def _get_image_bytes(self):
        try:
            total = self._current_total()
            if total == 0:
                return None
            # 防止越界，循环取模
            idx = self.current_index % total
            item = self.images_ref[idx]
            return item.get('image_data') if isinstance(item, dict) else None
        except Exception:
            return None

    def _get_original_bytes(self):
        try:
            total = self._current_total()
            if total == 0:
                return None
            idx = self.current_index % total
            item = self.images_ref[idx] if isinstance(self.images_ref, list) else None
            if not isinstance(item, dict):
                return None
            dd = item.get('data_dict') or {}
            # 优先从data_dict中获得原图路径（若已有）
            src = dd.get('source_abs') or dd.get('source_path')
            if not src:
                # 图生图批量：使用父组件的相对路径映射
                parent_widget = self.parent()
                page = getattr(parent_widget, 'parent_widget', None)
                rel = str(dd.get('filename') or '').strip()
                if page and hasattr(page, '_img_rows') and rel:
                    for r in page._img_rows:
                        if str(r.get('rel') or '') == rel:
                            src = r.get('abs')
                            break
            if not src or not os.path.isfile(src):
                return None
            with open(src, 'rb') as f:
                return f.read()
        except Exception:
            return None

    def _render_current(self):
        """渲染当前索引图片并更新计数"""
        try:
            img_bytes = self._get_image_bytes()
            if not img_bytes:
                self.gen_image_label.setText("图片加载失败")
                self.counter_label.setText("0/0")
                self.full_prompt_view.setPlainText("")
                # 无图片时隐藏审核菜单
                self.review_menu.menuAction().setVisible(False)
                return

            gen = QPixmap()
            if not gen.loadFromData(img_bytes):
                self.gen_image_label.setText("图片加载失败")
                self.full_prompt_view.setPlainText("")
                return
            self.gen_pixmap = gen

            if self._show_orig_panel:
                orig_bytes = self._get_original_bytes()
                if orig_bytes:
                    op = QPixmap()
                    if op.loadFromData(orig_bytes):
                        self.orig_pixmap = op
                        self.orig_image_label.setText("")
                    else:
                        self.orig_pixmap = None
                        self.orig_image_label.setText("原图加载失败")
                else:
                    self.orig_pixmap = None
                    self.orig_image_label.setText("无原图")

            self._rescale_to_labels()
            self._update_counter_label()
            # 更新完整提示词显示（prompt + style）
            total = self._current_total()
            if total > 0 and isinstance(self.images_ref, list):
                idx = self.current_index % total
                item = self.images_ref[idx]
                data_dict = item.get('data_dict') if isinstance(item, dict) else None
                if isinstance(data_dict, dict):
                    prompt = data_dict.get('prompt', '')
                    style = data_dict.get('style', '')
                    full_prompt = f"{prompt}, {style}" if style else prompt
                    self.full_prompt_view.setPlainText(full_prompt)
                    # 仅当 XLSX 批量生成的图片时显示审核菜单
                    is_xlsx_generated = bool(data_dict.get('is_xlsx_generated'))
                    self.review_menu.menuAction().setVisible(is_xlsx_generated)
                else:
                    self.full_prompt_view.setPlainText("")
                    self.review_menu.menuAction().setVisible(False)
            else:
                self.full_prompt_view.setPlainText("")
                self.review_menu.menuAction().setVisible(False)
        except Exception as e:
            self.gen_image_label.setText(f"图片加载失败: {str(e)}")

    def _rescale_to_labels(self):
        try:
            avail_rect = self.image_container.contentsRect()
            avail_w = max(1, avail_rect.width())
            avail_h = max(1, avail_rect.height())
            if bool(self._show_orig_panel):
                half_w = max(1, int(avail_w / 2) - 3)
                if self.orig_pixmap:
                    o_scaled = self.orig_pixmap.scaled(
                        half_w,
                        avail_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.orig_image_label.setPixmap(o_scaled)
                if self.gen_pixmap:
                    g_scaled = self.gen_pixmap.scaled(
                        half_w,
                        avail_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.gen_image_label.setPixmap(g_scaled)
            else:
                if self.gen_pixmap:
                    g_scaled = self.gen_pixmap.scaled(
                        avail_w,
                        avail_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.gen_image_label.setPixmap(g_scaled)
        except Exception:
            pass

    def _update_counter_label(self):
        try:
            total = self._current_total()
            if total <= 0:
                self.counter_label.setText("0/0")
            else:
                cur = (self.current_index % total) + 1
                self.counter_label.setText(f"{cur}/{total}")
        except Exception:
            pass

    def _refresh_counter_only(self):
        # 仅刷新计数文本，以反映新添加的图片数量
        self._update_counter_label()

    def _on_prev(self):
        total = self._current_total()
        if total <= 0:
            return
        self.current_index = (self.current_index - 1) % total
        self._render_current()

    def _on_next(self):
        total = self._current_total()
        if total <= 0:
            return
        self.current_index = (self.current_index + 1) % total
        self._render_current()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 窗口调整大小时重绘缩放
        self._rescale_to_labels()

class ErrorResponseDialog(QDialog):
    """显示完整错误返回体的弹窗"""
    def __init__(self, title: str, body_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 450)

        layout = QVBoxLayout(self)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        # 展示前对包含的base64数据进行脱敏处理：将数据体替换为“base64编码数据”
        raw_text = body_text if isinstance(body_text, str) else str(body_text)
        self.text.setPlainText(self._mask_base64_chunks(raw_text))
        layout.addWidget(self.text)

        btn_bar = QHBoxLayout()
        copy_btn = QPushButton("复制")
        close_btn = QPushButton("关闭")
        btn_bar.addWidget(copy_btn)
        btn_bar.addStretch(1)
        btn_bar.addWidget(close_btn)
        layout.addLayout(btn_bar)

        def _copy():
            try:
                QApplication.clipboard().setText(self.text.toPlainText())
            except Exception:
                pass

        copy_btn.clicked.connect(_copy)
        close_btn.clicked.connect(self.accept)

    @staticmethod
    def _mask_base64_chunks(s: str) -> str:
        """将文本中可能出现的base64数据体替换为固定占位符。
        处理策略：
        - data URI：匹配 'data:<mime>;base64,<...>'，仅保留前缀，将数据体替换为“base64编码数据”。
        - JSON/文本中的超长base64串：匹配引号内长度>=200的base64字符集，替换为“base64编码数据”。
        - 单引号场景同样处理。
        """
        if not isinstance(s, str):
            s = str(s)
        # data URI 的base64数据
        s = re.sub(r"(data:[^;]+;base64,)\s*[A-Za-z0-9+/=\r\n]+", r"\1base64编码数据", s)
        # 双引号中的超长base64文本
        s = re.sub(r'("\s*)([A-Za-z0-9+/=\s]{200,})(\s*")', r'"base64编码数据"', s)
        # 单引号中的超长base64文本
        s = re.sub(r"('\s*)([A-Za-z0-9+/=\s]{200,})(\s*')", r"'base64编码数据'", s)
        return s

class AttachmentPreviewDialog(QDialog):
    """附件图片预览弹窗，矩阵排列并支持删除附件（仅从数组移除，不删缓存）"""

    def __init__(self, attachment_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("附件预览")
        self.resize(800, 600)
        self._parent = parent
        # 直接引用列表，便于更新
        self.attachment_paths = attachment_paths

        self.main_layout = QVBoxLayout(self)
        # 菜单栏：文件 -> 清空附件
        menubar = QMenuBar(self)
        file_menu = menubar.addMenu("文件")
        clear_action = file_menu.addAction("清空附件")
        clear_action.triggered.connect(self._on_clear_attachments)
        self.main_layout.addWidget(menubar)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        # 不显示水平滚动条
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_layout.addWidget(self.scroll_area)

        # 三列布局，按窗口宽度的1/3自适应
        self._cols = 3
        self._tiles = []  # (tile_frame, img_label, name_label, del_btn, path)

        self._build_grid()

    def _build_grid(self):
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(8)
        # 使附件预览的网格整体左上对齐，避免居中显示
        grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        if not self.attachment_paths:
            empty_label = QLabel("暂无附件")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(empty_label, 0, 0)
        else:
            self._tiles.clear()
            cols = self._cols
            for i, path in enumerate(self.attachment_paths):
                row = i // cols
                col = i % cols

                tile = QFrame()
                v = QVBoxLayout(tile)
                v.setSpacing(6)
                # 仅保留一个将图片与按钮框起来的白色边框；内部无多余外边距
                v.setContentsMargins(6, 6, 6, 6)
                tile.setStyleSheet("QFrame { border: 1px solid #FFFFFF; border-radius: 0px; background: transparent; }")

                # 图片预览
                pix = QPixmap(path)
                img_label = QLabel()
                img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                img_label.setStyleSheet("QLabel { background: transparent; border: none; }")
                if not pix.isNull():
                    # 初始缩略图尺寸，在布局更新时会重新自适应
                    thumb = pix.scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    img_label.setPixmap(thumb)
                else:
                    # 保持图片区域空白，文件名由下方标签显示
                    img_label.setText("")

                v.addWidget(img_label)

                # 文件名（仅文件名.扩展名），单行、无边框，居中显示
                base_name = os.path.basename(path)
                name_label = QLabel(base_name)
                name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                name_label.setWordWrap(False)
                name_label.setStyleSheet("QLabel { background: transparent; border: none; }")
                # 保持单行高度固定，避免因宽度变化导致高度抖动
                try:
                    fm0 = QFontMetrics(name_label.font())
                    name_label.setFixedHeight(fm0.height())
                except Exception:
                    pass
                v.addWidget(name_label)

                # 删除按钮
                del_btn = QPushButton("删除")
                del_btn.clicked.connect(lambda _, p=path: self._on_delete(p))
                v.addWidget(del_btn)

                grid.addWidget(tile, row, col)
                self._tiles.append((tile, img_label, name_label, del_btn, path))

        self.scroll_area.setWidget(container)
        # 当内容小于视口时，确保内容左上对齐而非居中
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        # 构建完成后更新尺寸以消除水平滚动条
        self._update_layout_sizes()

    def _on_delete(self, path: str):
        try:
            # 通过父级移除，保证主界面数组更新
            if self._parent and hasattr(self._parent, 'remove_attachment_avatar'):
                self._parent.remove_attachment_avatar(path)
            elif self._parent and hasattr(self._parent, 'remove_attachment'):
                self._parent.remove_attachment(path)
            else:
                # 兜底：直接在本地列表中移除
                if path in self.attachment_paths:
                    self.attachment_paths.remove(path)
            # 重新构建网格
            self._build_grid()
        except Exception as e:
            QMessageBox.warning(self, "警告", f"删除附件失败: {e}")

    def _on_clear_attachments(self):
        try:
            if self._parent and hasattr(self._parent, 'clear_attachments_avatar'):
                self._parent.clear_attachments_avatar()
            elif self._parent and hasattr(self._parent, 'clear_attachments'):
                self._parent.clear_attachments()
            else:
                self.attachment_paths.clear()
            self._build_grid()
        except Exception as e:
            QMessageBox.warning(self, "警告", f"清空附件失败: {e}")

    def _update_layout_sizes(self):
        """根据窗口宽度将每个格子宽度设为窗口的1/3，并自适应缩略图尺寸"""
        try:
            viewport = self.scroll_area.viewport()
            vw = max(1, viewport.width())
            # 目标宽度为视口的1/3，减去栅格间距的影响
            spacing = 8
            tile_w = max(180, vw // self._cols - spacing * 2)
            img_target = max(120, tile_w - 24)  # 给内部留出少量空间

            for tile, img_label, name_label, del_btn, path in self._tiles:
                tile.setFixedWidth(tile_w)
                # 固定纵横比为 3:4（宽:高）
                tile_h = max(240, int(tile_w * 4 / 3))
                tile.setFixedHeight(tile_h)
                pix = QPixmap(path)
                if not pix.isNull():
                    # 计算内部可用空间（扣除边距和文件名/按钮高度以及布局间距）
                    margin = 12  # v.setContentsMargins(6,6,6,6)
                    inner_w = max(10, tile_w - margin)
                    inner_h = max(10, tile_h - margin)
                    try:
                        name_h = name_label.height() or name_label.sizeHint().height()
                    except Exception:
                        name_h = 18
                    try:
                        btn_h = del_btn.height() or del_btn.sizeHint().height()
                    except Exception:
                        btn_h = 28
                    spacing_v = 6  # v.setSpacing(6)
                    reserved_h = name_h + btn_h + spacing_v * 2
                    img_avail_h = max(60, inner_h - reserved_h)
                    # 按可用宽高缩放图片，保持比例
                    thumb = pix.scaled(inner_w, img_avail_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    img_label.setPixmap(thumb)
                # 更新文件名为单行省略以适配当前宽度
                try:
                    fm = QFontMetrics(name_label.font())
                    text_w = max(10, inner_w)
                    elided = fm.elidedText(os.path.basename(path), Qt.TextElideMode.ElideRight, text_w)
                    name_label.setText(elided)
                except Exception:
                    pass
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 窗口尺寸变化时更新格子宽度与缩略图
        self._update_layout_sizes()

    def showEvent(self, event):
        super().showEvent(event)
        # 首次显示时根据实际视口宽度更新，保持与后续resize一致的间距
        self._update_layout_sizes()

class ImageGenerationWorker(QThread):
    """图像生成工作线程"""
    progress_updated = pyqtSignal(str)
    # 修改信号，传递完整的数据字典
    image_generated = pyqtSignal(dict, bytes)  # data_dict, image_data
    error_occurred = pyqtSignal(str, dict)  # error_message, data_dict
    # 新增：任务开始信号，用于将提示词标记为“生成中”（橙色）
    item_started = pyqtSignal(dict)
    finished = pyqtSignal()
    
    def __init__(self, api_token, prompt_data_list, model="yunwu-xl", size="1024x1024", num_images=1, max_workers=10):
        super().__init__()
        self.api_token = api_token
        self.prompt_data_list = prompt_data_list if isinstance(prompt_data_list, list) else [prompt_data_list]
        self.model = model
        self.size = size
        self.num_images = num_images
        self.max_workers = max_workers
        self.is_running = True
        self.completed_count = 0
        self.total_count = len(self.prompt_data_list)
        self.lock = threading.Lock()
        self.active_futures = set()  # 存储所有活跃的Future对象
        
    def run(self):
        """执行图像生成任务 - 动态控制并发数量"""
        self.executor = None
        try:
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
            # 动态控制并发：每完成一个任务就启动下一个
            future_to_data = {}
            # 为plus接口按num_images展开任务队列（有参考图时重复调用）
            task_queue = []
            for dd in (self.prompt_data_list if isinstance(self.prompt_data_list, list) else [self.prompt_data_list]):
                ref_paths = dd.get('ref_image_paths') or []
                repeat = self.num_images if len(ref_paths) > 0 else 1
                for _ in range(repeat):
                    task_queue.append(dd)
            single_batch = len(self.prompt_data_list if isinstance(self.prompt_data_list, list) else [self.prompt_data_list]) == 1
            expected_total = 0
            for dd in (self.prompt_data_list if isinstance(self.prompt_data_list, list) else [self.prompt_data_list]):
                ref_paths = dd.get('ref_image_paths') or []
                if len(ref_paths) > 0:
                    expected_total += self.num_images
                else:
                    expected_total += (self.num_images if single_batch else 1)
            self.total_count = expected_total
            running_tasks = 0  # 当前运行的任务数
            
            # 初始启动最多max_workers个任务
            while task_queue and running_tasks < self.max_workers and self.is_running:
                data_dict = task_queue.pop(0)
                # 发出开始任务信号
                try:
                    self.item_started.emit(data_dict)
                except Exception:
                    pass
                future = self.executor.submit(self._generate_single_image, data_dict)
                future_to_data[future] = data_dict
                self.active_futures.add(future)  # 跟踪活跃的Future
                running_tasks += 1
                # 每次提交一次调用后，间隔0.1秒再继续
                try:
                    time.sleep(0.1)
                except Exception:
                    pass
            
            # 处理完成的任务并动态启动新任务
            while future_to_data and self.is_running:
                # 等待至少一个任务完成
                for future in as_completed(future_to_data):
                    if not self.is_running:
                        break
                        
                    data_dict = future_to_data.pop(future)
                    self.active_futures.discard(future)  # 从活跃Future集合中移除
                    running_tasks -= 1
                    
                    try:
                        image_data = future.result()
                        try:
                            if isinstance(image_data, list):
                                if len(image_data) == 0:
                                    inc = self.num_images if (not (data_dict.get('ref_image_paths') or []) and single_batch) else 1
                                    with self.lock:
                                        self.completed_count += inc
                                        self.progress_updated.emit(f"{self.completed_count}/{self.total_count} 已完成")
                                    self.error_occurred.emit(f"生成图片失败: 返回空列表", data_dict)
                                else:
                                    for img_bytes in image_data:
                                        if img_bytes:
                                            self.image_generated.emit(data_dict, img_bytes)
                                        else:
                                            self.error_occurred.emit(f"生成图片失败: 空图片", data_dict)
                                        with self.lock:
                                            self.completed_count += 1
                                            self.progress_updated.emit(f"{self.completed_count}/{self.total_count} 已完成")
                            elif image_data:
                                self.image_generated.emit(data_dict, image_data)
                                with self.lock:
                                    self.completed_count += 1
                                    self.progress_updated.emit(f"{self.completed_count}/{self.total_count} 已完成")
                            else:
                                self.error_occurred.emit(f"生成图片失败: {data_dict['prompt']}", data_dict)
                                with self.lock:
                                    self.completed_count += 1
                                    self.progress_updated.emit(f"{self.completed_count}/{self.total_count} 已完成")
                        except Exception as ie:
                            self.error_occurred.emit(f"处理生成结果异常: {str(ie)}", data_dict)
                    except Exception as e:
                        inc = self.num_images if (not (data_dict.get('ref_image_paths') or []) and single_batch) else 1
                        with self.lock:
                            self.completed_count += inc
                            self.progress_updated.emit(f"{self.completed_count}/{self.total_count} 已完成")
                        self.error_occurred.emit(f"生成图片异常: {str(e)}", data_dict)
                    
                    # 如果还有待处理任务且当前运行任务数未达到上限，启动新任务
                    if task_queue and running_tasks < self.max_workers and self.is_running:
                        next_data_dict = task_queue.pop(0)
                        self.item_started.emit(next_data_dict)
                        new_future = self.executor.submit(self._generate_single_image, next_data_dict)
                        future_to_data[new_future] = next_data_dict
                        self.active_futures.add(new_future)  # 跟踪新的Future
                        running_tasks += 1
                        # 每次提交一次调用后，间隔0.1秒再继续
                        time.sleep(0.1)
                    break
                    
        except Exception as e:
            # 对于异常情况，传递None作为data_dict，表示是全局错误
            self.error_occurred.emit(f"生成过程中发生错误: {str(e)}", None)
        finally:
            # 确保线程池被正确关闭
            if self.executor:
                self.executor.shutdown(wait=False)
                self.executor = None
            self.active_futures.clear()  # 清空活跃Future集合
            self.finished.emit()
    
    def _generate_single_image(self, data_dict):
        """生成单张图片的内部方法"""
        if not self.is_running:
            return None
            
        # 拼接提示词和style字段
        prompt = data_dict['prompt']
        style = data_dict.get('style', '')
        if style:
            full_prompt = f"{prompt}, {style}"
        else:
            full_prompt = prompt
        
        # 根据参考图路径的数量决定调用的接口
        ref_paths = data_dict.get('ref_image_paths') or []
        if len(ref_paths) > 0:
            result = self.generate_image_with_ref(full_prompt, ref_paths, return_detail=True)
        else:
            # 调用云雾AI API生成图像（返回详细错误信息）
            result = self.generate_image(full_prompt, return_detail=True)

        if isinstance(result, tuple):
            # (image_bytes, error_detail, error_full_body)
            image_bytes, error_detail, error_full_body = result
            if image_bytes is None:
                if error_detail:
                    data_dict['error_detail'] = error_detail
                if error_full_body:
                    data_dict['error_full_body'] = error_full_body
            return image_bytes
        else:
            return result
    
    # 已移除：响应图片格式检测逻辑（统一按URL处理PNG）

    def generate_image(self, prompt, return_detail: bool = False):
        """调用云雾AI API生成单张图像"""
        try:
            # 在开始API调用前检查是否应该停止
            if not self.is_running:
                return None
                
            url = "https://yunwu.zeabur.app/v1/images/generations"
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "prompt": prompt,
                "size": self.size,
                "n": self.num_images
            }
            try:
                request_body_str = json.dumps(data, ensure_ascii=False, indent=2)
            except Exception:
                request_body_str = str(data)
            
            # 输出请求信息到控制台
            print("-------------------------------------------------------------------")
            print(f"[AI图片生成] 调用API: {url}")
            print(f"[AI图片生成] 模型: {self.model}, 尺寸: {self.size}, 提示词: {prompt}")
            
            # 在发送请求前再次检查是否应该停止
            if not self.is_running:
                return None
            
            response = requests.post(url, headers=headers, json=data, timeout=600)
            
            # 在处理响应前检查是否应该停止
            if not self.is_running:
                return None
            
            if response.status_code == 200:
                result = response.json()
                if "data" in result and isinstance(result["data"], list) and len(result["data"]) > 0:
                    images = []
                    print(f"[AI图片生成] 返回图片数量: {len(result['data'])}")
                    for idx, item in enumerate(result["data"]):
                        img_url = item.get("url")
                        if not img_url:
                            print(f"[AI图片生成] 第{idx+1}张缺少url字段，跳过")
                            continue
                        # 输出URL中的图片名
                        try:
                            url_name = os.path.basename(urlparse(img_url).path) or ""
                            if url_name:
                                print(f"[AI图片生成] URL图片名: {url_name}")
                        except Exception:
                            pass
                        try:
                            img_resp = requests.get(img_url, headers={'Accept': 'image/*'}, timeout=600)
                            img_resp.raise_for_status()
                            images.append(img_resp.content)
                            print(f"[AI图片生成] 第{idx+1}张已下载，大小: {len(img_resp.content)} bytes")
                        except Exception as e:
                            logger.error(f"下载第{idx+1}张图片失败: {str(e)}")
                    if len(images) == 0:
                        if return_detail:
                            try:
                                body_text = json.dumps(result, ensure_ascii=False, indent=2)
                            except Exception:
                                body_text = str(result)
                            combined = f"请求体：\n{request_body_str}\n-----------------------\n响应体：\n{body_text}"
                            return None, "没有可用的图像数据", combined
                        return None
                    return (images, None, None) if return_detail else images
                else:
                    logger.error(f"API响应中没有图像数据: {result}")
                    print(f"[AI图片生成] API调用失败: 响应中没有图像数据")
                    if return_detail:
                        try:
                            body_text = json.dumps(result, ensure_ascii=False, indent=2)
                        except Exception:
                            body_text = str(result)
                        combined = f"请求体：\n{request_body_str}\n-----------------------\n响应体：\n{body_text}"
                        return None, "响应中没有图像数据", combined
                    return None
            else:
                logger.error(f"API请求失败: {response.status_code}, {response.text}")
                print(f"[AI图片生成] API调用失败: HTTP {response.status_code}")
                if return_detail:
                    body_text = response.text
                    combined = f"请求体：\n{request_body_str}\n-----------------------\n响应体：\n{body_text}"
                    return None, f"HTTP {response.status_code}", combined
                return None
                
        except Exception as e:
            logger.error(f"生成图像时发生错误: {str(e)}")
            print(f"[AI图片生成] API调用异常: {str(e)}")
            if return_detail:
                try:
                    combined = f"请求体：\n{request_body_str}\n-----------------------\n响应体：\n无"
                except Exception:
                    combined = f"请求体：\n无\n-----------------------\n响应体：\n无"
                return None, f"API调用异常: {str(e)}", combined
            return None

    def _encode_image_to_data_url(self, file_path: str) -> str:
        """读取本地图片并返回data URL字符串"""
        try:
            ext = os.path.splitext(file_path)[1].lower()
            mime = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.webp': 'image/webp',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp'
            }.get(ext, 'application/octet-stream')
            with open(file_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            return f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.error(f"读取参考图片失败: {file_path}, 错误: {e}")
            return ""

    def extract_image_url(self, response):
        """从API响应中提取图片URL"""
        try:
            response.raise_for_status()
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"]
            # content 可能是字符串或包含markdown的字符串
            if isinstance(content, str):
                match = re.search(r"!\[.*?\]\((.*?)\)", content)
                if match:
                    return match.group(1)
            # 兼容content为列表的情况（若服务端返回结构化message）
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "output_image":
                        url = item.get("image_url", {}).get("url")
                        if url:
                            return url
                # 若列表项仍为文本，尝试拼接后再匹配markdown
                joined = " ".join([it.get("text", "") if isinstance(it, dict) else str(it) for it in content])
                match = re.search(r"!\[.*?\]\((.*?)\)", joined)
                if match:
                    return match.group(1)
        except (requests.exceptions.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"解析响应错误: {e}")
            logger.error(f"响应状态: {getattr(response, 'status_code', 'unknown')}")
            try:
                logger.error(f"响应文本: {response.text}")
            except Exception:
                pass
            return None
        return None

    def extract_image_urls(self, response_json):
        """从chat completions响应中提取所有图片URL"""
        urls = []
        try:
            choices = response_json.get("choices", [])
            for choice in choices:
                content = choice.get("message", {}).get("content")
                # 文本：匹配markdown图片
                if isinstance(content, str):
                    for m in re.finditer(r"!\[.*?\]\((.*?)\)", content):
                        urls.append(m.group(1))
                # 列表：结构化返回
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "output_image":
                            url = item.get("image_url", {}).get("url")
                            if url:
                                urls.append(url)
                    joined = " ".join([it.get("text", "") if isinstance(it, dict) else str(it) for it in content])
                    for m in re.finditer(r"!\[.*?\]\((.*?)\)", joined):
                        urls.append(m.group(1))
        except Exception as e:
            logger.error(f"提取图片URL列表失败: {e}")
        # 去重保持顺序
        seen = set()
        uniq = [u for u in urls if not (u in seen or seen.add(u))]
        return uniq

    def generate_image_with_ref(self, prompt: str, ref_image_paths: list, return_detail: bool = False):
        """调用chat completions，支持参考图并下载生成图片"""
        try:
            if not self.is_running:
                return None

            url = "https://yunwu.ai/v1/chat/completions"
            base64_image_contents = [
                {"type": "image_url", "image_url": {"url": self._encode_image_to_data_url(p)}}
                for p in ref_image_paths if p
            ]
            content = [{"type": "text", "text": prompt}] + base64_image_contents

            payload_obj = {
                "model": self.model,
                "size": self.size,
                "messages": [
                    {
                        "role": "user",
                        "content": content
                    }
                ]
            }
            payload = json.dumps(payload_obj, ensure_ascii=False)
            try:
                request_body_plus = json.dumps(payload_obj, ensure_ascii=False, indent=2)
            except Exception:
                request_body_plus = str(payload_obj)
            
            print("-------------------------------------------------------------------")
            print("[AI图片生成+] 调用API: https://yunwu.ai/v1/chat/completions")
            print(f"[AI图片生成+] 模型: {self.model}, 尺寸: {self.size}, 提示词: {prompt}")
            print(f"[AI图片生成+] 共{len(ref_image_paths)}张参考图片")
            print(f"[AI图片生成+] 参考图片：{ref_image_paths}")
            # plus接口不支持一次返回多图，此处不再传递n，仅用于控制重复调用次数

            headers = {
                'Accept': 'application/json',
                'Authorization': f"Bearer {self.api_token}",
                'Content-Type': 'application/json'
            }

            if not self.is_running:
                return None
            response = requests.post(url, headers=headers, data=payload, timeout=400)

            if not self.is_running:
                return None
            
            # 提取所有图片URL并下载/解码
            try:
                response_json = response.json()
            except Exception:
                response_json = None

            # 仅提取一张图片URL并下载
            chosen_url = None
            if isinstance(response_json, dict):
                urls = self.extract_image_urls(response_json)
                if urls:
                    chosen_url = urls[0]
            if not chosen_url:
                chosen_url = self.extract_image_url(response)

            if chosen_url:
                try:
                    # 输出URL中的图片名
                    try:
                        url_name = os.path.basename(urlparse(chosen_url).path) or ""
                        if url_name:
                            print(f"[AI图片生成+] URL图片名: {url_name}")
                    except Exception:
                        pass
                    img_resp = requests.get(chosen_url, headers={'Accept': 'image/*'}, timeout=400)
                    img_resp.raise_for_status()
                    img_bytes = img_resp.content
                    return (img_bytes, None, None) if return_detail else img_bytes
                except Exception as de:
                    logger.error(f"下载图片失败: {de}")
                    if return_detail:
                        combined = f"请求体：\n{request_body_plus}\n-----------------------\n响应体：\n无"
                        return None, f"下载图片失败: {de}", combined
                    return None

            # 如仍失败，返回错误详情
            logger.error("未从响应中提取到图片URL")
            if return_detail:
                try:
                    response_json = response.json()
                except Exception:
                    response_json = None
                try:
                    err_body = json.dumps(response_json, ensure_ascii=False, indent=2) if response_json else response.text
                except Exception:
                    err_body = response.text if hasattr(response, 'text') else None
                combined = f"请求体：\n{request_body_plus}\n-----------------------\n响应体：\n{err_body}"
                return None, "未从响应中提取到图片URL", combined
            return None
        except requests.exceptions.Timeout:
            logger.error(f"Timeout generating image with ref for prompt: '{prompt[:40]}...'")
            if return_detail:
                combined = f"请求体：\n{request_body_plus}\n-----------------------\n响应体：\n无"
                return None, "生成请求超时", combined
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for prompt with ref '{prompt[:40]}...': {e}")
            if return_detail:
                combined = f"请求体：\n{request_body_plus}\n-----------------------\n响应体：\n无"
                return None, f"请求失败: {e}", combined
            return None
        except Exception as e:
            logger.error(f"生成图像(plus)时发生错误: {str(e)}")
            if return_detail:
                combined = f"请求体：\n{request_body_plus}\n-----------------------\n响应体：\n无"
                return None, f"生成图像(plus)时发生错误: {str(e)}", combined
            return None
    
    def stop(self):
        """停止生成任务"""
        self.is_running = False
        # 取消所有活跃的Future任务
        for future in list(self.active_futures):
            if not future.done():
                future.cancel()
        # 立即关闭线程池，不等待正在执行的任务完成
        if hasattr(self, 'executor') and self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None

class ImageDisplayWidget(QWidget):
    """图像显示组件"""
    
    def __init__(self, config_manager, parent_widget=None):
        super().__init__()
        self.config_manager = config_manager
        self.parent_widget = parent_widget  # 保存父组件引用以访问auto_crop_checkbox
        self.init_ui()
        self.images = []  # 存储生成的图像信息
        
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        
        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 创建图像容器
        self.image_container = QWidget()
        self.image_layout = QGridLayout(self.image_container)
        self.image_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.image_layout.setSpacing(10)
        
        self.scroll_area.setWidget(self.image_container)
        layout.addWidget(self.scroll_area)
        
    def add_image(self, data_dict, image_data, save_path=None):
        """添加生成的图像和"另存为"按钮"""
        try:
            # 创建图像框架
            image_frame = QFrame()
            image_frame.setFrameStyle(QFrame.Shape.Box)
            # 设置固定宽度，确保每行5个时每个框架占据1/5的宽度
            image_frame.setFixedWidth(200)  # 设置固定宽度
            frame_layout = QVBoxLayout(image_frame)
            
            # 显示图像
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            image_label = QLabel()
            image_label.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio))  # 调整图片大小适应框架
            
            # 设置图片标签可点击
            image_label.setStyleSheet("QLabel { }")
            image_label.setCursor(Qt.CursorShape.PointingHandCursor)
            # 记录当前图片索引，供预览循环起始位置使用
            current_index = len(self.images)
            image_label.mousePressEvent = lambda event, idx=current_index: self.show_image_preview(idx)
            
            frame_layout.addWidget(image_label)
            
            # 显示Prompt
            prompt_label = QLabel(data_dict.get('prompt', ''))
            prompt_label.setWordWrap(True)
            prompt_label.setMaximumHeight(60)  # 限制prompt标签高度
            frame_layout.addWidget(prompt_label)

            # 按钮行："另存为" + （批量图）"打回"
            buttons_row = QHBoxLayout()
            save_as_btn = QPushButton("另存为")
            save_as_btn.clicked.connect(lambda: self.save_image_as(image_data, data_dict))
            buttons_row.addWidget(save_as_btn)

            # 仅在批量生成图片时显示“打回”按钮
            # 约定：批量生成的数据会带有 is_batch=True；水印处理不显示打回
            is_batch = bool(data_dict.get('is_batch'))
            is_watermark = str(data_dict.get('prompt', '')).startswith('水印处理:')
            if is_batch and not is_watermark:
                reject_btn = QPushButton("打回")
                # 绑定打回事件：移除此frame并联动左侧标红与选中
                reject_btn.clicked.connect(lambda: self._reject_frame(image_frame, data_dict))
                buttons_row.addWidget(reject_btn)

            frame_layout.addLayout(buttons_row)

            # 将图像框架添加到布局
            row, col = divmod(len(self.images), 6) # 每行5个
            self.image_layout.addWidget(image_frame, row, col)
            self.images.append({
                'data_dict': data_dict,
                'image_data': image_data,
                'save_path': save_path,
                'frame': image_frame,
                'image_label': image_label
            })

        except Exception as e:
            print(f"添加图像失败: {e}")

    def _reject_frame(self, image_frame: QFrame, data_dict: dict):
        """打回当前图片：移除frame并联动左侧标记失败+选中"""
        try:
            # 1) 左侧联动：标记为失败（红色）并选中复选框
            parent = self.parent_widget
            if parent and hasattr(parent, 'mark_prompt_as_failed'):
                try:
                    if isinstance(data_dict, dict):
                        data_dict['rejected'] = True
                except Exception:
                    pass
                parent.mark_prompt_as_failed(data_dict)

                # 选中对应行复选框（按filename匹配）
                try:
                    target_filename = str((data_dict or {}).get('filename') or '').strip()
                    row_idx = -1
                    max_rows = min(parent.prompt_table.rowCount(), len(parent.prompt_data))
                    for i in range(max_rows):
                        fn = str(parent.prompt_data[i].get('filename') or '').strip()
                        if fn == target_filename:
                            row_idx = i
                            break
                    if row_idx >= 0:
                        chk = parent.prompt_table.item(row_idx, 0)
                        if chk:
                            chk.setCheckState(Qt.CheckState.Checked)
                except Exception:
                    pass

            # 1.5) 将文件移动到输出目录的 rejected 子目录
            try:
                target_item = None
                for it in self.images:
                    if it.get('frame') is image_frame:
                        target_item = it
                        break
                save_path = target_item.get('save_path') if isinstance(target_item, dict) else None
                if save_path and os.path.isfile(save_path):
                    output_dir = self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
                    output_dir = os.path.abspath(output_dir)
                    rejected_dir = os.path.join(output_dir, 'rejected')
                    os.makedirs(rejected_dir, exist_ok=True)
                    base = os.path.basename(save_path)
                    dest_path = os.path.join(rejected_dir, base)
                    if os.path.exists(dest_path):
                        name, ext = os.path.splitext(base)
                        ts = datetime.now().strftime("%Y%m%d%H%M%S")
                        dest_path = os.path.join(rejected_dir, f"{name}-{ts}{ext}")
                    shutil.move(save_path, dest_path)
                    print(f"[AI图片生成] 打回已移动到: {dest_path}")
                    Toast.info(f"已将图片移动到 {rejected_dir}", self)
            except Exception as me:
                logger.warning(f"打回移动文件失败: {me}")

            # 2) 右侧移除：删除该frame并重排剩余items
            self.image_layout.removeWidget(image_frame)
            image_frame.setParent(None)

            # 从images列表中移除对应项
            try:
                idx = -1
                for i, it in enumerate(self.images):
                    if it.get('frame') is image_frame:
                        idx = i
                        break
                if idx >= 0:
                    self.images.pop(idx)
            except Exception:
                pass

            # 重新排布网格并刷新预览索引绑定
            self._reflow_grid()
        except Exception as e:
            logger.error(f"打回图片失败: {e}")

    def _reflow_grid(self):
        """根据当前self.images重排网格并刷新点击预览的索引绑定"""
        try:
            # 清空布局中的所有控件位置（不销毁控件）
            # 逐个移除，再重新添加
            for i in range(self.image_layout.count()):
                item = self.image_layout.itemAt(i)
                w = item.widget() if item else None
                if w:
                    self.image_layout.removeWidget(w)

            # 按当前顺序重新添加并绑定预览索引
            for i, it in enumerate(self.images):
                row, col = divmod(i, 6)
                frame = it.get('frame')
                self.image_layout.addWidget(frame, row, col)
                img_label = it.get('image_label')
                if isinstance(img_label, QLabel):
                    img_label.mousePressEvent = lambda event, idx=i: self.show_image_preview(idx)
        except Exception as e:
            logger.warning(f"重排网格失败: {e}")
    
    def show_image_preview(self, start_index:int):
        """显示图片预览弹窗（支持上一张/下一张循环浏览）"""
        try:
            # 在日志中记录点击的索引和图片基本信息，便于崩溃分析
            meta = {}
            if 0 <= start_index < len(self.images):
                item = self.images[start_index]
                meta = {
                    'filename': item.get('filename'),
                    'prompt': (item.get('prompt') or '')[:80],
                    'has_data': bool(item.get('image_data')),
                    'save_path': item.get('save_path')
                }
            logger.info(f"预览图片点击: index={start_index}, meta={meta}")

            dialog = GeneratedImagePreviewDialog(self.images, start_index, self)
            dialog.exec()
        except Exception as e:
            # 使用logger记录完整异常信息
            logger.exception(f"显示图片预览失败: {e}")

    def save_image_as(self, image_data, data_dict):
        """手动保存图片到指定位置"""
        try:
            # 优先使用filename作为文件名
            if 'filename' in data_dict and data_dict['filename']:
                suggested_filename = data_dict['filename']
                # 确保文件名有扩展名，改为.jpg
                base_filename, _ = os.path.splitext(suggested_filename)
                suggested_filename = f"{base_filename}.jpg"
            else:
                # 如果没有filename，则使用prompt生成文件名
                prompt_prefix = data_dict.get('prompt', '')[:30]
                safe_prefix = re.sub(r'[^\w\-.]', '_', prompt_prefix)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                suggested_filename = f"{safe_prefix}_{timestamp}.jpg"
            
            # 获取上次另存为的路径
            last_save_path = self.config_manager.get_image_last_save_path()
            full_suggested_path = os.path.join(last_save_path, suggested_filename)
            
            # 打开文件保存对话框
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存图片",
                full_suggested_path,
                "JPEG Images (*.jpg);;PNG Images (*.png)"
            )
            
            if file_path:
                # 使用PIL处理图片
                img = Image.open(BytesIO(image_data))
                
                # 根据自动切图复选框状态决定是否resize
                if self.parent_widget and hasattr(self.parent_widget, 'auto_crop_checkbox') and self.parent_widget.auto_crop_checkbox.isChecked():
                    try:
                        tw = int(self.parent_widget.width_spin.value())
                        th = int(self.parent_widget.height_spin.value())
                    except Exception:
                        tw, th = 720, 720
                    sw, sh = img.size
                    if sw > 0 and sh > 0 and tw > 0 and th > 0:
                        s = max(tw / sw, th / sh)
                        nw = max(1, int(round(sw * s)))
                        nh = max(1, int(round(sh * s)))
                        tmp = img.resize((nw, nh), Image.Resampling.LANCZOS)
                        l = max(0, (nw - tw) // 2)
                        t = max(0, (nh - th) // 2)
                        r = l + tw
                        b = t + th
                        resized_img = tmp.crop((l, t, r, b))
                    else:
                        resized_img = img
                else:
                    # 不进行resize，使用原始图片
                    resized_img = img
                
                # Convert to RGB mode for JPEG saving
                if resized_img.mode != 'RGB':
                    resized_img = resized_img.convert('RGB')
                
                # 根据文件扩展名保存
                if file_path.lower().endswith('.jpg') or file_path.lower().endswith('.jpeg'):
                    resized_img.save(file_path, 'JPEG', quality=85)
                else:
                    # 如果选择PNG格式，保持原有逻辑
                    resized_img.save(file_path, 'PNG')
                
                # 保存成功后更新配置的另存为路径
                self.config_manager.set_image_last_save_path(file_path)
                try:
                    print(f"[另存为] 本地文件名: {os.path.basename(file_path)}")
                except Exception:
                    pass
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存图片失败: {str(e)}")

    def clear_images(self):
        """清空所有图片"""
        # 清空图像容器中的所有子组件
        for i in reversed(range(self.image_layout.count())):
            child = self.image_layout.itemAt(i).widget()
            if child:
                child.setParent(None)
        
        # 清空图像列表
        self.images.clear()
    
    def open_output_directory(self):
        """打开图片输出目录"""
        try:
            # 从配置文件获取输出目录
            output_dir = self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
            
            # 转换为绝对路径
            output_dir = os.path.abspath(output_dir)
            
            # 确保目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 使用系统默认程序打开目录
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                os.startfile(output_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", output_dir])
            else:  # Linux
                subprocess.run(["xdg-open", output_dir])
                
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法打开输出目录: {str(e)}")

    def show_prompt_context_menu(self, position):
        """显示提示词表格的右键菜单"""
        # 获取点击位置的索引
        index = self.prompt_table.indexAt(position)
        if not index.isValid():
            return
        
        # 获取选中行的数据
        row = index.row()
        if row >= len(self.prompt_data):
            return
        
        # 创建右键菜单
        context_menu = QMenu(self)
        
        # 添加复制动作
        copy_action = context_menu.addAction("复制")
        copy_action.triggered.connect(lambda: self.copy_prompt_with_style(row))
        
        # 显示菜单
        context_menu.exec(self.prompt_table.mapToGlobal(position))
    
    def copy_prompt_with_style(self, row):
        """复制提示词（包含style列内容）到剪贴板"""
        if row >= len(self.prompt_data):
            return
        
        data = self.prompt_data[row]
        prompt = data.get('prompt', '')
        style = data.get('style', '')
        
        # 拼接提示词和style
        if style:
            full_prompt = f"{prompt}, {style}"
        else:
            full_prompt = prompt
        
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(full_prompt)
        
        # 显示Toast提示（统一使用Toast，不再回退到状态标签）
        Toast.show_message("提示词已复制到剪贴板", self)

class Img2ImgPage(QWidget):
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._img_rows = []
        self._current_root = ''
        self.attachment_paths = []
        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        row1 = QHBoxLayout()
        self.select_input_btn = QPushButton("选择文件夹")
        self.select_input_btn.setFixedWidth(100)
        self.select_input_btn.clicked.connect(self.on_select_input_dir)
        row1.addWidget(self.select_input_btn)
        self.input_dir_display = QLineEdit()
        self.input_dir_display.setReadOnly(True)
        row1.addWidget(self.input_dir_display, 1)
        self.recursive_checkbox = QCheckBox("下钻子目录")
        self.recursive_checkbox.setChecked(True)
        self.recursive_checkbox.toggled.connect(self.on_recursive_changed)
        row1.addWidget(self.recursive_checkbox)
        left_layout.addLayout(row1)

        self.img_table = QTableWidget()
        self.img_table.setColumnCount(5)
        self.img_table.setHorizontalHeaderLabels(["选择", "id", "filename", "width", "height"])
        hdr = self.img_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.img_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        left_layout.addWidget(self.img_table)

        self.addon_prompt_input = QPlainTextEdit()
        self.addon_prompt_input.setPlaceholderText("请输入您的公用提示词")
        self.addon_prompt_input.setPlainText(BATCH_CREATE_IMAGE_TO_IMAGE)
        self.addon_prompt_input.setFixedHeight(120)
        left_layout.addWidget(self.addon_prompt_input)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        panel = QWidget()
        panel.setMaximumHeight(105)
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(5, 5, 5, 5)
        p_layout.setSpacing(5)

        main_controls_layout = QHBoxLayout()
        main_controls_layout.setSpacing(10)

        first_group = QGroupBox()
        fg_layout = QVBoxLayout(first_group)
        fg_layout.setContentsMargins(5, 5, 5, 5)
        dir_row = QHBoxLayout()
        self.config_dir_btn = QPushButton("输出目录")
        self.config_dir_btn.clicked.connect(self.on_config_output_dir)
        dir_row.addWidget(self.config_dir_btn)
        self.output_dir_display = QLineEdit()
        self.output_dir_display.setReadOnly(True)
        dir_row.addWidget(self.output_dir_display, 1)
        self.open_dir_btn = QPushButton("打开目录")
        self.open_dir_btn.setEnabled(False)
        self.open_dir_btn.clicked.connect(self.on_open_output_dir)
        dir_row.addWidget(self.open_dir_btn)
        fg_layout.addLayout(dir_row)
        init_out = self.config_manager.ensure_img2img_output_directory()

        self.output_dir_display.setText(os.path.abspath(init_out))
        self.open_dir_btn.setEnabled(bool(init_out))

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gpt-4o-image-vip", "sora_image"])
        model_row.addWidget(self.model_combo)
        self.batch_generate_btn = QPushButton("批量生成")
        self.batch_generate_btn.clicked.connect(self.on_batch_generate_clicked)
        self.batch_generate_btn.setMinimumWidth(120)
        model_row.addWidget(self.batch_generate_btn)
        fg_layout.addLayout(model_row)
        main_controls_layout.addWidget(first_group, 1)

        third_group = QGroupBox()
        tg_layout = QHBoxLayout(third_group)
        tg_layout.setContentsMargins(5, 5, 5, 5)
        tg_layout.setSpacing(5)
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("请输入单个提示词")
        self.prompt_input.setMaximumHeight(120)
        self.prompt_input.setAcceptRichText(False)
        tg_layout.addWidget(self.prompt_input, 3)
        buttons_layout = QVBoxLayout()
        single_row = QHBoxLayout()
        self.generate_btn = QPushButton("单次生成")
        self.generate_btn.clicked.connect(self.on_generate_single_clicked)
        single_row.addWidget(self.generate_btn)
        self.num_images_spin = QSpinBox()
        self.num_images_spin.setRange(1, 4)
        self.num_images_spin.setValue(1)
        self.num_images_spin.setToolTip("单次生成的图片数量 (1-4)")
        self.num_images_spin.setFixedWidth(40)
        single_row.addWidget(self.num_images_spin)
        buttons_layout.addLayout(single_row)
        attach_row = QHBoxLayout()
        self.upload_attachment_btn = QPushButton("上传附件")
        self.upload_attachment_btn.clicked.connect(self.upload_attachments)
        attach_row.addWidget(self.upload_attachment_btn)
        self.view_attachment_btn = QPushButton("查看附件")
        self.view_attachment_btn.clicked.connect(self.view_attachments)
        attach_row.addWidget(self.view_attachment_btn)
        buttons_layout.addLayout(attach_row)
        tg_layout.addLayout(buttons_layout, 1)
        main_controls_layout.addWidget(third_group, 3)

        fourth_group = QGroupBox()
        fg2_layout = QVBoxLayout(fourth_group)
        fg2_layout.setContentsMargins(5, 5, 5, 5)
        fg2_layout.setSpacing(3)
        two_cols = QHBoxLayout()
        right_col = QVBoxLayout()
        self.watermark_checkbox = QCheckBox("水印")
        self.watermark_checkbox.setChecked(True)
        right_col.addWidget(self.watermark_checkbox)
        self.auto_crop_checkbox = QCheckBox("切图")
        self.auto_crop_checkbox.setChecked(True)
        right_col.addWidget(self.auto_crop_checkbox)
        two_cols.addLayout(right_col)
        dims_col = QVBoxLayout()
        w_row = QHBoxLayout()
        w_row.addWidget(QLabel("宽:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 1536)
        self.width_spin.setValue(720)
        self.width_spin.setFixedWidth(40)
        self.width_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        w_row.addWidget(self.width_spin)
        dims_col.addLayout(w_row)
        h_row = QHBoxLayout()
        h_row.addWidget(QLabel("高:"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 1536)
        self.height_spin.setValue(720)
        self.height_spin.setFixedWidth(40)
        self.height_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        h_row.addWidget(self.height_spin)
        dims_col.addLayout(h_row)
        two_cols.addLayout(dims_col)
        fg2_layout.addLayout(two_cols)
        main_controls_layout.addWidget(fourth_group, 0)

        p_layout.addLayout(main_controls_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(15)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #ccc; border-radius: 3px; text-align: center; background-color: #f0f0f0; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 2px; }
        """)
        ps_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: white;")
        self.status_label.setMaximumHeight(15)
        ps_layout.addWidget(self.status_label, 1)
        ps_layout.addWidget(self.progress_bar, 8)
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.setMaximumWidth(80)
        self.clear_btn.clicked.connect(self.on_clear_images)
        ps_layout.addWidget(self.clear_btn, 1)
        p_layout.addLayout(ps_layout)

        right_layout.addWidget(panel)
        self.image_display = ImageDisplayWidget(self.config_manager, self)
        right_layout.addWidget(self.image_display)

        splitter.addWidget(right)
        splitter.setSizes([150, 450])

    def on_select_input_dir(self):
        last_path = self.config_manager.ensure_img2img_last_open_path()
        directory = QFileDialog.getExistingDirectory(self, "选择文件夹", last_path)
        if directory:
            self.image_display.clear_images()
            absdir = os.path.abspath(directory)
            self.input_dir_display.setText(absdir)
            self.config_manager.set_img2img_last_open_path(absdir)
            print(f"[图生图] 已选择输入目录: {absdir}")
            self.populate_table(absdir, self.recursive_checkbox.isChecked())
            outdir = (self.output_dir_display.text() or '').strip()
            if outdir:
                self._preload_existing_outputs(outdir)

    def on_recursive_changed(self, checked):
        root = self.input_dir_display.text().strip()
        if root:
            self.image_display.clear_images()
            self.populate_table(root, bool(checked))
            outdir = (self.output_dir_display.text() or '').strip()
            if outdir:
                self._preload_existing_outputs(outdir)

    def populate_table(self, root: str, recursive: bool):
        self._current_root = str(root)
        exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
        files = []
        if recursive:
            for dirpath, _, filenames in os.walk(root):
                for name in filenames:
                    ext = os.path.splitext(name)[1].lower()
                    if ext in exts:
                        files.append(os.path.join(dirpath, name))
        else:
            for name in os.listdir(root):
                p = os.path.join(root, name)
                if os.path.isfile(p):
                    ext = os.path.splitext(name)[1].lower()
                    if ext in exts:
                        files.append(p)
        self.img_table.setRowCount(len(files))
        self._img_rows = []
        for i, path in enumerate(files):
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Checked)
            self.img_table.setItem(i, 0, chk)
            id_item = QTableWidgetItem(str(i + 1))
            self.img_table.setItem(i, 1, id_item)
            fn_item = QTableWidgetItem(os.path.basename(path))
            self.img_table.setItem(i, 2, fn_item)
            rel = os.path.relpath(path, root).replace('\\', '/')
            try:
                with Image.open(path) as im:
                    w, h = im.size
            except Exception:
                w, h = 0, 0
            self.img_table.setItem(i, 3, QTableWidgetItem(str(w)))
            self.img_table.setItem(i, 4, QTableWidgetItem(str(h)))
            self._img_rows.append({
                'abs': path,
                'rel': rel,
                'w': w,
                'h': h,
            })
        print(f"[图生图] 已加载文件: {len(files)}")

    def on_batch_generate_clicked(self):
        rows = self.img_table.rowCount()
        selected_indices = []
        for i in range(rows):
            chk_item = self.img_table.item(i, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                selected_indices.append(i)
        if len(selected_indices) == 0:
            Toast.info("没有可生成的图片", self)
            return
        outdir = (self.output_dir_display.text() or '').strip()
        if not outdir:
            Toast.info("没有选择输出目录", self)
            return
        try:
            os.makedirs(outdir, exist_ok=True)
        except Exception:
            pass
        prompt_base = self.addon_prompt_input.toPlainText().strip()
        tasks = []
        for idx in selected_indices:
            row = self._img_rows[idx] if idx < len(self._img_rows) else None
            if not isinstance(row, dict):
                continue
            abs_path = row.get('abs')
            rel_path = row.get('rel')
            w0 = int(row.get('w') or 0)
            h0 = int(row.get('h') or 0)
            if not abs_path or not rel_path:
                continue
            if w0 > h0:
                dims_phrase = "生成的图片宽1536，高1024"
            elif w0 < h0:
                dims_phrase = "生成的图片宽1024，高1536"
            else:
                dims_phrase = "生成的图片宽1024，高1024"
            prompt_row = prompt_base + (f"\n{dims_phrase}" if dims_phrase else "")
            tasks.append({
                'abs': abs_path,
                'rel': rel_path,
                'prompt': prompt_row,
                'outdir': outdir,
                'crop_w': w0,
                'crop_h': h0
            })
        if not tasks:
            Toast.info("没有可生成的图片", self)
            return
        self.batch_generate_btn.setText("中止生成")
        self.batch_generate_btn.clicked.disconnect(self.on_batch_generate_clicked)
        self.batch_generate_btn.clicked.connect(self.on_abort_batch_clicked)
        def worker_fn(t):
            try:
                api_token = self.config_manager.get_wuyun_token()
                if not api_token:
                    return {'status': 'error', 'task': t, 'error': '缺少API密钥'}
                url = "https://yunwu.ai/v1/chat/completions"
                content = [
                    {"type": "text", "text": t.get('prompt', '')},
                    {"type": "image_url", "image_url": {"url": self._encode_image_to_data_url(t.get('abs'))}}
                ]
                try:
                    print(f"[图生图] 调用接口: 源文件={os.path.basename(t.get('abs') or '')}, 路径={t.get('abs')}")
                    print(f"[图生图] 调用接口提示词: {t.get('prompt','')}")
                except Exception:
                    pass
                payload_obj = {
                    "model": self.model_combo.currentText(),
                    "size": "1024x1024",
                    "messages": [{"role": "user", "content": content}]
                }
                headers = {
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json"
                }
                response = requests.post(url, headers=headers, data=json.dumps(payload_obj, ensure_ascii=False), timeout=400)
                full_body = None
                try:
                    full_body = response.text
                    response_json = response.json()
                except Exception:
                    response_json = None
                chosen_url = None
                if isinstance(response_json, dict):
                    urls = self._extract_image_urls(response_json)
                    if urls:
                        chosen_url = urls[0]
                if not chosen_url:
                    chosen_url = self._extract_image_url_response(response)
                if not chosen_url:
                    return {"status": "error", "error": "未提取到图片URL", "task": t, "error_full_body": full_body}
                img_resp = requests.get(chosen_url, headers={"Accept": "image/*"}, timeout=400)
                img_resp.raise_for_status()
                img_bytes = img_resp.content
                return {"status": "ok", "task": t, "image_bytes": img_bytes}
            except Exception as e:
                return {"status": "error", "task": t, "error": str(e)}
        runner = ThreadPoolRunner(tasks, worker_fn, max_workers=10)
        self._runner = runner
        try:
            self.batch_generate_btn.setEnabled(False)
            self.select_input_btn.setEnabled(False)
            self.recursive_checkbox.setEnabled(False)
            self.config_dir_btn.setEnabled(False)
            self.open_dir_btn.setEnabled(False)
            self.prompt_input.setEnabled(False)
            self.addon_prompt_input.setEnabled(False)
            self.watermark_checkbox.setEnabled(False)
            self.auto_crop_checkbox.setEnabled(False)
            self.width_spin.setEnabled(False)
            self.height_spin.setEnabled(False)
        except Exception:
            pass
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"生成中… （0/{len(tasks)})")
        def on_item_done(res):
            try:
                if isinstance(res, dict) and res.get('status') == 'ok':
                    t = res.get('task', {})
                    rel = t.get('rel')
                    abs_path = t.get('abs')
                    outdir_local = t.get('outdir')
                    prompt_local = t.get('prompt')
                    img_bytes = res.get('image_bytes')
                    cw = t.get('crop_w') if isinstance(t, dict) else None
                    ch = t.get('crop_h') if isinstance(t, dict) else None
                    save_path, final_bytes = self._save_generated_image(img_bytes, outdir_local, rel, target_w=cw, target_h=ch)
                    try:
                        print(f"[图生图] 已保存: {os.path.abspath(save_path)}")
                    except Exception:
                        pass
                    dd = {
                        'prompt': prompt_local,
                        'filename': rel,
                        'is_batch': True,
                        'is_xlsx_generated': False
                    }
                    self.image_display.add_image(dd, final_bytes, save_path)
                    self._mark_img_row_success(rel)
                else:
                    t = res.get('task', {}) if isinstance(res, dict) else {}
                    rel = t.get('rel')
                    err = res.get('error') if isinstance(res, dict) else '生成失败'
                    full_body = res.get('error_full_body') if isinstance(res, dict) else None
                    self._show_error_dialog(err, full_body)
                    if rel:
                        self._mark_img_row_failed(rel)
            except Exception:
                pass
        def on_item_failed(info):
            try:
                t = info.get('task', {}) if isinstance(info, dict) else {}
                rel = t.get('rel')
                msg = info.get('error') if isinstance(info, dict) else '生成失败'
                self._show_error_dialog(msg, None)
                if rel:
                    self._mark_img_row_failed(rel)
            except Exception:
                pass
        def on_progress(cur, total, _):
            try:
                self.status_label.setText(f"生成中… （{cur}/{total})")
            except Exception:
                pass
        def on_finished():
            try:
                self.batch_generate_btn.setEnabled(True)
                self.select_input_btn.setEnabled(True)
                self.recursive_checkbox.setEnabled(True)
                self.config_dir_btn.setEnabled(True)
                self.open_dir_btn.setEnabled(True)
                self.prompt_input.setEnabled(True)
                self.addon_prompt_input.setEnabled(True)
                self.watermark_checkbox.setEnabled(True)
                self.auto_crop_checkbox.setEnabled(True)
                self.width_spin.setEnabled(True)
                self.height_spin.setEnabled(True)
            except Exception:
                pass
            self.batch_generate_btn.setText("批量生成")
            self.batch_generate_btn.clicked.disconnect(self.on_abort_batch_clicked)
            self.batch_generate_btn.clicked.connect(self.on_batch_generate_clicked)
            self.progress_bar.setVisible(False)
            self.status_label.setText("就绪")
        def on_item_started(t):
            try:
                rel = t.get('rel') if isinstance(t, dict) else None
                if rel:
                    self._mark_img_row_in_progress(rel)
            except Exception:
                pass
        runner.item_started.connect(on_item_started)
        runner.item_done.connect(on_item_done)
        runner.item_failed.connect(on_item_failed)
        runner.progress_updated.connect(on_progress)
        runner.finished.connect(on_finished)
        runner.start()

    def on_abort_batch_clicked(self):
        if hasattr(self, '_runner') and self._runner:
            print("[图生图] 中止批量生成，正在清空线程池...")
            self._runner.stop()
            self._runner = None
        self.batch_generate_btn.setText("批量生成")
        self.batch_generate_btn.clicked.disconnect(self.on_abort_batch_clicked)
        self.batch_generate_btn.clicked.connect(self.on_batch_generate_clicked)
        self.batch_generate_btn.setEnabled(True)
        self.select_input_btn.setEnabled(True)
        self.recursive_checkbox.setEnabled(True)
        self.config_dir_btn.setEnabled(True)
        self.open_dir_btn.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.addon_prompt_input.setEnabled(True)
        self.watermark_checkbox.setEnabled(True)
        self.auto_crop_checkbox.setEnabled(True)
        self.width_spin.setEnabled(True)
        self.height_spin.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("已中止")

    def _save_generated_image(self, img_bytes: bytes, outdir: str, rel_path: str, target_w: int | None = None, target_h: int | None = None) -> tuple[str, bytes]:
        try:
            parts = re.split(r"[\\/]+", str(rel_path).strip())
            parts = [re.sub(r'[<>:\\"\|\?\*]', '_', p).strip() for p in parts if p and p not in ['.', '..']]
            last = parts[-1] if parts else ''
            base_last, _ = os.path.splitext(last)
            last = f"{base_last}.jpg" if base_last else f"{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            rel_save = os.path.join(*parts[:-1], last) if len(parts) > 1 else last
            save_path = os.path.join(outdir or '.', rel_save)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            img = Image.open(BytesIO(img_bytes))
            if self.auto_crop_checkbox.isChecked():
                try:
                    if target_w and target_h and isinstance(target_w, int) and isinstance(target_h, int) and target_w > 0 and target_h > 0:
                        tw = int(target_w)
                        th = int(target_h)
                    else:
                        tw = int(self.width_spin.value())
                        th = int(self.height_spin.value())
                except Exception:
                    tw, th = 720, 720
                sw, sh = img.size
                if sw > 0 and sh > 0 and tw > 0 and th > 0:
                    s = max(tw / sw, th / sh)
                    nw = max(1, int(round(sw * s)))
                    nh = max(1, int(round(sh * s)))
                    tmp = img.resize((nw, nh), Image.Resampling.LANCZOS)
                    l = max(0, (nw - tw) // 2)
                    t0 = max(0, (nh - th) // 2)
                    r = l + tw
                    b = t0 + th
                    resized_img = tmp.crop((l, t0, r, b))
                else:
                    resized_img = img
            else:
                resized_img = img
            if resized_img.mode != 'RGB':
                resized_img = resized_img.convert('RGB')
            out_bytes = io.BytesIO()
            resized_img.save(out_bytes, format='JPEG', quality=85)
            final_bytes = out_bytes.getvalue()
            if self.watermark_checkbox.isChecked():
                final_bytes = add_watermark(final_bytes)
            with open(save_path, 'wb') as f:
                f.write(final_bytes)
            return save_path, final_bytes
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存图片失败: {str(e)}")
            fallback_path = os.path.join(outdir or '.', os.path.basename(rel_path) or f"{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
            return fallback_path, img_bytes

    def _mark_img_row_success(self, rel_path: str):
        try:
            row_idx = -1
            for i, r in enumerate(self._img_rows):
                if str(r.get('rel') or '') == str(rel_path or ''):
                    row_idx = i
                    break
            if row_idx >= 0:
                fn_item = self.img_table.item(row_idx, 2)
                if fn_item:
                    fn_item.setForeground(QColor('green'))
                chk_item = self.img_table.item(row_idx, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Unchecked)
        except Exception:
            pass

    def _mark_img_row_in_progress(self, rel_path: str):
        try:
            row_idx = -1
            for i, r in enumerate(self._img_rows):
                if str(r.get('rel') or '') == str(rel_path or ''):
                    row_idx = i
                    break
            if row_idx >= 0:
                fn_item = self.img_table.item(row_idx, 2)
                if fn_item:
                    fn_item.setForeground(QColor('orange'))
        except Exception:
            pass

    def _mark_img_row_failed(self, rel_path: str):
        try:
            row_idx = -1
            for i, r in enumerate(self._img_rows):
                if str(r.get('rel') or '') == str(rel_path or ''):
                    row_idx = i
                    break
            if row_idx >= 0:
                fn_item = self.img_table.item(row_idx, 2)
                if fn_item:
                    fn_item.setForeground(QColor('red'))
                    current_text = fn_item.text()
                    if not current_text.endswith("（生成失败）"):
                        fn_item.setText(current_text + "（生成失败）")
                chk_item = self.img_table.item(row_idx, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Checked)
        except Exception:
            pass

    def _mark_img_row_rejected(self, rel_path: str):
        try:
            row_idx = -1
            for i, r in enumerate(self._img_rows):
                if str(r.get('rel') or '') == str(rel_path or ''):
                    row_idx = i
                    break
            if row_idx >= 0:
                fn_item = self.img_table.item(row_idx, 2)
                if fn_item:
                    fn_item.setForeground(QColor('red'))
                    current_text = fn_item.text()
                    if not current_text.endswith("（被打回）"):
                        # 去除已有“生成失败”后缀，改为“被打回”
                        if current_text.endswith("（生成失败）"):
                            current_text = current_text[:-6]
                        fn_item.setText(current_text + "（被打回）")
                chk_item = self.img_table.item(row_idx, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Checked)
                print(f"[图生图] 左侧标记被打回: {rel_path}")
        except Exception:
            pass

    def _show_error_dialog(self, msg: str, full_body: str | None):
        try:
            body = full_body if full_body else (msg or "生成失败")
            dialog = ErrorResponseDialog("生成失败", body, parent=self)
            dialog.exec()
        except Exception:
            pass

    def mark_prompt_as_failed(self, failed_data_dict):
        try:
            rel = ''
            if isinstance(failed_data_dict, dict):
                rel = str(failed_data_dict.get('filename') or '').strip()
                is_rejected = bool(failed_data_dict.get('rejected'))
            if rel:
                if is_rejected:
                    self._mark_img_row_rejected(rel)
                else:
                    self._mark_img_row_failed(rel)
        except Exception:
            pass

    def mark_prompt_as_success(self, success_data_dict):
        try:
            rel = ''
            if isinstance(success_data_dict, dict):
                rel = str(success_data_dict.get('filename') or '').strip()
            if rel:
                self._mark_img_row_success(rel)
        except Exception:
            pass

    def on_config_output_dir(self):
        try:
            current_dir = self.config_manager.ensure_img2img_output_directory()
            directory = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
            if directory:
                self.image_display.clear_images()
                absdir = os.path.abspath(directory)
                self.output_dir_display.setText(absdir)
                self.open_dir_btn.setEnabled(True)
                self.config_manager.set_img2img_output_directory(absdir)
                print(f"[图生图] 输出目录: {absdir}")
                self._preload_existing_outputs(absdir)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"配置输出目录失败: {str(e)}")

    def on_open_output_dir(self):
        directory = self.output_dir_display.text().strip()
        if not directory:
            return
        directory = os.path.abspath(directory)
        os.makedirs(directory, exist_ok=True)
        if os.name == 'nt':
            os.startfile(directory)
        else:
            import subprocess, platform
            if platform.system() == "Darwin":
                subprocess.run(["open", directory])
            else:
                subprocess.run(["xdg-open", directory])
        print(f"[图生图] 已打开输出目录: {directory}")

    def _preload_existing_outputs(self, outdir: str):
        try:
            if not isinstance(self._img_rows, list) or not self._img_rows:
                return
            outdir = os.path.abspath(outdir or '.')
            count = 0
            for row in self._img_rows:
                rel = str(row.get('rel') or '').strip()
                if not rel:
                    continue
                parts = re.split(r"[\\/]+", rel)
                parts = [re.sub(r'[<>:\\"\|\?\*]', '_', p).strip() for p in parts if p and p not in ['.', '..']]
                last = parts[-1] if parts else ''
                base_last, _ = os.path.splitext(last)
                last_jpg = f"{base_last}.jpg" if base_last else ''
                rel_jpg = os.path.join(*parts[:-1], last_jpg) if len(parts) > 1 else last_jpg
                img_path = os.path.join(outdir, rel_jpg) if rel_jpg else None
                if img_path and os.path.isfile(img_path):
                    try:
                        with open(img_path, 'rb') as f:
                            img_bytes = f.read()
                        dd = {
                            'prompt': self.addon_prompt_input.toPlainText().strip(),
                            'filename': rel,
                            'is_batch': True,
                            'is_xlsx_generated': False
                        }
                        self.image_display.add_image(dd, img_bytes, img_path)
                        self._mark_img_row_success(rel)
                        count += 1
                    except Exception:
                        pass
            if count > 0:
                print(f"[图生图] 预加载已生成图片: {count} 项")
        except Exception as e:
            logger.error(f"预加载输出目录图片失败: {e}")

    def on_clear_images(self):
        self.image_display.clear_images()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        try:
            if hasattr(self, '_runner') and self._runner and self._runner.isRunning():
                self._runner.stop()
                self._runner.wait()
                print("图生图线程池已停止")
        except Exception:
            pass
        event.accept()

    def stop_all_tasks(self):
        try:
            if hasattr(self, '_runner') and self._runner and self._runner.isRunning():
                print("正在停止图生图线程池...")
                self._runner.stop()
                self._runner.wait()
        except Exception:
            pass
        try:
            if self.worker and self.worker.isRunning():
                print("正在停止图生图工作线程...")
                self.worker.stop()
                self.worker.wait()
        except Exception:
            pass

    def on_generate_single_clicked(self):
        text = self.prompt_input.toPlainText().strip()
        if not text:
            Toast.warning("请输入提示词", self)
            return
        if len(self.attachment_paths) == 0:
            Toast.warning("没有附件无法生图", self)
            return
        lines = text.splitlines()
        first = lines[0] if lines else ""
        rest = "\n".join(lines[1:]) if len(lines) > 1 else ""
        dims_phrase = ""
        try:
            if self.attachment_paths:
                p0 = self.attachment_paths[0]
                with Image.open(p0) as im0:
                    w0, h0 = im0.size
                if w0 > h0:
                    dims_phrase = "\"生成的图片宽1536，高1024\""
                elif w0 < h0:
                    dims_phrase = "\"生成的图片宽1024，高1536\""
                else:
                    dims_phrase = "\"生成的图片宽1024，高1024\""
        except Exception:
            dims_phrase = ""
        prompt = f"{first}, {CARTOON_STYLE_SUFFIX}" + (f"\n{rest}" if rest else "") + (f"\n{dims_phrase}" if dims_phrase else "")
        count = max(1, min(4, int(self.num_images_spin.value())))
        tasks = [{"prompt": prompt}] * count
        def worker_fn(t):
            try:
                api_token = self.config_manager.get_wuyun_token()
                if not api_token:
                    raise RuntimeError("缺少API密钥")
                url = "https://yunwu.ai/v1/chat/completions"
                base64_image_contents = [
                    {"type": "image_url", "image_url": {"url": self._encode_image_to_data_url(p)}}
                    for p in self.attachment_paths if p
                ]
                content = [{"type": "text", "text": t.get("prompt", "")} ] + base64_image_contents
                try:
                    for p in self.attachment_paths:
                        print(f"[图生图] 调用接口: 源文件={os.path.basename(p)}, 路径={p}")
                    print(f"[图生图] 调用接口提示词: {t.get('prompt','')}")
                except Exception:
                    pass
                payload_obj = {
                    "model": self.model_combo.currentText(),
                    "size": "1024x1024",
                    "messages": [{"role": "user", "content": content}]
                }
                headers = {
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json"
                }
                response = requests.post(url, headers=headers, data=json.dumps(payload_obj, ensure_ascii=False), timeout=400)
                try:
                    response_json = response.json()
                except Exception:
                    response_json = None
                full_body = None
                try:
                    full_body = response.text
                except Exception:
                    pass
                chosen_url = None
                if isinstance(response_json, dict):
                    urls = self._extract_image_urls(response_json)
                    if urls:
                        chosen_url = urls[0]
                if not chosen_url:
                    chosen_url = self._extract_image_url_response(response)
                if not chosen_url:
                    return {"status": "error", "error": "未从响应中提取到图片URL", "task": t, "error_full_body": full_body}
                img_resp = requests.get(chosen_url, headers={"Accept": "image/*"}, timeout=400)
                img_resp.raise_for_status()
                img_bytes = img_resp.content
                return {"status": "ok", "data_dict": {"prompt": t.get("prompt", ""), "is_batch": False}, "image_bytes": img_bytes}
            except Exception as e:
                return {"status": "error", "error": str(e), "task": t, "error_full_body": None}
        runner = ThreadPoolRunner(tasks, worker_fn, max_workers=10)
        self._runner = runner
        try:
            self.generate_btn.setEnabled(False)
            self.config_dir_btn.setEnabled(False)
            self.open_dir_btn.setEnabled(False)
            self.num_images_spin.setEnabled(False)
            self.prompt_input.setEnabled(False)
            self.upload_attachment_btn.setEnabled(False)
            self.view_attachment_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.model_combo.setEnabled(False)
            self.watermark_checkbox.setEnabled(False)
            self.auto_crop_checkbox.setEnabled(False)
            self.width_spin.setEnabled(False)
            self.height_spin.setEnabled(False)
        except Exception:
            pass
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"生成中… （0/{len(tasks)})")
        def on_item_done(res):
            try:
                if isinstance(res, dict) and res.get("status") == "ok" and res.get("image_bytes"):
                    dd = res.get("data_dict", {})
                    outdir = (self.output_dir_display.text() or '').strip() or self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
                    try:
                        os.makedirs(outdir, exist_ok=True)
                    except Exception:
                        pass
                    try:
                        ts = datetime.now().strftime('%Y%m%d%H%M%S')
                        prefix = re.sub(r'[^\w\-.]', '_', (dd.get('prompt','')[:30] or 'single'))
                        rel = os.path.join('single', f"{prefix}_{ts}.jpg")
                    except Exception:
                        rel = os.path.join('single', f"{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
                    save_path, final_bytes = self._save_generated_image(res.get("image_bytes"), outdir, rel)
                    try:
                        print(f"[图生图] 已保存: {os.path.abspath(save_path)}")
                    except Exception:
                        pass
                    self.image_display.add_image(dd, final_bytes, save_path)
                else:
                    err = res.get("error") if isinstance(res, dict) else "生成失败"
                    body = res.get("error_full_body") if isinstance(res, dict) else None
                    self._show_error_dialog(err or "生成失败", body)
            except Exception:
                pass
        def on_item_failed(info):
            try:
                msg = info.get("error") if isinstance(info, dict) else "生成失败"
                body = info.get("error_full_body") if isinstance(info, dict) else None
                self._show_error_dialog(msg, body)
            except Exception:
                pass
        def on_progress(cur, total, _):
            try:
                self.status_label.setText(f"生成中… （{cur}/{total})")
            except Exception:
                pass
        def on_finished():
            try:
                self.generate_btn.setEnabled(True)
                self.config_dir_btn.setEnabled(True)
                self.open_dir_btn.setEnabled(True)
                self.num_images_spin.setEnabled(True)
                self.prompt_input.setEnabled(True)
                self.upload_attachment_btn.setEnabled(True)
                self.view_attachment_btn.setEnabled(True)
                self.clear_btn.setEnabled(True)
                self.model_combo.setEnabled(True)
                self.watermark_checkbox.setEnabled(True)
                self.auto_crop_checkbox.setEnabled(True)
                self.width_spin.setEnabled(True)
                self.height_spin.setEnabled(True)
            except Exception:
                pass
            self.progress_bar.setVisible(False)
            self.status_label.setText("就绪")
        runner.item_done.connect(on_item_done)
        runner.item_failed.connect(on_item_failed)
        runner.progress_updated.connect(on_progress)
        runner.finished.connect(on_finished)
        runner.start()

    def _encode_image_to_data_url(self, file_path: str) -> str:
        try:
            ext = os.path.splitext(file_path)[1].lower()
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".bmp": "image/bmp"
            }.get(ext, "application/octet-stream")
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return ""

    def _extract_image_url_response(self, response):
        try:
            response.raise_for_status()
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"]
            if isinstance(content, str):
                m = re.search(r"!\[.*?\]\((.*?)\)", content)
                if m:
                    return m.group(1)
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "output_image":
                        url = item.get("image_url", {}).get("url")
                        if url:
                            return url
                joined = " ".join([it.get("text", "") if isinstance(it, dict) else str(it) for it in content])
                m = re.search(r"!\[.*?\]\((.*?)\)", joined)
                if m:
                    return m.group(1)
        except KeyboardInterrupt:
            print("[图生图] 请求已被用户中止")
            return None
        except Exception:
            return None
        return None

    def _extract_image_urls(self, response_json):
        urls = []
        try:
            choices = response_json.get("choices", [])
            for choice in choices:
                content = choice.get("message", {}).get("content")
                if isinstance(content, str):
                    for m in re.finditer(r"!\[.*?\]\((.*?)\)", content):
                        urls.append(m.group(1))
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "output_image":
                            url = item.get("image_url", {}).get("url")
                            if url:
                                urls.append(url)
                    joined = " ".join([it.get("text", "") if isinstance(it, dict) else str(it) for it in content])
                    for m in re.finditer(r"!\[.*?\]\((.*?)\)", joined):
                        urls.append(m.group(1))
        except Exception:
            pass
        seen = set()
        return [u for u in urls if not (u in seen or seen.add(u))]

    def upload_attachments(self):
        last_path = self.config_manager.get_reference_image_directory()
        files, _ = QFileDialog.getOpenFileNames(self, "选择附件图片", last_path, "Images (*.png *.jpg *.jpeg *.webp)")
        if not files:
            return
        try:
            first_dir = os.path.dirname(files[0]) if files else ""
            if first_dir:
                self.config_manager.set_reference_image_directory(first_dir)
        except Exception:
            pass
        cache_dir = self._get_cache_image_dir()
        appended = 0
        for src in files:
            try:
                fname = os.path.basename(src)
                dst = os.path.join(cache_dir, fname)
                shutil.copy2(src, dst)
                self.attachment_paths.append(dst)
                appended += 1
            except Exception:
                pass
        if appended > 0:
            Toast.success(f"已添加 {appended} 个附件到缓存", self)
            self.update_view_attachment_button_text()
        else:
            Toast.info("未添加任何附件", self)

    def view_attachments(self):
        try:
            dialog = AttachmentPreviewDialog(self.attachment_paths, parent=self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查看附件出错: {e}")

    def remove_attachment(self, path: str):
        try:
            if path in self.attachment_paths:
                self.attachment_paths.remove(path)
                Toast.info(f"已移除附件: {os.path.basename(path)}", self)
                self.update_view_attachment_button_text()
        except Exception:
            pass

    def clear_attachments(self):
        try:
            self.attachment_paths.clear()
            Toast.info("已清空所有附件", self)
            self.update_view_attachment_button_text()
        except Exception:
            pass

    def update_view_attachment_button_text(self):
        try:
            count = len(self.attachment_paths)
            base_text = "查看附件"
            text = base_text if count == 0 else f"{base_text} [{count}]"
            if hasattr(self, "view_attachment_btn") and self.view_attachment_btn:
                self.view_attachment_btn.setText(text)
        except Exception:
            pass

    def _get_cache_image_dir(self) -> str:
        try:
            duoki_editor_dir = Path(__file__).resolve().parents[2]
            cache_dir = duoki_editor_dir / "cache" / "image"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return str(cache_dir)
        except Exception:
            fallback = Path.cwd() / "duoki_editor" / "cache" / "image"
            fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback)

class ScaledImageLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_pm = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)

    def setPixmap(self, pm: QPixmap):
        self._orig_pm = pm
        self._update_scaled()

    def resizeEvent(self, event):
        self._update_scaled()
        return super().resizeEvent(event)

    def _update_scaled(self):
        try:
            if not self._orig_pm or self._orig_pm.isNull():
                return
            h = max(1, self.height())
            scaled = self._orig_pm.scaledToHeight(h, Qt.TransformationMode.SmoothTransformation)
            super().setPixmap(scaled)
        except Exception:
            pass

class AvatarImageGenerator(QWidget):
    image_downloaded_avatar = pyqtSignal(str)
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._img_rows = []
        self.attachment_paths = []
        self._labels_by_image_name = {}
        self.image_downloaded_avatar.connect(self._on_image_downloaded_avatar)
        self.init_ui_avatar()

    def init_ui_avatar(self):
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        row1 = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setFixedWidth(100)
        self.select_all_btn.clicked.connect(self.toggle_select_all_avatar)
        row1.addWidget(self.select_all_btn)
        row1.addStretch()
        left_layout.addLayout(row1)

        self.img_table = QTableWidget()
        self.img_table.setColumnCount(3)
        self.img_table.setHorizontalHeaderLabels(["选择", "character", "image"])
        hdr = self.img_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.img_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        left_layout.addWidget(self.img_table)

        try:
            self._init_auth_and_cache_avatar()
            self._populate_character_rows_avatar()
        except Exception:
            pass

        self.addon_prompt_input = QPlainTextEdit()
        self.addon_prompt_input.setPlaceholderText("请输入您的公用提示词")
        self.addon_prompt_input.setPlainText(BATCH_CREATE_AVATAR_IMAGE)
        self.addon_prompt_input.setFixedHeight(120)
        left_layout.addWidget(self.addon_prompt_input)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        panel = QWidget()
        panel.setMaximumHeight(105)
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(5, 5, 5, 5)
        p_layout.setSpacing(5)

        main_controls_layout = QHBoxLayout()
        main_controls_layout.setSpacing(10)

        prompt_group = QGroupBox()
        pg_layout = QVBoxLayout(prompt_group)
        pg_layout.setContentsMargins(5, 5, 5, 5)
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("请输入单个提示词")
        self.prompt_input.setMaximumHeight(120)
        self.prompt_input.setAcceptRichText(False)
        pg_layout.addWidget(self.prompt_input)
        main_controls_layout.addWidget(prompt_group, 6)

        first_group = QGroupBox()
        fg_layout = QVBoxLayout(first_group)
        fg_layout.setContentsMargins(5, 5, 5, 5)
        dir_row = QHBoxLayout()
        self.config_dir_btn = QPushButton("输出目录")
        self.config_dir_btn.clicked.connect(self.on_config_output_dir_avatar)
        dir_row.addWidget(self.config_dir_btn)
        self.output_dir_display = QLineEdit()
        self.output_dir_display.setReadOnly(True)
        dir_row.addWidget(self.output_dir_display, 1)
        self.open_dir_btn = QPushButton("打开目录")
        self.open_dir_btn.setEnabled(False)
        self.open_dir_btn.clicked.connect(self.on_open_output_dir_avatar)
        dir_row.addWidget(self.open_dir_btn)
        fg_layout.addLayout(dir_row)
        init_out = self.config_manager.ensure_avatar_output_directory()

        self.output_dir_display.setText(os.path.abspath(init_out))
        self.open_dir_btn.setEnabled(bool(init_out))

        model_row = QHBoxLayout()
        model_row.setSpacing(6)
        model_row.addWidget(QLabel("模型:"), 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gpt-4o-image-vip", "sora_image"])
        self.model_combo.setFixedWidth(120)
        model_row.addWidget(self.model_combo, 0)
        self.batch_generate_btn = QPushButton("批量生成")
        self.batch_generate_btn.clicked.connect(self.on_batch_generate_clicked_avatar)
        self.batch_generate_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        model_row.addWidget(self.batch_generate_btn, 1)
        fg_layout.addLayout(model_row)
        main_controls_layout.addWidget(first_group, 3)

        third_group = QGroupBox()
        tg_layout = QHBoxLayout(third_group)
        tg_layout.setContentsMargins(5, 5, 5, 5)
        tg_layout.setSpacing(5)
        buttons_layout = QVBoxLayout()
        single_row = QHBoxLayout()
        self.generate_btn = QPushButton("单次生成")
        self.generate_btn.clicked.connect(self.on_generate_single_clicked_avatar)
        single_row.addWidget(self.generate_btn)
        self.num_images_spin = QSpinBox()
        self.num_images_spin.setRange(1, 4)
        self.num_images_spin.setValue(1)
        self.num_images_spin.setToolTip("单次生成的图片数量 (1-4)")
        self.num_images_spin.setFixedWidth(40)
        single_row.addWidget(self.num_images_spin)
        buttons_layout.addLayout(single_row)
        attach_row = QHBoxLayout()
        self.upload_attachment_btn = QPushButton("上传附件")
        self.upload_attachment_btn.clicked.connect(self.upload_attachments_avatar)
        attach_row.addWidget(self.upload_attachment_btn)
        self.view_attachment_btn = QPushButton("查看附件")
        self.view_attachment_btn.clicked.connect(self.view_attachments_avatar)
        attach_row.addWidget(self.view_attachment_btn)
        buttons_layout.addLayout(attach_row)
        tg_layout.addLayout(buttons_layout, 1)
        main_controls_layout.addWidget(third_group, 2)

        p_layout.addLayout(main_controls_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(15)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #ccc; border-radius: 3px; text-align: center; background-color: #f0f0f0; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 2px; }
        """)
        ps_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: white;")
        self.status_label.setMaximumHeight(15)
        ps_layout.addWidget(self.status_label, 1)
        ps_layout.addWidget(self.progress_bar, 8)
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.setMaximumWidth(80)
        self.clear_btn.clicked.connect(self.on_clear_images_avatar)
        ps_layout.addWidget(self.clear_btn, 1)
        p_layout.addLayout(ps_layout)

        right_layout.addWidget(panel)
        self.image_display = ImageDisplayWidget(self.config_manager, self)
        right_layout.addWidget(self.image_display)

        splitter.addWidget(right)
        splitter.setSizes([150, 450])

    def toggle_select_all_avatar(self):
        try:
            select_mode = (self.select_all_btn.text() == "全选")
            for i in range(self.img_table.rowCount()):
                chk_item = self.img_table.item(i, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Checked if select_mode else Qt.CheckState.Unchecked)
            self.select_all_btn.setText("取消全选" if select_mode else "全选")
        except Exception:
            pass

    def _init_auth_and_cache_avatar(self):
        from duoki_editor.core.auth_manager import AuthManager
        self.auth_manager = getattr(self, 'auth_manager', None) or AuthManager()
        try:
            self.auth_manager.load_auth_data()
        except Exception:
            pass
        self._image_cache_dir = self._get_cache_image_dir_avatar()

    def _populate_character_rows_avatar(self):
        from duoki_editor.utils.constants_loader import get_npc_id_map_3
        mapping = get_npc_id_map_3()
        keys = list(mapping.keys())
        self.img_table.setRowCount(0)
        self._img_rows = []
        for k in keys:
            v = str(mapping.get(k, '')).strip()
            image_name = f"{v}-image.png" if v else ""
            r = self.img_table.rowCount()
            self.img_table.insertRow(r)
            chk = QTableWidgetItem()
            chk.setFlags(chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.img_table.setItem(r, 0, chk)
            self.img_table.setItem(r, 1, QTableWidgetItem(str(k)))
            img_label = ScaledImageLabel("加载中…")
            self.img_table.setCellWidget(r, 2, img_label)
            self.img_table.setRowHeight(r, 64)
            self._img_rows.append({'character': k, 'value': v, 'image_name': image_name})
            if image_name:
                self._labels_by_image_name[image_name] = img_label
            # 延迟到首次点击“角色皮肤”页签后再触发下载

    def _get_cached_image_path_avatar(self, image_name: str) -> str:
        normalized = image_name.replace('/', os.sep).replace('\\', os.sep)
        path = os.path.join(self._image_cache_dir, normalized)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def _load_or_download_image_avatar(self, image_name: str, label: QLabel):
        cached = self._get_cached_image_path_avatar(image_name)
        if os.path.exists(cached):
            pm = QPixmap(cached)
            if not pm.isNull():
                label.setPixmap(pm)
                label.setText("")
                return
        base_url = "https://portal-test.qidianlingzhi.com:10199/client_resources/getFile?path=client/common/image/unit/"
        url = base_url + image_name
        import threading
        def download_worker():
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                cookie_header = ''
                if hasattr(self, 'auth_manager') and self.auth_manager:
                    cookie_header = self.auth_manager.get_cookie_header()
                if cookie_header:
                    headers['Cookie'] = cookie_header
                print(f"[角色皮肤] 下载图片: {url}")
                resp = requests.get(url, timeout=10, headers=headers, verify=False)
                resp.raise_for_status()
                with open(cached, 'wb') as f:
                    f.write(resp.content)
                print(f"[角色皮肤] 图片下载成功: {cached}")
                self.image_downloaded_avatar.emit(image_name)
            except Exception as e:
                print(f"[角色皮肤] 图片下载失败: {e}")
        t = threading.Thread(target=download_worker, daemon=True)
        t.start()

    def _on_image_downloaded_avatar(self, image_name: str):
        cached = self._get_cached_image_path_avatar(image_name)
        lbl = self._labels_by_image_name.get(image_name)
        if isinstance(lbl, QLabel) and os.path.exists(cached):
            pm = QPixmap(cached)
            if not pm.isNull():
                lbl.setPixmap(pm)
                lbl.setText("")
                try:
                    self.img_table.viewport().update()
                except Exception:
                    pass

    def _refresh_cached_images_avatar(self):
        try:
            print("[角色皮肤] 首次渲染：检查缓存并加载图片")
            for row in self._img_rows:
                image_name = row.get('image_name') or ''
                if not image_name:
                    continue
                cached = self._get_cached_image_path_avatar(image_name)
                if os.path.exists(cached):
                    lbl = self._labels_by_image_name.get(image_name)
                    if isinstance(lbl, QLabel):
                        pm = QPixmap(cached)
                        if not pm.isNull():
                            lbl.setPixmap(pm)
                            lbl.setText("")
                else:
                    lbl = self._labels_by_image_name.get(image_name)
                    if isinstance(lbl, QLabel):
                        self._load_or_download_image_avatar(image_name, lbl)
            try:
                self.img_table.viewport().update()
            except Exception:
                pass
        except Exception:
            pass

    def on_batch_generate_clicked_avatar(self):
        rows = self.img_table.rowCount()
        selected_indices = []
        for i in range(rows):
            chk_item = self.img_table.item(i, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                selected_indices.append(i)
        if len(selected_indices) == 0:
            Toast.info("没有可生成的图片", self)
            return
        outdir = (self.output_dir_display.text() or '').strip()
        if not outdir:
            Toast.info("没有选择输出目录", self)
            return
        try:
            os.makedirs(outdir, exist_ok=True)
        except Exception:
            pass
        raw = self.prompt_input.toPlainText().strip()
        idx_fw = raw.find("：")
        idx_hw = raw.find(":")
        pos = -1
        if idx_fw >= 0 and idx_hw >= 0:
            pos = idx_fw if (idx_fw <= idx_hw) else idx_hw
        elif idx_fw >= 0:
            pos = idx_fw
        elif idx_hw >= 0:
            pos = idx_hw
        cosplay = raw[:pos].strip() if pos >= 0 else raw.strip()
        addons = raw[pos+1:].strip() if pos >= 0 else ""
        prompt_row_template = BATCH_CREATE_AVATAR_IMAGE.replace("{cosplay}", cosplay).replace("{addons}", addons)
        tasks = []
        for idx in selected_indices:
            row = self._img_rows[idx] if idx < len(self._img_rows) else None
            if not isinstance(row, dict):
                continue
            image_name = str(row.get('image_name') or '').strip()
            if not image_name:
                continue
            abs_path = self._get_cached_image_path_avatar(image_name)
            if not os.path.exists(abs_path):
                # 若未下载则跳过此行
                print(f"[角色皮肤] 缓存未找到，跳过: {image_name}")
                continue
            rel_path = image_name
            print(f"[角色皮肤] 加入任务: {rel_path}、{abs_path}、{prompt_row_template}")
            tasks.append({
                'abs': abs_path,
                'rel': rel_path,
                'prompt': prompt_row_template,
                'outdir': outdir
            })
        if not tasks:
            Toast.info("没有可生成的图片", self)
            return
        self.batch_generate_btn.setText("中止生成")
        self.batch_generate_btn.clicked.disconnect(self.on_batch_generate_clicked_avatar)
        self.batch_generate_btn.clicked.connect(self.on_abort_batch_clicked_avatar)
        def worker_fn(t):
            try:
                api_token = self.config_manager.get_wuyun_token()
                if not api_token:
                    return {'status': 'error', 'task': t, 'error': '缺少API密钥'}
                url = "https://yunwu.ai/v1/chat/completions"
                content = [
                    {"type": "text", "text": t.get('prompt', '')},
                    {"type": "image_url", "image_url": {"url": self._encode_image_to_data_url_avatar(t.get('abs'))}}
                ]
                try:
                    print(f"[角色皮肤] 调用接口: 源文件={os.path.basename(t.get('abs') or '')}, 路径={t.get('abs')}")
                    print(f"[角色皮肤] 调用接口提示词: {t.get('prompt','')}")
                except Exception:
                    pass
                payload_obj = {
                    "model": self.model_combo.currentText(),
                    "size": "1024x1024",
                    "messages": [{"role": "user", "content": content}]
                }
                headers = {
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json"
                }
                response = requests.post(url, headers=headers, data=json.dumps(payload_obj, ensure_ascii=False), timeout=400)
                full_body = None
                try:
                    full_body = response.text
                    response_json = response.json()
                except Exception:
                    response_json = None
                chosen_url = None
                if isinstance(response_json, dict):
                    urls = self._extract_image_urls_avatar(response_json)
                    if urls:
                        chosen_url = urls[0]
                if not chosen_url:
                    chosen_url = self._extract_image_url_response_avatar(response)
                if not chosen_url:
                    return {"status": "error", "error": "未提取到图片URL", "task": t, "error_full_body": full_body}
                img_resp = requests.get(chosen_url, headers={"Accept": "image/*"}, timeout=400)
                img_resp.raise_for_status()
                img_bytes = img_resp.content
                return {"status": "ok", "task": t, "image_bytes": img_bytes}
            except Exception as e:
                return {"status": "error", "task": t, "error": str(e)}
        runner = ThreadPoolRunner(tasks, worker_fn, max_workers=10)
        self._runner = runner
        try:
            self.batch_generate_btn.setEnabled(False)
            self.config_dir_btn.setEnabled(False)
            self.open_dir_btn.setEnabled(False)
            self.prompt_input.setEnabled(False)
            self.addon_prompt_input.setEnabled(False)
        except Exception:
            pass
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"生成中… （0/{len(tasks)})")
        def on_item_done(res):
            try:
                if isinstance(res, dict) and res.get('status') == 'ok':
                    t = res.get('task', {})
                    rel = t.get('rel')
                    abs_path = t.get('abs')
                    outdir_local = t.get('outdir')
                    prompt_local = t.get('prompt')
                    img_bytes = res.get('image_bytes')
                    raw_prompt = self.prompt_input.toPlainText().strip()
                    safe_prompt = re.sub(r'[^\w\-\u4e00-\u9fff]+', '_', raw_prompt)[:50].strip('_') or 'prompt'
                    parts = re.split(r"[\\/]+", str(rel).strip())
                    parts = [p for p in parts if p and p not in ['.', '..']]
                    base = os.path.splitext(parts[-1] if parts else '')[0]
                    ts = datetime.now().strftime('%Y%m%d%H%M%S')
                    new_name = f"{base}_{safe_prompt}_{ts}.jpg"
                    new_rel = os.path.join(*parts[:-1], new_name) if len(parts) > 1 else new_name
                    save_path, final_bytes = self._save_generated_image_simple_avatar(img_bytes, outdir_local, new_rel)
                    try:
                        print(f"[角色皮肤] 已保存: {os.path.abspath(save_path)}")
                    except Exception:
                        pass
                    dd = {
                        'prompt': prompt_local,
                        'filename': rel,
                        'is_batch': True,
                        'is_xlsx_generated': False
                    }
                    self.image_display.add_image(dd, final_bytes, save_path)
                    self._mark_img_row_success_avatar(rel)
                else:
                    t = res.get('task', {}) if isinstance(res, dict) else {}
                    rel = t.get('rel')
                    err = res.get('error') if isinstance(res, dict) else '生成失败'
                    full_body = res.get('error_full_body') if isinstance(res, dict) else None
                    self._show_error_dialog_avatar(err, full_body)
                    if rel:
                        self._mark_img_row_failed_avatar(rel)
            except Exception:
                pass
        def on_item_failed(info):
            try:
                t = info.get('task', {}) if isinstance(info, dict) else {}
                rel = t.get('rel')
                msg = info.get('error') if isinstance(info, dict) else '生成失败'
                self._show_error_dialog_avatar(msg, None)
                if rel:
                    self._mark_img_row_failed_avatar(rel)
            except Exception:
                pass
        def on_progress(cur, total, _):
            try:
                self.status_label.setText(f"生成中… （{cur}/{total})")
            except Exception:
                pass
        def on_finished():
            try:
                self.batch_generate_btn.setEnabled(True)
                self.config_dir_btn.setEnabled(True)
                self.open_dir_btn.setEnabled(True)
                self.prompt_input.setEnabled(True)
                self.addon_prompt_input.setEnabled(True)
            except Exception:
                pass
            self.batch_generate_btn.setText("批量生成")
            self.batch_generate_btn.clicked.disconnect(self.on_abort_batch_clicked_avatar)
            self.batch_generate_btn.clicked.connect(self.on_batch_generate_clicked_avatar)
            self.progress_bar.setVisible(False)
            self.status_label.setText("就绪")
        runner.item_started.connect(lambda t: self._mark_img_row_in_progress_avatar(t.get('rel') if isinstance(t, dict) else None))
        runner.item_done.connect(on_item_done)
        runner.item_failed.connect(on_item_failed)
        runner.progress_updated.connect(on_progress)
        runner.finished.connect(on_finished)
        runner.start()

    def on_abort_batch_clicked_avatar(self):
        if hasattr(self, '_runner') and self._runner:
            print("[角色皮肤] 中止批量生成，正在清空线程池...")
            self._runner.stop()
            self._runner = None
        self.batch_generate_btn.setText("批量生成")
        try:
            self.batch_generate_btn.clicked.disconnect(self.on_abort_batch_clicked_avatar)
        except Exception:
            pass
        self.batch_generate_btn.clicked.connect(self.on_batch_generate_clicked_avatar)
        self.batch_generate_btn.setEnabled(True)
        self.config_dir_btn.setEnabled(True)
        self.open_dir_btn.setEnabled(True)
        self.prompt_input.setEnabled(True)
        self.addon_prompt_input.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("已中止")

    def _save_generated_image_simple_avatar(self, img_bytes: bytes, outdir: str, rel_path: str) -> tuple[str, bytes]:
        try:
            parts = re.split(r"[\\/]+", str(rel_path).strip())
            parts = [re.sub(r'[<>:\\"\|\?\*]', '_', p).strip() for p in parts if p and p not in ['.', '..']]
            last = parts[-1] if parts else ''
            base_last, _ = os.path.splitext(last)
            last = f"{base_last}.jpg" if base_last else f"{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
            rel_save = os.path.join(*parts[:-1], last) if len(parts) > 1 else last
            save_path = os.path.join(outdir or '.', rel_save)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            img = Image.open(BytesIO(img_bytes))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            out_bytes = io.BytesIO()
            img.save(out_bytes, format='JPEG', quality=85)
            final_bytes = out_bytes.getvalue()
            with open(save_path, 'wb') as f:
                f.write(final_bytes)
            return save_path, final_bytes
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存图片失败: {str(e)}")
            fallback_path = os.path.join(outdir or '.', os.path.basename(rel_path) or f"{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
            return fallback_path, img_bytes

    def _mark_img_row_success_avatar(self, rel_path: str):
        try:
            row_idx = -1
            for i, r in enumerate(self._img_rows):
                if str(r.get('rel') or '') == str(rel_path or ''):
                    row_idx = i
                    break
            if row_idx >= 0:
                item = self.img_table.item(row_idx, 1)
                if item:
                    item.setForeground(QColor('green'))
                chk_item = self.img_table.item(row_idx, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Unchecked)
        except Exception:
            pass

    def _mark_img_row_in_progress_avatar(self, rel_path: str | None):
        try:
            if not rel_path:
                return
            row_idx = -1
            for i, r in enumerate(self._img_rows):
                if str(r.get('rel') or '') == str(rel_path or ''):
                    row_idx = i
                    break
            if row_idx >= 0:
                item = self.img_table.item(row_idx, 1)
                if item:
                    item.setForeground(QColor('orange'))
        except Exception:
            pass

    def _mark_img_row_failed_avatar(self, rel_path: str):
        try:
            row_idx = -1
            for i, r in enumerate(self._img_rows):
                if str(r.get('rel') or '') == str(rel_path or ''):
                    row_idx = i
                    break
            if row_idx >= 0:
                item = self.img_table.item(row_idx, 1)
                if item:
                    item.setForeground(QColor('red'))
                    current_text = item.text()
                    if not current_text.endswith("（生成失败）"):
                        item.setText(current_text + "（生成失败）")
                chk_item = self.img_table.item(row_idx, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Checked)
        except Exception:
            pass

    def _show_error_dialog_avatar(self, msg: str, full_body: str | None):
        try:
            body = full_body if full_body else (msg or "生成失败")
            dialog = ErrorResponseDialog("生成失败", body, parent=self)
            dialog.exec()
        except Exception:
            pass

    def on_config_output_dir_avatar(self):
        try:
            current_dir = self.config_manager.ensure_avatar_output_directory()
            directory = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
            if directory:
                self.image_display.clear_images()
                absdir = os.path.abspath(directory)
                self.output_dir_display.setText(absdir)
                self.open_dir_btn.setEnabled(True)
                self.config_manager.set_avatar_output_directory(absdir)
                print(f"[角色皮肤] 输出目录: {absdir}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"配置输出目录失败: {str(e)}")

    def on_open_output_dir_avatar(self):
        directory = self.output_dir_display.text().strip()
        if not directory:
            return
        directory = os.path.abspath(directory)
        os.makedirs(directory, exist_ok=True)
        if os.name == 'nt':
            os.startfile(directory)
        else:
            import subprocess, platform
            if platform.system() == "Darwin":
                subprocess.run(["open", directory])
            else:
                subprocess.run(["xdg-open", directory])
        print(f"[角色皮肤] 已打开输出目录: {directory}")

    def on_clear_images_avatar(self):
        self.image_display.clear_images()

    def closeEvent(self, event):
        try:
            if hasattr(self, '_runner') and self._runner and self._runner.isRunning():
                self._runner.stop()
                self._runner.wait()
        except Exception:
            pass
        try:
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                self.worker.stop()
                self.worker.wait()
        except Exception:
            pass
        event.accept()

    def stop_all_tasks_avatar(self):
        try:
            if hasattr(self, '_runner') and self._runner and self._runner.isRunning():
                print("正在停止角色皮肤线程池...")
                self._runner.stop()
                self._runner.wait()
        except Exception:
            pass
        try:
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                print("正在停止角色皮肤工作线程...")
                self.worker.stop()
                self.worker.wait()
        except Exception:
            pass

    def on_generate_single_clicked_avatar(self):
        text = self.prompt_input.toPlainText().strip()
        if not text:
            Toast.warning("请输入提示词", self)
            return
        if len(self.attachment_paths) == 0:
            Toast.warning("没有附件无法生图", self)
            return
        raw = text
        idx_fw = raw.find("：")
        idx_hw = raw.find(":")
        pos = -1
        if idx_fw >= 0 and idx_hw >= 0:
            pos = idx_fw if (idx_fw <= idx_hw) else idx_hw
        elif idx_fw >= 0:
            pos = idx_fw
        elif idx_hw >= 0:
            pos = idx_hw
        cosplay = raw[:pos].strip() if pos >= 0 else raw.strip()
        addons = raw[pos+1:].strip() if pos >= 0 else ""
        prompt = BATCH_CREATE_AVATAR_IMAGE.replace("{cosplay}", cosplay).replace("{addons}", addons)
        count = max(1, min(4, int(self.num_images_spin.value())))
        tasks = [{"prompt": prompt}] * count
        def worker_fn(t):
            try:
                api_token = self.config_manager.get_wuyun_token()
                if not api_token:
                    raise RuntimeError("缺少API密钥")
                url = "https://yunwu.ai/v1/chat/completions"
                base64_image_contents = [
                    {"type": "image_url", "image_url": {"url": self._encode_image_to_data_url_avatar(p)}}
                    for p in self.attachment_paths if p
                ]
                content = [{"type": "text", "text": t.get("prompt", "")} ] + base64_image_contents
                try:
                    for p in self.attachment_paths:
                        print(f"[角色皮肤] 调用接口: 源文件={os.path.basename(p)}, 路径={p}")
                    print(f"[角色皮肤] 调用接口提示词: {t.get('prompt','')}")
                except Exception:
                    pass
                payload_obj = {
                    "model": self.model_combo.currentText(),
                    "size": "1024x1024",
                    "messages": [{"role": "user", "content": content}]
                }
                headers = {
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json"
                }
                response = requests.post(url, headers=headers, data=json.dumps(payload_obj, ensure_ascii=False), timeout=400)
                try:
                    response_json = response.json()
                except Exception:
                    response_json = None
                full_body = None
                try:
                    full_body = response.text
                except Exception:
                    pass
                chosen_url = None
                if isinstance(response_json, dict):
                    urls = self._extract_image_urls_avatar(response_json)
                    if urls:
                        chosen_url = urls[0]
                if not chosen_url:
                    chosen_url = self._extract_image_url_response_avatar(response)
                if not chosen_url:
                    return {"status": "error", "error": "未从响应中提取到图片URL", "task": t, "error_full_body": full_body}
                img_resp = requests.get(chosen_url, headers={"Accept": "image/*"}, timeout=400)
                img_resp.raise_for_status()
                img_bytes = img_resp.content
                return {"status": "ok", "data_dict": {"prompt": t.get("prompt", ""), "is_batch": False}, "image_bytes": img_bytes}
            except Exception as e:
                return {"status": "error", "error": str(e), "task": t, "error_full_body": None}
        runner = ThreadPoolRunner(tasks, worker_fn, max_workers=10)
        self._runner = runner
        try:
            self.generate_btn.setEnabled(False)
            self.config_dir_btn.setEnabled(False)
            self.open_dir_btn.setEnabled(False)
            self.num_images_spin.setEnabled(False)
            self.prompt_input.setEnabled(False)
            self.upload_attachment_btn.setEnabled(False)
            self.view_attachment_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.model_combo.setEnabled(False)
        except Exception:
            pass
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"生成中… （0/{len(tasks)})")
        def on_item_done(res):
            try:
                if isinstance(res, dict) and res.get("status") == "ok" and res.get("image_bytes"):
                    dd = res.get("data_dict", {})
                    outdir = (self.output_dir_display.text() or '').strip() or self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
                    try:
                        os.makedirs(outdir, exist_ok=True)
                    except Exception:
                        pass
                    ts = datetime.now().strftime('%Y%m%d%H%M%S')
                    raw_prompt = self.prompt_input.toPlainText().strip()
                    safe_prompt = re.sub(r'[^\w\-\u4e00-\u9fff]+', '_', raw_prompt)[:50].strip('_') or 'prompt'
                    orig_base = os.path.splitext(os.path.basename(self.attachment_paths[0]))[0] if self.attachment_paths else 'image'
                    new_name = f"{orig_base}_{safe_prompt}_{ts}.jpg"
                    rel = os.path.join('single', new_name)
                    save_path, final_bytes = self._save_generated_image_simple_avatar(res.get("image_bytes"), outdir, rel)
                    try:
                        print(f"[角色皮肤] 已保存: {os.path.abspath(save_path)}")
                    except Exception:
                        pass
                    self.image_display.add_image(dd, final_bytes, save_path)
                else:
                    err = res.get("error") if isinstance(res, dict) else "生成失败"
                    body = res.get("error_full_body") if isinstance(res, dict) else None
                    self._show_error_dialog_avatar(err or "生成失败", body)
            except Exception:
                pass
        def on_item_failed(info):
            try:
                msg = info.get("error") if isinstance(info, dict) else "生成失败"
                body = info.get("error_full_body") if isinstance(info, dict) else None
                self._show_error_dialog_avatar(msg, body)
            except Exception:
                pass
        def on_progress(cur, total, _):
            try:
                self.status_label.setText(f"生成中… （{cur}/{total})")
            except Exception:
                pass
        def on_finished():
            try:
                self.generate_btn.setEnabled(True)
                self.config_dir_btn.setEnabled(True)
                self.open_dir_btn.setEnabled(True)
                self.num_images_spin.setEnabled(True)
                self.prompt_input.setEnabled(True)
                self.upload_attachment_btn.setEnabled(True)
                self.view_attachment_btn.setEnabled(True)
                self.clear_btn.setEnabled(True)
                self.model_combo.setEnabled(True)
            except Exception:
                pass
            self.progress_bar.setVisible(False)
            self.status_label.setText("就绪")
        runner.item_done.connect(on_item_done)
        runner.item_failed.connect(on_item_failed)
        runner.progress_updated.connect(on_progress)
        runner.finished.connect(on_finished)
        runner.start()

    def _encode_image_to_data_url_avatar(self, file_path: str) -> str:
        try:
            ext = os.path.splitext(file_path)[1].lower()
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".bmp": "image/bmp"
            }.get(ext, "application/octet-stream")
            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return ""

    def _extract_image_url_response_avatar(self, response):
        try:
            response.raise_for_status()
            response_json = response.json()
            content = response_json["choices"][0]["message"]["content"]
            if isinstance(content, str):
                m = re.search(r"!\[.*?\]\((.*?)\)", content)
                if m:
                    return m.group(1)
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "output_image":
                        url = item.get("image_url", {}).get("url")
                        if url:
                            return url
                joined = " ".join([it.get("text", "") if isinstance(it, dict) else str(it) for it in content])
                m = re.search(r"!\[.*?\]\((.*?)\)", joined)
                if m:
                    return m.group(1)
        except KeyboardInterrupt:
            print("[角色皮肤] 请求已被用户中止")
            return None
        except Exception:
            return None
        return None

    def _extract_image_urls_avatar(self, response_json):
        urls = []
        try:
            choices = response_json.get("choices", [])
            for choice in choices:
                content = choice.get("message", {}).get("content")
                if isinstance(content, str):
                    for m in re.finditer(r"!\[.*?\]\((.*?)\)", content):
                        urls.append(m.group(1))
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "output_image":
                            url = item.get("image_url", {}).get("url")
                            if url:
                                urls.append(url)
                    joined = " ".join([it.get("text", "") if isinstance(it, dict) else str(it) for it in content])
                    for m in re.finditer(r"!\[.*?\]\((.*?)\)", joined):
                        urls.append(m.group(1))
        except Exception:
            pass
        seen = set()
        return [u for u in urls if not (u in seen or seen.add(u))]

    def upload_attachments_avatar(self):
        last_path = self.config_manager.get_reference_image_directory()
        files, _ = QFileDialog.getOpenFileNames(self, "选择附件图片", last_path, "Images (*.png *.jpg *.jpeg *.webp)")
        if not files:
            return
        try:
            first_dir = os.path.dirname(files[0]) if files else ""
            if first_dir:
                self.config_manager.set_reference_image_directory(first_dir)
        except Exception:
            pass
        cache_dir = self._get_cache_image_dir_avatar()
        appended = 0
        for src in files:
            try:
                fname = os.path.basename(src)
                dst = os.path.join(cache_dir, fname)
                shutil.copy2(src, dst)
                self.attachment_paths.append(dst)
                appended += 1
            except Exception:
                pass
        if appended > 0:
            Toast.success(f"已添加 {appended} 个附件到缓存", self)
            self.update_view_attachment_button_text_avatar()
        else:
            Toast.info("未添加任何附件", self)

    def view_attachments_avatar(self):
        try:
            dialog = AttachmentPreviewDialog(self.attachment_paths, parent=self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查看附件出错: {e}")

    def remove_attachment_avatar(self, path: str):
        try:
            if path in self.attachment_paths:
                self.attachment_paths.remove(path)
                Toast.info(f"已移除附件: {os.path.basename(path)}", self)
                self.update_view_attachment_button_text_avatar()
        except Exception:
            pass

    def clear_attachments_avatar(self):
        try:
            self.attachment_paths.clear()
            Toast.info("已清空所有附件", self)
            self.update_view_attachment_button_text_avatar()
        except Exception:
            pass

    def update_view_attachment_button_text_avatar(self):
        try:
            count = len(self.attachment_paths)
            base_text = "查看附件"
            text = base_text if count == 0 else f"{base_text} [{count}]"
            if hasattr(self, "view_attachment_btn") and self.view_attachment_btn:
                self.view_attachment_btn.setText(text)
        except Exception:
            pass

    def _get_cache_image_dir_avatar(self) -> str:
        try:
            duoki_editor_dir = Path(__file__).resolve().parents[2]
            cache_dir = duoki_editor_dir / "cache" / "image"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return str(cache_dir)
        except Exception:
            fallback = Path.cwd() / "duoki_editor" / "cache" / "image"
            fallback.mkdir(parents=True, exist_ok=True)
            return str(fallback)

    

class AIImageGenerator(QWidget):
    """AI图像生成器主界面"""
    
    def __init__(self, data_manager=None):
        super().__init__()
        self.data_manager = data_manager
        self.config_manager = ConfigManager()
        self.constants_loader = ConstantsLoader()
        self.worker = None
        self.prompt_data = []  # 初始化prompt_data列表
        # 附件参考图路径数组（缓存中的绝对路径）
        self.attachment_paths = []
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        tab_widget = QTabWidget()
        main_layout.addWidget(tab_widget)

        text2img_tab = QWidget()
        t2i_layout = QHBoxLayout(text2img_tab)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        t2i_layout.addWidget(splitter)
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)
        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)
        splitter.setSizes([150, 450])
        tab_widget.addTab(text2img_tab, "文生图")

        self.img2img_page = Img2ImgPage(self.config_manager)
        tab_widget.addTab(self.img2img_page, "图生图")
        self.avatar_page = AvatarImageGenerator(self.config_manager)
        avatar_index = tab_widget.addTab(self.avatar_page, "角色皮肤")
        self._avatar_tab_index = avatar_index
        self._avatar_tab_refreshed = False
        tab_widget.currentChanged.connect(self._on_main_tab_changed)

        
    def create_left_panel(self):
        """创建左侧面板"""
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # 打开文件按钮和文件路径显示的水平布局
        file_layout = QHBoxLayout()
        
        # 打开文件按钮
        self.open_file_btn = QPushButton("打开文件")
        self.open_file_btn.setFixedWidth(100) 
        self.open_file_btn.clicked.connect(self.open_xlsx_file)
        file_layout.addWidget(self.open_file_btn)
        
        # 文件路径显示标签
        self.file_path_label = QLabel("未选择文件")
        self.file_path_label.setWordWrap(True)  # 允许换行
        # 给文件路径标签添加伸缩，推动右侧按钮贴边
        file_layout.addWidget(self.file_path_label, 1)
        
        # 筛选失败按钮（隐藏）
        self.filter_failed_btn = QPushButton("保留失败")
        self.filter_failed_btn.setFixedWidth(100)
        self.filter_failed_btn.setEnabled(False)  # 默认不可用，生成结束后启用
        self.filter_failed_btn.clicked.connect(self.filter_failed_prompts)
        self.filter_failed_btn.hide()  # 按需求隐藏该按钮

        # 在原位置增加“全选/取消全选”按钮
        self.select_all_btn = QPushButton("取消全选")
        self.select_all_btn.setFixedWidth(100)
        self.select_all_btn.clicked.connect(self.toggle_select_all)
        file_layout.addWidget(self.select_all_btn)
        file_layout.setAlignment(self.select_all_btn, Qt.AlignmentFlag.AlignRight)
        
        left_layout.addLayout(file_layout)
        
        # Prompt数据表（左侧新增复选框列）
        self.prompt_table = QTableWidget()
        self.prompt_table.setColumnCount(2)
        self.prompt_table.setHorizontalHeaderLabels(["选择", "Prompt"])
        
        # 设置表格属性
        header = self.prompt_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.prompt_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # 设置右键菜单策略
        self.prompt_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.prompt_table.customContextMenuRequested.connect(self.show_prompt_context_menu)
        
        left_layout.addWidget(self.prompt_table)

        mode_row = QHBoxLayout()
        self.story_prompt_radio = QRadioButton("剧情生图提示词")
        self.common_prompt_radio = QRadioButton("一般生图提示词")
        self.story_prompt_radio.setChecked(True)
        mode_row.addWidget(self.story_prompt_radio)
        mode_row.addWidget(self.common_prompt_radio)
        mode_row.addStretch()
        left_layout.addLayout(mode_row)

        self.addon_prompt_input = QPlainTextEdit()
        self.addon_prompt_input.setPlaceholderText("请输入您的公用提示词")
        self.addon_prompt_input.setPlainText(BATCH_CREATE_STORY_PROMPT)
        self.addon_prompt_input.setFixedHeight(120)
        left_layout.addWidget(self.addon_prompt_input)

        self.story_prompt_radio.toggled.connect(lambda checked: self._on_prompt_mode_changed(checked))

        # 设置提示词表的Tooltip样式
        self.prompt_table.setStyleSheet("""
            QToolTip {
                color: black;
                white-space: normal;
                background-color: orange;
            }
        """)

        return left_widget

    def _on_main_tab_changed(self, idx: int):
        if hasattr(self, "_avatar_tab_index") and idx == self._avatar_tab_index:
            if not getattr(self, "_avatar_tab_refreshed", False):
                self._avatar_tab_refreshed = True
                print("[角色皮肤] 首次打开页签，触发缓存刷新")
                self.avatar_page._refresh_cached_images_avatar()
    
    def create_right_panel(self):
        """创建右侧面板"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)  # 移除内边距
        
        # 控制面板 - 水平布局
        control_panel = self.create_control_panel()
        right_layout.addWidget(control_panel)
        
        # 图片显示区域
        self.image_display = ImageDisplayWidget(self.config_manager, self)
        right_layout.addWidget(self.image_display)
        
        return right_widget
    
    def create_control_panel(self):
        """创建控制面板"""
        panel = QWidget()
        panel.setMaximumHeight(105)  # 设置面板最大高度，容纳三行控件标准高度
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)  # 减少边距
        layout.setSpacing(5)  # 减少间距
        
        # 主要控制区域 - 水平分为四个组
        main_controls_layout = QHBoxLayout()
        main_controls_layout.setSpacing(10)
        
        # 第一列 (20%宽度) - 模型和尺寸选择
        first_group = QGroupBox()
        first_group_layout = QVBoxLayout(first_group)
        first_group_layout.setContentsMargins(5, 5, 5, 5)
        
        # 模型 - label和下拉框水平排列
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["gpt-4o-image-vip", "sora_image"])
        self.model_combo.setFixedWidth(120)  # 设置固定宽度
        model_layout.addWidget(self.model_combo)
        first_group_layout.addLayout(model_layout)
        
        # 图像尺寸 - label和下拉框水平排列
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("尺寸:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems(["1024x1024", "1536x1024", "1024x1536"])
        self.size_combo.setFixedWidth(120)  # 设置固定宽度
        size_layout.addWidget(self.size_combo)
        first_group_layout.addLayout(size_layout)
        
        main_controls_layout.addWidget(first_group, 0)  # 第一列变窄，保持1
        
        # 第二列 (25%宽度) - 配置目录、打开目录按钮和批量生成按钮
        second_group = QGroupBox()
        second_group_layout = QVBoxLayout(second_group)
        second_group_layout.setContentsMargins(5, 5, 5, 5)
        
        # 上方：配置目录和打开目录按钮水平排列
        dir_buttons_layout = QHBoxLayout()
        
        self.config_dir_btn = QPushButton("配置目录")
        self.config_dir_btn.clicked.connect(self.config_output_directory)
        dir_buttons_layout.addWidget(self.config_dir_btn)
        
        self.open_dir_btn = QPushButton("打开目录")
        self.open_dir_btn.clicked.connect(self.open_output_directory)
        dir_buttons_layout.addWidget(self.open_dir_btn)
        
        second_group_layout.addLayout(dir_buttons_layout)
        
        # 下方：批量添加水印 与 批量生成 按钮水平排列
        batch_row_layout = QHBoxLayout()
        # 批量添加水印按钮（原“添加水印”移至此处并改名）
        self.add_watermark_btn = QPushButton("批量处理图片")
        self.add_watermark_btn.clicked.connect(self.batch_process_images)
        batch_row_layout.addWidget(self.add_watermark_btn)

        # 批量生成按钮
        self.batch_generate_btn = QPushButton("批量生成")
        self.batch_generate_btn.clicked.connect(self.batch_generate_images)
        batch_row_layout.addWidget(self.batch_generate_btn)

        second_group_layout.addLayout(batch_row_layout)
        
        main_controls_layout.addWidget(second_group, 1)  # 第二列保持1
        
        # 第三列 (40%宽度) - 提示词输入和按钮
        third_group = QGroupBox()
        third_group_layout = QHBoxLayout(third_group)  # 改为水平布局
        third_group_layout.setContentsMargins(5, 5, 5, 5)
        third_group_layout.setSpacing(5)
        
        # 第一列：提示词输入框
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("请输入单个提示词")
        self.prompt_input.setMaximumHeight(120)  # 设置为两行高度
        self.prompt_input.setAcceptRichText(False)  # 禁用富文本，只接受纯文本
        third_group_layout.addWidget(self.prompt_input, 3)  # 占3份宽度
        
        # 第二列：两个按钮垂直排列（仅保留“单张生成”）
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(5)

        # 上行：单次生成按钮 + 生成数量（1-4）
        single_buttons_row = QHBoxLayout()
        self.generate_btn = QPushButton("单次生成")
        # 改为根据“角色一致”状态调用不同方法
        self.generate_btn.clicked.connect(self.on_generate_single_clicked)
        single_buttons_row.addWidget(self.generate_btn)

        self.num_images_spin = QSpinBox()
        self.num_images_spin.setRange(1, 4)
        self.num_images_spin.setValue(1)
        self.num_images_spin.setToolTip("单次生成的图片数量 (1-4)")
        self.num_images_spin.setFixedWidth(40)
        single_buttons_row.addWidget(self.num_images_spin)

        buttons_layout.addLayout(single_buttons_row)

        # 下行：上传附件 与 查看附件 按钮（左右排列）
        attachment_buttons_row = QHBoxLayout()
        self.upload_attachment_btn = QPushButton("上传附件")
        self.upload_attachment_btn.clicked.connect(self.upload_attachments)
        attachment_buttons_row.addWidget(self.upload_attachment_btn)

        self.view_attachment_btn = QPushButton("查看附件")
        self.view_attachment_btn.clicked.connect(self.view_attachments)
        attachment_buttons_row.addWidget(self.view_attachment_btn)

        buttons_layout.addLayout(attachment_buttons_row)
        # 初始化查看附件按钮文案
        if hasattr(self, 'update_view_attachment_button_text'):
            self.update_view_attachment_button_text()

        third_group_layout.addLayout(buttons_layout, 1)  # 占1份宽度
        
        main_controls_layout.addWidget(third_group, 3)  # 第三列变宽，从2变为3
        
        # 第四列 - 复选框选项（两列排列）
        fourth_group = QGroupBox()
        fourth_group_layout = QVBoxLayout(fourth_group)
        fourth_group_layout.setContentsMargins(5, 5, 5, 5)
        fourth_group_layout.setSpacing(3)
        
        # 重排为两列：
        # 左侧第一列：上“卡通风格” 下“角色一致”
        # 右侧第二列：上“水印” 下“切图”
        # 最右第三列：宽/高 数字输入框
        two_cols_layout = QHBoxLayout()
        left_col_layout = QVBoxLayout()
        right_col_layout = QVBoxLayout()
        dims_col_layout = QVBoxLayout()

        # 左列：卡通风格、角色一致
        self.cartoon_style_checkbox = QCheckBox("卡通风格")
        self.cartoon_style_checkbox.setChecked(True)  # 默认不勾选
        left_col_layout.addWidget(self.cartoon_style_checkbox)

        self.role_consistency_checkbox = QCheckBox("角色一致")
        self.role_consistency_checkbox.setChecked(True)  # 默认勾选
        left_col_layout.addWidget(self.role_consistency_checkbox)

        # 右列：水印、切图
        self.watermark_checkbox = QCheckBox("水印")
        self.watermark_checkbox.setChecked(False)  # 默认不勾选
        right_col_layout.addWidget(self.watermark_checkbox)

        self.auto_crop_checkbox = QCheckBox("切图")
        self.auto_crop_checkbox.setChecked(False)  # 默认不勾选
        right_col_layout.addWidget(self.auto_crop_checkbox)

        two_cols_layout.addLayout(left_col_layout)
        two_cols_layout.addLayout(right_col_layout)
        
        # 右侧增加一列：宽/高 数字输入
        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("宽:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 1536)
        self.width_spin.setValue(720)
        self.width_spin.setFixedWidth(40)
        self.width_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        width_row.addWidget(self.width_spin)
        dims_col_layout.addLayout(width_row)

        height_row = QHBoxLayout()
        height_row.addWidget(QLabel("高:"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 1536)
        self.height_spin.setValue(720)
        self.height_spin.setFixedWidth(40)
        self.height_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        height_row.addWidget(self.height_spin)
        dims_col_layout.addLayout(height_row)

        two_cols_layout.addLayout(dims_col_layout)
        fourth_group_layout.addLayout(two_cols_layout)
        
        main_controls_layout.addWidget(fourth_group, 0)  # 第四列进一步变窄，使用最小宽度
        
        layout.addLayout(main_controls_layout)

        # 绑定“切图”勾选与宽高输入框的启用状态
        self.auto_crop_checkbox.toggled.connect(self.update_crop_dimensions_enabled)

        # 初始化宽高输入框启用状态
        self.update_crop_dimensions_enabled()
        
        # 进度条和状态
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(15)  # 减少进度条高度
        # 设置进度条为蓝色
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 3px;
                text-align: center;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 2px;
            }
        """)
        
        # 进度条、状态标签和清空按钮水平排列
        progress_status_layout = QHBoxLayout()
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: white;")  # 减小字体
        self.status_label.setMaximumHeight(15)  # 减少状态标签高度
        progress_status_layout.addWidget(self.status_label, 1)  # 状态标签占较少空间
        progress_status_layout.addWidget(self.progress_bar, 8)  # 进度条占更多空间
        
        # 清空列表按钮（在就绪状态下显示，进度条显示时隐藏）
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.clicked.connect(self.clear_images)
        self.clear_btn.setMaximumWidth(80)
        progress_status_layout.addWidget(self.clear_btn, 1)
        
        layout.addLayout(progress_status_layout)

        return panel
    
    def generate_single_image(self):
        """生成单张图片"""
        # 获取提示词输入框的内容
        prompt = self.prompt_input.toPlainText().strip()
        
        if not prompt:
            QMessageBox.warning(self, "警告", "请输入提示词")
            return
        
        # 单次生成不拼接公用样式，仅在勾选卡通风格时追加常量
        style_text = CARTOON_STYLE_SUFFIX if self.cartoon_style_checkbox.isChecked() else ''
        
        model = self.model_combo.currentText()
        # 若勾选“切图”，携带当前宽高；否则保持None以原尺寸输出
        width_val = int(self.width_spin.value()) if self.auto_crop_checkbox.isChecked() else None
        height_val = int(self.height_spin.value()) if self.auto_crop_checkbox.isChecked() else None
        self.start_generation([{ 'prompt': prompt, 'style': style_text, 'filename': '', 'width': width_val, 'height': height_val }], model)

    def on_generate_single_clicked(self):
        """根据“角色一致”复选框状态选择生成路径"""
        try:
            if self.role_consistency_checkbox.isChecked():
                # 勾选“角色一致”时，调用plus流程（参考图）
                self.generate_single_image_plus()
            else:
                # 未勾选时，调用当前单张生成流程
                self.generate_single_image()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"触发生成失败: {str(e)}")

    def _encode_image_to_data_url(self, file_path: str) -> str:
        """读取本地图片并返回data URL字符串"""
        try:
            ext = os.path.splitext(file_path)[1].lower()
            mime = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.webp': 'image/webp',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp'
            }.get(ext, 'application/octet-stream')
            with open(file_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            return f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.error(f"读取参考图片失败: {file_path}, 错误: {e}")
            return ""

    def _build_ref_image_paths(self, prompt: str) -> list:
        """根据prompt匹配constants中的image_references，返回绝对路径列表（去重且存在）"""
        try:
            refs = self.constants_loader.get_image_references() or {}
            if not isinstance(refs, dict):
                return []
            matched_rel_paths = []
            for key, rel in refs.items():
                if key and isinstance(key, str) and key in prompt:
                    matched_rel_paths.append(rel)
            # 去重
            matched_rel_paths = list(dict.fromkeys(matched_rel_paths))

            if not matched_rel_paths:
                return []

            # 组装绝对路径：基于 duoki_editor 目录
            duoki_editor_dir = Path(__file__).resolve().parents[2]
            abs_paths = []
            for rel in matched_rel_paths:
                abs_path = duoki_editor_dir / rel
                if abs_path.exists():
                    abs_paths.append(str(abs_path))
                else:
                    logger.warning(f"参考图片不存在: {abs_path}")
            return abs_paths
        except Exception as e:
            logger.error(f"构建参考图片路径失败: {e}")
            return []

    def generate_single_image_plus(self):
        """使用参考图的单张生成（复用线程与进度条流程）"""
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "警告", "请输入提示词")
            return

        # 单次生成（plus）不拼接公用样式，仅在勾选卡通风格时追加常量
        style_text = CARTOON_STYLE_SUFFIX if self.cartoon_style_checkbox.isChecked() else ''

        # 构建参考图片路径（常量匹配 + 附件列表）
        ref_paths = self._build_ref_image_paths(prompt)
        # 将已上传附件追加到参考路径中（存在性校验并去重，保持顺序）
        try:
            attachment_existing = [p for p in self.attachment_paths if os.path.exists(p)]
            combined = ref_paths + attachment_existing
            # 去重保持顺序
            seen = set()
            ref_paths = [p for p in combined if not (p in seen or seen.add(p))]
        except Exception as e:
            logger.warning(f"合并附件参考图失败: {e}")
        if not ref_paths:
            print("[AI图片生成+] 未匹配到参考图片，按纯文本生成")
        
        # 复用 start_generation 流程，交由工作线程处理
        # 若勾选“切图”，携带当前宽高；否则保持None以原尺寸输出
        width_val = int(self.width_spin.value()) if self.auto_crop_checkbox.isChecked() else None
        height_val = int(self.height_spin.value()) if self.auto_crop_checkbox.isChecked() else None
        data_dict = {'prompt': prompt, 'style': style_text, 'filename': '', 'ref_image_paths': ref_paths, 'width': width_val, 'height': height_val}
        self.start_generation([data_dict], "wuyun")

    def _get_cache_image_dir(self) -> str:
        """返回缓存图片目录 duoki_editor/cache/image 的绝对路径，确保存在"""
        try:
            duoki_editor_dir = Path(__file__).resolve().parents[2]
            cache_dir = duoki_editor_dir / 'cache' / 'image'
            cache_dir.mkdir(parents=True, exist_ok=True)
            return str(cache_dir)
        except Exception as e:
            logger.error(f"创建缓存图片目录失败: {e}")
            # 兜底使用当前目录下的 cache/image
            fallback = Path.cwd() / 'duoki_editor' / 'cache' / 'image'
            fallback.mkdir(parents=True, exist_ok=True)
            return str(fallback)

    def upload_attachments(self):
        """上传附件：选择PNG/JPG/WEBP，复制到缓存目录并记录路径（追加）"""
        try:
            # 选择文件，支持多选，仅PNG/JPG
            # 从配置中读取最后一次上传附件目录
            last_path = ''
            if hasattr(self.config_manager, 'get_reference_image_directory'):
                last_path = self.config_manager.get_reference_image_directory()
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "选择附件图片",
                last_path,
                "Images (*.png *.jpg *.jpeg *.webp)"
            )
            if not files:
                return

            # 更新配置中的最后一次上传附件目录
            try:
                first_dir = os.path.dirname(files[0]) if files else ''
                if first_dir and hasattr(self.config_manager, 'set_reference_image_directory'):
                    self.config_manager.set_reference_image_directory(first_dir)
            except Exception as e:
                logger.warning(f"更新参考图片目录失败: {e}")

            cache_dir = self._get_cache_image_dir()
            import shutil

            appended_count = 0
            for src in files:
                try:
                    fname = os.path.basename(src)
                    dst = os.path.join(cache_dir, fname)
                    # 保持文件名不变，复制（存在则覆盖）
                    shutil.copy2(src, dst)
                    # 追加到附件数组（每次选择都 append 新路径）
                    self.attachment_paths.append(dst)
                    appended_count += 1
                except Exception as e:
                    logger.error(f"复制附件失败 {src}: {e}")

            if appended_count > 0:
                Toast.success(f"已添加 {appended_count} 个附件到缓存", self)
                self.update_view_attachment_button_text()
            else:
                Toast.info("请不要添加缓存目录下的图片", self)
        except Exception as e:
            logger.error(f"上传附件出错: {e}")
            QMessageBox.critical(self, "错误", f"上传附件出错: {e}")

    def view_attachments(self):
        """查看附件：打开预览窗口，矩阵展示并支持删除"""
        try:
            dialog = AttachmentPreviewDialog(self.attachment_paths, parent=self)
            dialog.exec()
        except Exception as e:
            logger.error(f"查看附件出错: {e}")
            QMessageBox.critical(self, "错误", f"查看附件出错: {e}")

    def remove_attachment(self, path: str):
        """从附件数组中移除一个路径（不删除缓存文件）"""
        try:
            if path in self.attachment_paths:
                self.attachment_paths.remove(path)
                # 刷新状态提示
                Toast.info(f"已移除附件: {os.path.basename(path)}", self)
                self.update_view_attachment_button_text()
        except Exception as e:
            logger.error(f"移除附件失败: {e}")

    def clear_attachments(self):
        """清空所有附件（仅清空数组，不删除缓存文件）"""
        try:
            self.attachment_paths.clear()
            Toast.info("已清空所有附件", self)
            self.update_view_attachment_button_text()
        except Exception as e:
            logger.error(f"清空附件失败: {e}")
            QMessageBox.warning(self, "警告", f"清空附件失败: {e}")

    def update_view_attachment_button_text(self):
        """根据附件数量更新“查看附件”按钮文案，>0时显示 [x]"""
        try:
            count = len(self.attachment_paths)
            base_text = "查看附件"
            text = base_text if count == 0 else f"{base_text} [{count}]"
            if hasattr(self, 'view_attachment_btn') and self.view_attachment_btn:
                self.view_attachment_btn.setText(text)
        except Exception:
            pass

    def open_xlsx_file(self):
        """打开Excel文件并加载prompt数据"""
        try:
            # 从配置文件获取上次打开的路径（图片模块专用）
            last_path = self.config_manager.get_last_open_path('image')
            
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择Excel文件",
                last_path,
                "Excel Files (*.xlsx *.xls)"
            )
            
            if file_path:
                # 保存当前打开的目录到配置文件（图片模块专用）
                self.config_manager.set_last_open_path(file_path, 'image')
                
                # 使用pandas读取Excel文件
                import pandas as pd
                df = pd.read_excel(file_path)
                
                # 检查必需的字段：使用prompt+filename，弃用style列
                required_fields = ['prompt', 'filename']
                missing_fields = [field for field in required_fields if field not in df.columns]
                
                if missing_fields:
                    # 显示toast提示
                    Toast.error(f"文件格式有误，缺少必要的列({', '.join(required_fields)})", self)
                    return

                # 检测 prompt 与 filename 列的重复值，弹出警告并列出重复行
                try:
                    duplicate_messages = []
                    for col in ['filename']:
                        if col not in df.columns:
                            continue
                        # 仅对非空值进行分组检测
                        valid_df = df[pd.notna(df[col])]
                        grouped = valid_df.groupby(valid_df[col])
                        for value, group in grouped:
                            if len(group) > 1:
                                # 将DataFrame索引转换为 1-based 行号，便于用户定位
                                rows = [int(i) + 1 for i in group.index.tolist()]
                                value_str = str(value)
                                # 避免过长文本撑爆弹窗，截断展示
                                if len(value_str) > 80:
                                    value_str = value_str[:80] + "..."
                                duplicate_messages.append(
                                    f"列 {col} 的值“{value_str}”重复出现在行：{', '.join(map(str, rows))}"
                                )
                    if duplicate_messages:
                        QMessageBox.warning(
                            self,
                            "重复数据警告",
                            "\n".join(duplicate_messages)
                        )
                except Exception:
                    # 重复检测失败不影响后续加载
                    pass
                
                # 清空现有数据
                self.prompt_table.setRowCount(0)
                self.prompt_data = []  # 存储完整数据的字典列表
                
                # 处理每一行数据
                for index, row in df.iterrows():
                    # 直接使用prompt列作为提示词
                    combined_prompt = str(row['prompt']).strip() if pd.notna(row['prompt']) else ''
                    if combined_prompt:
                        # 不在读取Excel阶段拼接公用样式；样式在生成阶段处理
                        # 存储到字典
                        data_dict = {
                            'prompt': combined_prompt,
                            'style': '',
                            'filename': str(row['filename']) if pd.notna(row['filename']) else '',
                            'width': None,
                            'height': None
                        }
                        self.prompt_data.append(data_dict)
                
                # 更新表格显示：新增复选框列，默认全选
                self.prompt_table.setRowCount(len(self.prompt_data))
                for i, data in enumerate(self.prompt_data):
                    # 复选框列
                    check_item = QTableWidgetItem()
                    check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                    check_item.setCheckState(Qt.CheckState.Checked)
                    self.prompt_table.setItem(i, 0, check_item)

                    # 提示词列
                    prompt_item = QTableWidgetItem(data['prompt'])
                    # 为每行添加tooltip，内容为完整提示词（prompt + style）
                    prompt_item.setToolTip(data.get('prompt'))
                    self.prompt_table.setItem(i, 1, prompt_item)
                
                # 每次加载Excel时，先清空一次右侧图片列表（不触发Toast）
                self.image_display.clear_images()

                # 自动加载已存在的图片：按 filename 在输出目录查找同名 .jpg
                output_dir = self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
                os.makedirs(output_dir, exist_ok=True)
                for data in self.prompt_data:
                    fname = str(data.get('filename') or '').strip()
                    if not fname:
                        continue
                    parts = re.split(r"[\\/]+", fname)
                    parts = [re.sub(r'[<>:\\"\|\?\*]', '_', p).strip() for p in parts if p and p not in ['.', '..']]
                    last = parts[-1] if parts else ''
                    base_last, _ = os.path.splitext(last)
                    last = f"{base_last}.jpg" if base_last else ''
                    rel_path = os.path.join(*parts[:-1], last) if len(parts) > 1 else last
                    img_path = os.path.join(output_dir, rel_path) if rel_path else None
                    if img_path and os.path.isfile(img_path):
                        with open(img_path, 'rb') as f:
                            img_bytes = f.read()
                        dd = dict(data)
                        dd['is_batch'] = True
                        dd['is_xlsx_generated'] = True
                        self.image_display.add_image(dd, img_bytes, img_path)
                        self.mark_prompt_as_success(dd)

                # 更新文件路径显示标签，仅显示文件名
                self.file_path_label.setText(os.path.basename(file_path))
                
                Toast.info(f"已加载 {len(self.prompt_data)} 个提示词", self)
                
                # 保留失败按钮按需求隐藏，改用全选按钮，不需要启用
                # if not self.worker:
                #     self.filter_failed_btn.setEnabled(True)
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载文件失败: {str(e)}")
    
    def batch_generate_images(self):
        """批量生成图片"""
        # 获取表格中的所有prompt数据
        if not hasattr(self, 'prompt_data') or not self.prompt_data:
            QMessageBox.warning(self, "警告", "请先加载包含提示词的Excel文件")
            return

        
        # 重置所有提示词行的颜色
        self.reset_prompt_colors()
        
        # 根据每条文本与 image_references 的匹配结果，决定是否走 plus 接口
        # 条件：需同时满足“角色一致”复选框已勾选 且 文本匹配到常量参考图
        # 忽略已上传附件（只依据文本匹配常量参考图）
        batched_data = []
        try:
            row_count = self.prompt_table.rowCount()
            for i in range(row_count):
                chk_item = self.prompt_table.item(i, 0)
                if not chk_item or chk_item.checkState() != Qt.CheckState.Checked:
                    continue  # 未选中，不进入队列

                # 拷贝条目，保留原有的 style/filename 等字段
                src = self.prompt_data[i] if i < len(self.prompt_data) else {}
                data = dict(src) if isinstance(src, dict) else {}
                prompt_text = data.get('prompt', '') or ''

                # 仅根据文本匹配常量中的参考图，忽略附件
                ref_paths = self._build_ref_image_paths(prompt_text)
                # 是否启用plus：需“角色一致”勾选 且 匹配到参考图
                use_plus = bool(ref_paths) and bool(getattr(self, 'role_consistency_checkbox', None) and self.role_consistency_checkbox.isChecked())
                if use_plus:
                    data['ref_image_paths'] = ref_paths
                else:
                    # 使用常规接口：不携带 ref_image_paths
                    data.pop('ref_image_paths', None)
                # 标记为批量生成，供图片卡片控制显示“打回”按钮
                data['is_batch'] = True
                # 仅“生成阶段”标记来源为 XLSX 批量生成，用于预览界面显示审核菜单
                data['is_xlsx_generated'] = True

                # 在生成阶段拼接公用样式，并按需追加卡通风格常量
                try:
                    style_text = self.addon_prompt_input.toPlainText().strip()
                    if self.cartoon_style_checkbox.isChecked():
                        style_text = f"{style_text}, {CARTOON_STYLE_SUFFIX}" if style_text else CARTOON_STYLE_SUFFIX
                    data['style'] = style_text
                except Exception:
                    # 保底：保持原有样式或空
                    data['style'] = data.get('style', '')

                # 批量切图尺寸统一按“切图”与面板宽高决定；未勾选时按原图（None）
                if getattr(self, 'auto_crop_checkbox', None) and self.auto_crop_checkbox.isChecked():
                    try:
                        data['width'] = int(self.width_spin.value())
                        data['height'] = int(self.height_spin.value())
                    except Exception:
                        data['width'] = None
                        data['height'] = None
                else:
                    data['width'] = None
                    data['height'] = None

                batched_data.append(data)
        except Exception as e:
            logger.error(f"批量构建参考图路径时发生错误: {e}")
            batched_data = []

        # 若没有任何选中项，提示并退出
        if not batched_data:
            Toast.info("请选择要生图的提示词", self)
            return

        self.batch_generate_btn.setText("中止生成")
        self.batch_generate_btn.clicked.disconnect(self.batch_generate_images)
        self.batch_generate_btn.clicked.connect(self.on_abort_text_batch_clicked)
        self.start_generation(batched_data, "wuyun")
    
    def start_generation(self, prompts, api_service):
        """开始图像生成任务"""
        try:
            # 固定使用wuyun服务商
            api_token = self.config_manager.get_wuyun_token()
            
            if not api_token:
                QMessageBox.critical(self, "错误", "未找到 wuyun API Token，请检查config.ini配置")
                return
            
            # 不再重置 self.prompt_data，保持表格与加载的Excel数据一致
            
            # 禁用所有控件
            self.set_controls_enabled(False)
            # 生成过程中禁用筛选失败按钮
            if hasattr(self, 'filter_failed_btn'):
                self.filter_failed_btn.setEnabled(False)

            # 显示进度条，隐藏清空按钮
            self.progress_bar.setVisible(True)
            self.clear_btn.setVisible(False)
            self.progress_bar.setRange(0, 0)  # 不确定进度

            # 在生成开始时显示 0/总数
            items = prompts if isinstance(prompts, list) else [prompts]
            requested_num = 1
            try:
                if isinstance(items, list) and len(items) == 1 and hasattr(self, 'num_images_spin'):
                    requested_num = max(1, min(4, int(self.num_images_spin.value())))
            except Exception:
                requested_num = 1
            total_est = 0
            single_batch = len(items) == 1
            for dd in items:
                if isinstance(dd, dict) and dd.get('ref_image_paths'):
                    total_est += requested_num
                else:
                    total_est += (requested_num if single_batch else 1)
            self.status_label.setText(f"生成中… （0/{total_est})")
            
            # 创建工作线程
            # 单次生成时按照数量控件的值；批量生成固定为1
            # requested_num 已在上方计算

            self.worker = ImageGenerationWorker(
                api_token=api_token,
                prompt_data_list=prompts,
                model=self.model_combo.currentText(),
                size=self.size_combo.currentText(),
                num_images=requested_num
            )
            
            # 连接信号
            self.worker.progress_updated.connect(self.update_progress)
            # 将开始生成的提示词标记为橙色
            self.worker.item_started.connect(self.mark_prompt_as_in_progress)
            self.worker.image_generated.connect(self.on_image_generated)
            self.worker.error_occurred.connect(self.on_error)
            self.worker.finished.connect(self.on_generation_finished)
            
            # 启动线程
            self.worker.start()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动生成任务失败: {str(e)}")
            self.on_generation_finished()
    
    def update_progress(self, message):
        """更新进度信息"""
        self.status_label.setText(f"生成中… （{message})")
    
    def on_image_generated(self, data_dict, image_data):
        """处理生成的图像并自动保存"""
        try:
            # 从配置获取输出目录
            output_dir = self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
            os.makedirs(output_dir, exist_ok=True)
            
            filename_raw = data_dict.get('filename')
            if filename_raw:
                parts = re.split(r"[\\/]+", str(filename_raw).strip())
                parts = [re.sub(r'[<>:\\"\|\?\*]', '_', p).strip() for p in parts if p and p not in ['.', '..']]
                last = parts[-1] if parts else ''
                base_last, _ = os.path.splitext(last)
                last = f"{base_last}.jpg" if base_last else f"{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                rel_path = os.path.join(*parts[:-1], last) if len(parts) > 1 else last
            else:
                prompt_prefix = data_dict.get('prompt', '')[:30]
                safe_prefix = re.sub(r'[^\w\-.]', '_', prompt_prefix)
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                rel_path = f"{safe_prefix}_{timestamp}.jpg"
            save_path = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # 使用PIL处理图片
            img = Image.open(BytesIO(image_data))
            
            # 根据自动切图复选框状态决定是否resize
            if self.auto_crop_checkbox.isChecked():
                try:
                    tw = int(self.width_spin.value())
                    th = int(self.height_spin.value())
                except Exception:
                    tw, th = 720, 720
                sw, sh = img.size
                if sw <= 0 or sh <= 0 or tw <= 0 or th <= 0:
                    resized_img = img
                else:
                    scale = max(tw / sw, th / sh)
                    new_w = max(1, int(round(sw * scale)))
                    new_h = max(1, int(round(sh * scale)))
                    tmp = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    left = max(0, (new_w - tw) // 2)
                    top = max(0, (new_h - th) // 2)
                    right = left + tw
                    bottom = top + th
                    resized_img = tmp.crop((left, top, right, bottom))
            else:
                # 不进行resize，使用原始图片
                resized_img = img
            
            # Convert to RGB mode for JPEG saving
            if resized_img.mode != 'RGB':
                resized_img = resized_img.convert('RGB')
            
            # 将图片转换为字节数据
            img_byte_arr = io.BytesIO()
            resized_img.save(img_byte_arr, format='JPEG', quality=85)
            img_bytes = img_byte_arr.getvalue()
            
            # 根据勾选框状态决定是否添加水印
            if self.watermark_checkbox.isChecked():
                # 添加水印
                final_bytes = add_watermark(img_bytes)
            else:
                # 不添加水印
                final_bytes = img_bytes
            
            # 保存图片
            with open(save_path, 'wb') as f:
                f.write(final_bytes)
            # 保存完成后输出本地文件名
            print(f"[AI图片生成] 本地文件名: {os.path.basename(save_path)}")
            
            # 将保存后的图片数据读取回来，用于UI显示
            with open(save_path, 'rb') as f:
                compressed_image_data = f.read()
            
            # 更新UI（使用保存后的图片数据）
            self.image_display.add_image(data_dict, compressed_image_data, save_path)
            
            # 将成功生成的提示词行标记为绿色
            self.mark_prompt_as_success(data_dict)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.on_error(f"保存图片失败: {str(e)}")

    def on_error(self, error_message, failed_data_dict=None):
        """处理错误"""

        # 如果有具体的失败数据，将对应的表格行标记为红色
        if failed_data_dict:
            self.mark_prompt_as_failed(failed_data_dict)

        # 如果有完整返回体，弹出长文本弹窗；否则退回到详细信息或通用信息
        full_body = None
        detailed_msg = None
        try:
            if isinstance(failed_data_dict, dict):
                full_body = failed_data_dict.get('error_full_body')
                detailed_msg = failed_data_dict.get('error_detail')
        except Exception:
            pass

        if full_body:
            dialog = ErrorResponseDialog("生成失败 - 完整返回体", full_body, parent=self)
            dialog.exec()
        else:
            if detailed_msg:
                QMessageBox.critical(self, "生成错误", detailed_msg)
            else:
                print(f"Toast manager not available, error: {error_message}")
                QMessageBox.critical(self, "生成错误", error_message)
        
        # 批量任务进行中不解锁控件；仅在无工作线程或线程已结束时解锁
        try:
            if not self.worker or (hasattr(self.worker, 'isRunning') and not self.worker.isRunning()):
                self.set_controls_enabled(True)
        except Exception:
            pass
    
    def on_generation_finished(self):
        """生成任务完成"""
        # 重新启用所有控件
        self.set_controls_enabled(True)
        # 生成完成后允许筛选失败
        if hasattr(self, 'filter_failed_btn'):
            self.filter_failed_btn.setEnabled(True)
        
        # 隐藏进度条，显示清空按钮
        self.progress_bar.setVisible(False)
        self.clear_btn.setVisible(True)
        
        # 更新状态
        self.status_label.setText("生成完成")
        
        # 清理工作线程
        if self.worker:
            self.worker = None
        if hasattr(self, 'batch_generate_btn') and self.batch_generate_btn:
            self.batch_generate_btn.setText("批量生成")
            try:
                self.batch_generate_btn.clicked.disconnect(self.on_abort_text_batch_clicked)
            except Exception:
                pass
            self.batch_generate_btn.clicked.connect(self.batch_generate_images)

    def on_abort_text_batch_clicked(self):
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            print("[文生图] 中止批量生成，正在清空线程池...")
            self.worker.stop()
            self.worker.wait()
            self.worker = None
        self.set_controls_enabled(True)
        self.progress_bar.setVisible(False)
        self.clear_btn.setVisible(True)
        self.status_label.setText("已中止")
        if hasattr(self, 'batch_generate_btn') and self.batch_generate_btn:
            self.batch_generate_btn.setText("批量生成")
            try:
                self.batch_generate_btn.clicked.disconnect(self.on_abort_text_batch_clicked)
            except Exception:
                pass
            self.batch_generate_btn.clicked.connect(self.batch_generate_images)

    def mark_prompt_as_in_progress(self, data_dict):
        """将正在生成的提示词行标记为橙色（按filename匹配行）"""
        try:
            if not isinstance(data_dict, dict):
                return
            target_filename = str(data_dict.get('filename') or '').strip()
            if not target_filename:
                return
            row_idx = -1
            for i in range(min(self.prompt_table.rowCount(), len(self.prompt_data))):
                fn = str(self.prompt_data[i].get('filename') or '').strip()
                if fn == target_filename:
                    row_idx = i
                    break
            if row_idx >= 0:
                item = self.prompt_table.item(row_idx, 1)
                if item:
                    item.setForeground(QColor('orange'))
        except Exception as e:
            logger.error(f"标记生成中提示词时发生错误: {str(e)}")
    
    def config_output_directory(self):
        """配置图片输出目录"""
        try:
            # 获取当前配置的输出目录
            current_dir = self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
            
            # 打开目录选择对话框
            selected_dir = QFileDialog.getExistingDirectory(
                self,
                "选择图片输出目录",
                current_dir
            )
            
            if selected_dir:
                # 更新配置文件
                self.config_manager.set('PATH', 'image_output_directory', selected_dir)
                self.config_manager.save()
                
                QMessageBox.information(self, "成功", f"图片输出目录已设置为: {selected_dir}")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"配置输出目录失败: {str(e)}")
    
    def clear_images(self):
        """清空所有生成的图片"""
        self.image_display.clear_images()
        Toast.info("已清空图片", self)
    
    def mark_prompt_as_failed(self, failed_data_dict):
        """将失败的提示词行添加"（生成失败）"标记（按filename匹配行）"""
        try:
            target_filename = str(failed_data_dict.get('filename') or '') if isinstance(failed_data_dict, dict) else ''
            target_filename = target_filename.strip()
            if not target_filename:
                return
            row_idx = -1
            for i in range(min(self.prompt_table.rowCount(), len(self.prompt_data))):
                fn = str(self.prompt_data[i].get('filename') or '').strip()
                if fn == target_filename:
                    row_idx = i
                    break
            if row_idx >= 0:
                item = self.prompt_table.item(row_idx, 1)
                if item:
                    current_text = item.text()
                    if not current_text.endswith("（生成失败）"):
                        item.setText(current_text + "（生成失败）")
                    item.setForeground(QColor('red'))
        except Exception as e:
            logger.error(f"标记失败提示词时发生错误: {str(e)}")
    
    def mark_prompt_as_success(self, success_data_dict):
        """将成功的提示词行标记为绿色（按filename匹配行）"""
        try:
            target_filename = str(success_data_dict.get('filename') or '') if isinstance(success_data_dict, dict) else ''
            target_filename = target_filename.strip()
            if not target_filename:
                return
            row_idx = -1
            for i in range(min(self.prompt_table.rowCount(), len(self.prompt_data))):
                fn = str(self.prompt_data[i].get('filename') or '').strip()
                if fn == target_filename:
                    row_idx = i
                    break
            if row_idx >= 0:
                prompt_item = self.prompt_table.item(row_idx, 1)
                if prompt_item:
                    prompt_item.setForeground(QColor('green'))
                chk_item = self.prompt_table.item(row_idx, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Unchecked)
        except Exception as e:
            logger.error(f"标记成功提示词时发生错误: {str(e)}")
    
    def reset_prompt_colors(self):
        """重置所有提示词行，移除失败标记，恢复默认颜色"""
        try:
            for i in range(self.prompt_table.rowCount()):
                item = self.prompt_table.item(i, 1)
                if item:
                    current_text = item.text()
                    # 始终移除失败标记文本后缀
                    if current_text.endswith("（生成失败）"):
                        item.setText(current_text.replace("（生成失败）", ""))
                    # 保留绿色（成功）项的颜色，其它恢复为黑色
                    current_color = item.foreground().color()
                    if current_color == QColor('green'):
                        continue
                    # 使用当前主题的默认文本颜色，而不是强制黑色
                    default_color = self.prompt_table.palette().color(QPalette.ColorRole.Text)
                    item.setForeground(default_color)
        except Exception as e:
            logger.error(f"重置提示词状态时发生错误: {str(e)}")

    def filter_failed_prompts(self):
        """去掉绿色成功项，保留失败项和未处理项"""
        try:
            failed_indices = []
            for i in range(self.prompt_table.rowCount()):
                item = self.prompt_table.item(i, 1)
                if not item:
                    continue
                text = item.text()
                color = item.foreground().color()
                is_green = (color == QColor('green'))
                is_failed_text = text.endswith("（生成失败）")
                if not is_green:  # 保留非绿色的项（包括红色失败项和黑色未处理项）
                    failed_indices.append(i)
            
            if not failed_indices:
                QMessageBox.information(self, "提示", "所有项都是成功项，无需筛选")
                return
            
            # 根据失败索引筛选 prompt_data
            new_prompt_data = [self.prompt_data[i] for i in failed_indices if i < len(self.prompt_data)]
            self.prompt_data = new_prompt_data
            
            # 重新填充表格，仅保留失败项，复选框默认选中
            self.prompt_table.setRowCount(len(self.prompt_data))
            for row, data in enumerate(self.prompt_data):
                chk_item = QTableWidgetItem()
                chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                chk_item.setCheckState(Qt.CheckState.Checked)
                self.prompt_table.setItem(row, 0, chk_item)

                item = QTableWidgetItem(data['prompt'] + "（生成失败）")
                item.setForeground(QColor('red'))
                self.prompt_table.setItem(row, 1, item)
            
            Toast.info(f"已去掉成功项，剩余 {len(self.prompt_data)} 条", self)
        except Exception as e:
            logger.error(f"筛选失败项时发生错误: {str(e)}")

    def toggle_select_all(self):
        """全选/取消全选切换"""
        try:
            # 当前按钮文本决定目标动作
            select_mode = (self.select_all_btn.text() == "全选")
            for i in range(self.prompt_table.rowCount()):
                chk_item = self.prompt_table.item(i, 0)
                if chk_item:
                    chk_item.setCheckState(Qt.CheckState.Checked if select_mode else Qt.CheckState.Unchecked)
            # 切换按钮文本
            self.select_all_btn.setText("取消全选" if select_mode else "全选")
        except Exception as e:
            logger.error(f"切换全选状态失败: {e}")
    
    def batch_process_images(self):
        """批量处理图片：按勾选项添加水印、调整尺寸、并在必要时转换为JPG"""
        # 打开文件选择对话框，支持多选
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter("图片文件 (*.jpg *.jpeg *.png *.webp)")
        file_dialog.setWindowTitle("选择要处理的图片")
        
        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = file_dialog.selectedFiles()
            
            if not selected_files:
                return
            
            # 获取输出目录
            output_dir = self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
            os.makedirs(output_dir, exist_ok=True)
            
            watermark_enabled = bool(getattr(self, 'watermark_checkbox', None) and self.watermark_checkbox.isChecked())
            resize_enabled = bool(getattr(self, 'auto_crop_checkbox', None) and self.auto_crop_checkbox.isChecked())
            
            processed_count = 0
            total_selected = len(selected_files)
            
            for file_path in selected_files:
                try:
                    original_filename = os.path.basename(file_path)
                    name, ext = os.path.splitext(original_filename)
                    ext = ext.lower()
                    is_jpg = (ext == '.jpg')
                    
                    # 判定是否需要处理
                    process_needed = watermark_enabled or resize_enabled or (not is_jpg)
                    if not process_needed:
                        # 水印与尺寸均未勾选且扩展名是jpg -> 跳过
                        continue
                    
                    with open(file_path, 'rb') as f:
                        original_bytes = f.read()
                    
                    working_bytes = original_bytes
                    
                    # 尺寸调整（若勾选）
                    if resize_enabled:
                        try:
                            width = int(self.width_spin.value())
                            height = int(self.height_spin.value())
                        except Exception:
                            width, height = 720, 720
                        try:
                            with Image.open(io.BytesIO(working_bytes)) as im:
                                sw, sh = im.size
                                if sw > 0 and sh > 0 and width > 0 and height > 0:
                                    s = max(width / sw, height / sh)
                                    nw = max(1, int(round(sw * s)))
                                    nh = max(1, int(round(sh * s)))
                                    tmp = im.resize((nw, nh), Image.Resampling.LANCZOS)
                                    l = max(0, (nw - width) // 2)
                                    t = max(0, (nh - height) // 2)
                                    r = l + width
                                    b = t + height
                                    out = tmp.crop((l, t, r, b))
                                else:
                                    out = im
                                if out.mode != 'RGB':
                                    out = out.convert('RGB')
                                buf = io.BytesIO()
                                out.save(buf, format='JPEG', quality=90)
                                working_bytes = buf.getvalue()
                        except Exception as e:
                            logger.error(f"尺寸调整失败 {original_filename}: {e}")
                            working_bytes = original_bytes
                    
                    # 水印（若勾选）
                    if watermark_enabled:
                        try:
                            working_bytes = add_watermark(working_bytes)
                        except Exception as e:
                            logger.error(f"添加水印失败 {original_filename}: {e}")
                            # 水印失败仍可继续转换
                    
                    # 扩展名转换：若原始扩展名不是 .jpg，则转为JPG
                    if not is_jpg:
                        try:
                            with Image.open(io.BytesIO(working_bytes)) as im:
                                if im.mode != 'RGB':
                                    im = im.convert('RGB')
                                buf = io.BytesIO()
                                im.save(buf, format='JPEG', quality=90)
                                working_bytes = buf.getvalue()
                        except Exception as e:
                            logger.error(f"转换为JPG失败 {original_filename}: {e}")
                            # 继续使用现有字节
                    
                    # 输出文件统一为 .jpg
                    output_filename = f"{name}.jpg"
                    output_path = os.path.join(output_dir, output_filename)
                    with open(output_path, 'wb') as f:
                        f.write(working_bytes)
                    
                    data_dict = {
                        'filename': output_filename,
                        'prompt': f"批量处理: {original_filename}",
                        'style': '',
                        'width': int(self.width_spin.value()) if resize_enabled else None,
                        'height': int(self.height_spin.value()) if resize_enabled else None
                    }
                    self.image_display.add_image(data_dict, working_bytes, output_path)
                    
                    processed_count += 1
                
                except Exception as e:
                    logger.error(f"处理文件 {file_path} 时出错: {str(e)}")
                    # 出错时跳过当前文件，继续处理剩余文件
                    continue
            
            # 弹窗提示处理结果
            QMessageBox.information(self, "提示", f"共选择 {total_selected} 张图片，处理了 {processed_count} 张图片")
    
    def open_output_directory(self):
        """打开图片输出目录"""
        try:
            # 从配置文件获取输出目录
            output_dir = self.config_manager.get('PATH', 'image_output_directory', fallback='./output/image')
            
            # 转换为绝对路径
            output_dir = os.path.abspath(output_dir)
            
            # 确保目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 使用系统默认程序打开目录
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                os.startfile(output_dir)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", output_dir])
            else:  # Linux
                subprocess.run(["xdg-open", output_dir])
                
        except Exception as e:
            QMessageBox.warning(self, "警告", f"无法打开输出目录: {str(e)}")
    
    def set_controls_enabled(self, enabled):
        """设置所有控件的启用/禁用状态"""
        # 侧边栏控件
        self.open_file_btn.setEnabled(enabled)
        # 提示词表保持可滚动，即使在禁用状态下也不整体禁用
        # 改为仅锁定表内交互（复选框与编辑），保留滚动条交互
        self._set_prompt_table_locked(not enabled)
        
        # 控制面板控件
        self.model_combo.setEnabled(enabled)
        self.size_combo.setEnabled(enabled)
        self.prompt_input.setEnabled(enabled)
        self.generate_btn.setEnabled(enabled)
        self.config_dir_btn.setEnabled(enabled)
        self.open_dir_btn.setEnabled(enabled)
        self.batch_generate_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        self.add_watermark_btn.setEnabled(enabled)
        self.upload_attachment_btn.setEnabled(enabled)
        self.view_attachment_btn.setEnabled(enabled)
        self.num_images_spin.setEnabled(enabled)
        self.cartoon_style_checkbox.setEnabled(enabled)
        self.role_consistency_checkbox.setEnabled(enabled)
        self.watermark_checkbox.setEnabled(enabled)
        self.auto_crop_checkbox.setEnabled(enabled)
        self.select_all_btn.setEnabled(enabled)
        self.addon_prompt_input.setEnabled(enabled)

    def _on_prompt_mode_changed(self, is_story):
        if is_story:
            self.addon_prompt_input.setPlainText(BATCH_CREATE_STORY_PROMPT)
        else:
            if self.common_prompt_radio.isChecked():
                self.addon_prompt_input.setPlainText(BATCH_CREATE_COMMON_PROMPT)
        # 宽高输入框：生成中始终锁定；解锁时仅当“切图”勾选才可用
        if enabled:
            is_crop = self.auto_crop_checkbox.isChecked()
            self.width_spin.setEnabled(is_crop)
            self.height_spin.setEnabled(is_crop)
        else:
            self.width_spin.setEnabled(False)
            self.height_spin.setEnabled(False)

    def _set_prompt_table_locked(self, locked: bool):
        """锁定/解锁提示词表的交互：
        - locked=True：选择列（复选框）不可更改，Prompt列不可编辑；滚动保留
        - locked=False：恢复复选框可勾选，Prompt列可编辑
        """
        if not hasattr(self, 'prompt_table') or self.prompt_table is None:
            return
        rows = self.prompt_table.rowCount()
        for i in range(rows):
            # 选择列（复选框）
            chk_item = self.prompt_table.item(i, 0)
            if chk_item:
                if locked:
                    # 保留显示但不可勾选
                    chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                else:
                    chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            # Prompt列
            prompt_item = self.prompt_table.item(i, 1)
            if prompt_item:
                if locked:
                    # 允许选中以便复制/右键菜单，但不可编辑
                    prompt_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                else:
                    prompt_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)

    def update_crop_dimensions_enabled(self):
        """根据“切图”复选框状态更新宽高输入框的启用状态"""
        is_crop = self.auto_crop_checkbox.isChecked()
        # 若当前整体控件被禁用（生成中），保持禁用
        all_enabled = self.generate_btn.isEnabled()
        should_enable = is_crop and all_enabled
        if hasattr(self, 'width_spin'):
            self.width_spin.setEnabled(should_enable)
        if hasattr(self, 'height_spin'):
            self.height_spin.setEnabled(should_enable)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        event.accept()

    def stop_all_tasks(self):
        try:
            if self.worker and self.worker.isRunning():
                print("停止文生图工作线程...")
                self.worker.stop()
                self.worker.wait()
        except Exception:
            pass
        try:
            if hasattr(self, 'img2img_page') and self.img2img_page:
                print("停止图生图线程池...")
                self.img2img_page.stop_all_tasks()
        except Exception:
            pass
        try:
            if hasattr(self, 'avatar_page') and self.avatar_page:
                print("停止角色皮肤线程池...")
                self.avatar_page.stop_all_tasks_avatar()
        except Exception:
            pass
    
    def show_prompt_context_menu(self, position):
        """显示提示词表格的右键菜单"""
        # 获取点击位置的索引
        index = self.prompt_table.indexAt(position)
        if not index.isValid():
            return
        
        # 获取选中行的数据
        row = index.row()
        if row >= len(self.prompt_data):
            return
        
        # 创建右键菜单
        context_menu = QMenu(self)
        
        # 添加复制动作
        copy_action = context_menu.addAction("复制")
        copy_action.triggered.connect(lambda: self.copy_prompt_with_style(row))
        
        # 显示菜单
        context_menu.exec(self.prompt_table.mapToGlobal(position))
    
    def copy_prompt_with_style(self, row):
        """复制提示词（包含style列内容）到剪贴板"""
        if row >= len(self.prompt_data):
            return
        
        data = self.prompt_data[row]
        prompt = data.get('prompt', '')
        style = data.get('style', '')
        
        # 拼接提示词和style
        if style:
            full_prompt = f"{prompt}, {style}"
        else:
            full_prompt = prompt
        
        # 复制到剪贴板
        clipboard = QApplication.clipboard()
        clipboard.setText(full_prompt)
        
        # 显示Toast提示（统一使用Toast）
        Toast.show_message("提示词已复制到剪贴板", self)
