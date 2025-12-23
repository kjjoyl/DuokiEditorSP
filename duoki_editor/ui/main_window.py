from PyQt6.QtWidgets import (QMainWindow, QTabWidget, QToolBar,
                            QMessageBox, QApplication, QStyleFactory, QWidget, QVBoxLayout)
from PyQt6.QtGui import QIcon, QAction, QActionGroup
from PyQt6.QtCore import Qt, QSize, pyqtSignal
import os
import sys
import shutil

from duoki_editor.modules.audio_inspector.audio_inspector import AudioInspector
from duoki_editor.modules.ai_image_generator.ai_image_generator import AIImageGenerator
from duoki_editor.modules.online_data.online_data_viewer import OnlineDataViewer
from duoki_editor.modules.content_validator.content_validator import ContentValidator
from duoki_editor.modules.content_generator.content_generator_widget import ContentGeneratorWidget
from duoki_editor.modules.toolkit.toolkit_widget import ToolkitWidget
# from duoki_editor.modules.template_manager.template_manager import TemplateManager
from duoki_editor.ui.splash_screen import SplashScreen
from duoki_editor.ui.toast import ToastManager
from duoki_editor.ui.login_dialog import LoginDialog
from duoki_editor.utils.worker_thread import DataFetchWorker, UsernameFetchWorker
from duoki_editor.utils.config_manager import ConfigManager
from duoki_editor.core.character_table_manager import CharacterTableManager
from duoki_editor.core.auth_manager import AuthManager
from duoki_editor.modules.content_generator.feishu_sync import FeishuBitableSync
from duoki_editor.core.data_manager import DataManager

