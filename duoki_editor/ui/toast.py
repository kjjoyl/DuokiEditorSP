"""
Toast 浮动提示组件
提供非模态的浮动提示功能
"""

from PyQt6.QtWidgets import QWidget, QLabel, QGraphicsOpacityEffect
from PyQt6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QRect
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt
import weakref


class ToastWidget(QWidget):
    """单个Toast提示组件"""
    
    finished = pyqtSignal()  # 动画完成信号
    
    def __init__(self, message, parent=None, duration=3000):
        super().__init__(parent)
        self.message = message
        self.duration = duration
        
        # 设置窗口属性
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # 创建标签
        self.label = QLabel(message, self)
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 12px 20px;
                background-color: rgba(0, 0, 0, 0.8);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
        """)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 调整大小
        self.label.adjustSize()
        self.resize(self.label.size())
        
        # 创建透明度效果
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        
        # 创建动画
        self.fade_in_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in_animation.setDuration(300)
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.fade_out_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out_animation.setDuration(300)
        self.fade_out_animation.setStartValue(1.0)
        self.fade_out_animation.setEndValue(0.0)
        self.fade_out_animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_out_animation.finished.connect(self.finished.emit)
        
        # 创建定时器
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.start_fade_out)
    
    def show_toast(self):
        """显示Toast"""
        self.show()
        self.fade_in_animation.start()
        self.timer.start(self.duration)
    
    def start_fade_out(self):
        """开始淡出动画"""
        self.fade_out_animation.start()
    
    def paintEvent(self, event):
        """绘制背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制圆角矩形背景
        rect = self.rect()
        painter.setBrush(QBrush(QColor(0, 0, 0, 200)))
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1))
        painter.drawRoundedRect(rect, 8, 8)


class ToastManager(QWidget):
    """Toast管理器，负责管理多个Toast的显示位置和队列"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        # 共享的全局状态：同一个父组件共享同一列表，避免多实例导致重叠
        if not hasattr(ToastManager, "_global_state"):
            ToastManager._global_state = weakref.WeakKeyDictionary()
        state = ToastManager._global_state.get(parent)
        if state is None:
            state = {"toasts": []}
            ToastManager._global_state[parent] = state
        self.active_toasts = state["toasts"]
        
        # 注册单例管理器，便于静态助手统一复用
        if not hasattr(ToastManager, "_managers"):
            ToastManager._managers = weakref.WeakKeyDictionary()
        if parent is not None and parent not in ToastManager._managers:
            ToastManager._managers[parent] = self
        self.toast_spacing = 10  # Toast之间的间距
        
    @classmethod
    def get_manager(cls, parent):
        """获取指定父组件的ToastManager单例"""
        if not hasattr(ToastManager, "_managers"):
            ToastManager._managers = weakref.WeakKeyDictionary()
        manager = ToastManager._managers.get(parent)
        if manager is None:
            manager = ToastManager(parent)
            ToastManager._managers[parent] = manager
        return manager

    def show_toast(self, message, duration=3000):
        """显示一个Toast提示"""
        toast = ToastWidget(message, self.parent_widget, duration)
        toast.finished.connect(lambda: self.remove_toast(toast))
        
        # 计算位置
        self.position_toast(toast)
        
        # 添加到活跃列表
        self.active_toasts.append(toast)
        
        # 显示Toast
        toast.show_toast()
        
        return toast
    
    def position_toast(self, toast):
        """计算Toast的显示位置"""
        if not self.parent_widget:
            return
            
        parent_rect = self.parent_widget.rect()
        toast_width = toast.width()
        toast_height = toast.height()
        
        # 计算基础位置（水平居中，顶部）
        x = (parent_rect.width() - toast_width) // 2
        y = 20
        
        # 如果有其他活跃的Toast，需要向下偏移
        for existing_toast in self.active_toasts:
            if existing_toast.isVisible():
                y += existing_toast.height() + self.toast_spacing
        
        # 设置位置
        toast.move(x, y)
    
    def remove_toast(self, toast):
        """移除Toast并重新排列其他Toast"""
        if toast in self.active_toasts:
            self.active_toasts.remove(toast)
            toast.deleteLater()
            
            # 重新排列剩余的Toast
            self.rearrange_toasts()
    
    def rearrange_toasts(self):
        """重新排列所有活跃的Toast"""
        if not self.parent_widget:
            return
            
        parent_rect = self.parent_widget.rect()
        y = 20
        for toast in self.active_toasts:
            if toast.isVisible():
                # 重新计算水平居中位置
                x = (parent_rect.width() - toast.width()) // 2
                toast.move(x, y)
                y += toast.height() + self.toast_spacing
    
    def show_success(self, message, duration=3000):
        """显示成功类型的Toast"""
        return self.show_toast(f"✅ {message}", duration)
    
    def show_error(self, message, duration=5000):
        """显示错误类型的Toast"""
        return self.show_toast(f"❌ {message}", duration)
    
    def show_warning(self, message, duration=4000):
        """显示警告类型的Toast"""
        return self.show_toast(f"⚠️ {message}", duration)
    
    def show_info(self, message, duration=3000):
        """显示信息类型的Toast"""
        return self.show_toast(f"ℹ️ {message}", duration)


class Toast:
    """静态助手，统一调度同一父组件的ToastManager以进行堆叠显示"""
    @staticmethod
    def show_message(message, parent, duration=3000):
        manager = ToastManager.get_manager(parent)
        return manager.show_toast(message, duration)

    @staticmethod
    def success(message, parent, duration=3000):
        manager = ToastManager.get_manager(parent)
        return manager.show_success(message, duration)

    @staticmethod
    def error(message, parent, duration=5000):
        manager = ToastManager.get_manager(parent)
        return manager.show_error(message, duration)

    @staticmethod
    def warning(message, parent, duration=4000):
        manager = ToastManager.get_manager(parent)
        return manager.show_warning(message, duration)

    @staticmethod
    def info(message, parent, duration=3000):
        manager = ToastManager.get_manager(parent)
        return manager.show_info(message, duration)