"""
抽屉式控件模块
用于替换树形结构，提供折叠/展开功能
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QLabel, QScrollArea, QFrame, QListWidget, QListWidgetItem,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QColor

class AccordionItem(QWidget):
    """抽屉项组件"""
    
    clicked = pyqtSignal(str)  # 点击信号，传递文件路径
    toggled = pyqtSignal(object, bool)  # 展开/折叠信号，传递自身和状态
    
    def __init__(self, title, data=None, parent=None):
        super().__init__(parent)
        self.title = title
        self.data = data  # 存储文件路径或其他数据
        self.is_expanded = False
        self.content_widget = None
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        # 创建主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 创建标题栏
        self.header = QFrame()
        self.header.setObjectName("accordion-header")
        self.header.setMinimumHeight(30)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 0, 10, 0)
        
        # 添加展开/折叠图标
        self.toggle_button = QPushButton("▶")  # 使用Unicode字符作为图标
        self.toggle_button.setObjectName("accordion-toggle-button")
        self.toggle_button.setFixedSize(20, 20)
        self.toggle_button.clicked.connect(self.toggle_content)
        header_layout.addWidget(self.toggle_button)
        
        # 添加标题
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("accordion-title")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        # 点击标题栏时切换展开/折叠状态
        self.header.mousePressEvent = self.header_clicked
        
        # 添加标题栏到主布局
        self.main_layout.addWidget(self.header)
        
        # 创建内容区域（初始隐藏）
        self.content_container = QWidget()
        self.content_container.setObjectName("accordion-content")
        self.content_container.setVisible(False)
        
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # 添加内容区域到主布局
        self.main_layout.addWidget(self.content_container)
    
    def header_clicked(self, event):
        """处理标题栏点击事件"""
        self.toggle_content()
    
    def toggle_content(self):
        """切换内容区域的显示/隐藏状态"""
        self.is_expanded = not self.is_expanded
        self.content_container.setVisible(self.is_expanded)
        
        # 更新展开/折叠图标
        self.toggle_button.setText("▼" if self.is_expanded else "▶")
        
        # 发送展开/折叠信号
        self.toggled.emit(self, self.is_expanded)
    
    def set_content(self, widget):
        """设置内容区域的控件"""
        # 清空现有内容
        layout = self.content_container.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 添加新控件
        self.content_widget = widget
        layout.addWidget(widget)
    
    def expand(self):
        """展开内容区域"""
        if not self.is_expanded:
            self.toggle_content()
    
    def collapse(self):
        """折叠内容区域"""
        if self.is_expanded:
            self.toggle_content()


class FileListWidget(QListWidget):
    """文件列表控件"""
    
    file_clicked = pyqtSignal(str)  # 文件点击信号，传递文件路径
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("file-list")
        
        # 设置样式
        self.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 5px 10px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:hover {
                background-color: #3c3f41;
            }
            QListWidget::item:selected {
                background-color: #4b6eaf;
            }
        """)
        
        # 连接信号
        self.itemClicked.connect(self.on_item_clicked)
    
    def on_item_clicked(self, item):
        """处理项点击事件"""
        # 获取文件路径
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path:
            self.file_clicked.emit(file_path)


