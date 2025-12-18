import pandas as pd
from duoki_editor.utils.excel_handler import ExcelHandler


class TemplateConfigManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TemplateConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.data = {}
            self.excel_handler = ExcelHandler()
            self.load_template_config_data()
            TemplateConfigManager._initialized = True

    def load_template_config_data(self):
        from duoki_editor.core.data_manager import DataManager
        excel_data = DataManager.load_table_from_mod_or_cache('TemplateConfig.xlsx', 'restaurant')
        if not excel_data:
            print('TemplateConfig.xlsx数据为空或未找到(mod或cache)')
            return
        total_rows = 0
        for sheet_name, df in excel_data.items():
            if df is None or len(df) <= 1:
                continue
            actual = df.iloc[1:].copy()
            cols = list(actual.columns)
            if 'npc1' in cols and 'npc1_character' not in cols:
                actual.rename(columns={'npc1': 'npc1_character'}, inplace=True)
            if 'npc2' in cols and 'npc2_character' not in cols:
                actual.rename(columns={'npc2': 'npc2_character'}, inplace=True)
            if 'npc1_name' in cols and 'npc1_character' not in cols:
                actual.rename(columns={'npc1_name': 'npc1_character'}, inplace=True)
            if 'npc2_name' in cols and 'npc2_character' not in cols:
                actual.rename(columns={'npc2_name': 'npc2_character'}, inplace=True)
            if 'id' in actual.columns:
                actual['id'] = actual['id'].astype(str)
            else:
                actual['id'] = ''
            if 'npc1_character' in actual.columns:
                actual['npc1_character'] = actual['npc1_character'].astype(str)
            else:
                actual['npc1_character'] = ''
            if 'npc2_character' in actual.columns:
                actual['npc2_character'] = actual['npc2_character'].astype(str)
            else:
                actual['npc2_character'] = ''
            actual = actual.dropna(how='all')
            self.data[sheet_name] = actual
            total_rows += len(actual)
        print(f"TemplateConfigManager已初始化，加载 {len(self.data)} 个sheet，共 {total_rows} 行数据")

    def get_sheet_names(self):
        return list(self.data.keys())

    def get_ids_by_sheet(self, sheet_name):
        df = self.data.get(sheet_name)
        if df is None or df.empty or 'id' not in df.columns:
            return []
        vals = []
        for v in df['id']:
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s:
                vals.append(s)
        return vals

    def get_npcs_by_id(self, template_id):
        key = str(template_id).strip()
        for _, df in self.data.items():
            if df is None or df.empty:
                continue
            if 'id' not in df.columns or 'npc1_character' not in df.columns or 'npc2_character' not in df.columns:
                continue
            matched = df[df['id'].astype(str).str.strip() == key]
            if matched.empty:
                continue
            r = matched.iloc[0]
            npc1 = '' if pd.isna(r.get('npc1_character')) else str(r.get('npc1_character')).strip()
            npc2 = '' if pd.isna(r.get('npc2_character')) else str(r.get('npc2_character')).strip()
            return npc1, npc2
        return None

