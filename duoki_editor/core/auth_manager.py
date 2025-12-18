import os
from pandas.core.base import NoNewAttributesMixin
import requests
from urllib.parse import urlparse, parse_qs
from duoki_editor.utils.config_manager import ConfigManager

class AuthManager:
    """认证管理器，处理用户登录、cookie存储和验证"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.portal_url = "https://portal-test.qidianlingzhi.com:10199/"
        self.cookie = None
        
    def load_auth_data(self):
        """从INI配置文件加载认证数据"""
        try:
            # 从INI文件的[KEY]部分加载Cookie
            cookie = self.config_manager.get_cookie()
            
            if cookie:
                print(f"加载的Cookie: {cookie}")
                self.cookie = cookie
                return True
        except Exception as e:
            print(f"加载认证数据失败: {e}")
            import traceback
            traceback.print_exc()
            print(f"=" * 50)
        return False
    
    def save_auth_data(self, cookie):
        """保存认证数据到INI配置文件"""
        try:
            store_value = cookie.strip()
            self.config_manager.set_cookie(store_value)
            
            # 验证是否成功保存
            saved_cookie = self.config_manager.get_cookie()
            if saved_cookie == store_value:
                print(f"Cookie保存验证成功")
            else:
                print(f"Cookie保存验证失败")
                return False
            
            self.cookie = store_value
            
            return True
        except Exception as e:
            print(f"保存认证数据失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def clear_auth_data(self):
        """清除INI配置文件中的认证数据"""
        try:
            # 从INI文件中移除Cookie
            self.config_manager.clear_cookie()
            
            # 清除内存中的认证数据
            self.cookie = None
            print("=" * 50)
            return True
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False
    
    def check_auth_status(self):
        """检查当前认证状态
        
        Returns:
            tuple: (is_authenticated, login_url_or_none)
                - is_authenticated: 是否已认证
                - login_url_or_none: 如果未认证，返回登录URL；如果已认证，返回None
        """
        try:
            # 先尝试加载本地认证数据
            self.load_auth_data()
            
            # 设置请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # 如果有本地保存的cookie，添加到请求中
            cookies = {}
            if self.cookie:
                # 支持多种cookie格式
                if '=' in self.cookie:
                    # 如果是完整的cookie字符串，解析它
                    for cookie_pair in self.cookie.split(';'):
                        if '=' in cookie_pair:
                            key, value = cookie_pair.strip().split('=', 1)
                            cookies[key] = value
                else:
                    # 如果只是token值，使用lgtk作为key
                    cookies = {'lgtk': self.cookie}
            
            # 访问portal页面检查认证状态
            response = requests.get(
                self.portal_url, 
                headers=headers, 
                cookies=cookies,
                allow_redirects=False,  # 不自动跟随重定向，获取原始响应
                timeout=10,
                verify=False
            )
            try:
                self._update_cookie_from_response(response)
            except Exception:
                pass
            
            # 根据响应状态判断认证状态
            if response.status_code == 200:
                # 检查响应内容是否包含登录相关内容
                content_text = response.text.lower()
                print(f"响应内容长度: {len(response.text)}")
                
                # 检查是否包含登录相关的关键词或重定向脚本
                if ('login' in content_text or 'window.location' in content_text or 
                    'redirect' in content_text or 'open.weixin.qq.com' in content_text):
                    print("认证状态检查：检测到登录重定向页面，需要登录")
                    
                    # 尝试从响应内容中提取登录URL
                    import re
                    # 匹配各种可能的登录URL模式
                    patterns = [
                        r"window\.location\.href\s*=\s*['\"]([^'\"]*)['\"]",
                        r"window\.open\s*\(\s*['\"]([^'\"]*)['\"]",
                        r"location\.href\s*=\s*['\"]([^'\"]*)['\"]",
                        r"href\s*=\s*['\"]([^'\"]*login[^'\"]*)['\"]"
                    ]
                    
                    login_url = None
                    for pattern in patterns:
                        match = re.search(pattern, response.text, re.IGNORECASE)
                        if match:
                            login_url = match.group(1)
                            print(f"提取到登录URL: {login_url}")
                            break
                    
                    # 如果没有提取到具体URL，返回portal URL让登录对话框处理
                    if not login_url:
                        login_url = self.portal_url
                        print(f"未提取到具体登录URL，使用portal URL: {login_url}")
                    
                    return False, login_url
                else:
                    # 如果返回200且不包含登录相关内容，说明已经认证
                    print("认证状态检查：已认证（200响应且无登录内容）")
                    return True, None
                    
            elif response.status_code in [302, 301, 303, 307, 308]:
                # 如果是重定向，检查重定向URL
                redirect_url = response.headers.get('Location', '')
                print(f"认证状态检查：重定向到 {redirect_url}")
                
                # 检查重定向URL是否包含login
                if 'login' in redirect_url.lower():
                    print("认证状态检查：重定向到登录页面，需要登录")
                    return False, redirect_url
                else:
                    # 重定向到非登录页面，可能已认证
                    print("认证状态检查：重定向到非登录页面，可能已认证")
                    return True, None
            else:
                # 其他状态码，根据具体情况判断
                print(f"认证状态检查：收到状态码 {response.status_code}")
                # 对于4xx或5xx错误，假设需要重新登录
                if response.status_code >= 400:
                    print("认证状态检查：服务器错误，可能需要重新登录")
                    return False, self.portal_url
                else:
                    # 其他状态码，保守起见认为已认证
                    return True, None
                
        except Exception as e:
            print(f"检查认证状态失败: {e}")
            # 网络错误等情况，假设需要登录
            return False, self.portal_url
    
    def get_lgtk(self):
        """获取当前cookie中的lgtk值"""
        if not self.cookie:
            return None
            
        # 如果cookie是完整的cookie字符串，解析出lgtk的值
        if 'lgtk=' in self.cookie:
            # 解析cookie字符串，提取lgtk的值
            cookies = {}
            for cookie_pair in self.cookie.split(';'):
                cookie_pair = cookie_pair.strip()
                if '=' in cookie_pair:
                    name, value = cookie_pair.split('=', 1)
                    cookies[name.strip()] = value.strip()
            
            lgtk_value = cookies.get('lgtk')
            return lgtk_value
        
        # 如果cookie本身就是lgtk的值，直接返回
        return self.cookie

    def get_cookie_header(self) -> str:
        if not self.cookie:
            return ""
        c = self.cookie.strip()
        if '=' in c:
            return c
        return f"lgtk={c}"

    def get_requests_cookies(self) -> dict:
        if not self.cookie:
            return {}
        c = self.cookie.strip()
        if '=' in c:
            d = {}
            for p in c.split(';'):
                p = p.strip()
                if '=' in p:
                    k, v = p.split('=', 1)
                    d[k.strip()] = v.strip()
            return d
        return {'lgtk': c}
    
    def extract_auth_from_url(self, url):
        """从URL中提取认证信息
        
        Args:
            url (str): 包含认证信息的URL
            
        Returns:
            tuple: (success, cookie)
        """
        try:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            
            # 尝试从URL参数中提取cookie和用户信息
            cookie = None
            
            # 检查常见的cookie参数名
            for param_name in ['lgtk', 'token', 'cookie']:
                if param_name in query_params:
                    cookie = query_params[param_name][0]
                    break
            
            if cookie:
                return True, cookie
            else:
                print("未能从URL中提取到cookie")
                return False, None
                
        except Exception as e:
            print(f"从URL提取认证信息失败: {e}")
            return False, None
    
    def validate_cookie(self, cookie):
        """验证cookie是否有效
        
        Args:
            cookie (str): 要验证的cookie
            
        Returns:
            bool: cookie是否有效
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # 支持多种cookie格式
            cookies = {}
            if '=' in cookie:
                # 如果是完整的cookie字符串，解析它
                for cookie_pair in cookie.split(';'):
                    if '=' in cookie_pair:
                        key, value = cookie_pair.strip().split('=', 1)
                        cookies[key] = value
            else:
                # 如果只是token值，使用lgtk作为key
                cookies = {'lgtk': cookie}
            
            response = requests.get(
                self.portal_url,
                headers=headers,
                cookies=cookies,
                allow_redirects=False,  # 不自动跟随重定向
                timeout=10,
                verify=False
            )
            try:
                self._update_cookie_from_response(response)
            except Exception:
                pass
            
            print(f"Cookie验证响应状态码: {response.status_code}")
            
            # 根据响应状态判断cookie有效性
            if response.status_code == 200:
                # 检查响应内容是否包含登录相关内容
                content_text = response.text.lower()
                
                # 如果包含登录相关内容，说明cookie无效
                if ('login' in content_text or 'window.location' in content_text or 
                    'redirect' in content_text or 'open.weixin.qq.com' in content_text):
                    print("Cookie验证：检测到登录重定向页面，cookie无效")
                    return False
                else:
                    # 如果返回200且不包含登录相关内容，说明cookie有效
                    print("Cookie验证：cookie有效（200响应且无登录内容）")
                    return True
                    
            elif response.status_code in [302, 301, 303, 307, 308]:
                # 如果是重定向，检查重定向URL
                redirect_url = response.headers.get('Location', '')
                print(f"Cookie验证：重定向到 {redirect_url}")
                
                # 检查重定向URL是否包含login
                if 'login' in redirect_url.lower():
                    print("Cookie验证：重定向到登录页面，cookie无效")
                    return False
                else:
                    # 重定向到非登录页面，cookie有效
                    print("Cookie验证：重定向到非登录页面，cookie有效")
                    return True
            else:
                # 其他状态码，认为cookie无效
                print(f"Cookie验证：收到状态码 {response.status_code}，cookie无效")
                return False
            
        except Exception as e:
            print(f"验证cookie失败: {e}")
            return False

    def _update_cookie_from_response(self, response):
        try:
            jar = getattr(response, 'cookies', None)
            if not jar:
                return
            items = list(jar.items())
            if not items:
                return
            header = '; '.join([f"{k}={v}" for k, v in items])
            if header:
                self.cookie = header
                self.config_manager.set_cookie(header)
                print("Cookie已从响应更新并持久化")
        except Exception:
            pass
