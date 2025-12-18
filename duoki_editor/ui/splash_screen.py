from PyQt6.QtWidgets import QSplashScreen, QProgressBar, QVBoxLayout, QLabel, QWidget, QPlainTextEdit
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QPainter, QColor, QRegion, QPainterPath, QTextCursor
import os
import sys

class SplashScreen(QSplashScreen):
    """启动页面，显示数据加载进度"""
    
    def __init__(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        image_path = os.path.join(base_dir, "resources", "images", "launcher.png")
        
        # 尝试加载背景图片
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            # 如果图片加载成功，调整到合适的尺寸
            if not pixmap.isNull():
                pixmap = pixmap.scaled(500, 300, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            else:
                # 图片加载失败，使用默认背景
                pixmap = QPixmap(QSize(500, 300))
                pixmap.fill(QColor(240, 240, 240))
        else:
            # 图片文件不存在，使用默认背景
            pixmap = QPixmap(QSize(500, 300))
            pixmap.fill(QColor(240, 240, 240))
        
        # 使用pixmap初始化QSplashScreen
        super().__init__(pixmap)
        
        # 设置窗口标志 - 无边框且置顶
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        # 设置窗口圆角样式
        self.setStyleSheet("""
            QSplashScreen {
                border-radius: 15px;
                background-color: transparent;
            }
        """)
        
        # 设置窗口遮罩以实现真正的圆角效果
        self.setMask(self.create_rounded_mask())
        
        # 创建布局
        self.layout_widget = QWidget(self)
        layout = QVBoxLayout(self.layout_widget)
        
        # 顶部日志输入框
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setStyleSheet("QPlainTextEdit{background: transparent; color: white; border: none; font-size: 11pt;}" )
        self.log_edit.setMaximumHeight(80)
        layout.addWidget(self.log_edit)
        # 添加标题
        self.title_label = QLabel("多奇编辑器")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: white;")
        layout.addWidget(self.title_label)
        
        # 添加空白间距
        spacer = QWidget()
        spacer.setMinimumHeight(150)  # 增加50像素的垂直间距
        layout.addWidget(spacer)
        
        # 添加状态标签
        self.status_label = QLabel("正在从服务器拉取数据...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 12pt; color: white;")
        layout.addWidget(self.status_label)
        
        # 添加进度文本
        self.progress_label = QLabel("0/0")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: white;")
        layout.addWidget(self.progress_label)
        
        # 添加进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid white;
                border-radius: 5px;
                text-align: center;
                height: 25px;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                width: 10px;
                margin: 0.5px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # 设置布局
        self.layout_widget.setLayout(layout)
        self.layout_widget.setGeometry(0, 0, 500, 300)
        
        # 删除这一行，因为已经在前面设置了窗口标志
        # self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
    
    def update_progress(self, current, total, message=None):
        """更新进度信息"""
        if message:
            self.status_label.setText(message)
        
        self.progress_bar.setValue(int(current / total * 100))
        self.progress_label.setText(f"{current}/{total}")
        
        # 刷新界面
        self.repaint()
    
    def capture_console(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        self._redirector = _ConsoleRedirector()
        self._redirector.message.connect(self._append_log_text)
        sys.stdout = self._redirector
        sys.stderr = self._redirector
        print("[Splash] 控制台输出已重定向到启动界面")
    
    def restore_console(self):
        if hasattr(self, '_old_stdout'):
            sys.stdout = self._old_stdout
        if hasattr(self, '_old_stderr'):
            sys.stderr = self._old_stderr
        print("[Splash] 控制台输出已恢复到标准输出")
    
    def _append_log_text(self, text: str):
        if not text:
            return
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)
        self.log_edit.insertPlainText(text)
        self.log_edit.moveCursor(QTextCursor.MoveOperation.End)

    def create_rounded_mask(self):
        """创建圆角遮罩"""
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 10, 10)
        region = QRegion(path.toFillPolygon().toPolygon())
        return region

class _ConsoleRedirector(QObject):
    message = pyqtSignal(str)
    def write(self, text):
        if text:
            self.message.emit(text)
    def flush(self):
        pass
