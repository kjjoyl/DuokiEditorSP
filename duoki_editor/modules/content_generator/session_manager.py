"""
会话管理器

管理对话会话和历史记录
"""

import os
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal


class ChatRecord:
    """对话记录"""
    
    def __init__(self, platform: str, agent: str, user_name: str, 
                 conversation_id: str, chat_id: str, user_message: str, 
                 ai_response: str, created_at: int):
        self.platform = platform
        self.agent = agent
        self.user_name = user_name
        self.conversation_id = conversation_id
        self.chat_id = chat_id
        self.user_message = user_message
        self.ai_response = ai_response
        self.created_at = created_at
        self.timestamp = datetime.fromtimestamp(created_at)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            '平台': self.platform,
            '智能体': self.agent,
            '用户名': self.user_name,
            '会话ID': self.conversation_id,
            '对话ID': self.chat_id,
            '用户消息': self.user_message,
            'AI回复': self.ai_response,
            '创建时间': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            '时间戳': self.created_at
        }
    
    def get_display_name(self) -> str:
        """获取显示名称"""
        return self.timestamp.strftime('%Y-%m-%d %H:%M:%S')


class SessionManager(QObject):
    """会话管理器"""
    
    # 信号定义
    record_saved = pyqtSignal(ChatRecord)  # 记录保存成功
    save_failed = pyqtSignal(str)          # 保存失败
    
    def __init__(self, output_directory: str):
        super().__init__()
        self.output_directory = output_directory
        self.current_records: List[ChatRecord] = []
        self.history_records: List[ChatRecord] = []
        
        # 确保输出目录存在
        os.makedirs(output_directory, exist_ok=True)
    
    def add_record(self, platform: str, agent: str, user_name: str,
                   conversation_id: str, chat_id: str, user_message: str,
                   ai_response: str, created_at: int) -> ChatRecord:
        """
        添加新的对话记录
        
        Args:
            platform: 平台名称
            agent: 智能体名称
            user_name: 用户名
            conversation_id: 会话ID
            chat_id: 对话ID
            user_message: 用户消息
            ai_response: AI回复
            created_at: 创建时间戳
            
        Returns:
            ChatRecord: 创建的记录对象
        """
        record = ChatRecord(
            platform=platform,
            agent=agent,
            user_name=user_name,
            conversation_id=conversation_id,
            chat_id=chat_id,
            user_message=user_message,
            ai_response=ai_response,
            created_at=created_at
        )
        
        self.current_records.append(record)
        
        # 保存到Excel文件
        try:
            self._save_to_excel(record)
            self.record_saved.emit(record)
        except Exception as e:
            self.save_failed.emit(f"保存记录失败: {str(e)}")
        
        return record
    
    def _save_to_excel(self, record: ChatRecord):
        """保存记录到Excel文件"""
        file_path = os.path.join(self.output_directory, f"{record.platform}.xlsx")
        
        # 准备数据
        data = record.to_dict()
        
        try:
            # 检查文件是否存在
            if os.path.exists(file_path):
                # 读取现有数据
                with pd.ExcelFile(file_path) as xls:
                    if record.agent in xls.sheet_names:
                        existing_df = pd.read_excel(file_path, sheet_name=record.agent)
                        # 添加新记录
                        new_df = pd.concat([existing_df, pd.DataFrame([data])], ignore_index=True)
                    else:
                        # 创建新的sheet
                        new_df = pd.DataFrame([data])
                
                # 读取所有现有的sheets
                all_sheets = {}
                for sheet_name in xls.sheet_names:
                    if sheet_name != record.agent:
                        all_sheets[sheet_name] = pd.read_excel(file_path, sheet_name=sheet_name)
                
                # 添加当前sheet
                all_sheets[record.agent] = new_df
                
                # 写入所有sheets
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    for sheet_name, df in all_sheets.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                # 创建新文件
                df = pd.DataFrame([data])
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name=record.agent, index=False)
                    
        except Exception as e:
            raise Exception(f"保存Excel文件失败: {str(e)}")
    
    def get_current_records(self) -> List[ChatRecord]:
        """获取当前会话的记录"""
        return self.current_records.copy()
    
    def get_history_records(self) -> List[ChatRecord]:
        """获取历史记录"""
        return self.history_records.copy()
    
    def clear_current_session(self):
        """清空当前会话"""
        if self.current_records:
            # 将当前记录移到历史记录
            self.history_records.extend(self.current_records)
            self.current_records.clear()
    
    def load_history_from_excel(self, platform: str, agent: str) -> List[ChatRecord]:
        """
        从Excel文件加载历史记录
        
        Args:
            platform: 平台名称
            agent: 智能体名称
            
        Returns:
            List[ChatRecord]: 历史记录列表
        """
        file_path = os.path.join(self.output_directory, f"{platform}.xlsx")
        records = []
        
        try:
            if os.path.exists(file_path):
                df = pd.read_excel(file_path, sheet_name=agent)
                
                for _, row in df.iterrows():
                    # 解析时间戳
                    if '时间戳' in row and pd.notna(row['时间戳']):
                        created_at = int(row['时间戳'])
                    else:
                        # 尝试从创建时间解析
                        try:
                            dt = pd.to_datetime(row['创建时间'])
                            created_at = int(dt.timestamp())
                        except:
                            created_at = int(datetime.now().timestamp())
                    
                    record = ChatRecord(
                        platform=row.get('平台', platform),
                        agent=row.get('智能体', agent),
                        user_name=row.get('用户名', ''),
                        conversation_id=row.get('会话ID', ''),
                        chat_id=row.get('对话ID', ''),
                        user_message=row.get('用户消息', ''),
                        ai_response=row.get('AI回复', ''),
                        created_at=created_at
                    )
                    records.append(record)
                    
        except Exception as e:
            print(f"加载历史记录失败: {str(e)}")
        
        return records