class AccordionWidget(QWidget):
    """抽屉式控件"""
    
    file_selected = pyqtSignal(str)  # 文件选择信号，传递文件路径
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []  # 存储抽屉项
        self.current_expanded_item = None  # 当前展开的抽屉项
        self.init_ui()
        
        # 监听应用程序的调色板变化，以便在主题切换时更新样式
        app = QApplication.instance()
        if app:
            app.paletteChanged.connect(self.update_theme_style)
    
    def init_ui(self):
        """初始化UI"""
        # 创建主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        # 创建内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 设置顶部对齐
        
        # 设置滚动区域的控件
        self.scroll_area.setWidget(self.content_widget)
        
        # 添加滚动区域到主布局
        main_layout.addWidget(self.scroll_area)
        
        # 设置样式
        self.setStyleSheet(self._get_theme_style())
    
    def add_item(self, title, data=None):
        """添加抽屉项"""
        item = AccordionItem(title, data)
        self.items.append(item)
        
        # 将项添加到布局中
        self.content_layout.addWidget(item)
        
        # 连接展开/折叠信号
        item.toggled.connect(self.on_item_toggled)
        
        # 返回创建的抽屉项
        return item
        
    def on_item_toggled(self, item, is_expanded):
        """处理抽屉项展开/折叠事件"""
        if is_expanded:
            # 折叠其他所有抽屉项
            for other_item in self.items:
                if other_item != item and other_item.is_expanded:
                    other_item.collapse()
            
            # 设置当前展开的抽屉项
            self.current_expanded_item = item
            
            # 重新排列抽屉项，使展开的抽屉项占据最大高度
            self.rearrange_items()
        else:
            # 如果当前折叠的是展开项，则清除当前展开项引用
            if self.current_expanded_item == item:
                self.current_expanded_item = None
            
    def rearrange_items(self):
        """重新排列抽屉项，使展开的抽屉项占据最大高度"""
        if not self.current_expanded_item:
            return
            
        # 清空布局
        for i in reversed(range(self.content_layout.count())):
            self.content_layout.takeAt(i)
            
        # 重新添加抽屉项，展开的抽屉项放在最后
        for item in self.items:
            if item != self.current_expanded_item:
                self.content_layout.addWidget(item)
                
        # 添加展开的抽屉项
        self.content_layout.addWidget(self.current_expanded_item)
        
        # 添加弹性空间，使展开的抽屉项占据最大高度
        self.content_layout.addStretch(1)
        
    def update_theme_style(self):
        """更新主题样式"""
        self.setStyleSheet(self._get_theme_style())
        
    def _get_theme_style(self):
        """获取当前主题的样式"""
        # 检测当前应用的主题
        app = QApplication.instance()
        
        # 判断是否为暗色主题
        is_dark_theme = True
        if hasattr(app, 'palette'):
            palette = app.palette()
            bg_color = palette.color(palette.ColorRole.Window)
            is_dark_theme = bg_color.lightness() < 128
        
        if is_dark_theme:
            return """
                QWidget#accordion-header {
                    background-color: #2d2d30;
                    border-bottom: 1px solid #3f3f46;
                }
                QWidget#accordion-header:hover {
                    background-color: #3e3e42;
                }
                QLabel#accordion-title {
                    color: #cccccc;
                    font-weight: bold;
                }
                QPushButton#accordion-toggle-button {
                    background: transparent;
                    border: none;
                    color: #cccccc;
                }
                QWidget#accordion-content {
                    background-color: #252526;
                    border-bottom: 1px solid #3f3f46;
                }
                QListWidget#file-list {
                    background-color: #252526;
                    border: none;
                    outline: none;
                }
                QListWidget#file-list::item {
                    padding: 5px 10px;
                    border-bottom: 1px solid #3f3f46;
                    color: #cccccc;
                }
                QListWidget#file-list::item:hover {
                    background-color: #3e3e42;
                }
                QListWidget#file-list::item:selected {
                    background-color: #0e639c;
                    color: #ffffff;
                }
            """
        else:
            return """
                QWidget#accordion-header {
                    background-color: #f5f5f5;
                    border-bottom: 1px solid #e0e0e0;
                }
                QWidget#accordion-header:hover {
                    background-color: #e9e9e9;
                }
                QLabel#accordion-title {
                    color: #333333;
                    font-weight: bold;
                }
                QPushButton#accordion-toggle-button {
                    background: transparent;
                    border: none;
                    color: #333333;
                }
                QWidget#accordion-content {
                    background-color: #ffffff;
                    border-bottom: 1px solid #e0e0e0;
                }
                QListWidget#file-list {
                    background-color: #ffffff;
                    border: none;
                    outline: none;
                }
                QListWidget#file-list::item {
                    padding: 5px 10px;
                    border-bottom: 1px solid #e0e0e0;
                    color: #333333;
                }
                QListWidget#file-list::item:hover {
                    background-color: #e9e9e9;
                }
                QListWidget#file-list::item:selected {
                    background-color: #007acc;
                    color: #ffffff;
                }
            """
        
        # 默认折叠
        item.collapse()
        
        return item
    
    def on_item_toggled(self, item, is_expanded):
        """处理抽屉项展开/折叠事件"""
        if is_expanded:
            # 如果有其他展开的抽屉，先折叠它
            if self.current_expanded_item and self.current_expanded_item != item:
                self.current_expanded_item.collapse()
            
            # 更新当前展开的抽屉
            self.current_expanded_item = item
        elif self.current_expanded_item == item:
            # 如果当前展开的抽屉被折叠，清除引用
            self.current_expanded_item = None
    
    def clear(self):
        """清空所有抽屉项"""
        self.current_expanded_item = None
        
        for item in self.items:
            self.content_layout.removeWidget(item)
            item.deleteLater()
        
        self.items = []