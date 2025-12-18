"""
Coze API客户端

提供与Coze平台的API交互功能
"""

import requests
import json
import time
import hashlib
import logging
from typing import Dict, Any, Optional, Generator
from PyQt6.QtCore import QObject, pyqtSignal, QThread

# 创建logger
logger = logging.getLogger(__name__)

# 为coze_client设置自定义格式器，缩短日志格式
def setup_coze_logger():
    """为coze_client设置自定义的日志格式"""
    # 创建自定义格式器，移除模块路径前缀
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # 为当前logger添加自定义处理器
    if not logger.handlers:
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.setLevel(logging.DEBUG)
        # 防止日志向上传播，避免重复输出
        logger.propagate = False

# 初始化自定义日志格式
setup_coze_logger()


def username_to_user_id(username: str) -> str:
    """
    将用户名转换为数字ID
    使用MD5哈希的前8位转换为整数，确保是正数
    
    Args:
        username: 用户名字符串
        
    Returns:
        str: 数字形式的用户ID
    """
    if not username:
        return "1000000"  # 默认用户ID
    
    # 使用MD5哈希
    hash_object = hashlib.md5(username.encode('utf-8'))
    hex_dig = hash_object.hexdigest()
    
    # 取前8位转换为整数，确保是正数
    user_id = int(hex_dig[:8], 16)
    
    # 确保是正数且在合理范围内
    user_id = abs(user_id) % 2147483647  # 32位整数最大值
    if user_id == 0:
        user_id = 1000000
    
    return str(user_id)


