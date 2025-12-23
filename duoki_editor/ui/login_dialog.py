from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLabel, QMessageBox, QWidget)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QNetworkCookie
import os
import sys
from urllib.parse import urlparse
from ..utils.cache_manager import CacheManager
from ..utils.config_manager import ConfigManager

class LoginWebPage(QWebEnginePage):
    """自定义WebPage类，用于处理登录页面的特殊逻辑"""
    
    # 定义信号，用于通知登录成功或失败
    login_success = pyqtSignal(str)  # 传递包含认证信息的URL
    login_failed = pyqtSignal()
    
    def __init__(self, profile=None, parent=None):
        if profile:
            super().__init__(profile, parent)
        else:
            super().__init__(parent)
        self.loadFinished.connect(self.on_load_finished)
        self.urlChanged.connect(self.on_url_changed)
    
    def on_load_finished(self, success):
        """页面加载完成时的回调"""
        if success:
            current_url = self.url().toString()
            print(f"页面加载完成")
        else:
            print("页面加载失败")
    
    def on_url_changed(self, url):
        """URL变化时的回调"""
        url_string = url.toString()
        
        # 检查是否是登录成功的回调URL
        if self.is_login_success_url(url_string):
            print("检测到登录成功")
            self.login_success.emit(url_string)
        elif self.is_login_failed_url(url_string):
            print("检测到登录失败")
            self.login_failed.emit()
    
    def is_login_success_url(self, url):
        """判断是否是登录成功的URL"""
        # 检查URL中是否包含认证相关参数
        parsed_url = urlparse(url)
        query_string = parsed_url.query.lower()
        
        # 检查是否包含token、cookie或其他认证参数
        success_indicators = ['lgtk=', 'token=', 'cookie=', 'auth=']
        return any(indicator in query_string for indicator in success_indicators)
    
    def is_login_failed_url(self, url):
        """判断是否是登录失败的URL"""
        # 检查是否跳转到注册说明页或错误页
        failed_indicators = ['register', 'signup', 'error', 'fail']
        return any(indicator in url.lower() for indicator in failed_indicators)

