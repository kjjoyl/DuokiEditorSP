"""
飞书多维表格数据同步模块
用于将AI生成的内容同步到飞书多维表格中
"""

import requests
import json
import logging
import time
import threading
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from duoki_editor.utils.config_manager import ConfigManager


class FeishuBitableSync:
    """飞书多维表格数据同步类"""
    
    def __init__(self):
        """初始化飞书同步客户端"""
        # 初始化配置管理器
        self.config_manager = ConfigManager()
        
        # 飞书应用配置（从配置管理器获取，如果为空则使用默认值）
        self.app_id = self.config_manager.get_feishu_app_id() or "cli_a87595f209f2d00d"
        self.app_secret = self.config_manager.get_feishu_app_secret() or "egKRPDQ4CSKZpkCHkk4A0fGlRaLA7BxZ"
        self.tenant_access_token = self.config_manager.get_feishu_tenant_access_token()
        self.refresh_token = self.config_manager.get_feishu_refresh_token()
        
        # 表格配置（从配置管理器获取，如果为空则使用默认值）
        self.app_token = self.config_manager.get_feishu_app_token() or "DW0WbSjM4aDcJBseiN2cJnAdnPh"
        self.table_id = self.config_manager.get_feishu_table_id() or "tblFrmsWjMRcaaez"
        
        # API端点
        self.base_url = "https://open.feishu.cn/open-apis"
        self.records_url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        
        # 令牌刷新定时器
        self._refresh_timer = None
        self._timer_lock = threading.Lock()
        
    def _get_tenant_access_token(self) -> bool:
        """获取租户访问令牌"""
        try:
            token_url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
            headers = {
                "Content-Type": "application/json; charset=utf-8"
            }
            data = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
            
            response = requests.post(token_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                self.logger.debug(f"飞书API响应: {result}")
                
                if result.get("code") == 0:
                    # 检查响应结构 - 飞书API直接在根级别返回token信息
                    if "tenant_access_token" not in result or "expire" not in result:
                        self.logger.error(f"飞书API响应缺少必要字段: {result}")
                        return False
                    
                    # 获取令牌和过期时间
                    self.tenant_access_token = result["tenant_access_token"]
                    expire_seconds = result["expire"]  # 过期时间（秒）
                    
                    # 计算过期时间戳（当前时间 + 过期秒数）
                    expire_timestamp = int(time.time()) + expire_seconds
                    
                    # 保存到配置管理器
                    self.config_manager.set_feishu_tenant_access_token(self.tenant_access_token)
                    self.config_manager.set_feishu_access_token_expire_at(str(expire_timestamp))
                    
                    self.logger.info(f"成功获取飞书租户访问令牌，过期时间: {datetime.fromtimestamp(expire_timestamp)}")
                    
                    # 启动定时刷新任务
                    self._schedule_token_refresh(expire_timestamp)
                    
                    return True
                else:
                    self.logger.error(f"获取租户访问令牌失败，错误码: {result.get('code')}, 错误信息: {result.get('msg', '未知错误')}")
                    return False
            else:
                self.logger.error(f"获取租户访问令牌请求失败: {response.status_code}, {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"获取租户访问令牌时发生异常: {str(e)}")
            return False
    
    def _is_token_expired_or_expiring_soon(self) -> bool:
        """检查令牌是否已过期或即将过期（30分钟内）"""
        try:
            expire_at_str = self.config_manager.get_feishu_access_token_expire_at()
            if not expire_at_str:
                return True  # 没有过期时间，认为需要获取新令牌
            
            expire_timestamp = int(expire_at_str)
            current_timestamp = int(time.time())
            
            # 检查是否在30分钟内过期（30分钟 = 1800秒）
            return (expire_timestamp - current_timestamp) <= 1800
            
        except (ValueError, TypeError):
            self.logger.warning("无法解析令牌过期时间，将重新获取令牌")
            return True
    
    def _schedule_token_refresh(self, expire_timestamp: int):
        """安排令牌刷新任务"""
        with self._timer_lock:
            # 取消之前的定时器
            if self._refresh_timer:
                self._refresh_timer.cancel()
            
            # 计算刷新时间（过期前30分钟）
            current_timestamp = int(time.time())
            refresh_delay = expire_timestamp - current_timestamp - 1800  # 提前30分钟
            
            if refresh_delay > 0:
                self.logger.info(f"将在 {refresh_delay} 秒后自动刷新令牌")
                self._refresh_timer = threading.Timer(refresh_delay, self._auto_refresh_token)
                self._refresh_timer.daemon = True
                self._refresh_timer.start()
            else:
                self.logger.warning("令牌即将过期，立即刷新")
                # 在新线程中立即刷新
                threading.Thread(target=self._auto_refresh_token, daemon=True).start()
    
    def _auto_refresh_token(self):
        """自动刷新令牌的后台任务"""
        self.logger.info("开始自动刷新飞书租户访问令牌")
        success = self._get_tenant_access_token()
        if success:
            self.logger.info("自动刷新令牌成功")
        else:
            self.logger.error("自动刷新令牌失败")
    
    def ensure_valid_token(self) -> bool:
        """确保有有效的令牌"""
        # 如果没有令牌或令牌即将过期，则获取新令牌
        if not self.tenant_access_token or self._is_token_expired_or_expiring_soon():
            return self._get_tenant_access_token()
        return True
        
    def _refresh_access_token(self) -> bool:
        """刷新访问令牌"""
        if not self.refresh_token:
            self.logger.error("没有refresh_token，无法刷新访问令牌")
            return False
            
        try:
            refresh_url = f"{self.base_url}/authen/v1/refresh_access_token"
            headers = {
                "Content-Type": "application/json; charset=utf-8"
            }
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(refresh_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    # 更新令牌
                    self.tenant_access_token = result["data"]["access_token"]
                    new_refresh_token = result["data"].get("refresh_token")
                    
                    # 保存到配置管理器
                    self.config_manager.set_feishu_tenant_access_token(self.tenant_access_token)
                    if new_refresh_token:
                        self.refresh_token = new_refresh_token
                        self.config_manager.set_feishu_refresh_token(self.refresh_token)
                    
                    self.logger.info("成功刷新飞书访问令牌")
                    return True
                else:
                    self.logger.error(f"刷新令牌失败: {result}")
                    return False
            else:
                self.logger.error(f"刷新令牌请求失败: {response.status_code}, {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"刷新令牌时发生异常: {str(e)}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
    
    def _make_request(self, method: str, url: str, data: Optional[Dict] = None, retry_on_auth_error: bool = True) -> Optional[Dict]:
        """发送HTTP请求"""
        try:
            # 确保令牌有效
            if not self.ensure_valid_token():
                self.logger.error("无法获取有效的访问令牌")
                return None
                
            headers = self._get_headers()
            
            if method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=headers, json=data, timeout=30)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=30)
            else:
                self.logger.error(f"不支持的HTTP方法: {method}")
                return None
            
            # 检查响应状态
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    self.logger.info("飞书API请求成功")
                    return result
                else:
                    self.logger.error(f"飞书API返回错误: {result}")
                    return None
            elif response.status_code == 400:
                # 检查是否是令牌无效错误
                try:
                    result = response.json()
                    if result.get("code") == 99991663 and retry_on_auth_error:  # Invalid access token
                        self.logger.warning("访问令牌无效，尝试重新获取令牌")
                        if self._get_tenant_access_token():
                            # 获取成功，重试请求
                            self.logger.info("令牌重新获取成功，重试请求")
                            return self._make_request(method, url, data, retry_on_auth_error=False)
                        else:
                            self.logger.error("令牌重新获取失败")
                            return None
                    else:
                        self.logger.error(f"HTTP请求失败: {response.status_code}, {response.text}")
                        return None
                except json.JSONDecodeError:
                    self.logger.error(f"HTTP请求失败: {response.status_code}, {response.text}")
                    return None
            else:
                self.logger.error(f"HTTP请求失败: {response.status_code}, {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"请求异常: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析错误: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"未知错误: {str(e)}")
            return None
    
    def add_record(self, content_1: str, content_2: str, content_3: str, content_4: str, content_5: str, 
                   npc1: str, npc2: str, keywords: str, user: str) -> Optional[str]:
        """
        向飞书多维表格添加新记录
        
        Args:
            content_1: 第一个方案内容
            content_2: 第二个方案内容
            content_3: 第三个方案内容
            content_4: 第四个方案内容
            content_5: 第五个方案内容
            npc1: NPC1名称
            npc2: NPC2名称
            keywords: 关键字
            user: 当前用户名
            
        Returns:
            Optional[str]: 成功时返回record_id，失败时返回None
        """
        try:
            # 获取当前时间
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 构建请求数据
            record_data = {
                "fields": {
                    "content_1": content_1,
                    "content_2": content_2,
                    "content_3": content_3,
                    "content_4": content_4,
                    "content_5": content_5,
                    "npc1": npc1,
                    "npc2": npc2,
                    "keywords": keywords,
                    "user": user,
                    "date": current_time
                }
            }
            
            self.logger.info(f"准备添加记录到飞书表格: user={user}, npc1={npc1}, npc2={npc2}")
            
            # 发送请求
            result = self._make_request("POST", self.records_url, record_data)
            
            if result and result.get("data") and result["data"].get("record"):
                record_id = result["data"]["record"].get("record_id")
                if record_id:
                    self.logger.info(f"成功添加记录到飞书多维表格，record_id: {record_id}")
                    return record_id
                else:
                    self.logger.error("响应中未找到record_id")
                    return None
            else:
                self.logger.error("添加记录到飞书多维表格失败")
                return None
                
        except Exception as e:
            self.logger.error(f"添加记录时发生异常: {str(e)}")
            return None
    
    def sync_ai_content(self, ai_data: Dict[str, Any]) -> Optional[str]:
        """
        同步AI生成的内容到飞书表格
        
        Args:
            ai_data: 包含AI生成内容的字典，应包含以下键:
                - content_1: 第一个方案内容
                - content_2: 第二个方案内容
                - content_3: 第三个方案内容
                - content_4: 第四个方案内容
                - content_5: 第五个方案内容
                - npc1: NPC1名称
                - npc2: NPC2名称  
                - keywords: 关键字
                - user: 当前用户名
                
        Returns:
            Optional[str]: 成功时返回record_id，失败时返回None
        """
        try:
            # 验证必需的字段
            required_fields = ["content_1", "content_2", "content_3", "content_4", "content_5", "npc1", "npc2", "keywords", "user"]
            for field in required_fields:
                if field not in ai_data:
                    self.logger.error(f"缺少必需字段: {field}")
                    return None
            
            # 提取数据
            content_1 = str(ai_data.get("content_1", "")).strip()
            content_2 = str(ai_data.get("content_2", "")).strip()
            content_3 = str(ai_data.get("content_3", "")).strip()
            content_4 = str(ai_data.get("content_4", "")).strip()
            content_5 = str(ai_data.get("content_5", "")).strip()
            npc1 = str(ai_data.get("npc1", "")).strip()
            npc2 = str(ai_data.get("npc2", "")).strip()
            keywords = str(ai_data.get("keywords", "")).strip()
            user = str(ai_data.get("user", "")).strip()
            
            # 验证至少有一个方案内容不为空
            if not any([content_1, content_2, content_3, content_4, content_5]):
                self.logger.warning("所有方案内容都为空，跳过同步")
                return None
            
            # 添加记录
            return self.add_record(content_1, content_2, content_3, content_4, content_5, npc1, npc2, keywords, user)
            
        except Exception as e:
            self.logger.error(f"同步AI内容时发生异常: {str(e)}")
            return None
    
    def update_record(self, record_id: str, selected: int) -> bool:
        """
        更新飞书多维表格中指定记录的selected字段
        
        Args:
            record_id: 要更新的记录ID
            selected: 选中的tab页索引（1-5）
            
        Returns:
            bool: 是否更新成功
        """
        try:
            # 构建更新URL
            update_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
            
            # 构建请求数据
            update_data = {
                "fields": {
                    "selected": selected
                }
            }
            
            self.logger.info(f"准备更新记录selected字段: record_id={record_id}, selected={selected}")
            
            # 发送PUT请求
            result = self._make_request("PUT", update_url, update_data)
            
            if result:
                self.logger.info(f"成功更新记录selected字段: record_id={record_id}, selected={selected}")
                return True
            else:
                self.logger.error(f"更新记录selected字段失败: record_id={record_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"更新记录时发生异常: {str(e)}")
            return False
    
    def test_connection(self) -> bool:
        """
        测试与飞书API的连接
        
        Returns:
            bool: 连接是否正常
        """
        try:
            # 尝试获取表格信息来测试连接
            test_url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}"
            result = self._make_request("GET", test_url)
            
            if result:
                self.logger.info("飞书API连接测试成功")
                return True
            else:
                self.logger.error("飞书API连接测试失败")
                return False
                
        except Exception as e:
            self.logger.error(f"连接测试时发生异常: {str(e)}")
            return False


# 全局实例
_feishu_sync_instance = None


def get_feishu_sync() -> FeishuBitableSync:
    """获取飞书同步实例（单例模式）"""
    global _feishu_sync_instance
    if _feishu_sync_instance is None:
        _feishu_sync_instance = FeishuBitableSync()
    return _feishu_sync_instance


def sync_ai_content_to_feishu(content_1: str, content_2: str, content_3: str, content_4: str, content_5: str,
                             npc1: str, npc2: str, keywords: str, user: str) -> Optional[str]:
    """
    便捷函数：同步AI生成的内容到飞书多维表格
    
    Args:
        content_1: 第一个方案内容
        content_2: 第二个方案内容
        content_3: 第三个方案内容
        content_4: 第四个方案内容
        content_5: 第五个方案内容
        npc1: NPC1名称
        npc2: NPC2名称
        keywords: 关键字
        user: 当前用户名
        
    Returns:
        Optional[str]: 成功时返回record_id，失败时返回None
    """
    try:
        sync_client = FeishuBitableSync()
        ai_data = {
            'content_1': content_1,
            'content_2': content_2,
            'content_3': content_3,
            'content_4': content_4,
            'content_5': content_5,
            'npc1': npc1,
            'npc2': npc2,
            'keywords': keywords,
            'user': user
        }
        return sync_client.sync_ai_content(ai_data)
    except Exception as e:
        logging.error(f"飞书同步便捷函数异常: {str(e)}")
        return None