from PyQt6.QtCore import QThread, pyqtSignal
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

class DataFetchWorker(QThread):
    """数据拉取工作线程"""
    
    # 定义信号
    progress_updated = pyqtSignal(int, int, str)  # 当前进度, 总数, 消息
    finished = pyqtSignal(bool)  # 成功/失败
    
    def __init__(self, data_manager):
        super().__init__()
        self.data_manager = data_manager
    
    def run(self):
        """线程执行函数"""
        try:
            # 调用数据管理器的拉取函数，传递进度回调
            success = self.data_manager.fetch_data_from_server(self.update_progress)
            self.finished.emit(success)
        except Exception as e:
            print(f"数据拉取线程出错: {e}")
            self.finished.emit(False)
    
    def update_progress(self, current, total, message):
        """更新进度回调"""
        self.progress_updated.emit(current, total, message)


class UsernameFetchWorker(QThread):
    """用户名获取工作线程"""
    
    # 定义信号
    username_fetched = pyqtSignal(str)  # 获取到的用户名
    fetch_failed = pyqtSignal(str)      # 获取失败的错误信息
    
    def __init__(self, auth_manager):
        super().__init__()
        self.auth_manager = auth_manager
    
    def run(self):
        """线程执行函数"""
        try:
            # 导入用户名爬取器
            # 添加项目根目录到Python路径
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            
            from .scrape_username import UsernameScraper
            
            # 创建爬取器实例
            scraper = UsernameScraper()
            
            # 执行爬取
            username = scraper.scrape_username()
            
            if username:
                self.username_fetched.emit(username)
            else:
                self.fetch_failed.emit("未能获取到用户名")
                
        except Exception as e:
            error_msg = f"获取用户名时出错: {str(e)}"
            print(error_msg)
            self.fetch_failed.emit(error_msg)

class ThreadPoolRunner(QThread):
    item_started = pyqtSignal(dict)
    item_done = pyqtSignal(dict)
    item_failed = pyqtSignal(dict)
    progress_updated = pyqtSignal(int, int, str)
    finished = pyqtSignal()

    def __init__(self, tasks, worker_fn, max_workers=10):
        super().__init__()
        self.tasks = list(tasks or [])
        self.worker_fn = worker_fn
        self.max_workers = int(max_workers or 10)
        self.total = len(self.tasks)
        self.current = 0
        self._stopping = False
        self._executor = None
        self._futures = None

    def run(self):
        if not self.tasks:
            self.finished.emit()
            return
        def _task_wrapper(t):
            self.item_started.emit(t)
            if self._stopping:
                return {'status': 'aborted', 'task': t}
            return self.worker_fn(t)
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {self._executor.submit(_task_wrapper, t): t for t in self.tasks}
        self._futures = futures
        try:
            pending = set(futures.keys())
            while pending:
                if self._stopping:
                    try:
                        self._executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    break
                done, not_done = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
                for fut in done:
                    t = futures.get(fut)
                    try:
                        res = fut.result()
                        self.item_done.emit(res if isinstance(res, dict) else {'task': t, 'result': res})
                    except Exception as e:
                        self.item_failed.emit({'task': t, 'error': str(e)})
                    self.current += 1
                    self.progress_updated.emit(self.current, self.total, '')
                pending = not_done
        finally:
            try:
                if self._executor:
                    self._executor.shutdown(wait=True, cancel_futures=True)
            except Exception:
                pass
            self.finished.emit()

    def stop(self):
        self._stopping = True
        if self._futures:
            # 取消未启动任务
            cancelled = 0
            for fut in list(self._futures.keys()):
                if fut.cancel():
                    cancelled += 1
            print(f"线程池停止: 已取消未启动任务 {cancelled}/{len(self._futures)}")
        if self._executor:
            try:
                self._executor.shutdown(wait=True, cancel_futures=True)
                self._executor = None
            except Exception as e:
                print(f"线程池停止异常: {e}")
