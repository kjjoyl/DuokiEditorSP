import pandas as pd
from duoki_editor.utils.excel_handler import ExcelHandler


class SpeechManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SpeechManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.data = {}
            self.excel_handler = ExcelHandler()
            self.load_speech_data()
            SpeechManager._initialized = True

    def load_speech_data(self):
        from duoki_editor.core.data_manager import DataManager
        excel_data = DataManager.load_table_from_mod_or_cache('Speech.xlsx', 'restaurant')
        if not excel_data:
            print('Speech.xlsx数据为空或未找到(mod或cache)')
            return
        total_rows = 0
        for sheet_name, df in excel_data.items():
            if df is None or len(df) <= 1:
                continue
            actual = df.iloc[1:].copy()
            if 'id' in actual.columns:
                actual['id'] = actual['id'].astype(str)
            else:
                actual['id'] = ''
            for c in ['param1', 'param2', 'param3', 'param4', 'param5']:
                if c in actual.columns:
                    actual[c] = actual[c].astype(str)
                else:
                    actual[c] = ''
            actual = actual.dropna(how='all')
            self.data[sheet_name] = actual
            total_rows += len(actual)
        print(f"SpeechManager已初始化，加载 {len(self.data)} 个sheet，共 {total_rows} 行数据")

    def get_sheet_data(self, sheet_name):
        df = self.data.get(sheet_name)
        return df if df is not None else pd.DataFrame()

    def get_rows_by_id(self, item_id):
        key = str(item_id).strip()
        frames = []
        for _, df in self.data.items():
            if df is None or df.empty or 'id' not in df.columns:
                continue
            matched = df[df['id'].astype(str).str.strip() == key]
            if not matched.empty:
                frames.append(matched.copy())
        if frames:
            return pd.concat(frames, ignore_index=True)
        return pd.DataFrame()

    def format_rows_by_id(self, item_id, delimiter='|', sheet_name=None):
        key = str(item_id).strip()
        out_rows = []
        columns_ref = None
        iterable = [(sheet_name, self.data.get(sheet_name))] if sheet_name else list(self.data.items())
        for _, df in iterable:
            if df is None or df.empty or 'id' not in df.columns:
                continue
            key_col = 'stage_id' if 'stage_id' in df.columns else 'id'
            matched = df[df[key_col].astype(str).str.strip() == key]
            if matched.empty:
                continue
            if columns_ref is None:
                columns_ref = list(matched.columns)
            for _, row in matched.iterrows():
                for c in ['param1', 'param2', 'param3', 'param4', 'param5']:
                    if c not in matched.columns:
                        continue
                    val = str(row.get(c) or '').strip()
                    if not val or val.lower() in {'nan', 'none'}:
                        continue
                    parts = [p.strip() for p in val.split(delimiter)]
                    parts = [p for p in parts if p]
                    if not parts:
                        continue
                    for p in parts:
                        new_row = row.copy()
                        for cc in ['param1', 'param2', 'param3', 'param4', 'param5']:
                            if cc in new_row.index:
                                new_row[cc] = ''
                        new_row['param'] = p
                        new_row[c] = p
                        out_rows.append(new_row.to_dict())
        if not out_rows:
            print(f"SpeechManager格式化id无结果: {item_id}")
            return pd.DataFrame()
        print(f"SpeechManager已格式化 id: {item_id}，生成 {len(out_rows)} 行")
        if columns_ref is None:
            return pd.DataFrame(out_rows)
        df_out = pd.DataFrame(out_rows)
        cols = [c for c in columns_ref if c in df_out.columns]
        if 'param' not in cols:
            cols.append('param')
        for c in df_out.columns:
            if c not in cols:
                cols.append(c)
        return df_out[cols]
