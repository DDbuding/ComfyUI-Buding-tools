"""
buding_SmartTextLoader - 智能文本批量加载器
支持版本控制、多语言编码、反向筛选、时间戳筛选、文件大小控制、智能排序等功能
"""
import os
import re
import json
import random
import time
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

# 尝试导入natsort用于自然排序
try:
    import natsort
    NATSORT_AVAILABLE = True
except ImportError:
    NATSORT_AVAILABLE = False
    print("⚠️ 建议安装 natsort 以获得更好的自然排序: pip install natsort")

# ComfyUI相关导入
try:
    from comfy.utils import ProgressBar
    # ComfyUI的ProgressBar不支持desc参数，需要适配
    class ComfyUIProgressBar:
        def __init__(self, total):
            self.total = total
            self.pbar = ProgressBar(total)
        def update(self, value, desc=None):
            if desc:
                print(f"{desc}: {value}/{self.total}")
            self.pbar.update(value)
except ImportError:
    # 如果不在ComfyUI环境中，提供简单的替代
    class ComfyUIProgressBar:
        def __init__(self, total):
            self.total = total
        def update(self, value, desc=None):
            if desc:
                print(f"{desc}: {value}/{self.total}")

class buding_SmartTextLoader:
    """智能文本批量加载器"""
    
    def __init__(self):
        # 缓存机制：存储扫描结果以提高性能
        self.cache: Dict[str, Any] = {}
        
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数"""
        inputs = {
            "required": {
                "directory_path": ("STRING", {"default": "", "multiline": False, "tooltip": "要扫描的资产库根目录路径"}),
                "file_extension": (
                    [".txt", ".srt", ".vtt", ".ass", ".ssa", "任意文件"], 
                    {"default": ".txt", "tooltip": "文件扩展名过滤，选择'任意文件'匹配所有文本类文件"}
                ),
                "scan_max_depth": ("INT", {"default": 3, "min": 0, "max": 10, "tooltip": "扫描子目录的最大深度"}),
                "keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "正向匹配关键词，每行一个（或关系）"}),
                "similarity_threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "模糊匹配的最低相似度要求"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "启用调试输出模式"}),
            },
            "optional": {
                # 智能映射系统
                "enable_mapping": ("BOOLEAN", {"default": False, "tooltip": "是否启用语义映射，将代号替换为规范关键词"}),
                "mapping_json": ("STRING", {"default": "{\n  \"temp_01\": \"主角A\",\n  \"temp_02\": \"主角B\",\n  \"draft\": \"草稿版\",\n  \"final\": \"最终版\"\n}", "multiline": True, "tooltip": "JSON格式的映射表，用于规范化路径/文件名"}),
                
                # 反向筛选
                "enable_negative_filter": ("BOOLEAN", {"default": False, "tooltip": "启用反向匹配模式"}),
                "negative_keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "反向排除关键词，每行一个"}),
                
                # 时间戳筛选
                "enable_time_filter": ("BOOLEAN", {"default": False, "tooltip": "启用时间戳筛选功能"}),
                "min_age_days": ("STRING", {"default": "0.0", "tooltip": "文件最小年龄（天），0表示不限制"}),
                "max_age_days": ("STRING", {"default": "0.0", "tooltip": "文件最大年龄（天），0表示今天"}),
                "date_filter_mode": (["修改时间", "创建时间"], {"default": "修改时间", "tooltip": "时间戳筛选类型"}),
                
                # 文件大小筛选
                "enable_size_filter": ("BOOLEAN", {"default": False, "tooltip": "启用文件大小筛选功能"}),
                "min_file_size": ("INT", {"default": 0, "min": 0, "max": 10737418240, "step": 1024, "tooltip": "最小文件大小（字节），最大10737418240字节(10GB)"}),
                "max_file_size": ("INT", {"default": 1048576, "min": 0, "max": 10737418240, "step": 1024, "tooltip": "最大文件大小（字节），最大10737418240字节(10GB)"}),
                
                # 排序与随机化
                "sort_mode": (["文件名(数字优先)", "文件名(字母)", "修改时间(新到旧)", "修改时间(旧到新)", "文件大小(大到小)", "文件大小(小到大)", "随机排序"], {"default": "文件名(数字优先)", "tooltip": "文件排序方式"}),
                "random_selection": ("BOOLEAN", {"default": False, "tooltip": "是否随机选择文件"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "tooltip": "随机种子，0表示自动生成"}),
                
                # 列表操作
                "file_limit": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "输出列表最大文件数量，0表示不限制"}),
                "start_index": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "从列表的哪个索引开始输出"}),
                "select_index": ("INT", {"default": -1, "min": -1, "step": 1, "tooltip": "强制选中列表中的特定索引文件，-1禁用"}),

                # 文本内容处理
                "text_encoding": (["utf-8-sig", "utf-8", "gbk", "自动检测"], {"default": "utf-8-sig", "tooltip": "文本编码格式，中文推荐使用utf-8-sig避免BOM乱码"}),
                "trim_whitespace": ("BOOLEAN", {"default": True, "tooltip": "去除读取内容的首尾空白字符"}),
                "normalize_line_endings": ("BOOLEAN", {"default": True, "tooltip": "标准化换行符为\\n格式"}),
            }
        }
        return inputs

    # 定义输出端口和类型
    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("SELECTED_CONTENT", "SELECTED_PATH", "ALL_PATHS", "FILE_COUNT")
    OUTPUT_IS_LIST = (False, False, False, False)
    FUNCTION = "load_batch"
    CATEGORY = "buding_Tools/File_Assets"
    
    @classmethod
    def IS_CHANGED(cls, directory_path, file_extension, scan_max_depth, keywords, similarity_threshold, debug_mode=False, **kwargs):
        """检查输入是否改变"""
        param_string = f"{directory_path}_{file_extension}_{scan_max_depth}_{keywords}_{similarity_threshold}_{str(kwargs)}"
        return hash(param_string)

    def load_batch(self, directory_path: str, keywords: str, file_extension: str = ".txt", 
                   scan_max_depth: int = 3, similarity_threshold: float = 0.7, 
                   debug_mode: bool = False, enable_mapping: bool = False, 
                   mapping_json: str = "", enable_negative_filter: bool = False, 
                   negative_keywords: str = "", enable_time_filter: bool = False, 
                   min_age_days: str = "0.0", max_age_days: str = "0.0", 
                   date_filter_mode: str = "修改时间", enable_size_filter: bool = False, 
                   min_file_size: int = 0, max_file_size: int = 1048576, 
                   sort_mode: str = "文件名(数字优先)", random_selection: bool = False, 
                   seed: int = 0, file_limit: int = 0, start_index: int = 0, 
                   select_index: int = -1, text_encoding: str = "utf-8-sig", 
                   trim_whitespace: bool = True, normalize_line_endings: bool = True, 
                   **kwargs: Any) -> Tuple[str, str, str, int]:
        """智能文本批量加载主函数"""
        
        # 参数验证：处理字符串转换为float和int
        try:
            min_age_days = float(min_age_days) if min_age_days else 0.0
        except (ValueError, TypeError):
            min_age_days = 0.0
            
        try:
            max_age_days = float(max_age_days) if max_age_days else 0.0
        except (ValueError, TypeError):
            max_age_days = 0.0
            
        try:
            min_file_size = int(min_file_size) if min_file_size else 0
        except (ValueError, TypeError):
            min_file_size = 0
            
        try:
            max_file_size = int(max_file_size) if max_file_size else 1048576
        except (ValueError, TypeError):
            max_file_size = 1048576
        
        # 初始化进度条
        pbar = ComfyUIProgressBar(100)
        pbar.update(5, desc="初始化加载器...")
        
        try:
            # 1. 扫描与缓存
            all_files = self._scan_directory_cached(
                directory_path, scan_max_depth, file_extension, debug_mode
            )
            pbar.update(10, desc=f"找到 {len(all_files)} 个文件。")
            
            # 2. 智能映射处理（新增核心功能）
            if enable_mapping:
                all_files = self._apply_semantic_mapping(all_files, mapping_json, debug_mode)
                pbar.update(15, desc="应用语义映射完成。")
            
            # 3. 正向筛选 (扩展名 + 关键词)
            matched_files = self._filter_positive(
                all_files, keywords, similarity_threshold, debug_mode
            )
            pbar.update(20, desc=f"正向筛选后剩余 {len(matched_files)} 个文件。")
            
            # 4. 反向筛选
            if enable_negative_filter:
                matched_files = self._filter_negative(
                    matched_files, negative_keywords, debug_mode
                )
                pbar.update(30, desc=f"反向筛选后剩余 {len(matched_files)} 个文件。")
            
            # 5. 时间戳筛选
            if enable_time_filter:
                matched_files = self._filter_by_timestamp(
                    matched_files, min_age_days, max_age_days, 
                    date_filter_mode, debug_mode
                )
                pbar.update(40, desc=f"时间筛选后剩余 {len(matched_files)} 个文件。")
                
            # 6. 文件大小筛选
            if enable_size_filter:
                matched_files = self._filter_by_file_size(
                    matched_files, min_file_size, max_file_size, debug_mode
                )
                pbar.update(50, desc=f"大小筛选后剩余 {len(matched_files)} 个文件。")
            
            # 7. 智能排序
            matched_files = self._apply_smart_sorting(matched_files, sort_mode)
            pbar.update(60, desc="完成排序。")
            
            # 8. 应用索引和限制
            final_files = self._apply_limits_and_selection(matched_files, {
                'random_selection': random_selection,
                'seed': seed,
                'file_limit': file_limit,
                'start_index': start_index,
                'select_index': select_index,
                'debug_mode': debug_mode
            })
            pbar.update(70, desc=f"最终输出 {len(final_files)} 个文件。")
            
            # 9. 准备输出数据
            # 注意：使用原始路径进行输出，映射仅用于匹配
            all_paths_list = []
            for f in final_files:
                # 如果有原始路径（经过映射），使用原始路径；否则使用当前路径
                original_path = f.get('original_path', f['path'])
                all_paths_list.append(original_path)
            
            all_paths_json = json.dumps(all_paths_list, ensure_ascii=False)
            file_count = len(all_paths_list)
            
            selected_content, selected_path = "", ""

            if all_paths_list:
                selected_path = all_paths_list[0]
                # 10. 读取第一个文件内容
                selected_content = self._load_file_content(
                    selected_path, text_encoding, 
                    trim_whitespace, normalize_line_endings,
                    debug_mode
                )
                pbar.update(90, desc="加载内容完成。")

            pbar.update(100, desc="处理完毕。")
            
            if debug_mode:
                print(f"🎉 智能文本加载完成: {file_count} 个文件")
                if selected_path:
                    print(f"📄 选中文件: {os.path.basename(selected_path)}")

            return (selected_content, selected_path, all_paths_json, file_count)
            
        except Exception as e:
            error_msg = f"❌ 智能文本加载失败: {str(e)}"
            if debug_mode:
                print(error_msg)
                import traceback
                traceback.print_exc()
            return ("", "", "[]", 0)

    def _scan_directory_cached(self, root_dir: str, max_depth: int, extension: str, debug_mode: bool) -> List[Dict]:
        """扫描目录并使用缓存"""
        # 清理路径
        root_dir = root_dir.strip().strip('"\'')
        
        if not root_dir or not os.path.exists(root_dir):
            if debug_mode:
                print(f"❌ 目录不存在: {root_dir}")
            return []
        
        # 使用根目录、深度、扩展名和目录修改时间作为缓存键
        try:
            dir_mtime = os.path.getmtime(root_dir)
        except OSError:
            dir_mtime = 0
            
        cache_key = f"{root_dir}|{max_depth}|{extension}|{dir_mtime}"
        
        # 检查缓存是否有效
        if cache_key in self.cache:
            if debug_mode:
                print(f"📚 使用缓存：{root_dir}")
            return self.cache[cache_key]
        
        # 执行深度递归扫描
        if debug_mode:
            print(f"🔄 正在扫描目录：{root_dir} (深度: {max_depth}, 扩展名: {extension})")
        
        all_files = []
        root_path = Path(root_dir)
        
        try:
            for root, dirs, files in os.walk(root_dir):
                # 计算当前深度
                current_depth = len(Path(root).relative_to(root_path).parts)
                if current_depth > max_depth:
                    dirs[:] = []  # 阻止 os.walk 继续向下搜索
                    continue
                    
                for file in files:
                    # 扩展名过滤
                    if extension != "任意文件" and not file.lower().endswith(extension.lower()):
                        continue
                    
                    file_path = os.path.join(root, file)
                    
                    try:
                        # 记录文件信息
                        file_info = {
                            'path': file_path,
                            'filename': file,
                            'clean_name': self._clean_filename_for_match(file),
                            'mtime': os.path.getmtime(file_path),
                            'ctime': os.path.getctime(file_path),
                            'size': os.path.getsize(file_path),
                        }
                        all_files.append(file_info)
                    except OSError:
                        # 跳过无法访问的文件
                        continue
                        
        except Exception as e:
            if debug_mode:
                print(f"❌ 目录扫描失败: {e}")
            return []
        
        # 存储到缓存
        self.cache[cache_key] = all_files
        
        if debug_mode:
            print(f"✅ 扫描完成: 找到 {len(all_files)} 个文件")
        
        return all_files

    def _apply_semantic_mapping(self, files: List[Dict], mapping_json: str, debug_mode: bool) -> List[Dict]:
        """应用语义映射，将文件路径中的代号替换为规范化关键词"""
        if not mapping_json or not mapping_json.strip():
            if debug_mode:
                print("⚠️ 映射JSON为空，跳过语义映射")
            return files
        
        try:
            # 解析映射JSON
            mapping_dict = json.loads(mapping_json)
            if not isinstance(mapping_dict, dict):
                if debug_mode:
                    print("❌ 映射JSON格式错误：必须是字典格式")
                return files
            
            if debug_mode:
                print(f"🗺️ 应用语义映射，共 {len(mapping_dict)} 条规则")
                for old, new in mapping_dict.items():
                    print(f"  • {old} → {new}")
            
            # 对每个文件应用映射
            mapped_files = []
            for file_info in files:
                original_path = file_info['path']
                original_filename = file_info['filename']
                original_clean_name = file_info['clean_name']
                
                # 应用映射到完整路径
                mapped_path = original_path
                mapped_filename = original_filename
                mapped_clean_name = original_clean_name
                
                # 对路径中的每个部分应用映射
                path_parts = original_path.replace('\\', '/').split('/')
                mapped_parts = []
                
                for part in path_parts:
                    mapped_part = part
                    for old_term, new_term in mapping_dict.items():
                        if old_term in mapped_part:
                            mapped_part = mapped_part.replace(old_term, new_term)
                    mapped_parts.append(mapped_part)
                
                mapped_path = '\\'.join(mapped_parts) if '\\' in original_path else '/'.join(mapped_parts)
                
                # 对文件名应用映射
                for old_term, new_term in mapping_dict.items():
                    if old_term in mapped_filename:
                        mapped_filename = mapped_filename.replace(old_term, new_term)
                
                # 重新计算映射后的clean_name
                mapped_clean_name = self._clean_filename_for_match(mapped_filename)
                
                # 创建新的文件信息对象
                mapped_file_info = file_info.copy()
                mapped_file_info.update({
                    'path': mapped_path,
                    'filename': mapped_filename,
                    'clean_name': mapped_clean_name,
                    'original_path': original_path,  # 保留原始路径用于最终输出
                })
                
                mapped_files.append(mapped_file_info)
                
                if debug_mode and (mapped_path != original_path or mapped_filename != original_filename):
                    print(f"  🔄 {original_path} → {mapped_path}")
            
            if debug_mode:
                print(f"✅ 语义映射完成，处理了 {len(mapped_files)} 个文件")
            
            return mapped_files
            
        except json.JSONDecodeError as e:
            if debug_mode:
                print(f"❌ 映射JSON解析失败: {e}")
            return files
        except Exception as e:
            if debug_mode:
                print(f"❌ 语义映射应用失败: {e}")
            return files

    def _clean_filename_for_match(self, filename: str) -> str:
        """清理文件名，用于模糊匹配"""
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        
        # 移除常见的版本号和分隔符
        name = re.sub(r'[_\-\s]+', ' ', name)
        
        # 移除数字版本标识 (如 v1, v2, _v1, _v2)
        name = re.sub(r'[ _]?[vV][0-9]+', '', name)
        
        # 移除纯数字（但保留中文数字）
        name = re.sub(r'\b\d+\b', '', name)
        
        # 只保留字母、中文、空格、基本标点
        name = re.sub(r'[^\w\u4e00-\u9fff\s\-_\.\(\)\[\]]', '', name)
        
        return name.lower().strip()

    def _calculate_similarity(self, clean_keyword: str, file_info: Dict) -> float:
        """使用 difflib 计算模糊相似度"""
        import difflib
        clean_filename = file_info['clean_name']
        
        if not clean_keyword or not clean_filename:
            return 0.0

        # SequenceMatcher计算编辑距离相似度
        similarity = difflib.SequenceMatcher(None, clean_keyword, clean_filename).ratio()
        
        # 精确匹配加分
        if clean_keyword == clean_filename:
            similarity = min(1.0, similarity + 0.2)
        # 包含匹配加分
        elif clean_keyword in clean_filename or clean_filename in clean_keyword:
            similarity = min(1.0, similarity + 0.1)
            
        return similarity

    def _filter_positive(self, files: List[Dict], keywords_str: str, threshold: float, debug_mode: bool) -> List[Dict]:
        """正向筛选：文件名必须包含任一关键词，且相似度达标"""
        if not keywords_str:
            return files

        keywords = [kw.strip().lower() for kw in keywords_str.split('\n') if kw.strip()]
        
        if debug_mode:
            print(f"🔍 正向筛选关键词: {keywords}")
        
        filtered_files = []
        for file_info in files:
            for keyword in keywords:
                # 简单包含匹配
                if keyword in file_info['filename'].lower():
                    # 模糊匹配验证
                    similarity = self._calculate_similarity(keyword, file_info)
                    
                    if similarity >= threshold:
                        file_info['match_score'] = similarity
                        file_info['match_keyword'] = keyword
                        filtered_files.append(file_info)
                        if debug_mode:
                            print(f"  ✅ {file_info['filename']} 匹配关键词 '{keyword}' (相似度: {similarity:.3f})")
                        break
                else:
                    # 即使简单包含不匹配，也尝试模糊匹配
                    clean_keyword = self._clean_filename_for_match(keyword)
                    similarity = self._calculate_similarity(clean_keyword, file_info)
                    
                    if similarity >= threshold:
                        file_info['match_score'] = similarity
                        file_info['match_keyword'] = keyword
                        filtered_files.append(file_info)
                        if debug_mode:
                            print(f"  🎯 {file_info['filename']} 模糊匹配关键词 '{keyword}' (相似度: {similarity:.3f})")
                        break
                        
        if debug_mode:
            print(f"✅ 正向筛选结果: {len(filtered_files)}/{len(files)} 个文件")
        
        return filtered_files

    def _filter_negative(self, files: List[Dict], negative_keywords_str: str, debug_mode: bool) -> List[Dict]:
        """反向筛选：移除文件名包含指定关键词的文件"""
        if not negative_keywords_str:
            return files
        
        negative_keywords = [kw.strip().lower() for kw in negative_keywords_str.split('\n') if kw.strip()]
        
        if debug_mode:
            print(f"🚫 反向筛选关键词: {negative_keywords}")
        
        filtered_files = []
        excluded_count = 0
        
        for file_info in files:
            # 检查文件名是否包含任何一个反向关键词
            is_negative_match = any(kw in file_info['filename'].lower() for kw in negative_keywords)
            
            if not is_negative_match:
                filtered_files.append(file_info)
            else:
                excluded_count += 1
                if debug_mode:
                    matched_keywords = [kw for kw in negative_keywords if kw in file_info['filename'].lower()]
                    print(f"  🚫 排除 {file_info['filename']} (匹配: {matched_keywords})")
        
        if debug_mode:
            print(f"✅ 反向筛选结果: 排除 {excluded_count} 个文件，剩余 {len(filtered_files)} 个")
        
        return filtered_files

    def _filter_by_timestamp(self, files: List[Dict], min_age_days: float, max_age_days: float, 
                           date_filter_mode: str, debug_mode: bool) -> List[Dict]:
        """按时间戳筛选文件"""
        if min_age_days == 0.0 and max_age_days == 0.0:
            return files
        
        now = datetime.datetime.now()
        min_time = now - datetime.timedelta(days=min_age_days) if min_age_days > 0 else None
        max_time = now - datetime.timedelta(days=max_age_days) if max_age_days > 0 else now
        
        if debug_mode:
            print(f"⏰ 时间筛选: {min_age_days}-{max_age_days} 天前 ({date_filter_mode})")
            if min_time:
                print(f"   最早时间: {min_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if max_time and max_age_days > 0:
                print(f"   最晚时间: {max_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        filtered_files = []
        excluded_count = 0
        
        for file_info in files:
            file_path = file_info['path']
            
            try:
                # 获取文件时间戳
                if date_filter_mode == "修改时间":
                    timestamp = file_info['mtime']
                else:  # "创建时间"
                    timestamp = file_info['ctime']
                
                file_time = datetime.datetime.fromtimestamp(timestamp)
                
                # 检查时间范围
                if min_time and file_time < min_time:
                    excluded_count += 1
                    if debug_mode:
                        print(f"  ⏰ 排除 {file_info['filename']} (太旧: {file_time.strftime('%Y-%m-%d')})")
                    continue
                if max_time and max_age_days > 0 and file_time > max_time:
                    excluded_count += 1
                    if debug_mode:
                        print(f"  ⏰ 排除 {file_info['filename']} (太新: {file_time.strftime('%Y-%m-%d')})")
                    continue
                
                filtered_files.append(file_info)
                
            except OSError:
                continue
        
        if debug_mode:
            print(f"✅ 时间筛选结果: 排除 {excluded_count} 个文件，剩余 {len(filtered_files)} 个")
        
        return filtered_files

    def _filter_by_file_size(self, files: List[Dict], min_size: int, max_size: int, debug_mode: bool) -> List[Dict]:
        """按文件大小筛选"""
        if debug_mode:
            print(f"📏 大小筛选: {min_size}-{max_size} 字节")
        
        filtered_files = []
        excluded_count = 0
        
        for file_info in files:
            file_size = file_info['size']
            
            # 检查大小范围
            if min_size > 0 and file_size < min_size:
                excluded_count += 1
                if debug_mode:
                    print(f"  📏 排除 {file_info['filename']} (太小: {file_size} 字节)")
                continue
            if max_size > 0 and file_size > max_size:
                excluded_count += 1
                if debug_mode:
                    size_kb = file_size / 1024
                    print(f"  📏 排除 {file_info['filename']} (太大: {size_kb:.1f} KB)")
                continue
            
            filtered_files.append(file_info)
        
        if debug_mode:
            print(f"✅ 大小筛选结果: 排除 {excluded_count} 个文件，剩余 {len(filtered_files)} 个")
        
        return filtered_files

    def _apply_smart_sorting(self, files: List[Dict], sort_mode: str) -> List[Dict]:
        """智能排序算法"""
        if not files:
            return files
        
        if sort_mode == "文件名(数字优先)":
            if NATSORT_AVAILABLE:
                # 使用natsort库进行自然排序
                return natsort.natsorted(files, key=lambda x: x['filename'])
            else:
                # 回退到自定义自然排序
                def natural_key(filename):
                    return [int(text) if text.isdigit() else text.lower() 
                           for text in re.split(r'(\d+)', filename)]
                return sorted(files, key=lambda x: natural_key(x['filename']))
        
        elif sort_mode == "文件名(字母)":
            return sorted(files, key=lambda x: x['filename'].lower())
        
        elif sort_mode == "修改时间(新到旧)":
            return sorted(files, key=lambda x: x['mtime'], reverse=True)
        
        elif sort_mode == "修改时间(旧到新)":
            return sorted(files, key=lambda x: x['mtime'])
        
        elif sort_mode == "文件大小(大到小)":
            return sorted(files, key=lambda x: x['size'], reverse=True)
        
        elif sort_mode == "文件大小(小到大)":
            return sorted(files, key=lambda x: x['size'])
        
        elif sort_mode == "随机排序":
            # 注意：这里不使用种子，种子在后面的随机选择中使用
            import random
            shuffled = files.copy()
            random.shuffle(shuffled)
            return shuffled
        
        else:
            return files

    def _apply_limits_and_selection(self, files: List[Dict], kwargs: Dict) -> List[Dict]:
        """应用索引限制和选择"""
        if not files:
            return []
        
        result_files = files.copy()
        
        # 随机选择
        if kwargs['random_selection']:
            used_seed = kwargs['seed']
            if used_seed == 0:
                used_seed = random.randint(1, 2_147_483_647)
            
            rng = random.Random(used_seed)
            rng.shuffle(result_files)
            
            if kwargs['debug_mode']:
                print(f"🎲 随机选择使用种子: {used_seed}")
        
        # 应用起始索引
        if kwargs['start_index'] > 0:
            if kwargs['start_index'] < len(result_files):
                result_files = result_files[kwargs['start_index']:]
            else:
                result_files = []
        
        # 应用数量限制
        if kwargs['file_limit'] > 0 and len(result_files) > kwargs['file_limit']:
            result_files = result_files[:kwargs['file_limit']]
        
        # 强制选择特定索引
        if kwargs['select_index'] >= 0 and kwargs['select_index'] < len(result_files):
            selected_file = result_files[kwargs['select_index']]
            result_files = [selected_file]
        
        return result_files

    def _load_file_content(self, file_path: str, encoding: str, trim_whitespace: bool, 
                          normalize_line_endings: bool, debug: bool) -> str:
        """根据编码加载文件内容"""
        content = ""
        
        try:
            # 1. 编码检测和加载
            if encoding == "自动检测":
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
            else:
                # 使用指定编码
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                if debug_mode:
                    print(f"📝 使用指定编码: {encoding}")

            # 2. 内容后处理
            if normalize_line_endings:
                # 标准化换行符 (Windows/Linux/Mac 统一为 \n)
                content = content.replace('\r\n', '\n').replace('\r', '\n')
            
            if trim_whitespace:
                content = content.strip()
                
            return content
            
        except Exception as e:
            error_msg = f"[READ ERROR] 文件: {os.path.basename(file_path)}, 编码: {encoding}, 错误: {str(e)}"
            if debug_mode:
                print(error_msg)
            return error_msg


# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SmartTextLoader": buding_SmartTextLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SmartTextLoader": "📝 智能文本批量加载器",
}
