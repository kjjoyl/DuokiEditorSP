"""
对AI批量生成的台词表进行后处理，并转换成游戏后台系统所需的格式
"""
import os
import sys
import pandas as pd
import argparse
import re
import logging

from duoki_editor.utils.constants_loader import get_app_name_map, get_npc_id_map_1, get_npc_id_map_2, get_app_id_map, get_bgm_list, get_prefix_mapping
from duoki_editor.core.scene_graph_manager import SceneGraphManager

logger = logging.getLogger('post_process')

npc_id_map_1 = get_npc_id_map_1()

npc_id_map_2 = get_npc_id_map_2()


npc_id_map = npc_id_map_2


def validate_and_fix_scene_id(scene_id, sheet_name, scene_graph_manager):
    """
    校验并修复sceneId，按照5种匹配规则进行尝试
    
    Args:
        scene_id (str): 原始sceneId
        sheet_name (str): 当前sheet名称
        scene_graph_manager: SceneGraphManager实例
        
    Returns:
        tuple: (是否成功, 修复后的sceneId或None, 错误信息)
    """
    if pd.isna(scene_id) or scene_id == '':
        return False, None, "sceneId为空"
    
    scene_id_str = str(scene_id)
    
    # 直接从原始SceneGraph文件加载指定sheet的数据（不加前缀）
    try:
        from duoki_editor.utils.excel_handler import ExcelHandler
        excel_handler = ExcelHandler()
        cache_dir = scene_graph_manager._get_cache_dir()
        file_path = os.path.join(cache_dir, "restaurant", "SceneGraph.xlsx")
        file_path = os.path.abspath(file_path)
        
        if not os.path.exists(file_path):
            return False, None, f"SceneGraph.xlsx文件不存在于 {file_path}"
        
        # 加载所有sheets
        excel_data = excel_handler.load_excel(file_path)
        
        if not excel_data or sheet_name not in excel_data:
            return False, None, f"SceneGraph中没有找到名为'{sheet_name}'的sheet数据"
        
        # 获取原始的sheet数据（未加前缀）
        sheet_scene_data = excel_data[sheet_name]
        
        if sheet_scene_data.empty:
            return False, None, f"SceneGraph的'{sheet_name}'sheet为空"
        
        # 获取有效的scene_id列表（原始数据，未加前缀）
        if 'scene_id' not in sheet_scene_data.columns:
            return False, None, f"SceneGraph的'{sheet_name}'sheet中没有scene_id列"
        
        valid_scene_ids = set(sheet_scene_data['scene_id'].astype(str).tolist())
        
    except Exception as e:
        return False, None, f"加载SceneGraph数据失败: {str(e)}"
    
    # 规则1: 完全匹配
    if scene_id_str in valid_scene_ids:
        return True, scene_id_str, None
    
    # 规则2: 后缀替换为"通用"
    if '-' in scene_id_str:
        parts = scene_id_str.split('-')
        if len(parts) > 1:
            generic_scene_id = '-'.join(parts[:-1]) + '-通用'
            if generic_scene_id in valid_scene_ids:
                return True, generic_scene_id, None
    
    # 规则3: 添加前缀
    prefix_mapping = get_prefix_mapping()
    prefix = prefix_mapping.get(sheet_name, '')
    
    if prefix:
        prefixed_scene_id = prefix + scene_id_str
        if prefixed_scene_id in valid_scene_ids:
            return True, prefixed_scene_id, None
        
        # 规则4: 添加前缀并将后缀替换为"通用"
        if '-' in scene_id_str:
            parts = scene_id_str.split('-')
            if len(parts) > 1:
                prefixed_generic_scene_id = prefix + '-'.join(parts[:-1]) + '-通用'
                if prefixed_generic_scene_id in valid_scene_ids:
                    return True, prefixed_generic_scene_id, None
                
                # 规则5: 在规则4基础上去掉倒数第二个为单独英文字母的段并使用"通用"后缀
                if len(parts) > 2:
                    second_last = parts[-2]
                    if len(second_last) == 1 and second_last.isalpha() and second_last.isascii():
                        parts.pop(-2)
                        parts[-1] = '通用'
                        prefixed_generic_scene_id_2 = prefix + '-'.join(parts)
                        if prefixed_generic_scene_id_2 in valid_scene_ids:
                            return True, prefixed_generic_scene_id_2, None
    
    # 所有规则都失败
    return False, None, f"无法在SceneGraph中找到匹配的sceneId: {scene_id_str}"


