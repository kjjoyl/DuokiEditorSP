import requests
import re
from bs4 import BeautifulSoup
import sys
import os
import time
import logging

# 禁用Selenium的调试日志
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from duoki_editor.core.auth_manager import AuthManager
from duoki_editor.utils.config_manager import ConfigManager

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium未安装，将尝试使用requests方法（可能无法处理JavaScript渲染的页面）")


class UsernameScraper:
    """用户名爬取器"""
    
    def __init__(self):
        self.auth_manager = AuthManager()
        self.config_manager = ConfigManager()
        server_url_without_port = self.config_manager.get_server_url_without_port()
        if server_url_without_port:
            self.target_url = f"{server_url_without_port}/users"
        else:
            self.target_url = "https://portal-test.qidianlingzhi.com/users"
        self.session = requests.Session()
        self.driver = None
        
    def setup_session(self):
        """设置会话，包括headers和cookies"""
        # 设置请求头
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # 加载认证数据
        if not self.auth_manager.load_auth_data():
            return False
            
        # 设置cookies
        if self.auth_manager.cookie:
            cookies = {}
            if '=' in self.auth_manager.cookie:
                # 解析完整的cookie字符串
                for cookie_pair in self.auth_manager.cookie.split(';'):
                    cookie_pair = cookie_pair.strip()
                    if '=' in cookie_pair:
                        key, value = cookie_pair.split('=', 1)
                        cookies[key.strip()] = value.strip()
            else:
                # 如果只是token值，使用lgtk作为key
                cookies['lgtk'] = self.auth_manager.cookie
                
            # 设置cookies到session
            for key, value in cookies.items():
                self.session.cookies.set(key, value)
                
            return True
        else:
            return False
    
    def fetch_page(self):
        """获取目标页面内容"""
        try:
            response = self.session.get(
                self.target_url,
                timeout=30,
                verify=False,  # 忽略SSL证书验证
                allow_redirects=True
            )
            
            if response.status_code == 200:
                return response.text
            else:
                return None
                
        except Exception as e:
            return None
    
    def extract_username_from_html(self, html_content):
        """从HTML内容中提取用户名"""
        try:
            # 使用BeautifulSoup解析HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 查找header标签
            header = soup.find('header')
            if not header:
                return None
                
            # 查找header下的所有li标签
            li_tags = header.find_all('li')
            
            if len(li_tags) < 2:
                return None
                
            # 获取第二个li标签（索引为1）
            second_li = li_tags[1]
            
            # 查找li标签中的span元素
            span = second_li.find('span')
            if not span:
                return None
                
            # 获取span的文本内容
            span_text = span.get_text(strip=True)
            
            # 使用正则表达式提取"欢迎，"后面的内容
            match = re.search(r'欢迎，(.+)', span_text)
            if match:
                username = match.group(1).strip()
                return username
            else:
                return None
                
        except Exception as e:
            return None
    
    def extract_username_with_regex(self, html_content):
        """使用正则表达式直接从HTML中提取用户名（备用方法）"""
        try:
            # 匹配目标li标签的模式
            pattern = r'<li[^>]*class="[^"]*text-medium[^"]*"[^>]*>.*?<span[^>]*>欢迎，([^<]+)</span>.*?</li>'
            
            matches = re.findall(pattern, html_content, re.DOTALL | re.IGNORECASE)
            
            if matches:
                username = matches[0].strip()
                return username
            else:
                return None
                
        except Exception as e:
            return None
    
    def setup_selenium_driver(self):
        """设置Selenium WebDriver"""
        if not SELENIUM_AVAILABLE:
            return False
            
        try:
            # 设置Chrome选项
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # 无头模式
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            chrome_options.add_argument('--ignore-certificate-errors')
            chrome_options.add_argument('--ignore-ssl-errors')
            chrome_options.add_argument('--ignore-certificate-errors-spki-list')
            # 禁用统计数据发送和遥测
            chrome_options.add_argument('--disable-background-networking')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-client-side-phishing-detection')
            chrome_options.add_argument('--disable-default-apps')
            chrome_options.add_argument('--disable-hang-monitor')
            chrome_options.add_argument('--disable-popup-blocking')
            chrome_options.add_argument('--disable-prompt-on-repost')
            chrome_options.add_argument('--disable-sync')
            chrome_options.add_argument('--metrics-recording-only')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-ipc-flooding-protection')
            
            # 创建WebDriver实例
            self.driver = webdriver.Chrome(options=chrome_options)
            
            # 设置cookies
            if self.auth_manager.cookie:
                # 先访问域名以设置cookies
                portal_base = self.config_manager.get_server_url_without_port()
                if not portal_base:
                    portal_base = "https://portal-test.qidianlingzhi.com"
                self.driver.get(portal_base)
                
                cookies = {}
                if '=' in self.auth_manager.cookie:
                    # 解析完整的cookie字符串
                    for cookie_pair in self.auth_manager.cookie.split(';'):
                        cookie_pair = cookie_pair.strip()
                        if '=' in cookie_pair:
                            key, value = cookie_pair.split('=', 1)
                            cookies[key.strip()] = value.strip()
                else:
                    # 如果只是token值，使用lgtk作为key
                    cookies['lgtk'] = self.auth_manager.cookie
                
                # 添加cookies到driver
                domain = portal_base.split('://', 1)[-1].split('/', 1)[0]
                for key, value in cookies.items():
                    self.driver.add_cookie({
                        'name': key,
                        'value': value,
                        'domain': domain
                    })
                
            return True
            
        except Exception as e:
            return False
    
    def fetch_page_with_selenium(self):
        """使用Selenium获取页面内容"""
        try:
            # 访问目标页面
            self.driver.get(self.target_url)
            
            # 等待页面加载完成，查找包含用户名的元素
            wait = WebDriverWait(self.driver, 20)
            
            # 等待页面中出现包含"欢迎"文本的元素
            try:
                welcome_element = wait.until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '欢迎')]"))
                )
            except TimeoutException:
                pass
            
            # 额外等待一些时间确保页面完全加载
            time.sleep(3)
            
            # 获取页面源码
            html_content = self.driver.page_source
            
            return html_content
            
        except Exception as e:
            return None
    
    def cleanup_selenium(self):
        """清理Selenium资源"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                pass
    
    def scrape_username(self):
        """主要的爬取方法"""
        print("开始获取用户名...")
        
        # 设置认证数据
        if not self.auth_manager.load_auth_data():
            return None
        
        html_content = None
        
        # 优先尝试使用Selenium（处理JavaScript渲染）
        if SELENIUM_AVAILABLE:
            if self.setup_selenium_driver():
                html_content = self.fetch_page_with_selenium()
                self.cleanup_selenium()
        
        # 如果Selenium失败，回退到requests方法
        if not html_content:
            if self.setup_session():
                html_content = self.fetch_page()
        
        if not html_content:
            return None
            
        # 方法1: 使用BeautifulSoup解析
        username = self.extract_username_from_html(html_content)
        
        # 如果方法1失败，尝试方法2: 使用正则表达式
        if not username:
            username = self.extract_username_with_regex(html_content)
        
        if username:
            print(f"成功获取用户名: {username}")
        
        return username


def main():
    """主函数"""
    print("=" * 60)
    print("用户名爬取脚本")
    print("=" * 60)
    
    scraper = UsernameScraper()
    username = scraper.scrape_username()
    
    if username:
        print("=" * 60)
        print(f"爬取成功！用户名: {username}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("爬取失败")
        print("=" * 60)
        
    return username


if __name__ == "__main__":
    main()