class CozeAPIClient(QObject):
    """Coze API客户端"""
    
    # 信号定义
    conversation_created = pyqtSignal(str)  # 会话创建成功，参数为会话ID
    conversation_failed = pyqtSignal(str)   # 会话创建失败，参数为错误信息
    message_received = pyqtSignal(str)      # 接收到消息，参数为消息内容
    chat_finished = pyqtSignal(dict)        # 对话完成，参数为完整的响应数据
    chat_failed = pyqtSignal(str)           # 对话失败，参数为错误信息
    chat_id_received = pyqtSignal(str)      # 接收到chat_id，参数为chat_id
    stream_aborted = pyqtSignal(str)        # 流式连接被中止，参数为已接收的内容
    non_stream_aborted = pyqtSignal(str)    # 非流式对话被中止，参数为中止消息
    
    def __init__(self, api_base: str, token: str):
        super().__init__()
        self.api_base = api_base.rstrip('/')
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self._should_abort_stream = False  # 用于控制是否中止流式连接
        self._stream_active = False  # 标记是否有活跃的流式连接
        self._should_abort_non_stream = False  # 用于控制是否中止非流式对话
        self._non_stream_active = False  # 标记是否有活跃的非流式对话
        self._should_stop_polling = False  # 轮询停止标志
    
    def abort_stream(self):
        """设置标志以中止流式连接"""
        logger.info("=== abort_stream() 被调用，设置中止标志 ===")
        self._should_abort_stream = True
        logger.info("设置中止流式连接标志")
        
        # 如果当前没有活跃的流式连接，立即发送stream_aborted信号
        # 这样可以确保UI能正确响应中止操作
        if not hasattr(self, '_stream_active') or not self._stream_active:
            logger.info("=== 没有活跃的流式连接，立即发送stream_aborted信号 ===")
            self.stream_aborted.emit("")
    
    def abort_non_stream(self):
        """设置标志以中止非流式对话"""
        logger.info("=== abort_non_stream() 被调用，设置中止标志 ===")
        self._should_abort_non_stream = True
        logger.info("设置中止非流式对话标志")
        
        # 如果当前没有活跃的非流式对话，立即发送non_stream_aborted信号
        if not hasattr(self, '_non_stream_active') or not self._non_stream_active:
            logger.info("=== 没有活跃的非流式对话，立即发送non_stream_aborted信号 ===")
            self.non_stream_aborted.emit("非流式对话被中止")

    def reset_abort_flag(self):
        """重置中止标志"""
        self._should_abort_stream = False
        
    def reset_non_stream_abort_flag(self):
        """重置非流式中止标志"""
        self._should_abort_non_stream = False
    
    def stop_polling(self):
        """停止轮询"""
        self._should_stop_polling = True
        logger.info("=== 设置轮询停止标志 ===")
    
    def reset_polling_flag(self):
        """重置轮询停止标志"""
        self._should_stop_polling = False
    
    def create_conversation(self) -> Optional[str]:
        """
        创建新的会话
        
        Returns:
            str: 会话ID，如果失败返回None
        """
        url = f"{self.api_base}/v1/conversation/create"
        
        try:
            response = requests.post(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if data.get('code') == 0:
                conversation_id = data.get('data', {}).get('id')
                if conversation_id:
                    self.conversation_created.emit(conversation_id)
                    return conversation_id
                else:
                    error_msg = "响应中未找到会话ID"
                    self.conversation_failed.emit(error_msg)
                    return None
            else:
                error_msg = data.get('msg', '创建会话失败')
                self.conversation_failed.emit(error_msg)
                return None
                
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            self.conversation_failed.emit(error_msg)
            return None
        except json.JSONDecodeError as e:
            error_msg = f"响应解析失败: {str(e)}"
            self.conversation_failed.emit(error_msg)
            return None
        except Exception as e:
            error_msg = f"创建会话时发生未知错误: {str(e)}"
            self.conversation_failed.emit(error_msg)
            return None
    
    def send_message(self, bot_id: str, conversation_id: str, user_name: str, message: str, stream: bool = True) -> Optional[Dict[str, Any]]:
        """
        发送消息到指定的Bot
        
        Args:
            bot_id: Bot ID
            conversation_id: 会话ID
            user_name: 用户名
            message: 消息内容
            
        Returns:
            dict: 响应数据，如果失败返回None
        """
        url = f"{self.api_base}/v3/chat"
        
        # 将用户名转换为数字ID
        user_id = username_to_user_id(user_name)
        
        payload = {
            "bot_id": bot_id,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "additional_messages": [
                {
                    "role": "user",
                    "content_type": "text",
                    "content": message
                }
            ],
            "stream": stream
        }
        
        # 在URL Query中添加conversation_id参数
        params = {
            "conversation_id": conversation_id
        }
        
        logger.info(f"发送消息请求 - 流式模式: {stream}")
        
        try:
            
            response = requests.post(
                url, 
                headers=self.headers, 
                json=payload, 
                params=params,
                stream=stream,
                timeout=60
            )
            
            logger.debug(f"响应状态码: {response.status_code}")
            response.raise_for_status()
            
            if stream:
                # 处理流式响应
                logger.info("开始处理流式响应")
                # 重置中止标志
                self.reset_abort_flag()
                # 设置流式连接活跃标志
                self._stream_active = True
                full_content = ""
                chat_data = None
                line_count = 0
                current_event = None
                events_received = []
                
                try:
                    for line in response.iter_lines():
                        # 检查是否需要中止流式连接
                        if self._should_abort_stream:
                            logger.info("检测到中止标志，主动中断流式连接")
                            break
                        if line:
                            line_count += 1
                            line_str = line.decode('utf-8').strip()
                            
                            # 处理事件行
                            if line_str.startswith('event:'):
                                current_event = line_str[6:].strip()  # 移除 'event:' 前缀
                                events_received.append(current_event)
                                logger.debug(f"检测到事件: {current_event}")
                                continue
                            
                            # 处理数据行
                            elif line_str.startswith('data:'):
                                try:
                                    data_str = line_str[5:].strip()  # 移除 'data:' 前缀
                                    if data_str == '[DONE]':
                                        logger.debug("收到 [DONE] 信号，结束流式响应")
                                        break
                                    
                                    # 解析JSON数据
                                    data = json.loads(data_str)
                                    
                                    # 根据事件类型处理数据
                                    if current_event == 'conversation.message.delta':
                                        # 提取内容
                                        content = data.get('content', '')
                                        if content:
                                            # 只在控制台输出content内容，其他信息记录到日志
                                            print(content, end='', flush=True)
                                            full_content += content
                                            self.message_received.emit(content)
                                    
                                    elif current_event == 'conversation.chat.completed':
                                        chat_data = data
                                        logger.debug("对话完成事件收到")
                                    
                                    elif current_event == 'conversation.chat.created':
                                        logger.debug("对话创建事件收到")
                                        # 从对话创建事件中获取chat_id
                                        if 'id' in data:
                                            chat_id = data['id']
                                            logger.info(f"从conversation.chat.created事件获取到chat_id: {chat_id}")
                                            # 通过信号传递chat_id给worker线程
                                            if hasattr(self, 'chat_id_received'):
                                                self.chat_id_received.emit(chat_id)
                                    
                                    elif current_event == 'conversation.chat.in_progress':
                                        logger.debug("对话进行中事件收到")
                                    
                                    # 重置当前事件
                                    current_event = None
                                        
                                except json.JSONDecodeError as e:
                                    logger.warning(f"JSON解析错误: {e}")
                                    continue
                    
                    logger.info(f"流式响应处理完成 - 总行数: {line_count}, 内容长度: {len(full_content)}")
                    logger.debug(f"收到的事件: {events_received}")
                    
                except Exception as e:
                    logger.warning(f"流式响应处理异常: {type(e).__name__} - {str(e)}")
                    logger.debug(f"已收到的事件: {events_received}, 已收到的内容长度: {len(full_content)}")
                    # 清除流式连接活跃标志
                    self._stream_active = False
                    
                    # 如果已经收到了内容，不应该算作失败
                    if full_content.strip():
                        logger.info("虽然发生异常，但已收到内容，视为成功")
                        # 创建一个虚拟的chat_data
                        chat_data = {
                            'id': 'stream_interrupted',
                            'status': 'completed',
                            'full_content': full_content
                        }
                        self.chat_finished.emit(chat_data)
                        return chat_data
                    else:
                        error_msg = f"流式响应异常: {str(e)}"
                        logger.error(error_msg)
                        self.chat_failed.emit(error_msg)
                        return None
                
                # 发送完成信号
                logger.info("流式响应处理完成")
                # 清除流式连接活跃标志
                self._stream_active = False
                
                # 检查是否是因为中止而结束
                if self._should_abort_stream:
                    logger.info("=== 流式连接被主动中止，发送stream_aborted信号 ===")
                    logger.info(f"发送stream_aborted信号，内容长度: {len(full_content)}")
                    self.stream_aborted.emit(full_content)
                    logger.info("=== stream_aborted信号已发送 ===")
                    return {
                        'id': 'stream_aborted',
                        'status': 'aborted',
                        'full_content': full_content
                    }
                
                if chat_data:
                    chat_data['full_content'] = full_content
                    logger.debug("发送chat_finished信号")
                    self.chat_finished.emit(chat_data)
                    return chat_data
                elif full_content.strip():
                    # 如果有内容但没有收到完成事件，也视为成功
                    logger.info("没有收到完成事件，但有内容，创建虚拟完成事件")
                    chat_data = {
                        'id': 'stream_no_completion_event',
                        'status': 'completed',
                        'full_content': full_content
                    }
                    self.chat_finished.emit(chat_data)
                    return chat_data
                else:
                    error_msg = "未收到任何响应内容"
                    logger.error(error_msg)
                    self.chat_failed.emit(error_msg)
                    return None
            else:
                # 处理非流式响应
                logger.info("处理非流式响应")
                
                # 设置非流式活动状态
                self._non_stream_active = True
                
                try:
                    # 检查是否需要中止非流式对话
                    if self._should_abort_non_stream:
                        logger.info("检测到非流式中止请求，停止处理")
                        self.non_stream_aborted.emit("非流式对话已被中止")
                        return None
                    
                    data = response.json()
                    
                    # 检查是否有错误
                    if data.get('code') != 0:
                        error_msg = data.get('msg', '发送消息失败')
                        logger.error(f"API错误: {error_msg}")
                        self.chat_failed.emit(error_msg)
                        return None
                    
                    # 提取响应数据
                    chat_data = data.get('data', {})
                    chat_id = chat_data.get('id')  # 获取chat_id
                    status = chat_data.get('status')
                    
                    # 发出chat_id_received信号，让Worker线程保存chat_id
                    if chat_id:
                        logger.info(f"非流式对话获取到chat_id: {chat_id}")
                        self.chat_id_received.emit(chat_id)
                    
                    logger.debug(f"Chat状态: {status}")
                    
                    # 如果状态是in_progress，需要轮询
                    if status == 'in_progress':
                        logger.info("开始轮询等待完成...")
                        return self._poll_for_completion(conversation_id, chat_id)
                    
                    # 如果状态是completed或其他最终状态，直接处理结果
                    messages = chat_data.get('messages', [])
                    
                    # 找到助手的回复
                    full_content = ""
                    for message in messages:
                        if message.get('role') == 'assistant':
                            # 只保留type为answer的内容
                            message_type = message.get('type', '')
                            if message_type != 'answer':
                                logger.debug(f"忽略非answer类型消息 ({message_type}): {message.get('content', '')[:100]}...")
                                continue
                            
                            content = message.get('content', '')
                            if content:
                                full_content += content
                    
                    logger.info(f"非流式响应完成，内容长度: {len(full_content)}")
                    
                    # 一次性发送完整内容
                    if full_content:
                        self.message_received.emit(full_content)
                    
                    # 发送完成信号
                    chat_data['full_content'] = full_content
                    self.chat_finished.emit(chat_data)
                    return chat_data
                
                finally:
                    # 确保清理非流式活动状态
                    self._non_stream_active = False
                
        except requests.exceptions.RequestException as e:
            error_msg = f"网络请求失败: {str(e)}"
            logger.error(f"网络请求异常: {error_msg}")
            self.chat_failed.emit(error_msg)
            return None
        except Exception as e:
            error_msg = f"发送消息时发生未知错误: {str(e)}"
            logger.error(f"未知异常: {error_msg}")
            self.chat_failed.emit(error_msg)
            return None

    def _poll_for_completion(self, conversation_id: str, chat_id: str, max_attempts: int = 30, interval: float = 2.0) -> Optional[Dict[str, Any]]:
        """
        轮询等待对话完成
        
        Args:
            conversation_id: 会话ID
            chat_id: 对话ID
            max_attempts: 最大轮询次数
            interval: 轮询间隔（秒）
            
        Returns:
            dict: 完成的响应数据，如果失败返回None
        """
        logger.info(f"开始轮询，最大尝试次数: {max_attempts}，间隔: {interval}秒")
        
        # 设置非流式活动状态
        self._non_stream_active = True
        
        try:
            for attempt in range(max_attempts):
                # 检查是否需要停止轮询
                if self._should_stop_polling:
                    logger.info("检测到轮询停止请求，停止轮询")
                    return None
                
                # 检查是否需要中止非流式对话
                if self._should_abort_non_stream:
                    logger.info("检测到非流式中止请求，停止轮询")
                    self.non_stream_aborted.emit("非流式对话已被中止")
                    return None
                
                logger.debug(f"轮询尝试 {attempt + 1}/{max_attempts}")
                
                # 调用轮询API
                poll_data = self.retrieve_chat(conversation_id, chat_id)
                if poll_data is None:
                    logger.warning(f"轮询请求失败，尝试 {attempt + 1}")
                    time.sleep(interval)
                    continue
                
                status = poll_data.get('status')
                logger.debug(f"轮询状态: {status}")
                
                # 检查是否完成
                if status == 'completed':
                    logger.info("对话完成！调用消息接口获取完整消息")
                    
                    # 调用专门的消息接口获取消息
                    messages = self.get_chat_messages(conversation_id, chat_id)
                    if messages is None:
                        error_msg = "获取消息失败"
                        logger.error(error_msg)
                        self.chat_failed.emit(error_msg)
                        return None
                    
                    logger.debug(f"获取到的消息数据类型: {type(messages)}")
                    
                    # 提取助手的回复
                    full_content = ""
                    for message in messages:
                        if message.get('role') == 'assistant':
                            # 只保留type为answer的内容
                            message_type = message.get('type', '')
                            if message_type != 'answer':
                                logger.debug(f"忽略非answer类型消息 ({message_type}): {message.get('content', '')[:100]}...")
                                continue
                            
                            content = message.get('content', '')
                            if content:
                                full_content += content
                    
                    logger.info(f"从消息接口获取到的完整内容长度: {len(full_content)}")
                    
                    # 一次性发送完整内容
                    if full_content:
                        self.message_received.emit(full_content)
                    
                    # 发送完成信号
                    result_data = poll_data.copy()
                    result_data['full_content'] = full_content
                    result_data['messages'] = messages
                    self.chat_finished.emit(result_data)
                    return result_data
                
                elif status == 'failed':
                    error_msg = "对话处理失败"
                    logger.error(f"轮询发现对话失败: {error_msg}")
                    self.chat_failed.emit(error_msg)
                    return None
                
                elif status == 'in_progress':
                    logger.debug(f"对话仍在进行中，等待 {interval} 秒后继续轮询...")
                    time.sleep(interval)
                
                else:
                    logger.warning(f"未知状态: {status}，继续轮询...")
                    time.sleep(interval)
            
            # 超过最大尝试次数
            error_msg = f"轮询超时，已尝试 {max_attempts} 次"
            logger.error(f"轮询超时: {error_msg}")
            self.chat_failed.emit(error_msg)
            return None
        
        finally:
            # 确保清理非流式活动状态
            self._non_stream_active = False

    def retrieve_chat(self, conversation_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        轮询获取对话状态
        
        Args:
            conversation_id: 会话ID
            chat_id: 对话ID
            
        Returns:
            dict: 响应数据，如果失败返回None
        """
        url = f"{self.api_base}/v3/chat/retrieve"
        
        params = {
            "conversation_id": conversation_id,
            "chat_id": chat_id
        }
        
        logger.debug(f"轮询API请求: {url}")
        
        try:
            response = requests.get(
                url, 
                headers=self.headers, 
                params=params,
                timeout=30
            )
            
            logger.debug(f"轮询API响应状态码: {response.status_code}")
            
            response.raise_for_status()
            
            data = response.json()
            
            # 检查是否有错误
            if data.get('code') != 0:
                error_msg = data.get('msg', '轮询请求失败')
                logger.error(f"轮询错误: {error_msg}")
                return None
            
            return data.get('data', {})
                
        except requests.exceptions.RequestException as e:
            error_msg = f"轮询网络请求失败: {str(e)}"
            logger.error(f"轮询网络请求异常: {error_msg}")
            return None
        except Exception as e:
            error_msg = f"轮询时发生未知错误: {str(e)}"
            logger.error(f"轮询未知异常: {error_msg}")
            return None

    def get_chat_messages(self, conversation_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        获取聊天消息
        
        Args:
            conversation_id: 会话ID
            chat_id: 对话ID
            
        Returns:
            dict: 消息数据，如果失败返回None
        """
        url = f"{self.api_base}/v3/chat/message/list"
        params = {
            'conversation_id': conversation_id,
            'chat_id': chat_id
        }
        
        logger.debug(f"获取消息请求: {url}")
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=30
            )
            
            logger.debug(f"获取消息响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('code') == 0:
                    return data.get('data', [])
                else:
                    logger.error(f"获取消息API错误: {data.get('msg', '未知错误')}")
                    return None
            else:
                logger.error(f"获取消息请求失败，状态码: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"获取消息请求异常: {str(e)}")
            return None

    def cancel_chat(self, chat_id: str, conversation_id: str) -> Dict[str, Any]:
        """
        取消进行中的对话并验证取消状态
        
        Args:
            chat_id: 对话ID
            conversation_id: 会话ID
            
        Returns:
            dict: 包含取消结果的字典
                - success: bool, 是否成功
                - status: str, 对话状态 (canceled/failed/other)
                - message: str, 结果消息
        """
        url = f"{self.api_base}/v3/chat/cancel"
        
        payload = {
            "chat_id": chat_id,
            "conversation_id": conversation_id
        }
        
        logger.info(f"取消对话请求 - chat_id: {chat_id}, conversation_id: {conversation_id}")
        
        try:
            # 发送取消请求
            response = requests.post(url, headers=self.headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            if data.get('code') == 0:
                logger.info("取消请求发送成功，验证取消状态...")
                
                # 验证取消状态
                chat_data = self.retrieve_chat(conversation_id, chat_id)
                if chat_data:
                    status = chat_data.get('status', 'unknown')
                    logger.info(f"取消后对话状态: {status}")
                    
                    if status == 'canceled':
                        return {
                            'success': True,
                            'status': 'canceled',
                            'message': '对话已成功取消'
                        }
                    else:
                        return {
                            'success': False,
                            'status': status,
                            'message': f'对话状态为{status}，未完全取消'
                        }
                else:
                    return {
                        'success': False,
                        'status': 'unknown',
                        'message': '无法验证取消状态'
                    }
            else:
                error_msg = data.get('msg', '取消对话失败')
                logger.error(f"取消对话失败: {error_msg}")
                return {
                    'success': False,
                    'status': 'failed',
                    'message': error_msg
                }
                
        except requests.exceptions.RequestException as e:
            error_msg = f"取消对话网络请求失败: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'status': 'error',
                'message': error_msg
            }
        except Exception as e:
            error_msg = f"取消对话时发生未知错误: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'status': 'error',
                'message': error_msg
            }


class CozeWorkerThread(QThread):
    """Coze API工作线程"""
    
    # 信号定义
    conversation_created = pyqtSignal(str)
    conversation_failed = pyqtSignal(str)
    message_received = pyqtSignal(str)
    chat_finished = pyqtSignal(dict)
    chat_failed = pyqtSignal(str)
    chat_cancelled = pyqtSignal(str)  # 新增：对话被取消信号
    stream_aborted = pyqtSignal(str)  # 新增：流式连接被中止信号
    non_stream_aborted = pyqtSignal(str)  # 新增：非流式对话被中止信号
    cancel_status_verified = pyqtSignal(dict)  # 新增：取消状态验证结果信号
    
    def __init__(self, client: CozeAPIClient, action: str, **kwargs):
        super().__init__()
        self.client = client
        self.action = action
        self.kwargs = kwargs
        self._is_cancelled = False
        self._current_chat_id = None  # 存储当前对话ID
        self._current_conversation_id = None  # 存储当前会话ID
        
        # 连接客户端信号
        self.client.conversation_created.connect(self.conversation_created)
        self.client.conversation_failed.connect(self.conversation_failed)
        self.client.message_received.connect(self.message_received)
        self.client.chat_finished.connect(self.chat_finished)
        self.client.chat_failed.connect(self.chat_failed)
        self.client.chat_id_received.connect(self._on_chat_id_received)
        self.client.stream_aborted.connect(self.stream_aborted)
        self.client.stream_aborted.connect(lambda content: logger.info(f"=== Worker收到stream_aborted信号，内容长度: {len(content)} ==="))
        self.client.non_stream_aborted.connect(self.non_stream_aborted)
        self.client.non_stream_aborted.connect(lambda content: logger.info(f"=== Worker收到non_stream_aborted信号: {content} ==="))
    
    def _on_chat_id_received(self, chat_id: str):
        """接收到chat_id时的回调"""
        self._current_chat_id = chat_id
        logger.info(f"Worker线程收到chat_id: {chat_id}")
    
    def run(self):
        """执行API调用"""
        if self._is_cancelled:
            return
            
        try:
            if self.action == 'create_conversation':
                self.client.create_conversation()
            elif self.action == 'send_message':
                # 存储会话ID和对话ID以便取消
                self._current_conversation_id = self.kwargs.get('conversation_id')
                result = self.client.send_message(**self.kwargs)
                if result and 'id' in result:
                    self._current_chat_id = result['id']
        except Exception as e:
            if not self._is_cancelled:
                # 只有在未被取消的情况下才发出错误信号
                logger.error(f"线程执行异常: {str(e)}")
                self.chat_failed.emit(f"执行异常: {str(e)}")
    
    def cancel(self):
        """取消操作"""
        self._is_cancelled = True
        self.quit()
        # 不在这里调用wait()，让调用者决定是否等待
    
    def cancel_stream_chat(self):
        """
        严格的流式对话取消流程：
        1. 发送取消请求
        2. 确认取消成功（data:status=canceled）
        3. 发送验证结果信号
        注意：不调用abort_stream()以避免触发旧的stream_aborted信号
        """
        logger.info("=== 开始严格的流式取消流程 ===")
        
        # 直接设置中止标志，但不触发旧的stream_aborted信号
        self.client._should_abort_stream = True
        logger.info("设置中止流式连接标志（严格模式）")
        
        if self._current_chat_id and self._current_conversation_id:
            logger.info(f"发送取消请求 - chat_id: {self._current_chat_id}, conversation_id: {self._current_conversation_id}")
            
            # 发送取消请求并获取验证结果
            cancel_result = self.client.cancel_chat(self._current_chat_id, self._current_conversation_id)
            
            # 发送验证结果信号，让UI根据结果决定是否重置状态
            self.cancel_status_verified.emit(cancel_result)
            
            if cancel_result['success'] and cancel_result['status'] == 'canceled':
                logger.info("流式对话取消成功，状态已确认为canceled")
            else:
                logger.warning(f"流式对话取消失败或状态异常: {cancel_result}")
        else:
            logger.warning("无法取消对话：缺少chat_id或conversation_id")
            # 发送失败结果
            self.cancel_status_verified.emit({
                'success': False,
                'status': 'error',
                'message': '缺少chat_id或conversation_id，无法发送取消请求'
            })
    
    def cancel_non_stream_chat(self):
        """
        取消非流式对话 - 严格按照流程执行
        流程：点击中止 => 停止轮询 => 发送取消请求 => 确认取消成功 => 处理前端
        """
        logger.info("=== 开始非流式对话取消流程 ===")
        
        # 步骤1：立即停止轮询
        logger.info("步骤1：停止轮询")
        self.client.stop_polling()
        
        # 步骤2：设置非流式中止标志
        logger.info("步骤2：设置非流式中止标志")
        self.client.abort_non_stream()
        
        # 步骤3：发送取消请求并验证状态
        if self._current_chat_id and self._current_conversation_id:
            logger.info(f"步骤3：发送取消请求 - chat_id: {self._current_chat_id}, conversation_id: {self._current_conversation_id}")
            
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                cancel_result = self.client.cancel_chat(self._current_chat_id, self._current_conversation_id)
                
                logger.info(f"取消尝试 {retry_count + 1}/{max_retries}: {cancel_result}")
                
                if cancel_result['success'] and cancel_result['status'] == 'canceled':
                    logger.info("步骤4：取消成功，状态已确认为canceled")
                    self.chat_cancelled.emit("非流式对话已成功取消")
                    return
                elif cancel_result['status'] == 'canceled':
                    # 即使success为False，但状态是canceled，也认为成功
                    logger.info("步骤4：状态已确认为canceled")
                    self.chat_cancelled.emit("非流式对话已成功取消")
                    return
                else:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"取消未完成，状态: {cancel_result['status']}，{2}秒后重试...")
                        time.sleep(2)
                    else:
                        logger.error(f"取消失败，已重试{max_retries}次，最终状态: {cancel_result['status']}")
                        # 不发送chat_cancelled信号，保持UI锁定状态
                        return
        else:
            logger.warning("无法取消非流式对话：缺少chat_id或conversation_id")
            logger.info(f"chat_id: {self._current_chat_id}, conversation_id: {self._current_conversation_id}")
            # 缺少必要信息时，也不发送取消信号，保持UI锁定
            return