def load_and_preprocess_excel(file_path: str) -> tuple[str, pd.DataFrame]:
    """
    Loads and preprocesses a single project Excel file.
    """
    try:
        xls = pd.ExcelFile(file_path, engine='openpyxl')
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        sheet_name = base_name.split('-english', 1)[0]
        logger.info(f"--- Processing sheet: {sheet_name} from {os.path.basename(file_path)} ---")
        
        df_full = pd.read_excel(xls, engine='openpyxl').fillna('')
    except Exception as e:
        logger.error(f"Failed to load Excel file {file_path}: {str(e)}")
        raise RuntimeError(f"Excel文件加载失败: {file_path}. 错误: {str(e)}")
    df_full['index'] = df_full.index
    return sheet_name, df_full


def find_num_choices(df_full: pd.DataFrame) -> int:
    """
    Finds the number of choices in the 'param1' column.
    Assumes that all choice blocks have the same number of options.
    Raises ValueError if inconsistent number of choices are found.
    """
    if 'param1' not in df_full.columns:
        return 1

    param1_col = df_full['param1'].dropna().astype(str)
    num_choices = 1
    choices = ['0']
    first_found = False

    for text in param1_col:
        matches = re.findall(r'\[([^\]]*\|[^\]]*)\]', text)
        if matches:
            current_choice_count = len(matches[0].split('|'))
            if not first_found:
                num_choices = current_choice_count
                first_found = True
            
            for match in matches:
                choices = match.split('|')
                if len(choices) != num_choices:
                    raise ValueError(
                        f"Inconsistent number of choices found. Expected {num_choices}, "
                        f"but found {len(choices)} in '{text}'"
                    )
    return num_choices, choices

def _get_choice(text, choice_index, num_choices):
    if not isinstance(text, str) or '[' not in text:
        return text

    def replace_match(match):
        # group(1) will be the content inside the brackets, e.g., "A|B|C"
        content = match.group(1)
        
        # Only process if it contains a pipe character (|)
        if '|' not in content:
            return match.group(0)  # Return the original text with brackets
        
        choices = content.split('|')
        
        # This check is now more flexible. If a block has only one option, it's likely a placeholder.
        # It's better to handle mismatches gracefully than to raise an error, 
        # as some fields might intentionally have fewer options.
        if len(choices) != num_choices:
             logger.warning(
                f"Inconsistent number of choices found in '{text}'. "
                f"Expected {num_choices}, but found {len(choices)}. "
                f"The first choice will be used."
            )
        
        return choices[choice_index] if choice_index < len(choices) else choices[0]

    # This regex matches content within brackets
    return re.sub(r'\[([^\]]+)\]', replace_match, text)


def split_df_by_choice(df: pd.DataFrame, choice_index: int, num_choices: int) -> pd.DataFrame:
    """
    Creates a new DataFrame by selecting a specific choice from columns that contain choice syntax.
    """
    df_new = df.copy()
    for col in df_new.columns:
        # Apply choice extraction only to object columns that might contain strings
        if df_new[col].dtype == 'object':
            df_new[col] = df_new[col].apply(lambda x: _get_choice(x, choice_index, num_choices))
    return df_new