class MainWindow(QMainWindow):
    """编辑器主窗口"""
    
    def __init__(self, data_manager, config, auth_manager=None):
        super().__init__()
        self.data_manager = data_manager
        self.config = config
        
        # 初始化配置管理器和认证管理器
        self.config_manager = ConfigManager()
        self.auth_manager = auth_manager or AuthManager()
        
        # 初始化飞书同步实例
        self.feishu_sync = FeishuBitableSync()
        
        # 初始化用户名变量
        self.user_name = ""
        self.login_status_action = None  # 保存登录状态菜单项的引用
        
        # 先进行登录验证，然后再显示splash
        self.check_authentication()
    
    def check_authentication(self):
        """检查用户认证状态"""
        print("开始检查认证状态...")
        
        # 检查认证状态
        is_authenticated, login_url = self.auth_manager.check_auth_status()
        
        if is_authenticated:
            print("用户已认证，直接启动应用")
            self.start_application()
        else:
            print("用户未认证，显示登录对话框")
            self.show_login_dialog(login_url)
    
    def show_login_dialog(self, login_url):
        """显示登录对话框"""
        self.config_manager.set('General', 'user_name', '')
        self.config_manager.save()
        print("已清空配置中的用户名参数")
        self.login_dialog = LoginDialog(login_url, self)
        
        # 连接信号
        self.login_dialog.login_success.connect(self.on_login_success)
        self.login_dialog.login_cancelled.connect(self.on_login_cancelled)
        
        # 显示对话框
        self.login_dialog.show()
    
    def on_login_success(self, cookie):
        """登录成功回调"""

        if self.auth_manager.save_auth_data(cookie):
            
            # 关闭登录对话框
            if hasattr(self, 'login_dialog'):
                self.login_dialog.close()
            
            # 启动应用
            self.start_application()
        else:
            print("认证数据保存失败")
            QMessageBox.critical(self, "错误", "保存认证数据失败，请重试")
    
    def on_login_cancelled(self):
        """登录取消回调"""
        print("用户取消登录，退出应用")
        QApplication.quit()
    
    def start_application(self):
        """启动应用程序主界面"""
        print("启动应用程序...")
        
        # 创建启动页面
        self.splash = SplashScreen()
        self.splash.show()
        self.splash.capture_console()
        
        # 处理事件，确保启动页面立即显示
        QApplication.processEvents()
        
        # 启动异步数据拉取
        self.start_data_fetch()
    
    def start_data_fetch(self):
        """启动异步数据拉取"""
        # 创建工作线程
        self.worker = DataFetchWorker(self.data_manager)
        
        # 连接信号
        self.worker.progress_updated.connect(self.splash.update_progress)
        self.worker.finished.connect(self.on_data_fetch_finished)
        
        # 启动线程
        self.worker.start()
    
    def on_data_fetch_finished(self, success):
        """数据拉取完成回调"""
        if success:
            # 初始化UI
            self.init_ui()
            
            # 关闭启动页面
            if hasattr(self, 'splash') and self.splash:
                self.splash.restore_console()
            self.splash.finish(self)
            
            # 显示主窗口并立即最大化
            self.showMaximized()
            
            # 确保飞书令牌有效（在后台异步执行）
            self.ensure_feishu_token()
            
            # 启动异步用户名获取
            self.start_username_fetch()
        else:
            # 关闭启动页面
            if hasattr(self, 'splash') and self.splash:
                self.splash.restore_console()
                self.splash.close()
            
            # 检查是否是认证失效导致的失败
            auth_status, login_url = self.auth_manager.check_auth_status()
            if not auth_status:
                print("检测到认证失效，重新显示登录对话框")
                # 重新显示登录对话框
                self.show_login_dialog(login_url)
            else:
                # 其他错误，显示错误消息并退出
                QMessageBox.critical(None, "错误", "从服务器拉取数据失败，请检查网络连接后重试。")
                QApplication.quit()
    
    def ensure_feishu_token(self):
        """确保飞书令牌有效"""
        try:
            print("开始检查飞书令牌状态...")
            # 在后台线程中执行令牌检查和获取，避免阻塞UI
            import threading
            
            def check_and_get_token():
                try:
                    # 调用飞书同步实例的令牌确保方法
                    self.feishu_sync.ensure_valid_token()
                    print("飞书令牌检查完成")
                except Exception as e:
                    print(f"飞书令牌检查失败: {e}")
            
            # 在后台线程中执行
            token_thread = threading.Thread(target=check_and_get_token, daemon=True)
            token_thread.start()
            
        except Exception as e:
            print(f"启动飞书令牌检查失败: {e}")
    
    def start_username_fetch(self):
        """启动异步用户名获取"""
        name = self.config_manager.get('General', 'user_name', '')
        if name:
            self.user_name = name
            print(f"从配置读取用户名: {name}")
            self.update_login_status_menu()
            if hasattr(self, 'content_generator'):
                self.content_generator.update_username_display(name)
            return
        # 创建用户名获取工作线程
        self.username_worker = UsernameFetchWorker(self.auth_manager)
        self.username_worker.username_fetched.connect(self.on_username_fetched)
        self.username_worker.fetch_failed.connect(self.on_username_fetch_failed)
        self.username_worker.start()
    
    def on_username_fetched(self, username):
        """用户名获取成功回调"""
        self.user_name = username
        self.config_manager.set_general_user_name(username)
        print(f"已写入用户名到配置: {username}")
        self.update_login_status_menu()
        # 同步用户名到文案助手界面
        if hasattr(self, 'content_generator'):
            self.content_generator.update_username_display(username)
    
    def on_username_fetch_failed(self, error_msg):
        """用户名获取失败回调"""
        print(f"用户名获取失败: {error_msg}")
        # 即使获取失败，也保持已登录状态，只是不显示用户名
        self.user_name = ""
        self.update_login_status_menu()
        # 同步用户名获取失败状态到文案助手界面
        if hasattr(self, 'content_generator'):
            self.content_generator.update_username_display("")
    
    def update_login_status_menu(self):
        """更新登录状态菜单项"""
        if self.login_status_action:
            if self.user_name:
                # 显示用户名和已登录状态
                self.login_status_action.setText(f'{self.user_name} - 已登录✌️')
            else:
                # 只显示已登录状态
                self.login_status_action.setText('已登录✌️')
    
    def init_ui(self):
        # 设置窗口基本属性
        self.setWindowTitle("DuokiEditor - 游戏内容编辑器")
        self.setGeometry(100, 100, 1280, 800)
        
        # 设置窗口图标（统一为 duoki_editor/resources 路径）
        base_dir = os.path.dirname(os.path.dirname(__file__))
        if sys.platform == 'darwin':
            icon_path = os.path.join(base_dir, "resources", "icons", "app_icon.icns")
        else:
            icon_path = os.path.join(base_dir, "resources", "icons", "app_icon.ico")
        
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 创建工具栏（但隐藏它）
        # self.create_tool_bar()
        # self.main_toolbar.setVisible(False)
        
        # 创建状态栏
        self.statusBar().showMessage('就绪')
        
        # 初始化Toast管理器
        self.toast_manager = ToastManager(self)
        
        # 创建主内容区域
        self.create_main_content()
    
    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 账户菜单（原设置菜单）
        account_menu = menubar.addMenu('账户')
        
        # 显示登录状态
        cookie_header = self.auth_manager.get_cookie_header()
        if cookie_header:
            # 显示已登录状态，初始时不显示用户名（异步获取中）
            if self.user_name:
                self.login_status_action = QAction(f'{self.user_name} - 已登录✌️', self)
            else:
                self.login_status_action = QAction('已登录✌️', self)
            self.login_status_action.setEnabled(False)  # 设为不可点击，仅显示信息
            account_menu.addAction(self.login_status_action)
        else:
            # 显示未登录状态
            self.login_status_action = QAction('未登录❌', self)
            self.login_status_action.setEnabled(False)  # 设为不可点击，仅显示信息
            account_menu.addAction(self.login_status_action)
        
        account_menu.addSeparator()  # 添加分隔线
        
        # 退出登录
        logout_action = QAction('退出登录', self)
        logout_action.triggered.connect(self.logout)
        account_menu.addAction(logout_action)
        
        # 退出程序（原退出菜单项）
        exit_action = QAction('退出程序', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        account_menu.addAction(exit_action)
        
        # 界面菜单 - 样式切换
        interface_menu = menubar.addMenu('界面')
        
        # 创建样式切换动作组
        self.style_group = QActionGroup(self)
        self.style_group.setExclusive(True)  # 确保只能选择一个样式
        
        # 获取所有可用的样式
        available_styles = QStyleFactory.keys()
        
        # 为每个样式创建菜单项
        self.style_actions = {}
        for style in available_styles:
            action = QAction(style, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, s=style: self.change_style(s))
            self.style_group.addAction(action)
            interface_menu.addAction(action)
            self.style_actions[style] = action
        
        # 从配置文件加载保存的样式设置
        saved_style = self.config_manager.get_theme()
        
        # 应用保存的样式
        if saved_style in available_styles:
            QApplication.setStyle(saved_style)
            self.style_actions[saved_style].setChecked(True)
        else:
            # 如果保存的样式不可用，使用当前样式
            current_style = QApplication.instance().style().objectName()
            if current_style in self.style_actions:
                self.style_actions[current_style].setChecked(True)
                # 更新配置文件为当前样式
                self.config_manager.set_theme(current_style)
            else:
                # 如果当前样式也不在列表中，默认选择第一个
                if available_styles:
                    QApplication.setStyle(available_styles[0])
                    self.style_actions[available_styles[0]].setChecked(True)
                    self.config_manager.set_theme(available_styles[0])
        
        # 工具菜单
        tools_menu = menubar.addMenu('工具')
        
        tools_menu.addSeparator()  # 添加分隔线
        
        # 添加清空音频缓存功能
        clear_audio_cache_action = QAction('清空音频缓存', self)
        clear_audio_cache_action.triggered.connect(self.clear_audio_cache)
        tools_menu.addAction(clear_audio_cache_action)
        
        # 添加清空图片缓存功能
        clear_image_cache_action = QAction('清空图片缓存', self)
        clear_image_cache_action.triggered.connect(self.clear_image_cache)
        tools_menu.addAction(clear_image_cache_action)
        
        tools_menu.addSeparator()  # 添加分隔线
        
        self.use_fixed_data_action = QAction('使用修正数据', self)
        self.use_fixed_data_action.setCheckable(True)
        self.use_fixed_data_action.setChecked(False)
        self.use_fixed_data_action.triggered.connect(self.on_use_fixed_data_toggled)
        tools_menu.addAction(self.use_fixed_data_action)

        refetch_data_action = QAction('重新拉取数据', self)
        refetch_data_action.triggered.connect(self.refetch_data)
        tools_menu.addAction(refetch_data_action)

        # 帮助菜单
        help_menu = menubar.addMenu('帮助')
        
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    
    
    def create_tool_bar(self):
        """创建工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setIconSize(QSize(24, 24))
        
        # 从配置中读取工具栏位置
        position = self.config_manager.get_toolbar_position()
        toolbar_area = Qt.ToolBarArea.TopToolBarArea  # 默认上方
        
        if position == 'top':
            toolbar_area = Qt.ToolBarArea.TopToolBarArea
        elif position == 'bottom':
            toolbar_area = Qt.ToolBarArea.BottomToolBarArea
        elif position == 'left':
            toolbar_area = Qt.ToolBarArea.LeftToolBarArea
        elif position == 'right':
            toolbar_area = Qt.ToolBarArea.RightToolBarArea
            
        self.addToolBar(toolbar_area, toolbar)
        
        # 保存toolbar引用以便后续使用
        self.main_toolbar = toolbar
        
        # 连接工具栏移动信号
        toolbar.topLevelChanged.connect(self.on_toolbar_moved)
        
        # 添加模板管理按钮 - 已隐藏
        # template_manager_action = QAction("模板管理", self)
        # template_manager_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(0))
        # toolbar.addAction(template_manager_action)
        
        # 添加音频检查器按钮
        audio_inspector_action = QAction("内容质检", self)
        audio_inspector_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(0))
        toolbar.addAction(audio_inspector_action)
        
        # 添加AI生图按钮
        ai_image_action = QAction("图片生成", self)
        ai_image_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(2))
        toolbar.addAction(ai_image_action)
        
        # 添加线上数据按钮
        online_data_action = QAction("线上数据", self)
        online_data_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(5))
        toolbar.addAction(online_data_action)
        
    def change_style(self, style_name):
        """切换应用样式"""
        try:
            # 应用新样式
            QApplication.setStyle(style_name)
            
            # 清除自定义样式表，让新样式生效
            self.setStyleSheet("")
            
            # 显示状态消息
            self.statusBar().showMessage(f'已切换到 {style_name} 样式')
            
            # 保存样式设置到配置文件
            self.config_manager.set_theme(style_name)
            
        except Exception as e:
            QMessageBox.warning(self, '样式切换失败', f'无法切换到 {style_name} 样式：{str(e)}')
        
    def on_toolbar_moved(self, floating):
        """工具栏位置改变时的回调函数"""
        if not floating and hasattr(self, 'main_toolbar'):
            # 获取当前工具栏区域
            area = self.toolBarArea(self.main_toolbar)
            
            # 将区域枚举转换为字符串
            position_map = {
                Qt.ToolBarArea.TopToolBarArea: 'top',
                Qt.ToolBarArea.BottomToolBarArea: 'bottom',
                Qt.ToolBarArea.LeftToolBarArea: 'left',
                Qt.ToolBarArea.RightToolBarArea: 'right'
            }
            
            if area in position_map:
                position = position_map[area]
                # 保存新的位置到配置文件
                self.config_manager.set_toolbar_position(position)
        

    def create_main_content(self):
        """创建主内容区域"""
        # 初始化CharacterTableManager
        self.character_table_manager = CharacterTableManager()
        print(f"CharacterTableManager已初始化，共加载 {len(self.character_table_manager.get_character_table_data())} 行角色数据")
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        
        # 显示标签栏并设置为左侧竖向排列
        self.tab_widget.tabBar().setVisible(True)
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.West)
        
        # 创建模板管理模块 - 已隐藏
        # self.template_manager = TemplateManager(self.data_manager)
        # self.tab_widget.addTab(self.template_manager, "模板管理")
        
        # 创建游戏质检模块
        self.audio_inspector = AudioInspector(self.data_manager, self.auth_manager)
        # 将Toast管理器传递给音频验收模块
        self.audio_inspector.toast_manager = self.toast_manager
        
        self.tab_widget.addTab(self.audio_inspector, "游戏质检")
        
        # 创建内容校验模块
        self.content_validator = ContentValidator(self.data_manager, self.auth_manager)
        # 将Toast管理器传递给内容校验模块
        self.content_validator.toast_manager = self.toast_manager
        self.tab_widget.addTab(self.content_validator, "内容处理")
        
        # 创建AI图像生成模块
        self.ai_image_generator = AIImageGenerator(self.data_manager)
        self.ai_image_generator.toast_manager = self.toast_manager
        self.tab_widget.addTab(self.ai_image_generator, "图像生成")

        # 创建文案助手模块（调整位置在线上数据之前）
        self.content_generator = ContentGeneratorWidget(self)
        self.tab_widget.addTab(self.content_generator, "文案工具")

        self.toolkit_widget = ToolkitWidget()
        self.toolkit_widget.toast_manager = self.toast_manager
        self.toolkit_widget.config_manager = self.config_manager
        self.tab_widget.addTab(self.toolkit_widget, "小工具集")

        # 创建线上数据查看器（调整为最后一个）
        self.online_data_viewer = OnlineDataViewer(self.data_manager, self.auth_manager, self.config_manager)
        self.online_data_viewer.toast_manager = self.toast_manager
        self.tab_widget.addTab(self.online_data_viewer, "线上数据")
        
        # 设置为中心部件
        self.setCentralWidget(self.tab_widget)
        self._apply_role_tab_visibility()

    def _apply_role_tab_visibility(self):
        role = ''
        try:
            role = self.config_manager.get_role()
        except Exception:
            role = ''
        role_norm = str(role or 'admin').strip().lower()
        allowed = None
        if role_norm == 'admin':
            allowed = None
        elif role_norm == 'qa':
            allowed = {"游戏质检"}
        else:
            allowed = {"小工具集", "线上数据"}
        if allowed is not None:
            count = self.tab_widget.count()
            first_visible = -1
            for i in range(count):
                title = self.tab_widget.tabText(i)
                visible = (title in allowed)
                try:
                    self.tab_widget.setTabVisible(i, visible)
                except Exception:
                    pass
                if first_visible < 0 and visible:
                    first_visible = i
            if first_visible >= 0:
                self.tab_widget.setCurrentIndex(first_visible)
    

    
    def logout(self):
        """退出登录"""
        reply = QMessageBox.question(
            self, '确认退出登录', 
            '确定要退出登录吗？退出后需要重新登录才能使用。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 清除认证数据
            self.auth_manager.clear_auth_data()
            
            # 退出程序
            QApplication.quit()
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self, "关于 DuokiEditor",
            "DuokiEditor 是多奇机器人专用编辑器，用于编辑和管理游戏数据。\n\n"
            "版本: 0.1.0\n"
            "作者: Seinfield"
        )
    
    def clear_image_cache(self):
        """清空图片缓存"""
        try:
            # 直接执行清理
            self._do_clear_image_cache()
        except Exception as e:
            self.toast_manager.show_error(f"清空图片缓存失败: {e}")
    
    def _do_clear_image_cache(self):
        """实际执行图片缓存清理"""
        try:
            image_cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "image")
            if os.path.exists(image_cache_path):
                # 删除目录下的所有文件和子目录
                for item in os.listdir(image_cache_path):
                    item_path = os.path.join(image_cache_path, item)
                    try:
                        if os.path.isfile(item_path):
                            os.unlink(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                    except PermissionError as pe:
                        print(f"无法删除文件 {item_path}: {pe}")
                        # 尝试强制删除
                        try:
                            import stat
                            os.chmod(item_path, stat.S_IWRITE)
                            if os.path.isfile(item_path):
                                os.unlink(item_path)
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                        except Exception as e2:
                            print(f"强制删除失败 {item_path}: {e2}")
                            continue
                
                # 确保目录存在
                os.makedirs(image_cache_path, exist_ok=True)
                
                self.toast_manager.show_success("图片缓存已清空")
            else:
                os.makedirs(image_cache_path, exist_ok=True)
                self.toast_manager.show_info("图片缓存目录不存在，已创建")
        except Exception as e:
            self.toast_manager.show_error(f"清空图片缓存失败: {e}")

    def clear_audio_cache(self):
        """清空音频缓存"""
        try:
            # 检查是否正在播放音频
            if hasattr(self, 'audio_inspector') and hasattr(self.audio_inspector, 'tts_player'):
                if hasattr(self.audio_inspector.tts_player, 'is_playing') and self.audio_inspector.tts_player.is_playing:
                    # 显示toast提示
                    self.toast_manager.show_warning("播放过程中无法清除缓存")
                    return
                
                # 如果没有播放，先停止播放器确保资源释放
                self.audio_inspector.tts_player.stop()
                print("已停止音频播放器")
            
            # 直接执行清理
            self._do_clear_audio_cache()
        except Exception as e:
            self.toast_manager.show_error(f"清空音频缓存失败: {e}")
    
    def on_use_fixed_data_toggled(self, checked):
        DataManager.use_mod_override = bool(checked)
        state = '开启' if checked else '关闭'
        print(f"使用修正数据开关: {state}")
    
    def _do_clear_audio_cache(self):
        """实际执行音频缓存清理"""
        try:
            audio_cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "audio")
            if os.path.exists(audio_cache_path):
                # 删除目录下的所有文件和子目录
                for item in os.listdir(audio_cache_path):
                    item_path = os.path.join(audio_cache_path, item)
                    try:
                        if os.path.isfile(item_path):
                            os.unlink(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                    except PermissionError as pe:
                        print(f"无法删除文件 {item_path}: {pe}")
                        # 尝试强制删除
                        try:
                            import stat
                            os.chmod(item_path, stat.S_IWRITE)
                            if os.path.isfile(item_path):
                                os.unlink(item_path)
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                        except Exception as e2:
                            print(f"强制删除失败 {item_path}: {e2}")
                            continue
                
                # 确保目录存在
                os.makedirs(audio_cache_path, exist_ok=True)
                
                self.toast_manager.show_success("音频缓存已清空")
            else:
                os.makedirs(audio_cache_path, exist_ok=True)
                self.toast_manager.show_info("音频缓存目录不存在，已创建")
        except Exception as e:
            self.toast_manager.show_error(f"清空音频缓存失败: {e}")
    
    def refetch_data(self):
        """重新拉取数据"""
        try:
            # 强制从线上拉取数据，忽略use_local_xlsx_cache设置
            original_use_local_cache = self.data_manager.config.use_local_xlsx_cache
            self.data_manager.config.use_local_xlsx_cache = False
            
            # 显示进度对话框
            self.splash = SplashScreen()
            self.splash.show()
            QApplication.processEvents()
            
            # 启动异步数据拉取
            self.worker = DataFetchWorker(self.data_manager)
            self.worker.progress_updated.connect(self.splash.update_progress)
            self.worker.finished.connect(lambda success: self.on_refetch_finished(success, original_use_local_cache))
            self.worker.start()
            
        except Exception as e:
            self.toast_manager.show_error(f"重新拉取数据失败: {e}")
    
    def on_refetch_finished(self, success, original_use_local_cache):
        """重新拉取数据完成回调"""
        # 恢复原始use_local_xlsx_cache设置
        self.data_manager.config.use_local_xlsx_cache = original_use_local_cache
        
        # 关闭启动页面
        self.splash.finish(self)
        
        if success:
            self.toast_manager.show_success("数据已成功从线上重新拉取")
            
            # 刷新UI - 不直接调用不存在的refresh_data方法
            # 而是通过重新加载主窗口的方式刷新数据
            try:
                # 如果模块有load_data方法则调用
                if hasattr(self.audio_inspector, 'load_data'):
                    self.audio_inspector.load_data()
                if hasattr(self.ai_image_generator, 'load_data'):
                    self.ai_image_generator.load_data()
                if hasattr(self.online_data_viewer, 'load_data'):
                    self.online_data_viewer.load_data()
                
                self.statusBar().showMessage('UI已刷新')
            except Exception as e:
                print(f"刷新UI时出错: {e}")
        else:
            self.toast_manager.show_error("从服务器拉取数据失败，请检查网络连接后重试。")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        if hasattr(self, 'ai_image_generator') and self.ai_image_generator:
            try:
                if hasattr(self.ai_image_generator, 'stop_all_tasks'):
                    print("正在停止AI图片生成模块的任务...")
                    self.ai_image_generator.stop_all_tasks()
            except Exception as e:
                print(f"停止AI图片生成模块任务异常: {e}")
        # 停止各模块的线程池/任务
        if hasattr(self, 'audio_inspector') and self.audio_inspector:
            if hasattr(self.audio_inspector, 'stop_all_tasks'):
                print("正在停止游戏质检模块的线程池...")
                self.audio_inspector.stop_all_tasks()
        '''
        if hasattr(self, 'toolkit_widget') and self.toolkit_widget:
            if hasattr(self.toolkit_widget, 'stop_all_tasks'):
                print("正在停止小工具集模块的线程池...")
                self.toolkit_widget.stop_all_tasks()
        if hasattr(self, 'content_validator') and self.content_validator:
            if hasattr(self.content_validator, 'stop_all_tasks'):
                print("正在停止内容处理模块的线程池...")
                self.content_validator.stop_all_tasks()
        if hasattr(self, 'online_data_viewer') and self.online_data_viewer:
            if hasattr(self.online_data_viewer, 'stop_all_tasks'):
                print("正在停止线上数据模块的线程池...")
                self.online_data_viewer.stop_all_tasks()
        '''
        # 保存配置
        self.config.save()
        event.accept()
