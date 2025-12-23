import os
import sys
from pathlib import Path
import argparse
import warnings

# 禁用urllib3的SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 屏蔽 pydub 在启动时的 RuntimeWarning（找不到 ffmpeg/avconv 的提示）
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub.utils")

# 关闭 Selenium Manager 的匿名遥测上报，避免 Plausible 警告日志
os.environ.setdefault("SE_AVOID_STATS", "true")

if os.name == "nt" and hasattr(os, "dup2") and not os.environ.get("DUOKI_KEEP_STDERR"):
    devnull = open(os.devnull, "w")
    os.dup2(devnull.fileno(), sys.stderr.fileno())
    sys.stderr = devnull

from duoki_editor.main import main
from duoki_editor.core.config import Config

# 获取当前目录（项目根目录）
current_dir = str(Path(__file__).parent)  # 新增这行

# 添加项目根目录到Python路径
sys.path.insert(0, current_dir)

# 设置工作目录为项目根目录
os.chdir(current_dir)

if __name__ == "__main__":
    # 创建参数解析器
    parser = argparse.ArgumentParser(description='DuokiEditor 开发模式')
    parser.add_argument('--use-cache', action='store_true', help='使用本地缓存，不从服务器下载数据')
    
    # 解析参数
    args = parser.parse_args()
    
    # 设置配置
    config = Config()
    config.set_use_local_cache(True)  # 修改为正确的方法名
    
    print(f"xlsx文件缓存状态: {config.use_local_xlsx_cache}")  # 修改为正确的属性名
    print("在开发环境中启动 DuokiEditor...")
    
    # 运行主程序
    sys.exit(main(config))
