from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, 
                            QListWidget, QTabWidget, QTextEdit, QLabel,
                            QListWidgetItem, QMessageBox)
from PyQt6.QtCore import Qt
import os


class TemplateManager(QWidget):
    """模板管理主界面"""
    
    def __init__(self, data_manager=None):
        super().__init__()
        self.data_manager = data_manager
        self.template_base_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'resources', 'data', 'template', 'base'
        )
        self.init_ui()
        self.load_template_files()
        
    def init_ui(self):
        """初始化用户界面"""
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # 创建水平分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧文件列表
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)
        
        # 文件列表标题
        file_list_label = QLabel("模板文件")
        left_layout.addWidget(file_list_label)
        
        # 文件列表
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self.on_file_selected)
        left_layout.addWidget(self.file_list)
        
        # 设置左侧面板宽度
        left_widget.setFixedWidth(250)
        splitter.addWidget(left_widget)
        
        # 右侧页签容器
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_widget.setLayout(right_layout)
        
        # 创建页签容器
        self.tab_widget = QTabWidget()
        
        # 模板列表页签
        self.template_list_tab = QWidget()
        template_list_layout = QVBoxLayout()
        self.template_list_tab.setLayout(template_list_layout)
        
        self.template_list_text = QTextEdit()
        self.template_list_text.setReadOnly(True)
        self.template_list_text.setPlaceholderText("请选择左侧的模板文件查看内容")
        template_list_layout.addWidget(self.template_list_text)
        
        # 初始文案页签
        self.initial_content_tab = QWidget()
        initial_content_layout = QVBoxLayout()
        self.initial_content_tab.setLayout(initial_content_layout)
        
        self.initial_content_text = QTextEdit()
        self.initial_content_text.setReadOnly(True)
        self.initial_content_text.setPlaceholderText("初始文案内容将在此显示")
        initial_content_layout.addWidget(self.initial_content_text)
        
        # 中文文案页签
        self.chinese_content_tab = QWidget()
        chinese_content_layout = QVBoxLayout()
        self.chinese_content_tab.setLayout(chinese_content_layout)
        
        self.chinese_content_text = QTextEdit()
        self.chinese_content_text.setReadOnly(True)
        self.chinese_content_text.setPlaceholderText("中文文案内容将在此显示")
        chinese_content_layout.addWidget(self.chinese_content_text)
        
        # 英语浓度页签
        self.english_density_tab = QWidget()
        english_density_layout = QVBoxLayout()
        self.english_density_tab.setLayout(english_density_layout)
        
        self.english_density_text = QTextEdit()
        self.english_density_text.setReadOnly(True)
        self.english_density_text.setPlaceholderText("英语浓度信息将在此显示")
        english_density_layout.addWidget(self.english_density_text)
        
        # 添加页签到容器
        self.tab_widget.addTab(self.template_list_tab, "模板列表")
        self.tab_widget.addTab(self.initial_content_tab, "初始文案")
        self.tab_widget.addTab(self.chinese_content_tab, "中文文案")
        self.tab_widget.addTab(self.english_density_tab, "英语浓度")
        
        right_layout.addWidget(self.tab_widget)
        splitter.addWidget(right_widget)
        
        # 设置分割器比例
        splitter.setSizes([250, 800])
        
        main_layout.addWidget(splitter)
        
    def load_template_files(self):
        """加载模板文件列表"""
        try:
            if not os.path.exists(self.template_base_path):
                self.file_list.addItem("模板目录不存在")
                return
                
            files = os.listdir(self.template_base_path)
            if not files:
                self.file_list.addItem("模板目录为空")
                return
                
            for file_name in files:
                file_path = os.path.join(self.template_base_path, file_name)
                if os.path.isfile(file_path):
                    item = QListWidgetItem(file_name)
                    item.setData(Qt.ItemDataRole.UserRole, file_path)
                    self.file_list.addItem(item)
                    
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载模板文件失败：{str(e)}")
            
    def on_file_selected(self, item):
        """文件选择事件处理"""
        try:
            file_path = item.data(Qt.ItemDataRole.UserRole)
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 在模板列表页签中显示文件内容
                self.template_list_text.setPlainText(content)
                
                # TODO: 根据文件类型和内容解析并显示在相应页签中
                # 这里可以根据实际需求解析不同类型的模板文件
                
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取文件失败：{str(e)}")