#!/usr/bin/env python3
"""
简化文本批量加载器
基于智能文本批量加载器的逻辑，提供简洁的批量文本加载功能
"""

import os
import random
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union

class buding_SimpleTextBatchLoader:
    """简化文本批量加载器"""
    
    # 类级别缓存：存储目录扫描结果
    _scan_cache = {}  # {"directory_path": {"files": [...], "timestamp": time}}
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数"""
        inputs = {
            "required": {
                "directory_path": ("STRING", {"default": "", "tooltip": "文本文件所在目录路径"}),
                "file_extension": (
                    [".txt", ".srt", ".vtt", ".ass", ".ssa", "任意文件"], 
                    {"default": ".txt", "tooltip": "文件扩展名过滤，选择'任意文件'匹配所有文本类文件"}
                ),
                "positive_keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "正向筛选关键词，每行一个"}),
                "positive_input_mode": (["包含匹配", "精确匹配", "正则表达式"], {"default": "包含匹配", "tooltip": "正向关键词匹配模式"}),
                "max_files": ("INT", {"default": 100, "min": 1, "max": 1000, "step": 1, "tooltip": "最大加载文件数量"}),
                "start_index": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "从列表的哪个索引开始"}),
                "always_reload": ("BOOLEAN", {"default": False, "tooltip": "开启后始终重新加载，不使用缓存"}),
                "similarity_threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "模糊匹配度阈值"}),
                "scan_max_depth": ("INT", {"default": 5, "min": 1, "max": 20, "step": 1, "tooltip": "目录扫描最大深度"}),
                "enable_negative_enhance": ("BOOLEAN", {"default": False, "tooltip": "启用反向关键词增强匹配"}),
                "negative_keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "反向排除关键词，每行一个"}),
                "sort_mode": (["文件名(数字优先)", "文件名(字母)", "修改时间(新到旧)", "修改时间(旧到新)", "随机排序"], {"default": "文件名(数字优先)", "tooltip": "文件排序方式"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "启用调试输出"}),
                "mode": (["批量", "单选"], {"default": "批量", "tooltip": "选择输出模式：批量返回整批文件，单选只返回force_select_index指定的文件"}),
                "force_select_index": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "单选模式下的文件索引，从0开始"}),
                "random_selection": ("BOOLEAN", {"default": False, "tooltip": "是否随机选择文件"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "tooltip": "随机种子，0表示自动生成"}),
            }
        }
        return inputs
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("text_content_list", "merged_text_content", "file_paths", "load_log")
    OUTPUT_IS_LIST = (True, False, True, False)  # file_paths也返回列表格式，确保数据一致性
    FUNCTION = "load_text_batch"
    CATEGORY = "buding_Tools/简化文本加载"
    DESCRIPTION = "简化版文本批量加载器，基于SmartTextLoader逻辑"
    
    @classmethod
    def IS_CHANGED(cls, directory_path, file_extension, positive_keywords, positive_input_mode,
                   max_files, start_index, always_reload, similarity_threshold,
                   scan_max_depth, enable_negative_enhance, negative_keywords, sort_mode,
                   debug_mode, mode, force_select_index, random_selection, seed):
        """检查输入是否改变 - 完整包含所有会影响输出的参数"""
        if always_reload:
            return float("nan")  # 强制重新加载
        
        # 使用frozenset确保包含所有影响输出的参数，参数顺序不影响哈希值
        key_params = {
            'directory_path': directory_path,
            'file_extension': file_extension,
            'positive_keywords': positive_keywords,
            'positive_input_mode': positive_input_mode,
            'max_files': max_files,
            'start_index': start_index,
            'similarity_threshold': similarity_threshold,
            'scan_max_depth': scan_max_depth,
            'enable_negative_enhance': enable_negative_enhance,
            'negative_keywords': negative_keywords,
            'sort_mode': sort_mode,
            'mode': mode,
            'force_select_index': force_select_index,
            'random_selection': random_selection,
            'seed': seed,
        }
        return hash(frozenset(key_params.items()))
    
    def load_text_batch(self, directory_path: str, file_extension: str, positive_keywords: str,
                        positive_input_mode: str, max_files: int, start_index: int,
                        always_reload: bool, similarity_threshold: float,
                        scan_max_depth: int, enable_negative_enhance: bool, negative_keywords: str,
                        sort_mode: str, debug_mode: bool, mode: str, force_select_index: int,
                        random_selection: bool, seed: int) -> Tuple[List[str], str, List[str], str]:
        """加载文本批量文件"""
        
        # 清理路径
        directory_path = directory_path.strip().strip('"\'')
        current_time_str = time.strftime("%Y-%m-%d %H:%M")
        
        if not directory_path or not os.path.exists(directory_path):
            status = "📄 ❌ 加载失败：目录不存在"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            if debug_mode:
                print(f"❌ {status}: {directory_path}")
            return [], "", [], log
        
        # 设置随机种子
        if random_selection and seed > 0:
            random.seed(seed)
        
        try:
            # 1. 扫描或获取缓存的文本文件
            text_files = self._get_cached_file_list(directory_path, file_extension, scan_max_depth, debug_mode)
            
            if debug_mode:
                print(f"📁 扫描完成: 找到 {len(text_files)} 个文本文件")
            
            if not text_files:
                status = "📄 ❌ 加载失败：未找到匹配的文件 (请检查后缀)"
                log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
                return [], "", [], log
            
            # 2. 关键词筛选
            filtered_files = self._filter_by_keywords(text_files, positive_keywords, 
                                                     positive_input_mode, similarity_threshold, 
                                                     debug_mode)
            
            if debug_mode:
                print(f"🔍 正向筛选后: {len(filtered_files)} 个文件")
            
            if not filtered_files:
                status = "📄 ❌ 加载失败：未找到匹配的文件 (请检查关键词)"
                log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
                return [], "", [], log
            
            # 3. 反向关键词增强匹配
            if enable_negative_enhance and negative_keywords.strip():
                filtered_files = self._apply_negative_filter(filtered_files, negative_keywords, debug_mode)
                
                if debug_mode:
                    print(f"🚫 反向筛选后: {len(filtered_files)} 个文件")
            
            # 4. 排序
            filtered_files = self._sort_files(filtered_files, sort_mode, debug_mode)
            
            # 5. 随机选择
            if random_selection:
                if seed == 0:
                    seed = random.randint(0, 0xFFFFFFFFFFFFFFFF)
                    random.seed(seed)
                random.shuffle(filtered_files)
                
                if debug_mode:
                    print(f"🎲 随机排序完成，种子: {seed}")
            
            # 6. 设置默认选中索引（用于批量模式的预览）
            selected_index = start_index
            if force_select_index >= 0 and force_select_index < len(filtered_files):
                selected_index = force_select_index
            elif start_index >= len(filtered_files):
                selected_index = max(0, len(filtered_files) - 1)
            
            # 7. 加载文本内容
            text_contents, file_paths = self._load_text_contents(filtered_files, debug_mode)
            
            if not text_contents:
                status = "📄 ❌ 加载失败：无法读取文本文件"
                log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
                return [], "", [], log
            
            # 8. 根据模式处理输出
            if mode == "单选":
                # 单选模式：只返回force_select_index指定的文件
                selected_index = min(force_select_index, len(text_contents) - 1) if text_contents else 0
                selected_content = text_contents[selected_index] if text_contents else ""
                selected_path = file_paths[selected_index] if file_paths else ""
                
                # 所有输出都针对单个文件
                result_contents = [selected_content] if selected_content else []
                result_merged = selected_content
                result_paths = [selected_path] if selected_path else []
                result_count = 1
                
                if debug_mode:
                    print(f"🎯 单选模式：选中第{selected_index}个文件")
                    print(f"📄 返回路径：{selected_path}")
                    
            else:  # 批量模式
                # 批量模式：先应用start_index切片，再限制max_files数量
                result_contents = text_contents
                result_paths = file_paths
                
                # 先应用start_index切片
                if start_index > 0:
                    if start_index < len(result_contents) and start_index < len(result_paths):
                        result_contents = result_contents[start_index:]
                        result_paths = result_paths[start_index:]
                    else:
                        # 如果start_index超出范围，返回空
                        result_contents = []
                        result_paths = []
                
                # 再应用max_files限制
                if max_files > 0:
                    result_contents = result_contents[:max_files]
                    result_paths = result_paths[:max_files]
                
                result_count = len(result_contents)
                
                # 合并所有文本内容
                result_merged = "\n---\n".join(result_contents)
                
                if debug_mode:
                    print(f"📦 批量模式：返回 {len(result_contents)} 个文本列表")
            
            # 生成成功日志
            last_filename = os.path.basename(result_paths[-1]) if result_paths else "None"
            log = (
                f"📊 批量加载完成 | 🔢 总计: {result_count} 个文件\n"
                f"📂 根目录: {directory_path}\n"
                f"🔚 结束于: {last_filename}\n"
                f"🕒 时间: {current_time_str}"
            )
            
            # 9. 返回结果 (与老节点格式一致)
            # 返回格式：(text_content_list, merged_text_content, file_paths, load_log)
            return result_contents, result_merged, result_paths, log
            
        except Exception as e:
            status = f"📄 ❌ 加载失败：{str(e)}"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            if debug_mode:
                print(f"❌ {status}")
                import traceback
                traceback.print_exc()
            return [], "", [], log
    
    def _get_cached_file_list(self, directory_path: str, file_extension: str, max_depth: int, debug_mode: bool) -> List[Dict[str, Any]]:
        """获取缓存的文件列表，避免重复扫描大文件夹"""
        current_time = time.time()
        cache_key = directory_path
        
        # 检查缓存是否有效（30秒内有效）
        if cache_key in self._scan_cache:
            cached = self._scan_cache[cache_key]
            if current_time - cached['timestamp'] < 30:
                if debug_mode:
                    print(f"💾 使用缓存文件列表 (距离上次扫描 {int(current_time - cached['timestamp'])}s)")
                return cached['files']
        
        # 缓存过期或不存在，执行新扫描
        files = self._scan_text_files(directory_path, file_extension, max_depth, debug_mode)
        
        # 更新缓存
        self._scan_cache[cache_key] = {
            'files': files,
            'timestamp': current_time
        }
        
        if debug_mode:
            print(f"🔄 缓存已更新 (扫描 {len(files)} 个文件)")
        
        return files
    
    def _scan_text_files(self, directory_path: str, file_extension: str, max_depth: int, debug_mode: bool) -> List[Dict[str, Any]]:
        """扫描文本文件 - 采用乐观过滤（扩展名）,延迟验证到加载阶段"""
        text_files = []
        
        # 处理文件扩展名选项 (与smart_text_loader逻辑一致)
        if file_extension == "任意文件":
            extensions = {'.txt', '.srt', '.vtt', '.ass', '.ssa', '.md', '.log', '.csv', '.json', '.xml', '.yaml', '.yml'}
        else:
            extensions = {file_extension.strip().lower()}
        
        def scan_recursive(current_dir: str, current_depth: int):
            if current_depth > max_depth:
                return
            
            try:
                for item in os.listdir(current_dir):
                    item_path = os.path.join(current_dir, item)
                    
                    if os.path.isfile(item_path):
                        # 检查扩展名（乐观过滤 - O(1) 查询，不打开文件）
                        file_ext = os.path.splitext(item)[1].lower()
                        if file_ext not in extensions:
                            continue
                        
                        # 直接添加文件信息，验证延迟到加载阶段
                        file_info = {
                            'path': item_path,
                            'filename': item,
                            'mtime': os.path.getmtime(item_path)
                        }
                        text_files.append(file_info)
                    
                    elif os.path.isdir(item_path):
                        scan_recursive(item_path, current_depth + 1)
                        
            except PermissionError:
                if debug_mode:
                    print(f"⚠️ 无权限访问目录: {current_dir}")
            except Exception as e:
                if debug_mode:
                    print(f"⚠️ 扫描目录出错 {current_dir}: {e}")
        
        scan_recursive(directory_path, 0)
        return text_files
    
    def _filter_by_keywords(self, files: List[Dict[str, Any]], keywords: str, mode: str, 
                           threshold: float, debug_mode: bool) -> List[Dict[str, Any]]:
        """优化后的关键词筛选：必须满足所有行（AND 逻辑）"""
        if not keywords.strip():
            return files
        
        keyword_list = [kw.strip().lower() for kw in keywords.split('\n') if kw.strip()]
        filtered_files = []
        
        for file_info in files:
            filename = file_info['filename'].lower()
            
            # 【核心修改点】：初始设为匹配成功，必须通过每一个关键词的考验
            all_keywords_matched = True
            
            for keyword in keyword_list:
                line_matched = False
                
                if mode == "包含匹配":
                    if keyword in filename:
                        line_matched = True
                elif mode == "精确匹配":
                    if keyword == filename:
                        line_matched = True
                elif mode == "正则表达式":
                    try:
                        if re.search(keyword, filename, re.IGNORECASE):
                            line_matched = True
                    except re.error:
                        pass
                
                # 如果有一个关键词没对上，就判死刑，跳出关键词循环
                if not line_matched:
                    all_keywords_matched = False
                    break
            
            # 只有通过了所有关键词筛选的文件才会被添加
            if all_keywords_matched:
                filtered_files.append(file_info)
        
        return filtered_files
    
    def _apply_negative_filter(self, files: List[Dict[str, Any]], negative_keywords: str, debug_mode: bool) -> List[Dict[str, Any]]:
        """应用反向关键词过滤"""
        if not negative_keywords.strip():
            return files
        
        negative_list = [kw.strip().lower() for kw in negative_keywords.split('\n') if kw.strip()]
        filtered_files = []
        
        for file_info in files:
            filename = file_info['filename'].lower()
            
            # 检查是否包含任何反向关键词
            is_negative = any(neg_kw in filename for neg_kw in negative_list)
            
            if not is_negative:
                filtered_files.append(file_info)
        
        return filtered_files
    
    def _sort_files(self, files: List[Dict[str, Any]], sort_mode: str, debug_mode: bool) -> List[Dict[str, Any]]:
        """排序文件"""
        if not files:
            return files
        
        if sort_mode == "文件名(数字优先)":
            def sort_key(item):
                filename = item['filename']
                # 提取数字进行排序
                numbers = re.findall(r'\d+', filename)
                if numbers:
                    return (0, int(numbers[0]), filename.lower())
                else:
                    return (1, 0, filename.lower())
            return sorted(files, key=sort_key)
        
        elif sort_mode == "文件名(字母)":
            return sorted(files, key=lambda x: x['filename'].lower())
        
        elif sort_mode == "修改时间(新到旧)":
            return sorted(files, key=lambda x: x['mtime'], reverse=True)
        
        elif sort_mode == "修改时间(旧到新)":
            return sorted(files, key=lambda x: x['mtime'])
        
        elif sort_mode == "随机排序":
            shuffled = files.copy()
            random.shuffle(shuffled)
            return shuffled
        
        else:
            return files
    
    def _load_text_contents(self, files: List[Dict[str, Any]], debug_mode: bool) -> Tuple[List[str], List[str]]:
        """加载文本文件内容"""
        text_contents = []
        file_paths = []
        
        for file_info in files:
            file_path = file_info['path']
            try:
                if debug_mode:
                    print(f"📝 加载文本: {os.path.basename(file_path)}")
                
                # 使用智能编码检测（简化版）
                content = self._read_text_file(file_path, debug_mode)
                
                if content is not None:
                    text_contents.append(content)
                    file_paths.append(file_path)
                
            except Exception as text_error:
                if debug_mode:
                    print(f"⚠️ 加载文本失败，跳过: {os.path.basename(file_path)}, 错误: {text_error}")
                continue
        
        return text_contents, file_paths
    
    def _read_text_file(self, file_path: str, debug_mode: bool) -> str:
        """读取单个文本文件，使用智能编码检测"""
        encodings_to_try = ['utf-8-sig', 'utf-8', 'gbk', 'utf-16', 'latin-1']
        used_encoding = None
        
        for enc in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                    used_encoding = enc
                    break
            except UnicodeDecodeError:
                continue
        
        if used_encoding is None:
            # 如果都失败了，使用错误处理模式
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            used_encoding = 'utf-8-replace'
        
        if debug_mode:
            print(f"📝 自动检测编码: {used_encoding}")
        
        # 标准化换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        return content

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SimpleTextBatchLoader": buding_SimpleTextBatchLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SimpleTextBatchLoader": "📝 简化文本批量加载器",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
