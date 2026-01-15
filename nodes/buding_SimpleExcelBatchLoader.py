import os
import csv
import random
import time
import re
from pathlib import Path

# 尝试导入 openpyxl 以支持 .xlsx
try:
    import openpyxl
except ImportError:
    print("[buding_Tools] 警告: 未找到 openpyxl，.xlsx 功能将受限。请运行: pip install openpyxl")

# 导入通用工具函数
# 注意：通用工具函数不存在，直接使用内置实现


class buding_SimpleExcelBatchLoader:
    def __init__(self):
        # 默认输出路径设为 ComfyUI 的 output 文件夹
        self.comfy_output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "output")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory_path": ("STRING", {"default": "", "tooltip": "要扫描的目录路径"}),
                "file_type": ([".xlsx", ".csv", ".txt", "all"], {"default": "all", "tooltip": "支持的文件格式"}),
                "positive_keywords": ("STRING", {"multiline": True, "default": "", "tooltip": "正向筛选关键词，多行文本输入"}),
                "keyword_input_mode": (["多行文本", "单行文本"], {"default": "多行文本", "tooltip": "正向关键词输入模式"}),
                "keyword_match_mode": (["包含匹配", "精确匹配", "正则表达式"], {"default": "包含匹配", "tooltip": "正向关键词匹配模式"}),
                "max_files": ("INT", {"default": 1, "min": 1, "tooltip": "文件加载上限"}),
                "start_index": ("INT", {"default": 0, "min": 0, "tooltip": "起始索引"}),
                "force_select_index": ("INT", {"default": -1, "min": -1, "tooltip": "强制选择特定文件，-1表示不强制"}),
                "always_reload": ("BOOLEAN", {"default": True, "tooltip": "始终重新加载"}),
                "similarity_threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "tooltip": "模糊匹配度阈值"}),
                "scan_max_depth": ("INT", {"default": 1, "min": 1, "tooltip": "扫描最大深度"}),
                "enable_negative_enhance": ("BOOLEAN", {"default": False, "tooltip": "启用反向关键词增强匹配"}),
                "negative_keywords": ("STRING", {"multiline": True, "default": "", "tooltip": "反向排除关键词"}),
                "sort_mode": (["name", "date_newest", "date_oldest", "size"], {"default": "name", "tooltip": "文件排序方式"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "启用调试模式"}),
                "random_selection": ("BOOLEAN", {"default": False, "tooltip": "随机选择开关"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "tooltip": "随机种子"}),
                # --- 模式控制 ---
                "operation_mode": (["Single (单选模式)", "Bulk Merger (合并模式)"], {"default": "Single (单选模式)", "tooltip": "工作模式选择"}),
                "output_path": ("STRING", {"default": "", "tooltip": "合并模式下的输出路径，留空默认ComfyUI output目录"}),
                "overwrite_output": ("BOOLEAN", {"default": True, "tooltip": "是否覆盖已存在的输出文件"}),
                "generate_merged_text": ("BOOLEAN", {"default": False, "tooltip": "生成合并文本（惰性优化开关，默认关闭）"}),
            }
        }

    RETURN_TYPES = ("STRING", "LIST", "STRING", "STRING")
    RETURN_NAMES = ("file_path_output", "row_content_list", "merged_text_all", "load_log")
    OUTPUT_IS_LIST = (False, True, False, False)  # ✅ 只有 row_content_list 是列表
    FUNCTION = "load_excel_batch"
    CATEGORY = "buding_Tools/资产加载"
    
    # ✅ 缓存机制：30 秒 TTL
    _scan_cache = {}

    def load_excel_batch(
        self,
        directory_path: str,
        file_type: str,
        positive_keywords: str,
        keyword_input_mode: str,
        keyword_match_mode: str,
        max_files: int,
        start_index: int,
        force_select_index: int,
        always_reload: bool,
        similarity_threshold: float,
        scan_max_depth: int,
        enable_negative_enhance: bool,
        negative_keywords: str,
        sort_mode: str,
        debug_mode: bool,
        random_selection: bool,
        seed: int,
        operation_mode: str,
        output_path: str,
        overwrite_output: bool,
        generate_merged_text: bool,
    ):
        # 清理路径
        directory_path = directory_path.strip().strip('"\'')
        current_time_str = time.strftime("%Y-%m-%d %H:%M")

        # 1. 扫描与筛选（使用缓存）
        all_files = self._get_cached_file_list(
            directory_path, file_type, positive_keywords, keyword_input_mode,
            keyword_match_mode, similarity_threshold, scan_max_depth,
            enable_negative_enhance, negative_keywords, sort_mode,
            debug_mode, random_selection, seed, always_reload
        )
        
        if not all_files:
            status = "📊 ❌ 加载失败：未找到匹配文件"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            if debug_mode:
                print(f"[buding_SimpleExcelBatchLoader] {status}")
            return {"result": ("", [], "", log), "ui": {"text": status}}

        # 2. 截取当前批次
        selected_files = all_files[start_index : start_index + max_files]
        
        if not selected_files:
            status = "📊 ❌ 加载失败：索引超出范围"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            if debug_mode:
                print(f"[buding_SimpleExcelBatchLoader] {status}")
            return {"result": ("", [], "", log), "ui": {"text": status}}

        # 3. 执行模式分流
        final_file_path = ""
        rows_for_preview = []
        
        if "Single" in operation_mode:
            # 单选模式
            if 0 <= force_select_index < len(selected_files):
                target_file = selected_files[force_select_index]
            else:
                target_file = selected_files[0]
            final_file_path = target_file
            rows_for_preview = self._read_any_to_rows(target_file)
        else:
            # 合并模式 (Bulk Merger)
            final_file_path = self._perform_bulk_merge(selected_files, output_path, overwrite_output, debug_mode)
            rows_for_preview = self._read_any_to_rows(final_file_path)[:20]  # 仅读取前20行用于预览

        # 4. 惰性资源优化：生成大文本
        merged_text_all = ""
        if generate_merged_text:
            if "Single" in operation_mode:
                # 单选模式下生成文本
                merged_text_all = "\n".join([",".join(map(str, r)) for r in rows_for_preview])
            else:
                # 合并模式下提示节省内存
                merged_text_all = "合并结果已写入物理文件，此处跳过以节省内存"

        # 5. 生成状态信息 (文本进度条)
        status_ui = self._generate_visual_status(len(selected_files), len(all_files), start_idx=start_index)
        
        # 生成成功日志
        last_filename = os.path.basename(selected_files[-1]) if selected_files else "None"
        log = (
            f"📊 批量加载完成 | 🔢 总计: {len(selected_files)} 个文件\n"
            f"📂 根目录: {directory_path}\n"
            f"🔚 结束于: {last_filename}\n"
            f"🕒 时间: {current_time_str}"
        )

        if debug_mode:
            print(f"[buding_SimpleExcelBatchLoader] {status_ui}")
            print(f"   工作模式: {operation_mode}")
            print(f"   输出文件: {final_file_path}")
            print(f"   预览行数: {len(rows_for_preview)}")

        # 6. 智能防洪保护（隐性保障）
        self._smart_sleep(selected_files, operation_mode, debug_mode)

        return {
            "ui": {"text": status_ui},
            "result": (
                final_file_path, 
                [",".join(map(str, r)) for r in rows_for_preview], 
                merged_text_all, 
                log
            )
        }

    def _read_any_to_rows(self, file_path: str) -> list:
        """通用读取：支持 .xlsx, .csv, .txt"""
        rows = []
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".xlsx":
                if 'openpyxl' in globals():
                    wb = openpyxl.load_workbook(file_path, data_only=True)
                    ws = wb.active
                    for row in ws.iter_rows(values_only=True):
                        rows.append(list(row) if row else [])
                    wb.close()
                else:
                    print(f"[buding_Tools] 警告: 需要安装 openpyxl 来读取 .xlsx 文件: {file_path}")
            elif ext == ".csv":
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    rows = list(csv.reader(f))
            elif ext == ".txt":
                # TXT容器化逻辑
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    rows = [["Filename", "Content"], [os.path.basename(file_path), content]]
        except Exception as e:
            print(f"[buding_Tools] 读取失败: {file_path}, {e}")
        return rows

    def _perform_bulk_merge(self, files: list, output_path: str, overwrite_output: bool, debug_mode: bool = False) -> str:
        """执行物理合并逻辑：WPS 兼容性优化"""
        # 确定输出路径
        user_path = output_path.strip()
        if user_path:
            out_file = user_path if user_path.lower().endswith(".csv") else user_path + ".csv"
            # 自动建路逻辑
            out_dir = os.path.dirname(out_file)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)
                if debug_mode:
                    print(f"   自动创建目录: {out_dir}")
        else:
            timestamp = int(time.time())
            out_file = os.path.join(self.comfy_output_dir, f"buding_merged_assets_{timestamp}.csv")

        # 覆盖逻辑
        if not overwrite_output and os.path.exists(out_file):
            out_file = out_file.replace(".csv", f"_{int(time.time())}.csv")
            if debug_mode:
                print(f"   文件已存在，创建新文件: {out_file}")

        # 物理合并写入
        try:
            with open(out_file, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig (BOM) 解决 WPS 乱码
                writer = csv.writer(f)
                main_header = None
                
                for i, f_path in enumerate(files):
                    current_rows = self._read_any_to_rows(f_path)
                    if not current_rows: 
                        continue
                    
                    if debug_mode:
                        print(f"   合并文件 {i+1}/{len(files)}: {os.path.basename(f_path)} ({len(current_rows)} 行)")
                    
                    if i == 0:
                        # 第一个文件：写入全部（包括表头）
                        main_header = current_rows[0] if current_rows else []
                        writer.writerows(current_rows)
                    else:
                        # 后续文件：表头平权逻辑，跳过表头只写数据
                        if len(current_rows) > 1:
                            # 确保列数与主表头一致
                            data_rows = current_rows[1:]
                            if main_header:
                                # 填充列数不足的行
                                for row in data_rows:
                                    while len(row) < len(main_header):
                                        row.append("")
                                writer.writerows(data_rows)
                            else:
                                writer.writerows(data_rows)
                        
            if debug_mode:
                print(f"   合并完成: {out_file}")
                
        except Exception as e:
            print(f"[buding_Tools] 合并失败: {e}")
            return ""
                    
        return out_file

    def _generate_visual_status(self, current_batch: int, total: int, start_idx: int = 0) -> str:
        """生成可视化状态信息"""
        if total == 0: 
            return "⚠️ 无文件"
        
        progress = min(1.0, (start_idx + current_batch) / total)
        bar_len = 10
        filled = int(bar_len * progress)
        bar = "■" * filled + "□" * (bar_len - filled)
        
        batch_num = start_idx // current_batch + 1 if current_batch > 0 else 1
        return f"🚀 第 {batch_num} 批 | [{bar}] {int(progress*100)}% | 范围: {start_idx}-{start_idx+current_batch-1} | 总数: {total}"

    def _get_cached_file_list(self, directory_path: str, file_type: str, positive_keywords: str,
                              keyword_input_mode: str, keyword_match_mode: str, 
                              similarity_threshold: float, scan_max_depth: int,
                              enable_negative_enhance: bool, negative_keywords: str,
                              sort_mode: str, debug_mode: bool, random_selection: bool, 
                              seed: int, always_reload: bool = False) -> list:
        """✅ 缓存包装：30 秒 TTL"""
        # 缓存键：基于扫描相关参数
        cache_key = (
            directory_path, file_type, scan_max_depth,
            positive_keywords, keyword_input_mode, keyword_match_mode,
            enable_negative_enhance, negative_keywords,
            sort_mode, random_selection, seed
        )
        
        current_time = time.time()
        
        # 检查缓存
        if cache_key in self._scan_cache and not always_reload:
            cached_time, cached_files = self._scan_cache[cache_key]
            if current_time - cached_time < 30:  # 30 秒 TTL
                if debug_mode:
                    print(f"[buding_SimpleExcelBatchLoader] ✅ 使用缓存结果")
                return cached_files
        
        # 执行扫描
        result = self._scan_excel_files(
            directory_path, file_type, positive_keywords, keyword_input_mode,
            keyword_match_mode, similarity_threshold, scan_max_depth,
            enable_negative_enhance, negative_keywords, sort_mode,
            debug_mode, random_selection, seed
        )
        
        # 缓存结果
        self._scan_cache[cache_key] = (current_time, result)
        return result

    def _scan_excel_files(
        self, 
        directory_path: str, 
        file_type: str, 
        positive_keywords: str, 
        keyword_input_mode: str,
        keyword_match_mode: str, 
        similarity_threshold: float, 
        scan_max_depth: int,
        enable_negative_enhance: bool, 
        negative_keywords: str, 
        sort_mode: str,
        debug_mode: bool, 
        random_selection: bool, 
        seed: int
    ) -> list:
        """扫描表格文件"""
        if not directory_path or not os.path.exists(directory_path):
            if debug_mode:
                print(f"[buding_SimpleExcelBatchLoader] 目录不存在: {directory_path}")
            return []
        
        # 支持的文件扩展名
        type_extensions = {
            ".xlsx": [".xlsx"],
            ".csv": [".csv"], 
            ".txt": [".txt"],
            "all": [".xlsx", ".csv", ".txt"]
        }
        
        extensions = type_extensions.get(file_type, type_extensions["all"])
        
        # 扫描文件
        all_files = []
        directory = Path(directory_path)
        
        for ext in extensions:
            pattern = f"*{ext}"
            if scan_max_depth == 1:
                files = list(directory.glob(pattern))
            else:
                files = list(directory.rglob(pattern))
                # 限制深度
                if scan_max_depth > 1:
                    files = [f for f in files if len(f.relative_to(directory).parts) <= scan_max_depth]
            
            all_files.extend(files)
        
        # 转换为文件信息字典
        file_infos = []
        for file_path in all_files:
            if file_path.is_file():
                stat = file_path.stat()
                file_infos.append({
                    'path': str(file_path),
                    'name': file_path.name,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                })
        
        if debug_mode:
            print(f"[buding_SimpleExcelBatchLoader] 扫描完成: 找到 {len(file_infos)} 个文件")
        
        # 应用关键词过滤
        if positive_keywords:
            file_infos = self._apply_positive_filter(file_infos, positive_keywords, keyword_input_mode, keyword_match_mode, debug_mode)
        
        if enable_negative_enhance and negative_keywords:
            file_infos = self._apply_negative_filter(file_infos, negative_keywords, debug_mode)
        
        # 排序
        file_infos = self._sort_files(file_infos, sort_mode, debug_mode)
        
        # 随机选择
        if random_selection:
            if seed == 0:
                seed = random.randint(0, 0xFFFFFFFFFFFFFFFF)
            random.seed(seed)
            random.shuffle(file_infos)
            if debug_mode:
                print(f"[buding_SimpleExcelBatchLoader] 随机排序完成，种子: {seed}")
        
        # 返回文件路径列表
        return [info['path'] for info in file_infos]

    def _apply_positive_filter(self, file_infos: list, keywords: str, input_mode: str, match_mode: str, debug_mode: bool = False) -> list:
        """应用正向关键词筛选"""
        if not keywords.strip():
            return file_infos
        
        # 解析关键词
        if input_mode == "多行文本":
            keyword_list = [kw.strip() for kw in keywords.split('\n') if kw.strip()]
        else:
            keyword_list = [kw.strip() for kw in keywords.replace('、', ' ').split() if kw.strip()]
        
        filtered = []
        for file_info in file_infos:
            file_name = file_info['name'].lower()
            
            for keyword in keyword_list:
                keyword_lower = keyword.lower()
                
                if match_mode == "精确匹配":
                    if keyword_lower == file_name:
                        filtered.append(file_info)
                        break
                elif match_mode == "正则表达式":
                    try:
                        if re.search(keyword, file_name, re.IGNORECASE):
                            filtered.append(file_info)
                            break
                    except re.error:
                        pass
                else:  # 包含匹配
                    if keyword_lower in file_name:
                        filtered.append(file_info)
                        break
        
        if debug_mode:
            print(f"[buding_SimpleExcelBatchLoader] 正向筛选: {len(file_infos)} -> {len(filtered)} 个文件")
        
        return filtered

    def _apply_negative_filter(self, file_infos: list, keywords: str, debug_mode: bool = False) -> list:
        """应用反向关键词筛选"""
        if not keywords.strip():
            return file_infos
        
        keyword_list = [kw.strip() for kw in keywords.split('\n') if kw.strip()]
        
        filtered = []
        for file_info in file_infos:
            file_name = file_info['name'].lower()
            should_exclude = False
            
            for keyword in keyword_list:
                if keyword.lower() in file_name:
                    should_exclude = True
                    break
            
            if not should_exclude:
                filtered.append(file_info)
        
        if debug_mode:
            print(f"[buding_SimpleExcelBatchLoader] 反向筛选: {len(file_infos)} -> {len(filtered)} 个文件")
        
        return filtered

    def _sort_files(self, file_infos: list, sort_mode: str, debug_mode: bool = False) -> list:
        """文件排序"""
        if sort_mode == "name":
            sorted_files = sorted(file_infos, key=lambda x: x['name'].lower())
        elif sort_mode == "date_newest":
            sorted_files = sorted(file_infos, key=lambda x: x['mtime'], reverse=True)
        elif sort_mode == "date_oldest":
            sorted_files = sorted(file_infos, key=lambda x: x['mtime'])
        elif sort_mode == "size":
            sorted_files = sorted(file_infos, key=lambda x: x['size'], reverse=True)
        else:
            sorted_files = file_infos
        
        if debug_mode:
            print(f"[buding_SimpleExcelBatchLoader] 排序完成: 模式={sort_mode}")
        
        return sorted_files

    def _smart_sleep(self, selected_files, operation_mode, debug_mode):
        """智能防洪延迟：根据任务强度动态调整"""
        delay = 0.0
        
        # 基础判定：合并模式或大量文件处理
        if "Bulk" in operation_mode:
            delay = 0.05  # 合并模式基础缓冲
        
        if len(selected_files) > 50:
            delay += 0.05
        if len(selected_files) > 100:
            delay += 0.05

        if delay > 0:
            if debug_mode:
                print(f"[buding_Tools] 🛡️ 智能防洪：延迟 {int(delay*1000)}ms 保护系统...")
            time.sleep(delay)  # ✅ 直接使用顶部导入的 time

    @classmethod
    def IS_CHANGED(cls, directory_path, file_type, positive_keywords, keyword_input_mode,
                   keyword_match_mode, max_files, start_index, force_select_index,
                   always_reload, similarity_threshold, scan_max_depth,
                   enable_negative_enhance, negative_keywords, sort_mode,
                   debug_mode, random_selection, seed, operation_mode,
                   output_path, overwrite_output, generate_merged_text):
        """基于关键参数的稳定哈希，防止无限循环重渲染"""
        if always_reload:
            return float("nan")  # 强制重新加载
        
        # ✅ 包含所有 20 个参数，确保参数改变时刷新
        key_params = {
            'directory_path': directory_path,
            'file_type': file_type,
            'positive_keywords': positive_keywords,
            'keyword_input_mode': keyword_input_mode,
            'keyword_match_mode': keyword_match_mode,
            'max_files': max_files,
            'start_index': start_index,
            'force_select_index': force_select_index,
            'similarity_threshold': similarity_threshold,
            'scan_max_depth': scan_max_depth,
            'enable_negative_enhance': enable_negative_enhance,
            'negative_keywords': negative_keywords,
            'sort_mode': sort_mode,  # ← 关键
            'debug_mode': debug_mode,
            'random_selection': random_selection,
            'seed': seed,
            'operation_mode': operation_mode,
            'output_path': output_path,
            'overwrite_output': overwrite_output,
            'generate_merged_text': generate_merged_text,
        }
        return hash(frozenset(key_params.items()))  # ✅ 改用 frozenset 提高性能

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SimpleExcelBatchLoader": buding_SimpleExcelBatchLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SimpleExcelBatchLoader": "📊 buding_SimpleExcelBatchLoader (简化Excel批量加载器)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
