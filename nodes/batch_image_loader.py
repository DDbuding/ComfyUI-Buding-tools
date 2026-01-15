"""
buding_BatchImageLoader - 智能图像批量加载器
专为AI图像资产管理设计，支持大规模图像处理的性能优化和智能筛选

核心功能：
- 两遍扫描内存优化机制
- OpenCV/Pillow双后端支持
- PNG元数据智能筛选
- 分辨率和宽高比精确匹配
- 智能映射系统
- 分层错误处理机制
"""

import os
import re
import json
import random
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union
import numpy as np
import torch

# 图像处理库导入
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("⚠️ OpenCV未找到，将使用Pillow作为图像后端")

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("❌ Pillow未找到，无法加载图像")

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

# 自然排序支持
try:
    from natsort import natsorted
    NATSORT_AVAILABLE = True
except ImportError:
    NATSORT_AVAILABLE = False
    print("⚠️ 建议安装 natsort 以获得更好的自然排序: pip install natsort")


class buding_BatchImageLoader:
    """
    智能图像批量加载器
    
    专为AI图像资产管理设计，支持：
    - 大规模图像内存优化处理
    - 基于元数据的智能筛选
    - 工作流尺寸精确匹配
    - 智能映射和错误恢复
    """
    
    # 静态缓存，用于存储已扫描的路径和元数据
    cache: Dict[str, Any] = {}
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数"""
        inputs = {
            "required": {
                "directory_path": ("STRING", {"default": "", "multiline": False, "tooltip": "要扫描的资产库根目录路径"}),
                "image_extension": ([".png|.jpg|.jpeg", ".png", ".jpg", ".jpeg", "any"], 
                                   {"default": ".png|.jpg|.jpeg", "tooltip": "使用 '|' 分隔。'any' 匹配所有格式。"}),
                "keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "正向匹配关键词，每行一个（或关系）"}),
                "similarity_threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "模糊匹配的最低相似度要求"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "启用调试输出模式"}),
            },
            "optional": {
                # 图像特有功能
                "metadata_keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "在PNG元数据中搜索关键词"}),
                "min_resolution": ("INT", {"default": 512, "min": 0, "max": 32768, "step": 64, "tooltip": "图像最小宽度/高度要求，最大32768像素"}),
                "max_resolution": ("INT", {"default": 2048, "min": 0, "max": 32768, "step": 64, "tooltip": "图像最大宽度/高度限制，最大32768像素"}),
                "aspect_ratio": (["any", "1:1", "16:9", "4:3", "3:2", "portrait"], {"default": "any", "tooltip": "宽高比筛选"}),
                
                # 性能与鲁棒性
                "fast_scan_mode": ("BOOLEAN", {"default": True, "tooltip": "两遍扫描：先元数据筛选，再加载像素"}),
                "scan_max_depth": ("INT", {"default": 10, "min": 1, "max": 100, "step": 1, "tooltip": "目录扫描最大深度，1表示只扫描当前目录"}),
                "image_backend": (["OpenCV", "Pillow"], {"default": "OpenCV" if OPENCV_AVAILABLE else "Pillow", "tooltip": "图像加载后端"}),
                "on_io_error": (["停止并报错", "跳过并警告"], {"default": "停止并报错", "tooltip": "文件缺失等IO错误处理"}),
                "on_data_error": (["跳过并警告", "停止并报错"], {"default": "跳过并警告", "tooltip": "文件损坏等数据错误处理"}),
                "max_filesize_kb": ("INT", {"default": 50000, "min": 0, "max": 10485760, "step": 1024, "tooltip": "最大文件大小限制(KB)，最大10485760KB(10GB)"}),
                "min_filesize_kb": ("INT", {"default": 50, "min": 0, "max": 10485760, "step": 1024, "tooltip": "最小文件大小限制(KB)，最大10485760KB(10GB)"}),
                
                # 通用功能（从文本加载器移植）
                "enable_mapping": ("BOOLEAN", {"default": False, "tooltip": "是否启用语义映射"}),
                "mapping_json": ("STRING", {"default": "{\n  \"temp_01\": \"主角A\",\n  \"temp_02\": \"主角B\",\n  \"draft\": \"草稿版\",\n  \"final\": \"最终版\"\n}", "multiline": True, "tooltip": "JSON格式的映射表"}),
                "enable_negative_filter": ("BOOLEAN", {"default": False, "tooltip": "启用反向匹配模式"}),
                "negative_keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "反向排除关键词"}),
                "enable_time_filter": ("BOOLEAN", {"default": False, "tooltip": "启用时间戳筛选功能"}),
                "min_age_days": ("STRING", {"default": "0.0", "tooltip": "文件最小年龄（天），0表示不限制"}),
                "max_age_days": ("STRING", {"default": "0.0", "tooltip": "文件最大年龄（天），0表示今天"}),
                "date_filter_mode": (["修改时间", "创建时间"], {"default": "修改时间", "tooltip": "时间戳筛选类型"}),
                "sort_mode": (["文件名(数字优先)", "文件名(字母)", "修改时间(新到旧)", "修改时间(旧到新)", "文件大小(大到小)", "文件大小(小到大)", "随机排序"], {"default": "文件名(数字优先)", "tooltip": "文件排序方式"}),
                "random_selection": ("BOOLEAN", {"default": False, "tooltip": "是否随机选择文件"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "tooltip": "随机种子，0表示自动生成"}),
                "file_limit": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "输出列表最大文件数量，0表示不限制"}),
                "start_index": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "从列表的哪个索引开始输出"}),
                "select_index": ("INT", {"default": -1, "min": -1, "step": 1, "tooltip": "强制选中列表中的特定索引文件，-1禁用"}),
            }
        }
        return inputs

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "INT", "STRING", "INT", "INT")
    RETURN_NAMES = ("image_list", "selected_image", "file_paths", "file_count", "error_log", "width", "height")
    OUTPUT_IS_LIST = (True, False, False, False, False, False, False)  # image_list返回列表格式
    FUNCTION = "load_batch"
    CATEGORY = "buding_Tools/File_Assets"
    
    @classmethod
    def IS_CHANGED(cls, directory_path, image_extension, keywords, similarity_threshold, debug_mode=False, **kwargs):
        """检查输入是否改变"""
        param_string = f"{directory_path}_{image_extension}_{keywords}_{similarity_threshold}_{str(kwargs)}"
        return hash(param_string)

    def load_batch(self, directory_path: str, keywords: str, image_extension: str = ".png|.jpg|.jpeg", 
                   similarity_threshold: float = 0.7, debug_mode: bool = False, 
                   metadata_keywords: str = "", min_resolution: int = 512, max_resolution: int = 2048, 
                   aspect_ratio: str = "any", fast_scan_mode: bool = True, scan_max_depth: int = 10,
                   image_backend: str = "OpenCV", on_io_error: str = "停止并报错", on_data_error: str = "跳过并警告", 
                   max_filesize_kb: int = 50000, min_filesize_kb: int = 50, enable_mapping: bool = False, 
                   mapping_json: str = "", enable_negative_filter: bool = False, negative_keywords: str = "", 
                   enable_time_filter: bool = False, min_age_days: str = "0.0", max_age_days: str = "0.0", 
                   date_filter_mode: str = "修改时间", sort_mode: str = "文件名(数字优先)", 
                   random_selection: bool = False, seed: int = 0, file_limit: int = 0, 
                   start_index: int = 0, select_index: int = -1, **kwargs: Any) -> Tuple[torch.Tensor, str, int, int]:
        """智能图像批量加载主函数"""
        
        # 参数验证：处理字符串转换为float
        try:
            min_age_days = float(min_age_days) if min_age_days else 0.0
        except (ValueError, TypeError):
            min_age_days = 0.0
            
        try:
            max_age_days = float(max_age_days) if max_age_days else 0.0
        except (ValueError, TypeError):
            max_age_days = 0.0
        
        # 检查依赖
        if not PILLOW_AVAILABLE:
            raise ImportError("Pillow未安装，无法加载图像。请安装: pip install Pillow")
        
        if image_backend == "OpenCV" and not OPENCV_AVAILABLE:
            if debug_mode:
                print("⚠️ OpenCV不可用，自动切换到Pillow后端")
            image_backend = "Pillow"
        
        # 初始化进度条和错误日志
        pbar = ComfyUIProgressBar(100)
        pbar.update(5, desc="初始化图像加载器...")
        error_log = []
        
        try:
            # 1. 两遍扫描机制：第一遍扫描元数据
            all_file_infos = self._scan_and_filter_metadata(
                directory_path, image_extension, keywords, similarity_threshold, 
                metadata_keywords, min_resolution, max_resolution, aspect_ratio,
                fast_scan_mode, scan_max_depth, image_backend, on_io_error, on_data_error,
                max_filesize_kb, min_filesize_kb, enable_mapping, mapping_json,
                enable_negative_filter, negative_keywords, enable_time_filter,
                min_age_days, max_age_days, date_filter_mode, debug_mode, error_log
            )
            pbar.update(70, desc=f"第一遍扫描完成，找到 {len(all_file_infos)} 个匹配文件")
            
            # 2. 应用排序和限制
            final_files = self._apply_limits_and_selection(
                all_file_infos, sort_mode, random_selection, seed, 
                file_limit, start_index, select_index, debug_mode
            )
            pbar.update(80, desc=f"排序和限制完成，最终输出 {len(final_files)} 个文件")
            
            # 3. 准备输出数据
            all_paths_list = []
            for f in final_files:
                original_path = f.get('original_path', f['path'])
                all_paths_list.append(original_path)
            
            file_count = len(all_paths_list)
            error_log_json = json.dumps(error_log, ensure_ascii=False)
            
            # 4. 第二遍扫描：加载所有最终选中的图像（返回列表）
            image_list, selected_image, selected_path, width, height = self._load_all_images(
                final_files, image_backend, debug_mode, error_log
            )
            pbar.update(100, desc="图像加载完成")
            
            if debug_mode:
                print(f"🎉 智能图像加载完成: {file_count} 个文件")
                print(f"📸 已加载 {len(image_list)} 个图像")
                if selected_path:
                    print(f"📸 首选图像: {os.path.basename(selected_path)} ({width}x{height})")
                if error_log:
                    print(f"⚠️ 错误日志: {len(error_log)} 个文件处理失败")

            return (image_list, selected_image, all_paths_list, file_count, error_log_json, width, height)
            
        except Exception as e:
            error_msg = f"❌ 智能图像加载失败: {str(e)}"
            if debug_mode:
                print(error_msg)
                import traceback
                traceback.print_exc()
            raise Exception(error_msg)

    def _scan_and_filter_metadata(self, root_dir: str, image_extension: str, keywords: str, 
                                 similarity_threshold: float, metadata_keywords: str, 
                                 min_resolution: int, max_resolution: int, aspect_ratio: str,
                                 fast_scan_mode: bool, scan_max_depth: int, image_backend: str, on_io_error: str, 
                                 on_data_error: str, max_filesize_kb: int, min_filesize_kb: int,
                                 enable_mapping: bool, mapping_json: str, enable_negative_filter: bool,
                                 negative_keywords: str, enable_time_filter: bool, min_age_days: float,
                                 max_age_days: float, date_filter_mode: str, debug_mode: bool, 
                                 error_log: List[str]) -> List[Dict]:
        """第一遍扫描：快速读取文件头和元数据进行筛选"""
        
        # 解析图像扩展名
        if image_extension == "any":
            extensions = None  # 不限制扩展名
        else:
            extensions = [ext.strip() for ext in image_extension.split('|') if ext.strip()]
        
        # 获取初始文件列表
        all_files = self._get_initial_file_list(root_dir, extensions, debug_mode, scan_max_depth)
        
        if debug_mode:
            print(f"🔍 初始扫描找到 {len(all_files)} 个图像文件")
        
        # 智能映射处理
        if enable_mapping:
            all_files = self._apply_semantic_mapping(all_files, mapping_json, debug_mode)
            if debug_mode:
                print(f"🗺️ 智能映射处理完成")
        
        filtered_list = []
        
        for file_info in all_files:
            file_path = file_info['path']
            
            try:
                # --- 阶段1: 文件大小和IO检查 ---
                if not self._check_filesize_limits(file_path, min_filesize_kb, max_filesize_kb):
                    continue
                
                # --- 阶段2: 快速读取图像头信息 ---
                image_info = self._extract_image_metadata_fast(file_path, image_backend, debug_mode)
                if not image_info:
                    continue
                
                # 合并基础信息和图像信息
                file_info.update(image_info)
                
                # --- 阶段3: 应用所有筛选条件 ---
                
                # 关键词筛选
                if keywords.strip() and not self._check_keywords_match(file_info, keywords, similarity_threshold):
                    continue
                
                # 分辨率筛选
                if not self._check_resolution_limits(file_info, min_resolution, max_resolution):
                    continue
                
                # 宽高比筛选
                if not self._check_aspect_ratio(file_info, aspect_ratio):
                    continue
                
                # 元数据关键词筛选
                if metadata_keywords.strip() and not self._check_metadata_keywords(file_info, metadata_keywords):
                    continue
                
                filtered_list.append(file_info)
                
            except FileNotFoundError as e:
                if on_io_error == "停止并报错":
                    raise
                else:
                    error_log.append(f"IO错误: 文件不存在 {file_path}")
                    if debug_mode:
                        print(f"⚠️ [IO Error] 文件缺失，跳过: {file_path}")
                    continue
            except Exception as e:
                if on_data_error == "停止并报错":
                    raise
                else:
                    error_log.append(f"数据错误: {file_path} - {str(e)}")
                    if debug_mode:
                        print(f"⚠️ [Data Error] 文件损坏，跳过: {file_path} ({e})")
                    continue
        
        if debug_mode:
            print(f"✅ 第一遍扫描完成，筛选后剩余 {len(filtered_list)} 个文件")
        
        return filtered_list

    def _get_initial_file_list(self, root_dir: str, extensions: Union[List[str], None], debug_mode: bool, scan_max_depth: int) -> List[Dict]:
        """获取初始文件列表"""
        # 清理路径
        root_dir = root_dir.strip().strip('"\'')
        
        if not root_dir or not os.path.exists(root_dir):
            if debug_mode:
                print(f"❌ 目录不存在: {root_dir}")
            return []
        
        # 扫描目录
        all_files = []
        root_path = Path(root_dir)
        
        def scan_directory_with_depth(directory: str, current_depth: int):
            """递归扫描目录，控制深度"""
            if current_depth > scan_max_depth:
                return
            
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    if os.path.isfile(item_path):
                        # 检查扩展名
                        if extensions is None or any(item_path.lower().endswith(ext.lower()) for ext in extensions):
                            file_info = {
                                'path': item_path,
                                'filename': os.path.basename(item_path),
                                'clean_name': self._clean_filename_for_match(os.path.basename(item_path))
                            }
                            all_files.append(file_info)
                    elif os.path.isdir(item_path):
                        # 递归扫描子目录
                        scan_directory_with_depth(item_path, current_depth + 1)
            except PermissionError:
                if debug_mode:
                    print(f"⚠️ 无权限访问目录: {directory}")
            except Exception as e:
                if debug_mode:
                    print(f"⚠️ 扫描目录出错 {directory}: {e}")
        
        # 开始扫描
        scan_directory_with_depth(root_dir, 1)
        
        if debug_mode:
            print(f"📁 扫描完成: 找到 {len(all_files)} 个文件 (最大深度: {scan_max_depth})")
        
        if debug_mode:
            print(f"📁 目录扫描完成: 找到 {len(all_files)} 个文件")
        
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

    def _check_keywords_match(self, file_info: Dict, keywords_str: str, threshold: float) -> bool:
        """检查关键词匹配"""
        if not keywords_str.strip():
            return True
        
        # 解析关键词列表
        keywords = [kw.strip().lower() for kw in keywords_str.split() if kw.strip()]
        clean_filename = file_info.get('clean_name', '').lower()
        
        for keyword in keywords:
            if not keyword:
                continue
            
            # 精确匹配
            if keyword == clean_filename:
                return True
            
            # 包含匹配
            if keyword in clean_filename or clean_filename in keyword:
                return True
            
            # 模糊匹配
            if threshold > 0:
                import difflib
                similarity = difflib.SequenceMatcher(None, keyword, clean_filename).ratio()
                if similarity >= threshold:
                    return True
        
        return False

    def _check_filesize_limits(self, file_path: str, min_kb: int, max_kb: int) -> bool:
        """检查文件大小限制"""
        try:
            file_size_bytes = os.path.getsize(file_path)
            file_size_kb = file_size_bytes // 1024
            
            if min_kb > 0 and file_size_kb < min_kb:
                return False
            if max_kb > 0 and file_size_kb > max_kb:
                return False
            
            return True
        except OSError:
            return False

    def _extract_image_metadata_fast(self, file_path: str, backend: str, debug_mode: bool) -> Dict[str, Any]:
        """快速提取图像元数据（不加载像素数据）"""
        try:
            if backend == "OpenCV":
                return self._extract_metadata_opencv_fast(file_path, debug_mode)
            else:
                return self._extract_metadata_pillow_fast(file_path, debug_mode)
        except Exception as e:
            if debug_mode:
                print(f"⚠️ 元数据提取失败 {file_path}: {e}")
            return {}

    def _extract_metadata_opencv_fast(self, file_path: str, debug_mode: bool) -> Dict[str, Any]:
        """OpenCV快速元数据提取"""
        try:
            # 使用cv2.imread只读取头信息
            img = cv2.imread(file_path, cv2.IMREAD_IGNORE_ORIENTATION | cv2.IMREAD_UNCHANGED)
            if img is None:
                return {}
            
            height, width = img.shape[:2]
            channels = img.shape[2] if len(img.shape) > 2 else 1
            
            return {
                'width': width,
                'height': height,
                'channels': channels,
                'metadata_text': '',  # OpenCV不读取PNG元数据
            }
        except Exception as e:
            if debug_mode:
                print(f"OpenCV元数据提取失败: {e}")
            return {}

    def _extract_metadata_pillow_fast(self, file_path: str, debug_mode: bool) -> Dict[str, Any]:
        """Pillow快速元数据提取"""
        try:
            with Image.open(file_path) as img:
                # 只读取尺寸信息，不加载像素数据
                width, height = img.size
                channels = len(img.getbands()) if hasattr(img, 'getbands') else 3
                
                # 提取PNG元数据
                metadata_text = ''
                if hasattr(img, 'info') and img.info:
                    for key, value in img.info.items():
                        if key.lower() in ['parameters', 'prompt', 'negative_prompt', 'description']:
                            metadata_text += str(value) + ' '
                
                return {
                    'width': width,
                    'height': height,
                    'channels': channels,
                    'metadata_text': metadata_text.strip(),
                }
        except Exception as e:
            if debug_mode:
                print(f"Pillow元数据提取失败: {e}")
            return {}

    def _check_resolution_limits(self, file_info: Dict, min_res: int, max_res: int) -> bool:
        """检查分辨率限制"""
        width = file_info.get('width', 0)
        height = file_info.get('height', 0)
        
        if width == 0 or height == 0:
            return False
        
        if min_res > 0 and (width < min_res or height < min_res):
            return False
        
        if max_res > 0 and (width > max_res or height > max_res):
            return False
        
        return True

    def _check_aspect_ratio(self, file_info: Dict, target_ratio: str) -> bool:
        """检查宽高比"""
        if target_ratio == "any":
            return True
        
        width = file_info.get('width', 0)
        height = file_info.get('height', 0)
        
        if width == 0 or height == 0:
            return False
        
        if target_ratio == "portrait":
            return height > width
        
        # 预定义宽高比
        ratios = {
            "1:1": 1.0,
            "16:9": 16.0 / 9.0,
            "4:3": 4.0 / 3.0,
            "3:2": 3.0 / 2.0,
        }
        
        expected = ratios.get(target_ratio)
        if expected is None:
            return True
        
        actual = width / height
        # 允许10%的误差
        return abs(actual - expected) < 0.1

    def _check_metadata_keywords(self, file_info: Dict, keywords_str: str) -> bool:
        """检查元数据关键词"""
        if not keywords_str.strip():
            return True
        
        metadata_text = file_info.get('metadata_text', '').lower()
        keywords = [kw.strip().lower() for kw in keywords_str.split() if kw.strip()]
        
        for keyword in keywords:
            if keyword in metadata_text:
                return True
        
        return False

    def _clean_filename_for_match(self, filename: str) -> str:
        """清理文件名，用于模糊匹配"""
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        
        # 移除常见的版本号和分隔符
        name = re.sub(r'[_\-\s]+', ' ', name)
        
        # 移除数字版本标识
        name = re.sub(r'[ _]?[vV][0-9]+', '', name)
        
        # 移除纯数字（但保留中文数字）
        name = re.sub(r'\b\d+\b', '', name)
        
        # 只保留字母、中文、空格、基本标点
        name = re.sub(r'[^\w\u4e00-\u9fff\s\-_\.\(\)\[\]]', '', name)
        
        return name.lower().strip()

    def _apply_limits_and_selection(self, files: List[Dict], sort_mode: str, random_selection: bool, 
                                  seed: int, file_limit: int, start_index: int, select_index: int, 
                                  debug: bool) -> List[Dict]:
        """应用排序、限制和选择逻辑"""
        if not files:
            return []
        
        # 排序
        sorted_files = self._apply_smart_sorting(files, sort_mode)
        
        # 随机选择
        if random_selection:
            if seed != 0:
                random.seed(seed)
            random.shuffle(sorted_files)
        
        # 索引选择
        if select_index >= 0 and select_index < len(sorted_files):
            return [sorted_files[select_index]]
        
        # 应用限制
        if start_index >= 0:
            sorted_files = sorted_files[start_index:]
        
        if file_limit > 0:
            sorted_files = sorted_files[:file_limit]
        
        return sorted_files

    def _apply_smart_sorting(self, files: List[Dict], sort_mode: str) -> List[Dict]:
        """智能排序"""
        if not files:
            return []
        
        if sort_mode == "文件名(数字优先)":
            if NATSORT_AVAILABLE:
                return natsorted(files, key=lambda x: x['filename'])
            else:
                return sorted(files, key=lambda x: x['filename'])
        
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
            shuffled = files.copy()
            random.shuffle(shuffled)
            return shuffled
        
        else:
            return files

    def _load_all_images(self, final_files: List[Dict], backend: str, debug_mode: bool, error_log: List[str]) -> Tuple[List[torch.Tensor], torch.Tensor, str, int, int]:
        """第二遍扫描：加载所有最终选中的图像（返回列表）"""
        if not final_files:
            return [], torch.zeros(1, 64, 64, 3), "", 0, 0
        
        image_list = []
        selected_image = None
        selected_path = ""
        width = 0
        height = 0
        
        for idx, file_info in enumerate(final_files):
            file_path = file_info.get('original_path', file_info['path'])
            
            try:
                if backend == "OpenCV":
                    image_tensor = self._load_image_opencv(file_path, debug_mode)
                else:
                    image_tensor = self._load_image_pillow(file_path, debug_mode)
                
                image_list.append(image_tensor)
                
                # 第一张图作为选中的预览图
                if idx == 0:
                    selected_image = image_tensor
                    selected_path = file_path
                    width = file_info.get('width', 0)
                    height = file_info.get('height', 0)
                
            except Exception as e:
                error_msg = f"图像加载失败 {file_path}: {e}"
                error_log.append(error_msg)
                if debug_mode:
                    print(f"🚨 [Load Error] {error_msg}")
                continue
        
        # 如果没有加载任何图像，返回空
        if not image_list:
            return [], torch.zeros(1, 64, 64, 3), "", 0, 0
        
        # 确保selected_image不为空
        if selected_image is None:
            selected_image = image_list[0]
        
        return image_list, selected_image, selected_path, width, height

    def _load_selected_image(self, final_files: List[Dict], backend: str, debug_mode: bool, error_log: List[str]) -> Tuple[torch.Tensor, str, int, int]:
        """第二遍扫描：加载最终选中的图像"""
        if not final_files:
            return torch.zeros(1, 64, 64, 3), "", 0, 0
        
        selected_file = final_files[0]
        selected_path = selected_file.get('original_path', selected_file['path'])
        width = selected_file.get('width', 0)
        height = selected_file.get('height', 0)
        
        try:
            if backend == "OpenCV":
                image_tensor = self._load_image_opencv(selected_path, debug_mode)
            else:
                image_tensor = self._load_image_pillow(selected_path, debug_mode)
            
            return image_tensor, selected_path, width, height
            
        except Exception as e:
            error_msg = f"最终图像加载失败 {selected_path}: {e}"
            error_log.append(error_msg)
            if debug_mode:
                print(f"🚨 [Final Load Error] {error_msg}")
            
            # 返回空张量，防止工作流中断
            return torch.zeros(1, 64, 64, 3), selected_path, 0, 0

    def _load_image_opencv(self, file_path: str, debug_mode: bool) -> torch.Tensor:
        """使用OpenCV加载图像"""
        try:
            img = cv2.imread(file_path, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("OpenCV无法读取图像文件")
            
            # BGR转RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            # 转换为张量
            img = img.astype(np.float32) / 255.0
            tensor = torch.from_numpy(img)[None,]  # 添加batch维度
            
            return tensor
            
        except Exception as e:
            if debug_mode:
                print(f"OpenCV加载失败: {e}")
            raise

    def _load_image_pillow(self, file_path: str, debug_mode: bool) -> torch.Tensor:
        """使用Pillow加载图像"""
        try:
            with Image.open(file_path) as img:
                # 转换为RGB
                img = img.convert("RGB")
                
                # 转换为numpy数组
                img_array = np.array(img).astype(np.float32) / 255.0
                
                # 转换为张量
                tensor = torch.from_numpy(img_array)[None,]  # 添加batch维度
                
                return tensor
                
        except Exception as e:
            if debug_mode:
                print(f"Pillow加载失败: {e}")
            raise

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_BatchImageLoader": buding_BatchImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_BatchImageLoader": "🖼️ buding_BatchImageLoader (批量图像加载器)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