class LoginDialog(QDialog):
    """微信登录对话框"""
    
    # 定义信号
    login_success = pyqtSignal(str)  # 传递cookie和用户信息
    login_cancelled = pyqtSignal()
    
    def __init__(self, login_url, parent=None):
        super().__init__(parent)
        self.login_url = login_url
        self.auth_data = None
        self.collected_cookies = {}  # 收集到的cookies
        self.cookie_check_timer = QTimer()  # 用于定期检查cookie的定时器
        self.cookie_check_timer.timeout.connect(self.check_for_auth_cookies)
        self.login_successful = False  # 标记是否登录成功
        self.cache_manager = CacheManager()
        self.init_ui()
        self.setup_webview()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("微信登录")
        self.setModal(True)
        
        # 设置9:16的尺寸比例，适合移动端登录页面
        width = 450
        height = 600 # 9:16比例
        self.resize(width, height)
        
        # 设置窗口标志，确保显示在任务栏
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | 
                           Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        
        # 设置窗口图标
        self.set_window_icon()
        
        # 创建主布局，去掉边距以消除黑条
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # 去掉边距
        layout.setSpacing(0)  # 去掉间距
        
        # 创建WebView，占据大部分空间
        self.web_view = QWebEngineView()
        # 设置WebView样式，去掉边框
        self.web_view.setStyleSheet("QWebEngineView { border: none; }")
        layout.addWidget(self.web_view)
        
        # 创建底部控制栏
        control_widget = QWidget()
        control_widget.setFixedHeight(50)  # 固定高度
        control_widget.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                border-top: 1px solid #ddd;
            }
        """)
        
        # 创建按钮布局
        button_layout = QHBoxLayout(control_widget)
        button_layout.setContentsMargins(10, 10, 10, 10)
        
        # 添加提示标签
        tip_label = QLabel("请使用微信扫码登录")
        tip_label.setStyleSheet("font-size: 12px; color: #666;")
        button_layout.addWidget(tip_label)
        
        button_layout.addStretch()
        
        # 清除缓存按钮
        self.clear_cache_button = QPushButton("清除缓存")
        self.clear_cache_button.setFixedSize(70, 30)
        self.clear_cache_button.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ff5252;
            }
        """)
        self.clear_cache_button.clicked.connect(self.clear_cookies_cache)
        button_layout.addWidget(self.clear_cache_button)

        # 刷新按钮
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setFixedSize(60, 30)
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
        """)
        self.refresh_button.clicked.connect(self.refresh_page)
        button_layout.addWidget(self.refresh_button)

        # 取消按钮
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setFixedSize(60, 30)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #ccc;
                color: #333;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #bbb;
            }
        """)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addWidget(control_widget)
        
        self.setLayout(layout)
    
    def set_window_icon(self):
        """设置窗口图标"""
        try:
            # 统一为 duoki_editor/resources 路径（开发与打包一致）
            base_dir = os.path.dirname(os.path.dirname(__file__))
            if sys.platform == 'darwin':
                icon_path = os.path.join(base_dir, "resources", "icons", "app_icon.icns")
            else:
                icon_path = os.path.join(base_dir, "resources", "icons", "app_icon.ico")
            
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"设置窗口图标失败: {e}")
    
    def setup_webview(self):
        """设置WebView"""
        # 创建自定义profile以便监听cookies
        self.profile = QWebEngineProfile("login_profile", self)
        
        # 设置User-Agent
        self.profile.setHttpUserAgent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        
        # 获取cookie store并监听cookie添加事件
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)
        
        # 创建自定义页面
        self.web_page = LoginWebPage(self.profile)
        self.web_view.setPage(self.web_page)
        
        # 连接信号
        self.web_page.login_success.connect(self.on_login_success)
        self.web_page.login_failed.connect(self.on_login_failed)
        
        # 加载登录页面
        if self.login_url:
            print(f"加载登录页面: {self.login_url}")
            self.web_view.load(QUrl(self.login_url))
            # 开始定期检查cookie
            self.cookie_check_timer.start(2000)  # 每2秒检查一次
        else:
            cfg = ConfigManager()
            portal_url = cfg.get_server_url()
            print(f"加载portal页面: {portal_url}")
            self.web_view.load(QUrl(portal_url))
            # 开始定期检查cookie
            self.cookie_check_timer.start(2000)  # 每2秒检查一次
    
    def refresh_page(self):
        """刷新页面"""
        self.web_view.reload()
    
    def on_cookie_added(self, cookie):
        """当有新cookie添加时的回调"""
        domain = cookie.domain()
        name = cookie.name().data().decode('utf-8')
        value = cookie.value().data().decode('utf-8')
        path = cookie.path()
        expires = cookie.expirationDate().toString() if cookie.expirationDate().isValid() else "Session"
        
        print(f"=== 收到新Cookie ===")
        print(f"名称: {name}")
        print(f"值: {value}")
        print(f"域名: {domain}")
        print(f"路径: {path}")
        print(f"过期时间: {expires}")
        print(f"是否安全: {cookie.isSecure()}")
        print(f"是否HttpOnly: {cookie.isHttpOnly()}")
        print("=" * 30)
        
        # 只收集目标域名的cookie
        if 'qidianlingzhi.com' in domain:
            self.collected_cookies[name] = value
            print(f"✅ 已收集目标Cookie: {name}={value}")
        else:
            print(f"❌ 跳过非目标域名Cookie: {domain}")
    
    def check_for_auth_cookies(self):
        """检查是否收集到了认证相关的cookie"""
        if not self.collected_cookies:
            return
            
        print(f"当前收集到的cookies: {list(self.collected_cookies.keys())}")
        
        # 检查是否有认证相关的cookie
        auth_cookie_names = ['lgtk', 'token', 'sessionid', 'auth', 'login', 'session', 'jwt']
        
        for cookie_name in auth_cookie_names:
            if cookie_name in self.collected_cookies:
                print(f"检测到认证cookie: {cookie_name}")
                self.cookie_check_timer.stop()
                self.handle_cookie_login()
                return
        
        # 检查是否有任何包含认证信息的cookie（更宽松的检测）
        for name, value in self.collected_cookies.items():
            # 检查cookie名称是否包含认证关键词
            if any(keyword in name.lower() for keyword in ['token', 'auth', 'session', 'login', 'jwt', 'user']):
                print(f"检测到可能的认证cookie: {name}")
                self.cookie_check_timer.stop()
                self.handle_cookie_login()
                return
            
            # 检查cookie值是否足够长（可能是token）
            if len(value) > 30:
                print(f"检测到长值cookie（可能是token）: {name}")
                self.cookie_check_timer.stop()
                self.handle_cookie_login()
                return
        
        # 如果收集到了任何来自目标域名的cookie，也尝试登录
        if len(self.collected_cookies) > 0:
            print(f"收集到 {len(self.collected_cookies)} 个cookie，尝试登录")
            self.cookie_check_timer.stop()
            self.handle_cookie_login()
    
    def handle_cookie_login(self):
        """处理通过cookie的登录"""
        print("\n🍪 === 开始处理Cookie登录 ===")
        print(f"收集到的Cookie数量: {len(self.collected_cookies)}")
        
        if self.collected_cookies:
            print("📋收集到的所有Cookie:")
            for name, value in self.collected_cookies.items():
                print(f"  - {name}: {value}")
        
        # 将收集到的cookies转换为cookie字符串
        cookie_string = "; ".join([f"{name}={value}" for name, value in self.collected_cookies.items()])
        
        if cookie_string:
            # 发送登录成功信号
            self.login_successful = True
            self.cleanup_webengine()
            self.login_success.emit(cookie_string)
            self.accept()
        else:
            print("❌ 没有收集到有效的cookie")
            print("=" * 50)
    
    def get_all_cookies_from_store(self):
        """从cookie store获取所有cookie（备用方法）"""
        print("尝试从cookie store获取所有cookie")
        # 这个方法可以作为备用，但QWebEngineCookieStore没有直接获取所有cookie的方法
        # 我们主要依赖cookieAdded信号来收集cookie
    
    def on_login_success(self, url):
        """登录成功回调"""
        print(f"\n🎉 === URL登录成功 ===")
        print(f"回调URL: {url}")
        
        # 从URL中提取认证信息
        from duoki_editor.core.auth_manager import AuthManager
        auth_manager = AuthManager()
        success, cookie = auth_manager.extract_auth_from_url(url)
        
        if success and cookie:
            print(f"Cookie内容: {cookie}")
            
            # 验证cookie是否有效
            if auth_manager.validate_cookie(cookie):
                print("✅ Cookie验证成功！")
                self.login_successful = True
                self.cleanup_webengine()
                self.login_success.emit(cookie)
                self.accept()
            else:
                print("❌ Cookie验证失败")
                self.handle_cookie_login()
        else:
            print("❌ 未能从URL中提取有效的认证信息")
            print(f"提取结果: success={success}, cookie={cookie}")
            self.handle_cookie_login()
    
    def on_login_failed(self):
        """登录失败回调"""
        print("登录失败")
        # 显示登录失败信息，但不阻塞用户操作
        # 用户可以继续尝试登录或关闭窗口退出应用
        print("检测到登录失败或跳转到注册页面")
        print("用户可以继续尝试登录或关闭窗口退出应用")
    
    def clear_cookies_cache(self):
        """清除QtWebEngine的cookies和缓存"""
        try:
            # 获取缓存信息
            cache_info = self.cache_manager.get_cache_info()
            cache_size = self.cache_manager.format_size(cache_info["total_size"])
            
            # 显示确认对话框
            reply = QMessageBox.question(
                self, 
                "确认清除缓存", 
                f"确定要清除所有cookies和缓存数据吗？\n\n"
                f"缓存大小: {cache_size}\n"
                f"文件数量: {cache_info['file_count']}\n"
                f"缓存路径: {len(cache_info['cache_paths'])} 个\n\n"
                f"这将清除所有登录状态和浏览数据。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                print("🧹 开始清除QtWebEngine缓存...")
                
                # 使用缓存管理器清除所有缓存
                results = self.cache_manager.clear_all_cache(self.profile)
                
                # 清除本地cookies字典
                self.collected_cookies.clear()

                from duoki_editor.utils.config_manager import ConfigManager
                config_manager = ConfigManager()
                config_manager.set('General', 'user_name', '')
                config_manager.save()
                print("已清空配置中的用户名参数")
                
                # 构建结果消息
                message_parts = ["缓存清除完成！\n"]
                
                if results["profile_cleared"]:
                    message_parts.append("✅ WebEngine Profile缓存已清除")
                
                if results["disk_cleared_paths"]:
                    message_parts.append(f"✅ 已清除 {len(results['disk_cleared_paths'])} 个磁盘缓存目录")
                
                if results["disk_failed_paths"]:
                    message_parts.append(f"⚠️ {len(results['disk_failed_paths'])} 个目录清除失败")
                
                message_parts.append("\n页面将重新加载。")
                
                # 显示结果消息
                if results["total_success"]:
                    QMessageBox.information(self, "清除完成", "\n".join(message_parts))
                else:
                    QMessageBox.warning(self, "部分清除完成", "\n".join(message_parts))
                
                # 重新加载页面
                self.refresh_page()
                
                print("🎉 缓存清除完成")
                    
        except Exception as e:
            print(f"❌ 清除缓存时出错: {e}")
            QMessageBox.critical(self, "错误", f"清除缓存时发生错误：{str(e)}")

    def cleanup_webengine(self):
        """清理WebEngine资源"""
        try:
            if hasattr(self, 'web_view') and self.web_view:
                # 停止加载
                self.web_view.stop()
                # 清理页面
                if hasattr(self.web_view, 'page') and self.web_view.page():
                    self.web_view.page().deleteLater()
                # 清理视图
                self.web_view.deleteLater()
                self.web_view = None
            
            if hasattr(self, 'profile') and self.profile:
                # 清理profile
                self.profile.deleteLater()
                self.profile = None
        except Exception as e:
            print(f"清理WebEngine资源时出错: {e}")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        print("登录对话框被关闭")
        self.cookie_check_timer.stop()
        self.cleanup_webengine()
        if not self.login_successful:
            self.login_cancelled.emit()
        event.accept()
    
    def reject(self):
        """取消按钮点击或ESC键按下"""
        print("用户取消登录")
        self.cookie_check_timer.stop()
        self.cleanup_webengine()
        if not self.login_successful:
            self.login_cancelled.emit()
        super().reject()
