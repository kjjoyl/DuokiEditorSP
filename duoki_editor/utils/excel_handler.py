import pandas as pd
import os

class ExcelHandler:
    """Excel文件处理工具类"""
    
    def load_excel(self, file_path):
        """
        加载Excel文件，返回包含所有工作表数据的字典
        
        Args:
            file_path: Excel文件路径
            
        Returns:
            dict: {sheet_name: DataFrame} 格式的字典
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        try:
            # 读取所有工作表，增加错误处理和macOS兼容性
            excel_data = pd.read_excel(
                file_path, 
                sheet_name=None,
                engine='openpyxl'  # 明确指定引擎，提高稳定性
            )
            
            # 验证数据完整性
            if not excel_data:
                raise ValueError(f"Excel文件为空或无法读取: {file_path}")
                
            return excel_data
            
        except PermissionError as e:
            raise PermissionError(f"无权限访问文件: {file_path}. 错误: {str(e)}")
        except pd.errors.EmptyDataError as e:
            raise ValueError(f"Excel文件为空: {file_path}. 错误: {str(e)}")
        except pd.errors.ExcelFileError as e:
            raise ValueError(f"Excel文件格式错误: {file_path}. 错误: {str(e)}")
        except Exception as e:
            # 捕获所有其他异常，防止程序崩溃
            raise RuntimeError(f"加载Excel文件时发生未知错误: {file_path}. 错误: {str(e)}")
    
    def save_excel(self, data_dict, file_path):
        """
        将数据保存为Excel文件
        
        Args:
            data_dict: {sheet_name: DataFrame} 格式的字典
            file_path: 保存的文件路径
        """
        # 确保目录存在
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        
        # 创建ExcelWriter对象
        with pd.ExcelWriter(file_path) as writer:
            # 将每个DataFrame写入对应的工作表
            for sheet_name, df in data_dict.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    def get_sheet_names(self, file_path):
        """
        获取Excel文件中所有工作表的名称
        
        Args:
            file_path: Excel文件路径
            
        Returns:
            list: 工作表名称列表
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 使用pandas获取所有工作表名称
        excel_file = pd.ExcelFile(file_path)
        return excel_file.sheet_names