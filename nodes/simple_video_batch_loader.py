#!/usr/bin/env python3
"""
简化视频批量加载器
基于智能视频批量加载器的逻辑，提供简洁的批量视频加载功能
"""

import os
import random
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union

import torch
import cv2
import numpy as np

class buding_SimpleVideoBatchLoader:
    """简化视频批量加载器"""

    # video_list（逐帧IMAGE列表）默认最多输出的帧数（仅影响单选模式的 video_list）
    _VIDEO_LIST_MAX_FRAMES = 240
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数"""
        inputs = {
            "required": {
                "directory_path": ("STRING", {"default": "", "tooltip": "视频文件所在目录路径"}),
                "video_container": (
                    [".mp4|.mov|.avi", ".mp4", ".mov", ".avi", "any"], 
                    {"default": ".mp4|.mov|.avi", "tooltip": "视频容器格式筛选，使用 '|' 分隔。'any' 匹配所有格式"}
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
    
    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "INT", "STRING")
    RETURN_NAMES = ("video_list", "selected_video_preview", "file_paths", "video_count", "load_log")
    OUTPUT_IS_LIST = (True, False, True, False, False)
    FUNCTION = "load_video_batch"
    CATEGORY = "buding_Tools/简化视频加载"
    DESCRIPTION = "简化版视频批量加载器，基于SmartVideoBatchLoader逻辑"
    
    # 类级别的缓存存储
    _scan_cache = {}
    
    @classmethod
    def IS_CHANGED(cls, directory_path, video_container, positive_keywords, positive_input_mode,
                   max_files, start_index, always_reload, similarity_threshold,
                   scan_max_depth, enable_negative_enhance, negative_keywords, sort_mode,
                   debug_mode, mode, force_select_index, random_selection, seed):
        """检查输入是否改变 - 完整包含所有会影响输出的参数"""
        if always_reload:
            return float("nan")  # 强制重新加载
        
        # 使用frozenset确保包含所有影响输出的参数，参数顺序不影响哈希值
        key_params = {
            'directory_path': directory_path,
            'video_container': video_container,
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
    
    def load_video_batch(self, directory_path: str, video_container: str, positive_keywords: str,
                        positive_input_mode: str, max_files: int, start_index: int,
                        always_reload: bool, similarity_threshold: float,
                        scan_max_depth: int, enable_negative_enhance: bool, negative_keywords: str,
                        sort_mode: str, debug_mode: bool, mode: str, force_select_index: int,
                        random_selection: bool, seed: int):
        """加载视频批量文件"""
        
        # 清理路径
        directory_path = directory_path.strip().strip('"\'')
        current_time_str = time.strftime("%Y-%m-%d %H:%M")
        if not directory_path or not os.path.exists(directory_path):
            status = "🎬 ❌ 加载失败：目录不存在"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            if debug_mode:
                print(f"❌ {status}: {directory_path}")
            result = ([], None, [], 0, log)
            return {"result": result, "ui": {}}
        
        # 设置随机种子
        if random_selection and seed > 0:
            random.seed(seed)
        
        try:
            # 1. 扫描视频文件（使用缓存）
            video_files = self._get_cached_file_list(directory_path, video_container, scan_max_depth, debug_mode)
            
            if debug_mode:
                print(f"📁 扫描完成: 找到 {len(video_files)} 个视频文件")
            
            if not video_files:
                status = "🎬 ❌ 加载失败：未找到匹配的文件 (请检查后缀)"
                log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
                result = ([], None, [], 0, log)
                return {"result": result, "ui": {}}
            
            # 2. 关键词筛选
            filtered_files = self._filter_by_keywords(video_files, positive_keywords, 
                                                     positive_input_mode, similarity_threshold, 
                                                     debug_mode)
            
            if debug_mode:
                print(f"🔍 正向筛选后: {len(filtered_files)} 个文件")

            if not filtered_files:
                status = "🎬 ❌ 加载失败：未找到匹配的文件 (请检查关键词)"
                log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
                result = ([], None, [], 0, log)
                return {"result": result, "ui": {}}
            
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
            
            # 7. 先切片，再加载：确保视频与路径严格对齐，且批量预览跟随 start_index
            if mode == "单选":
                selected_index = min(force_select_index, len(filtered_files) - 1) if filtered_files else 0
                selected_files = [filtered_files[selected_index]] if filtered_files else []
                preview_index = selected_index
            else:
                selected_files = filtered_files
                if start_index > 0:
                    selected_files = selected_files[start_index:] if start_index < len(selected_files) else []
                if max_files > 0:
                    selected_files = selected_files[:max_files]
                preview_index = start_index

            result_paths = [file_info['path'] for file_info in selected_files]

            # video_list 仅在单选模式下启用：输出为逐帧 IMAGE 列表，便于连接 VHS_VideoCombine
            if mode == "单选":
                selected_video_path = result_paths[0] if result_paths else ""
                result_videos, video_list_truncated = (
                    self._load_video_frames_as_images(
                        selected_video_path,
                        debug_mode=debug_mode,
                        max_frames=self._VIDEO_LIST_MAX_FRAMES,
                    )
                    if selected_video_path
                    else ([], False)
                )
            else:
                result_videos = []
            result_count = len(result_paths)

            # 8. 生成预览：批量时显示切片后“第一个”(跟随 start_index)，单选显示选中的那一个
            preview_path = result_paths[0] if result_paths else ""
            selected_video_preview = self._load_first_frame_as_image(preview_path, debug_mode) if preview_path else None
            ui_images = self._generate_preview_image(selected_video_preview, preview_index, debug_mode) if selected_video_preview is not None else {}

            if debug_mode:
                if mode == "单选":
                    print(f"🎯 单选模式：选中第{preview_index}个文件")
                else:
                    print(f"📦 批量模式：返回 {len(result_videos)} 个视频列表")
                print(f"📄 返回路径数：{len(result_paths)}")
            
            # 10. 返回结果（统一格式）
            # 返回格式：(video_list, selected_video_preview, file_paths, video_count)
            # OUTPUT_IS_LIST = (True, True, True, False) 意味着：
            #   [0] video_list 是列表
            #   [1] selected_video_preview 是列表（与[0]长度相同）
            #   [2] file_paths 是列表
            #   [3] video_count 是数字
            
            # 生成成功日志
            last_filename = os.path.basename(result_paths[-1]) if result_paths else "None"
            preview_status = "✅" if ui_images.get("images") else "❌"
            preview_name = ui_images.get("images", [{}])[0].get("filename", "None") if ui_images.get("images") else "None"
            video_list_info = ""
            if mode == "单选":
                suffix = " (truncated)" if locals().get("video_list_truncated") else ""
                video_list_info = f"\n🎞️ video_list帧数: {len(result_videos)}{suffix}"

            log = (
                f"📊 批量加载完成 | 🔢 总计: {result_count} 个文件\n"
                f"📂 根目录: {directory_path}\n"
                f"🔚 结束于: {last_filename}\n"
                f"🖼️ 预览: {preview_status} {preview_name}\n"
                f"🕒 时间: {current_time_str}"
                f"{video_list_info}"
            )

            result = (result_videos, selected_video_preview, result_paths, result_count, log)
            return {"result": result, "ui": ui_images}
            
        except Exception as e:
            error_msg = f"❌ 视频批量加载失败: {str(e)}"
            if debug_mode:
                print(error_msg)
                import traceback
                traceback.print_exc()
            # 异常情况也要返回统一格式
            status = f"🎬 ❌ 加载失败：{str(e)}"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            result = ([], None, [], 0, log)
            return {"result": result, "ui": {}}

    def _load_first_frame_as_image(self, video_path: str, debug_mode: bool) -> torch.Tensor:
        """只读取视频首帧生成 IMAGE 张量（[1, H, W, 3]，0-1 float），用于预览。"""
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                if debug_mode:
                    print(f"⚠️ 无法打开视频用于预览: {video_path}")
                return None

            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                if debug_mode:
                    print(f"⚠️ 无法读取首帧用于预览: {video_path}")
                return None

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_normalized = frame_rgb.astype(np.float32) / 255.0
            return torch.from_numpy(frame_normalized).unsqueeze(0)
        except Exception as e:
            if debug_mode:
                print(f"⚠️ 预览首帧生成失败: {e}")
            return None

    def _load_video_frames_as_images(self, video_path: str, debug_mode: bool, max_frames: int = 0, every_nth: int = 1) -> Tuple[List[torch.Tensor], bool]:
        """将视频读取为逐帧 IMAGE 列表（每帧 [1,H,W,3]，0-1 float）。

        Returns:
            (frames, truncated)
        """
        if every_nth < 1:
            every_nth = 1

        frames: List[torch.Tensor] = []
        truncated = False

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                if debug_mode:
                    print(f"⚠️ 无法打开视频用于 video_list: {video_path}")
                return [], False

            frame_index = 0
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                if frame_index % every_nth == 0:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frame_normalized = frame_rgb.astype(np.float32) / 255.0
                    frames.append(torch.from_numpy(frame_normalized).unsqueeze(0))

                    if max_frames and len(frames) >= max_frames:
                        truncated = True
                        break

                frame_index += 1

            cap.release()

            if debug_mode:
                if truncated:
                    print(f"🎞️ video_list 已截断：输出 {len(frames)} 帧 (max_frames={max_frames})")
                else:
                    print(f"🎞️ video_list 输出 {len(frames)} 帧")

            return frames, truncated

        except Exception as e:
            if debug_mode:
                print(f"⚠️ 生成 video_list 失败: {e}")
            return [], False
    
    def _get_cached_file_list(self, directory_path: str, video_container: str, max_depth: int,
                             debug_mode: bool) -> List[Dict[str, Any]]:
        """获取文件列表（带30秒TTL缓存）- 提高频繁调用时的性能，避免重复扫描大型视频库"""
        current_time = time.time()
        cache_key = (directory_path, video_container, max_depth)
        
        # 检查缓存是否存在且未过期
        if cache_key in self._scan_cache:
            cached = self._scan_cache[cache_key]
            if current_time - cached['timestamp'] < 30:  # 30秒过期
                if debug_mode:
                    print(f"💾 使用缓存的视频文件列表 (年龄: {current_time - cached['timestamp']:.1f}秒)")
                return cached['files']
        
        # 缓存未命中或已过期，执行扫描
        files = self._scan_video_files(directory_path, video_container, max_depth, debug_mode)
        
        # 更新缓存
        self._scan_cache[cache_key] = {
            'timestamp': current_time,
            'files': files
        }
        
        return files
    
    def _generate_preview_image(self, frame_tensor, index, debug_mode=False):
        """生成UI预览图
        
        Args:
            frame_tensor: 首帧张量，形状为 [1, height, width, channels]
            index: 视频索引
            debug_mode: 调试模式
            
        Returns:
            UI图像字典，用于ComfyUI前端显示
        """
        if frame_tensor is None:
            return {}

        try:
            import tempfile
            import time
            from PIL import Image
            import numpy as np
            
            # 将张量转换为PIL图像
            # frame_tensor: [1, H, W, C] -> numpy: [H, W, C]
            frame_np = frame_tensor[0].cpu().numpy()
            frame_np = (frame_np * 255).astype(np.uint8)
            
            # 转换为PIL图像
            pil_image = Image.fromarray(frame_np, 'RGB')
            
            # 生成唯一文件名（强制UI刷新）
            timestamp = int(time.time() * 1000)
            random_suffix = random.randint(1000, 9999)
            temp_filename = f"video_preview_{index}_{timestamp}_{random_suffix}.png"
            
            # 保存到ComfyUI的temp目录
            import folder_paths
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            full_path = os.path.join(temp_dir, temp_filename)
            pil_image.save(full_path)
            
            if debug_mode:
                print(f"🖼️ 生成预览图: {temp_filename}")
                print(f"📁 保存路径: {full_path}")
            
            # 返回完整的UI协议格式
            return {
                "images": [
                    {
                        "filename": temp_filename,
                        "subfolder": "",
                        "type": "temp"
                    }
                ]
            }
            
        except Exception as e:
            if debug_mode:
                print(f"⚠️ 生成预览图失败: {e}")
                import traceback
                traceback.print_exc()
            return {}
    
    def _scan_video_files(self, directory_path: str, video_container: str, max_depth: int, debug_mode: bool) -> List[Dict[str, Any]]:
        """扫描视频文件"""
        video_files = []
        
        # 处理视频容器选项 (转换为集合以获得O(1)查找性能，与smart_video_batch_loader逻辑一致)
        if video_container == "any":
            extensions = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v'}
        else:
            extensions = {ext.strip().lower() for ext in video_container.split('|') if ext.strip()}
        
        def scan_recursive(current_dir: str, current_depth: int):
            if current_depth > max_depth:
                return
            
            try:
                for item in os.listdir(current_dir):
                    item_path = os.path.join(current_dir, item)
                    
                    if os.path.isfile(item_path):
                        # 检查扩展名 (延迟验证：扫描阶段仅检查扩展名，不打开视频文件)
                        file_ext = os.path.splitext(item)[1].lower()
                        if file_ext not in extensions:
                            continue
                        
                        # ✅ 改进：仅在扫描阶段记录文件信息，不进行 cv2.VideoCapture 验证
                        # 真正的视频文件验证延迟到加载阶段（_load_single_video）
                        file_info = {
                            'path': item_path,
                            'filename': item,
                            'mtime': os.path.getmtime(item_path)
                        }
                        video_files.append(file_info)
                    
                    elif os.path.isdir(item_path):
                        scan_recursive(item_path, current_depth + 1)
                        
            except PermissionError:
                if debug_mode:
                    print(f"⚠️ 无权限访问目录: {current_dir}")
            except Exception as e:
                if debug_mode:
                    print(f"⚠️ 扫描目录出错 {current_dir}: {e}")
        
        scan_recursive(directory_path, 0)
        return video_files
    
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
    
    def _load_videos(self, files: List[Dict[str, Any]], debug_mode: bool) -> Tuple[List[torch.Tensor], List[str]]:
        """加载视频文件"""
        videos = []
        file_paths = []
        
        for file_info in files:
            video_path = file_info['path']
            try:
                if debug_mode:
                    print(f"🎬 加载视频: {os.path.basename(video_path)}")
                
                # 使用OpenCV加载视频
                video_tensor = self._load_single_video(video_path, debug_mode)
                
                if video_tensor is not None:
                    videos.append(video_tensor)
                    file_paths.append(video_path)
                
            except Exception as video_error:
                if debug_mode:
                    print(f"⚠️ 加载视频失败，跳过: {os.path.basename(video_path)}, 错误: {video_error}")
                continue
        
        return videos, file_paths
    
    def _load_single_video(self, video_path: str, debug_mode: bool) -> torch.Tensor:
        """加载单个视频文件"""
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                if debug_mode:
                    print(f"⚠️ 无法打开视频: {video_path}")
                return None
            
            frames = []
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 转换BGR到RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # 归一化到0-1
                frame_normalized = frame_rgb.astype(np.float32) / 255.0
                frames.append(frame_normalized)
            
            cap.release()
            
            if not frames:
                if debug_mode:
                    print(f"⚠️ 视频中没有帧: {video_path}")
                return None
            
            # 转换为tensor: (frames, height, width, channels)
            video_tensor = torch.from_numpy(np.stack(frames))
            
            if debug_mode:
                print(f"✅ 视频加载成功: {len(frames)} 帧, 形状: {video_tensor.shape}")
            
            return video_tensor
            
        except Exception as e:
            if debug_mode:
                print(f"⚠️ 视频加载出错: {e}")
            return None

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SimpleVideoBatchLoader": buding_SimpleVideoBatchLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SimpleVideoBatchLoader": "🎬 简化视频批量加载器",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