def process_single_combination(
    df_ori: pd.DataFrame, df_ori_text: pd.DataFrame, df_ori_other: pd.DataFrame, df_full: pd.DataFrame, 
    npc1: str, npc2: str, npc_duoki: str, difficulty: str, 
    map_name: str, game_name: str, story_version: int, stage_id_gen: str
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """
    Processes data for a single combination of NPCs and difficulty.
    """
    logger.debug(f"Processing pair ({npc1}, {npc2}) with difficulty '{difficulty}'")
    
    data = []
    for idx, step_row in df_ori.iterrows():
        step_name = step_row.get('step_name')
        content = ''
        column_name = f"{npc1}-{npc2}-{difficulty}"
        if column_name in df_full.columns:
            content = df_full.loc[idx, column_name]
        else:
            logger.warning(f"Column {column_name} not found for step {step_name}")
        
        data.append({'step_name': step_name, 'param1': content})

    df_cur = pd.DataFrame(data)
    df_text = df_ori_text.merge(df_cur, on='step_name', how='left')
    df = pd.concat([df_text, df_ori_other]).sort_values('index')

    if 'stage_id' not in df.columns:
        logger.error(f"'stage_id' column not found. Skipping this difficulty.")
        return None, None
        
    df['stage_id'] = stage_id_gen

    df['npc1_character'] = npc_id_map.get(f'{npc1}_{difficulty}', '')
    df['npc2_character'] = npc_id_map.get(f'{npc2}_{difficulty}', '')
    df['stateType'] = game_name
    df['sceneId'] = f'{game_name}-{story_version}'

    age_level_map = {'a7': 1}
    df['age_level'] = age_level_map.get(difficulty[:2], 1)
    df['english_level'] = int(difficulty[-1])
    # npcSceneId: 若原始文件的 stage_name 包含 "show_image_npc"，则为该文件所有对话写入原始文件中 stage_id 列第一行的值；否则为空
    npc_scene_id_val = ''
    try:
        has_show_image_npc = False
        if 'stage_name' in df_full.columns:
            has_show_image_npc = df_full['stage_name'].astype(str).str.contains('show_image_npc', na=False).any()
        if has_show_image_npc and 'stage_id' in df_full.columns:
            first_sid_series = df_full['stage_id'].dropna()
            if len(first_sid_series) > 0:
                npc_scene_id_val = str(first_sid_series.iloc[0])
            else:
                try:
                    npc_scene_id_val = str(df_full['stage_id'].iloc[0])
                except Exception:
                    npc_scene_id_val = ''
    except Exception:
        npc_scene_id_val = ''

    if npc_scene_id_val:
        parts = str(npc_scene_id_val).split('-')
        if len(parts) > 1:
            second = parts[1]
            if '_' in second:
                sub_parts = second.split('_')
                if len(sub_parts) > 1:
                    last_seg = sub_parts[-1]
                    if len(last_seg) == 1 and last_seg.isalpha() and last_seg.isascii():
                        second_clean = '_'.join(sub_parts[:-1])
                        parts[1] = second_clean
                        npc_scene_id_val = '-'.join(parts)

    df['npcSceneId'] = npc_scene_id_val
    stage_cols = ['npc1_character', 'npc2_character', 'npcSceneId', 'stateType', 'sceneId', 'age_level', 'english_level']
    
    df['param_rank'] = df.groupby(['stage_id', 'stage_name', 'speaker'] + stage_cols).cumcount() + 1
    df = df[df.param_rank <= 5]

    # 使用原始行序（df_full 中的 'index' 列）生成稳定的排序键，确保导出顺序与输入一致
    order_df = (
        df.groupby(['stage_id', 'stage_name', 'speaker'], as_index=False)['index']
          .min()
          .rename(columns={'index': 'row_order'})
    )
    res = df.pivot_table(
        index=['stage_id', 'stage_name', 'speaker'] + stage_cols,
        columns='param_rank',
        values='param1',
        aggfunc='first'
    ).reset_index()

    # 合并排序键并按原始行序排序
    res = res.merge(order_df, on=['stage_id', 'stage_name', 'speaker'], how='left')
    res = res.sort_values(['stage_id', 'row_order'])

    stage_data = res[['stage_id'] + stage_cols].drop_duplicates()
    res = res.drop(stage_cols, axis=1)
    
    res.rename(columns={i: f'param{i}' for i in range(1, 6)}, inplace=True)
    for i in range(1, 6):
        if f'param{i}' not in res.columns:
            res[f'param{i}'] = ''
    
    res = res.fillna('')
    
    return res, stage_data


def process_project_excel(file_path: str):
    """
    Processes a single project Excel file to generate speech and stage CSV files.
    This logic is adapted from the get_export_content function in the web app.
    
    Args:
        file_path (str): The path to the input project Excel file.
    """
    try:
        output_dir = os.path.dirname(file_path)
        
        # 1. Load and preprocess data
        sheet_name, df_full = load_and_preprocess_excel(file_path)
        assert len(sheet_name.split('-')) == 3, f'sheet 名称 "{sheet_name}" 不符合规范，应为：地图-玩法-剧情版本'
        map_name, game_name, story_version = sheet_name.split('-')
        game_name = str(game_name).replace('_', '-')
        story_version = int(story_version)

        # 2. Extract metadata
        generated_columns = [col for col in df_full.columns if '-' in col]
        '''
        normalized_columns = []
        for col in generated_columns:
            parts = str(col).split('-')
            if len(parts) == 2:
                new_col = f"{parts[0]}-{parts[1]}-a7e0"
                if new_col not in df_full.columns:
                    try:
                        df_full[new_col] = df_full[col]
                    except Exception:
                        df_full[new_col] = ''
                normalized_columns.append(new_col)
            else:
                normalized_columns.append(col)
        generated_columns = normalized_columns
        '''
        logger.info(f'生成列的数量 = {len(generated_columns)}')
        # 修改版本判断与断言：基于是否包含“多奇”文本
        is_old_version = any('多奇' in str(col) for col in generated_columns)
        global npc_id_map
        npc_id_map = npc_id_map_1 if is_old_version else npc_id_map_2
        logger.info(
            f"使用 npc_id_map_{'1' if is_old_version else '2'}，generated_columns 数量为 {len(generated_columns)}"
        )
        num_choices, choices = find_num_choices(df_full)
        logger.info(f"num_choices = {num_choices}, choices = {choices}")
        assert num_choices >= 1
        if num_choices == 1:
            choices = ['0']

        # 3. Prepare original dataframes for processing
        original_cols = [c for c in df_full.columns if c not in generated_columns]
        df_ori = df_full[original_cols]

        mask_text = df_ori['step_name'].apply(lambda x: str(x).strip() and str(x).strip()[0] not in '（(')
        df_ori_text = df_ori[mask_text].drop('param1', axis=1, errors='ignore')
        df_ori_other = df_ori[~mask_text].copy()
        
        all_res_list = []
        all_stage_data_list = []

        npc_duoki = 'duoki'
        logger.info(f"Using '{npc_duoki}' as duoki.")

        # 4. Process each combination of NPC and difficulty
        for col in generated_columns:
            assert len(col.split('-')) == 3
            npc1, npc2, difficulty = col.split('-')
            for i, choice in enumerate(choices):
                # For each choice, create a new version of the dataframe
                df_full_choice = split_df_by_choice(df_full, choice_index=i, num_choices=num_choices)
                # Also process df_ori_other for the current choice
                df_ori_other_choice = split_df_by_choice(df_ori_other, choice_index=i, num_choices=num_choices)
                # Use a unique stage_id_gen for each combination of npc, difficulty, and choice
                stage_id_gen = f'{map_name}_{game_name}_{choice}_{story_version}_{npc1}-{npc2}_{difficulty[:2]}_{difficulty[-2:]}'
                res, stage_data = process_single_combination(
                    df_ori, df_ori_text, df_ori_other_choice, df_full_choice,
                    npc1, npc2, npc_duoki, difficulty,
                    map_name, game_name, story_version, stage_id_gen
                )
                if res is not None and stage_data is not None:
                    all_res_list.append(res)
                    all_stage_data_list.append(stage_data)

        # 5. Combine and save results
        if not all_res_list:
            logger.warning(f"No content generated for {sheet_name}. No CSV files will be created.")
            return None, None, None

        all_res = pd.concat(all_res_list)
        all_stage_data = pd.concat(all_stage_data_list).drop_duplicates()
        return sheet_name, all_res, all_stage_data

    except Exception as e:
        logger.error(f"❌ Failed to process file {file_path}: {e}", exc_info=True)
        return None, None, None


def load_saved_speech_data(save_data_dir: str) -> dict:
    """
    从保存目录中读取Speech_save.xlsx文件，返回按sheet名称组织的数据字典
    
    Args:
        save_data_dir: 保存数据目录
    
    Returns:
        dict: 按sheet名称组织的DataFrame字典，第1行是列名，跳过第2行，从第3行开始读取数据
    """
    if not save_data_dir or not os.path.exists(save_data_dir):
        return {}
    
    file_path = os.path.join(save_data_dir, 'Speech_save.xlsx')
    if not os.path.exists(file_path):
        logger.info(f"Speech保存文件不存在: {file_path}")
        return {}
    
    try:
        saved_data = {}
        xls = pd.ExcelFile(file_path)
        
        for sheet_name in xls.sheet_names:
            # 读取整个sheet，不设置header
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            
            # 第1行是列名，跳过第2行，从第3行开始读取数据
            if len(df) > 2:
                # 获取第1行作为列名（索引为0）
                column_names = df.iloc[0].tolist()
                # 从第3行开始获取数据（索引为2），跳过第2行
                df_data = df.iloc[2:].reset_index(drop=True)
                df_data.columns = column_names
                
                # 找到id列，过滤掉id为空的行
                if 'id' in df_data.columns:
                    df_data = df_data[df_data['id'].notna()]
                
                # 移除完全为空的行
                df_data = df_data.dropna(how='all')
                
                if not df_data.empty:
                    saved_data[sheet_name] = df_data
                    logger.info(f"从 Speech_save.xlsx 的 {sheet_name} sheet 中加载了 {len(df_data)} 行数据")
        
        return saved_data
    except Exception as e:
        logger.error(f"读取Speech保存文件 {file_path} 时出错: {e}")
        return {}


def load_saved_template_data(save_data_dir: str) -> dict:
    """
    从保存目录中读取TemplateConfig_save.xlsx文件，返回按sheet名称组织的数据字典
    
    Args:
        save_data_dir: 保存数据目录
    
    Returns:
        dict: 按sheet名称组织的DataFrame字典，第1行是列名，跳过第2行，从第3行开始读取数据
    """
    if not save_data_dir or not os.path.exists(save_data_dir):
        return {}
    
    file_path = os.path.join(save_data_dir, 'TemplateConfig_save.xlsx')
    if not os.path.exists(file_path):
        logger.info(f"TemplateConfig保存文件不存在: {file_path}")
        return {}
    
    try:
        saved_data = {}
        xls = pd.ExcelFile(file_path)
        
        for sheet_name in xls.sheet_names:
            # 读取整个sheet，不设置header
            df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            
            # 第1行是列名，跳过第2行，从第3行开始读取数据
            if len(df) > 2:
                # 获取第1行作为列名（索引为0）
                column_names = df.iloc[0].tolist()
                # 从第3行开始获取数据（索引为2），跳过第2行
                df_data = df.iloc[2:].reset_index(drop=True)
                df_data.columns = column_names
                
                # 移除完全为空的行
                df_data = df_data.dropna(how='all')
                
                if not df_data.empty:
                    saved_data[sheet_name] = df_data
                    logger.info(f"从 TemplateConfig_save.xlsx 的 {sheet_name} sheet 中加载了 {len(df_data)} 行数据")
        
        return saved_data
    except Exception as e:
        logger.error(f"读取TemplateConfig保存文件 {file_path} 时出错: {e}")
        return {}


def merge_and_save_workbooks(output_dir: str, all_speech_data: dict, all_stage_data: dict, save_data_dir: str = None, generate_speech: bool = True, generate_template: bool = True):
    """
    Merges collected dataframes into final Excel workbooks with multiple sheets.
    
    Args:
        output_dir: 输出目录
        all_speech_data: 所有语音数据
        all_stage_data: 所有关卡数据
        save_data_dir: 保存数据目录，包含Speech_save.xlsx和TemplateConfig_save.xlsx文件
    """
    logger.info("--- Starting final merge process for Excel workbooks. ---")

    app_name_map = get_app_name_map()

    # --- Process Speech data ---
    if all_speech_data and generate_speech:
        # 加载保存的Speech数据
        saved_speech_data = load_saved_speech_data(save_data_dir)
        
        speech_dfs_by_app = {}
        for project_slug, df in all_speech_data.items():
            app_name_base = project_slug.split('-')[0]
            app_name = app_name_map.get(app_name_base, app_name_base)
            if app_name not in speech_dfs_by_app:
                speech_dfs_by_app[app_name] = []
            
            df_copy = df.copy()
            df_copy['id'] = df_copy.index  # Use original index for stable sort
            speech_dfs_by_app[app_name].append(df_copy)

        speech_output_path = os.path.join(output_dir, 'Speech_ai.xlsx')
        with pd.ExcelWriter(speech_output_path, engine='xlsxwriter') as writer:
            # 获取app_name_map的键列表，用于计算索引
            app_name_keys = list(app_name_map.keys())
            
            for app_name, dfs in speech_dfs_by_app.items():
                logger.info(f"Merging {len(dfs)} project(s) into sheet '{app_name}' for Speech_ai.xlsx")
                
                # 准备要合并的数据列表
                dfs_to_merge = []
                
                # 首先添加保存的数据（如果存在）
                if app_name in saved_speech_data:
                    saved_df = saved_speech_data[app_name].copy()
                    # 重命名字段：stage_name -> stage_type
                    if 'stage_name' in saved_df.columns:
                        saved_df = saved_df.rename(columns={'stage_name': 'stage_type'})
                    dfs_to_merge.append(saved_df)
                    logger.info(f"添加了 {len(saved_df)} 行保存的数据到 {app_name} sheet")
                
                # 然后添加新处理的数据
                merged_new_df = pd.concat(dfs, ignore_index=True)
                # 按 stage_id + 原始行序 排序，保证与输入表一致
                sort_keys = ['stage_id'] + ([ 'row_order' ] if 'row_order' in merged_new_df.columns else [])
                merged_new_df = merged_new_df.sort_values(by=sort_keys)
                # 不导出内部排序辅助列
                merged_new_df = merged_new_df.drop(columns=['row_order'], errors='ignore')
                
                # 重命名字段：stage_name -> stage_type
                if 'stage_name' in merged_new_df.columns:
                    merged_new_df = merged_new_df.rename(columns={'stage_name': 'stage_type'})
                
                dfs_to_merge.append(merged_new_df)
                
                # 合并所有数据
                merged_df = pd.concat(dfs_to_merge, ignore_index=True)
                
                # 根据app_name在app_name_map中的索引计算起始ID
                # 找到对应的中文键名
                chinese_key = None
                for key, value in app_name_map.items():
                    if value == app_name:
                        chinese_key = key
                        break
                
                if chinese_key and chinese_key in app_name_keys:
                    app_index = app_name_keys.index(chinese_key)
                    start_id = app_index * 10000 + 1
                else:
                    # 如果找不到对应的索引，使用默认值
                    start_id = 1
                
                merged_df['id'] = range(start_id, start_id + len(merged_df))
                
                # Reorder columns to have 'id' first, as requested
                cols = ['id'] + [col for col in merged_df.columns if col != 'id']
                merged_df = merged_df[cols]
                
                # Ensure Speech_ai column order exactly as required
                speech_expected_cols = ['id', 'stage_id', 'stage_type', 'speaker', 'param1', 'param2', 'param3', 'param4', 'param5']
                existing_speech_cols = [c for c in speech_expected_cols if c in merged_df.columns]
                merged_df = merged_df[existing_speech_cols]

                # Insert types row as the second row (first data row)
                speech_types_map = {
                    'id': 'int',
                    'stage_id': 'string',
                    'stage_type': 'string',
                    'speaker': 'string',
                    'param1': 'string',
                    'param2': 'string',
                    'param3': 'string',
                    'param4': 'string',
                    'param5': 'string'
                }
                types_row_df = pd.DataFrame([{col: speech_types_map.get(col, 'string') for col in existing_speech_cols}])
                output_df = pd.concat([types_row_df, merged_df], ignore_index=True)

                output_df.to_excel(writer, sheet_name=app_name, index=False)
        logger.info(f"✅ Successfully created '{os.path.basename(speech_output_path)}'")

    # --- Process Stage data ---
    if all_stage_data and generate_template:
        # 加载保存的TemplateConfig数据
        saved_template_data = {}
        if save_data_dir:
            saved_template_data = load_saved_template_data(save_data_dir)
        
        stage_dfs_by_app = {}
        for project_slug, df in all_stage_data.items():
            app_name_base = project_slug.split('-')[0]
            app_name = app_name_map.get(app_name_base, app_name_base)
            if app_name not in stage_dfs_by_app:
                stage_dfs_by_app[app_name] = []
            stage_dfs_by_app[app_name].append(df)

        # 获取app_id_map
        app_id_map = get_app_id_map()
        
        stage_output_path = os.path.join(output_dir, 'TemplateConfig_ai.xlsx')
        with pd.ExcelWriter(stage_output_path, engine='xlsxwriter') as writer:
            for app_name, dfs in stage_dfs_by_app.items():
                logger.info(f"Merging {len(dfs)} project(s) into sheet '{app_name}' for TemplateConfig_ai.xlsx")
                
                # 准备要合并的数据列表
                dfs_to_merge = []
                
                # 首先添加保存的数据（如果存在）
                if app_name in saved_template_data:
                    saved_df = saved_template_data[app_name].copy()
                    dfs_to_merge.append(saved_df)
                    logger.info(f"添加了 {len(saved_df)} 行保存的数据到 {app_name} sheet")
                
                # 然后添加新处理的数据
                merged_new_df = pd.concat(dfs, ignore_index=True)
                merged_new_df = merged_new_df.sort_values(by=['stage_id'])
                merged_new_df = merged_new_df.rename(columns={'age_level': 'age_tpye', 'english_level': 'english_ratio', 'stage_id': 'id', 'stateType': 'templateType'})
                dfs_to_merge.append(merged_new_df)
                
                # 合并所有数据
                merged_df = pd.concat(dfs_to_merge, ignore_index=True)
                
                # sceneId校验和修复
                if 'sceneId' in merged_df.columns:
                    scene_graph_manager = SceneGraphManager()
                    rows_to_drop = []  # 记录需要删除的行索引
                    
                    for index, row in merged_df.iterrows():
                        scene_id = row.get('sceneId')
                        stage_id = row.get('id', '未知')  # 用于日志输出
                        
                        success, fixed_scene_id, error_msg = validate_and_fix_scene_id(scene_id, app_name, scene_graph_manager)
                        
                        if success:
                            if fixed_scene_id != str(scene_id):
                                # sceneId被修复，更新数据并记录日志
                                merged_df.loc[index, 'sceneId'] = fixed_scene_id
                                logger.info(f"[{app_name}] stage_id: {stage_id} - sceneId从 '{scene_id}' 修复为 '{fixed_scene_id}'")
                        else:
                            # 校验失败，记录错误并标记该行删除
                            logger.error(f"[{app_name}] stage_id: {stage_id} - {error_msg}，跳过该行")
                            rows_to_drop.append(index)
                    
                    # 删除校验失败的行
                    if rows_to_drop:
                        merged_df = merged_df.drop(rows_to_drop).reset_index(drop=True)
                        logger.info(f"[{app_name}] 共跳过 {len(rows_to_drop)} 行sceneId校验失败的数据")
                
                # 为每行添加appId和bgm字段
                # appId: 根据sheet名从app_id_map获取
                app_id = app_id_map.get(app_name, 0)  # 如果找不到映射，默认为0
                merged_df['appId'] = app_id
                
                # bgm: 按sheet对应地图名称取列表，并循环填充
                # app_name 与 constants.json 的键一致（如 restaurant/zoo/clothing_store/ocean）
                bgm_list_for_sheet = get_bgm_list(app_name)
                if bgm_list_for_sheet:
                    bgm_values = [bgm_list_for_sheet[i % len(bgm_list_for_sheet)] for i in range(len(merged_df))]
                    merged_df['bgm'] = bgm_values
                else:
                    merged_df['bgm'] = ''  # 如果bgm列表为空，设置为空字符串
                
                # Ensure TemplateConfig_ai column order exactly as required
                template_expected_cols = ['id', 'npc1_character', 'npc2_character', 'npcSceneId', 'templateType', 'sceneId', 'age_tpye', 'english_ratio', 'appId', 'bgm']
                existing_template_cols = [c for c in template_expected_cols if c in merged_df.columns]
                merged_df = merged_df[existing_template_cols]

                # Insert types row as the second row (first data row)
                template_types_map = {
                    'id': 'string',
                    'npc1_character': 'string',
                    'npc2_character': 'string',
                    'npcSceneId': 'string',
                    'templateType': 'string',
                    'sceneId': 'string',
                    'age_tpye': 'int',
                    'english_ratio': 'int',
                    'appId': 'int',
                    'bgm': 'string'
                }
                template_types_row_df = pd.DataFrame([{col: template_types_map.get(col, 'string') for col in existing_template_cols}])
                template_output_df = pd.concat([template_types_row_df, merged_df], ignore_index=True)

                template_output_df.to_excel(writer, sheet_name=app_name, index=False)
        logger.info(f"✅ Successfully created '{os.path.basename(stage_output_path)}'")

def generate_config_files(input_files=None, input_directory=None, output_directory=None, save_data_dir=None, progress_callback=None, generate_speech=True, generate_template=True):
    """
    统一的配置文件生成接口，供content_validator调用
    
    Args:
        input_files: Excel文件路径列表（优先使用）
        input_directory: 包含Excel文件的输入目录（当input_files为None时使用）
        output_directory: 输出目录（当提供时，结果保存到此目录）
        save_data_dir: 保存数据目录，包含Speech_save.xlsx和TemplateConfig_save.xlsx文件
        progress_callback: 可选的进度回调函数，用于UI更新
    
    Returns:
        bool: 生成是否成功
    """
    try:
        if progress_callback:
            progress_callback("开始生成配置文件...")
        
        # 确定Excel文件列表
        excel_file_paths = []
        if input_files:
            # 使用提供的文件列表
            excel_file_paths = [f for f in input_files if f.endswith('.xlsx') and not os.path.basename(f).startswith('~')]
            logger.info(f"Processing {len(excel_file_paths)} files from provided list")
        elif input_directory:
            # 从目录中查找Excel文件
            if not os.path.isdir(input_directory):
                logger.error(f"Error: Input directory '{input_directory}' not found.")
                return False
            
            excel_files = [f for f in os.listdir(input_directory) if f.endswith('.xlsx') and not f.startswith('~')]
            excel_file_paths = [os.path.join(input_directory, f) for f in excel_files]
            logger.info(f"Starting post-processing for directory: {input_directory}")
        else:
            logger.error("Either input_files or input_directory must be provided")
            return False

        if not excel_file_paths:
            logger.warning("No Excel files (.xlsx) found to process.")
            return False

        if progress_callback:
            progress_callback("正在加载NPC映射数据...")
        
        # 确保NPC映射数据已加载
        get_app_name_map()
        
        if progress_callback:
            progress_callback("NPC映射数据加载完成")

        all_speech_data = {}
        all_stage_data = {}
        
        total_files = len(excel_file_paths)
        for i, file_path in enumerate(excel_file_paths):
            file_name = os.path.basename(file_path)
            if progress_callback:
                progress_callback(f"正在处理文件 {i+1}/{total_files}: {file_name}")
            
            try:
                project_slug, speech_df, stage_df = process_project_excel(file_path)
                if project_slug and speech_df is not None and stage_df is not None:
                    all_speech_data[project_slug] = speech_df
                    all_stage_data[project_slug] = stage_df
            except Exception as e:
                logger.error(f"❌ Failed to process file {file_path}: {e}")
                if progress_callback:
                    progress_callback(f"❌ 处理文件 {file_name} 失败: {e}")
        
        if all_speech_data and all_stage_data:
            if progress_callback:
                progress_callback("开始合并和保存工作簿...")
            
            # 确定输出目录
            save_directory = output_directory if output_directory else (input_directory if input_directory else os.path.dirname(excel_file_paths[0]))
            merge_and_save_workbooks(save_directory, all_speech_data, all_stage_data, save_data_dir, generate_speech=generate_speech, generate_template=generate_template)
            
            if progress_callback:
                progress_callback("配置文件生成完成！")
            logger.info("--- Post-processing complete. ---")
            return True
        else:
            logger.error("No valid data to process")
            return False
            
    except Exception as e:
        logger.error(f"Error during config file generation: {e}", exc_info=True)
        return False


def main():
    """
    Main function to run the post-processing script.
    It finds all project-specific Excel files in a given directory and processes them.
    """
    parser = argparse.ArgumentParser(
        description="Post-process batch-generated Excel files to produce final CSV outputs."
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="The directory containing the individual project Excel files generated by batch_gen.py."
    )
    args = parser.parse_args()

    input_directory = args.input_dir
    
    # 使用新的统一接口
    success = generate_config_files(input_directory=input_directory)
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()

