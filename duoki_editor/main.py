import sys
import os
import traceback
import logging
from datetime import datetime
from PyQt6.QtWidgets import QApplication
import threading

# 禁用urllib3的SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from duoki_editor.core.config import Config
from duoki_editor.core.data_manager import DataManager
from duoki_editor.ui.main_window import MainWindow

# 设置日志
def setup_logging():
    """设置日志系统"""
    # 获取应用程序目录
    if getattr(sys, 'frozen', False):
        # 打包后的环境
        base_dir = os.path.dirname(sys.executable)
        log_dir = os.path.join(base_dir, "_internal", "duoki_editor", "logs")
    else:
        # 开发环境
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base_dir, "duoki_editor", "logs")
    
    # 创建日志目录
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 创建日志文件名，包含时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"duoki_editor_{timestamp}.log")
    
    # 配置日志（在无控制台的打包环境中避免StreamHandler写入None）
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    handlers = [file_handler]

    # 仅当存在有效的标准流时才添加StreamHandler
    stream_target = sys.stderr if sys.stderr is not None else sys.stdout
    if stream_target is not None:
        handlers.append(logging.StreamHandler(stream_target))

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    # 禁用urllib3的调试日志
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    return log_file, log_dir

def install_crash_hooks(log_dir: str):
    """安装全局崩溃日志钩子，捕获未处理异常与线程异常"""
    crash_file = os.path.join(log_dir, "DuokiEditor_crash.log")

    def _write_crash(prefix: str, exc_type, exc_value, exc_tb):
        try:
            with open(crash_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {prefix}\n")
                f.write(f"异常类型: {getattr(exc_type, '__name__', str(exc_type))}\n")
                f.write(f"异常信息: {str(exc_value)}\n")
                f.write("堆栈:\n")
                f.write(''.join(traceback.format_tb(exc_tb)))
                f.write("\n\n")
        except Exception:
            pass

    # 全局未捕获异常（主线程）
    def _excepthook(exc_type, exc_value, exc_tb):
        logging.critical("未处理异常", exc_info=(exc_type, exc_value, exc_tb))
        _write_crash("未处理异常", exc_type, exc_value, exc_tb)
        # 保持默认行为，避免隐藏异常
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # 线程异常（Python 3.8+）
    def _thread_excepthook(args: threading.ExceptHookArgs):
        logging.critical(f"线程未处理异常 (线程: {args.thread.name})", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        _write_crash(f"线程未处理异常 (线程: {args.thread.name})", args.exc_type, args.exc_value, args.exc_traceback)

    if hasattr(threading, 'excepthook'):
        threading.excepthook = _thread_excepthook

def main(config=None):
    """主函数"""
    # 设置日志
    log_file, log_dir = setup_logging()
    install_crash_hooks(log_dir)
    logging.info(f"应用启动，日志文件: {log_file}")
    logging.info(f"Python版本: {sys.version}")
    logging.info(f"系统平台: {sys.platform}")
    
    try:
        # 创建应用程序
        logging.info("初始化QApplication")
        app = QApplication(sys.argv)
        
        # 加载配置
        logging.info("加载配置")
        if config is None:
            config = Config()
            # 对于打包版本，默认启用xlsx缓存以提高启动速度
            config.set_use_local_cache(True)
        
        # 创建共享的认证管理器
        from duoki_editor.core.auth_manager import AuthManager
        auth_manager = AuthManager()
        
        # 创建数据管理器
        logging.info("初始化数据管理器")
        data_manager = DataManager(config, auth_manager)
        
        # 创建主窗口
        logging.info("创建主窗口")
        main_window = MainWindow(data_manager, config, auth_manager)
        
        # 运行应用程序
        logging.info("启动应用程序主循环")
        return app.exec()
    
    except Exception as e:
        # 捕获所有异常并记录到日志
        logging.critical(f"应用发生严重错误: {str(e)}")
        logging.critical("详细错误信息:")
        logging.critical(traceback.format_exc())
        
        # 将错误信息写入特定文件以便查看
        if getattr(sys, 'frozen', False):
            # 打包后的环境
            base_dir = os.path.dirname(sys.executable)
        else:
            # 开发环境
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        log_dir = os.path.join(base_dir, "duoki_editor", "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        crash_file = os.path.join(log_dir, "DuokiEditor_crash.log")
        with open(crash_file, 'w', encoding='utf-8') as f:
            f.write(f"DuokiEditor崩溃时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"错误信息: {str(e)}\n\n")
            f.write("详细堆栈跟踪:\n")
            f.write(traceback.format_exc())
            f.write("\n\n系统信息:\n")
            f.write(f"Python版本: {sys.version}\n")
            f.write(f"系统平台: {sys.platform}\n")
        
        print(f"应用崩溃，详细日志已保存到: {crash_file}")
        
        # 返回错误码
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)