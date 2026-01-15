#!/usr/bin/env python3
"""
简化图像批量加载器
基于 buding_Directory Image Loader 的逻辑，提供简洁的批量图像加载功能
"""

import os
import random
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Union

import torch
import numpy as np
from PIL import Image, ImageOps

class buding_SimpleImageBatchLoader:
    """简化图像批量加载器"""
    
    # 类级别缓存：存储目录扫描结果
    _scan_cache = {}  # {"directory_path": {"files": [...], "timestamp": time}}
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数"""
        inputs = {
            "required": {
                "directory_path": ("STRING", {"default": "", "tooltip": "图像文件所在目录路径"}),
                "image_extension": (
                    [".png|.jpg|.jpeg", ".png", ".jpg", ".jpeg", "any"], 
                    {"default": ".png|.jpg|.jpeg", "tooltip": "使用 '|' 分隔。'any' 匹配所有格式。"}
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
    RETURN_NAMES = ("image_list", "selected_image", "file_paths", "image_count", "load_log")
    OUTPUT_IS_LIST = (True, False, True, False, False)  # file_paths也返回列表格式，确保数据一致性
    FUNCTION = "load_image_batch"
    CATEGORY = "buding_Tools/简化图像加载"
    DESCRIPTION = "简化版图像批量加载器，基于Directory Image Loader逻辑"
    
    @classmethod
    def IS_CHANGED(cls, directory_path, image_extension, positive_keywords, positive_input_mode,
                   max_files, start_index, always_reload, similarity_threshold,
                   scan_max_depth, enable_negative_enhance, negative_keywords, sort_mode,
                   debug_mode, mode, force_select_index, random_selection, seed):
        """检查输入是否改变 - 完整包含所有会影响输出的参数"""
        if always_reload:
            return float("nan")  # 强制重新加载
        
        # 使用frozenset确保包含所有影响输出的参数，参数顺序不影响哈希值
        key_params = {
            'directory_path': directory_path,
            'image_extension': image_extension,
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
    
    def load_image_batch(self, directory_path: str, image_extension: str, positive_keywords: str,
                        positive_input_mode: str, max_files: int, start_index: int,
                        always_reload: bool, similarity_threshold: float,
                        scan_max_depth: int, enable_negative_enhance: bool, negative_keywords: str,
                        sort_mode: str, debug_mode: bool, mode: str, force_select_index: int,
                        random_selection: bool, seed: int) -> Tuple[torch.Tensor, torch.Tensor, List[str], int, str]:
        """加载图像批量文件"""
        
        # 清理路径
        directory_path = directory_path.strip().strip('"\'')
        current_time_str = time.strftime("%Y-%m-%d %H:%M")
        if not directory_path or not os.path.exists(directory_path):
            status = "🖼️ ❌ 加载失败：目录不存在"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            if debug_mode:
                print(f"❌ {status}: {directory_path}")
            result = ([], None, [], 0, log)
            return {"result": result, "ui": {}}
        
        # 设置随机种子
        if random_selection and seed > 0:
            random.seed(seed)
        
        try:
            # 1. 扫描或获取缓存的图像文件
            image_files = self._get_cached_file_list(directory_path, image_extension, scan_max_depth, debug_mode)
            
            if debug_mode:
                print(f"📁 扫描完成: 找到 {len(image_files)} 个图像文件")
            
            if not image_files:
                status = "🖼️ ❌ 加载失败：未找到匹配的文件 (请检查后缀)"
                log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
                result = ([], None, [], 0, log)
                return {"result": result, "ui": {}}
            
            # 2. 关键词筛选
            filtered_files = self._filter_by_keywords(image_files, positive_keywords, 
                                                     positive_input_mode, similarity_threshold, 
                                                     debug_mode)
            
            if debug_mode:
                print(f"🔍 正向筛选后: {len(filtered_files)} 个文件")

            if not filtered_files:
                status = "🖼️ ❌ 加载失败：未找到匹配的文件 (请检查关键词)"
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
            
            # 7. 先切片再加载：减少无谓读图，并让批量预览跟随 start_index
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

            # 路径列表独立于解码成功与否，便于下游“按路径”节点
            result_paths = [file_info['path'] for file_info in selected_files]

            # 8. 加载图像（失败不应影响 file_paths 输出）
            result_images, _loaded_paths = self._load_images(selected_files, debug_mode)
            result_count = len(result_paths)

            # 9. 首图预览：批量为切片后第一个；单选为选中项
            selected_image = result_images[0] if result_images else None
            ui_images = self._generate_preview_image(selected_image, preview_index, debug_mode) if selected_image is not None else {}

            if debug_mode:
                if mode == "单选":
                    print(f"🎯 单选模式：选中第{preview_index}个文件")
                else:
                    print(f"📦 批量模式：返回 {len(result_images)} 个图像列表")
                print(f"📄 返回路径数：{len(result_paths)}")

            # 输出保持为列表格式
            result_images = result_images
                
            # 10. 返回结果 (与老节点格式一致)
            # 返回格式：(image_list, selected_image, file_paths, image_count)
            # OUTPUT_IS_LIST = (True, False, True, False) 意味着：
            #   [0] image_list 是列表
            #   [1] selected_image 是单个张量（用于预览）
            #   [2] file_paths 是列表
            #   [3] image_count 是数字
            
            last_filename = os.path.basename(result_paths[-1]) if result_paths else "None"
            preview_status = "✅" if ui_images.get("images") else "❌"
            preview_name = ui_images.get("images", [{}])[0].get("filename", "None") if ui_images.get("images") else "None"
            log = (
                f"📊 批量加载完成 | 🔢 总计: {result_count} 个文件\n"
                f"📂 根目录: {directory_path}\n"
                f"🔚 结束于: {last_filename}\n"
                f"🖼️ 预览: {preview_status} {preview_name}\n"
                f"🕒 时间: {current_time_str}"
            )

            result = (result_images, selected_image, result_paths, result_count, log)
            return {"result": result, "ui": ui_images}
            
        except Exception as e:
            error_msg = f"❌ 图像批量加载失败: {str(e)}"
            if debug_mode:
                print(error_msg)
                import traceback
                traceback.print_exc()
            status = f"🖼️ ❌ 加载失败：{str(e)}"
            log = f"{status}\n目录: {directory_path}\n时间: {current_time_str}"
            result = ([], None, [], 0, log)
            return {"result": result, "ui": {}}

    def _generate_preview_image(self, image_tensor, index, debug_mode=False):
        """生成UI预览图（保存到ComfyUI的temp目录并返回ui.images协议）"""
        if image_tensor is None:
            return {}

        try:
            import time
            from PIL import Image
            import numpy as np

            # image_tensor: [1, H, W, C] (0-1)
            img_np = image_tensor[0].cpu().numpy()
            img_np = (img_np * 255).astype(np.uint8)
            pil_image = Image.fromarray(img_np, 'RGB')

            timestamp = int(time.time() * 1000)
            random_suffix = random.randint(1000, 9999)
            temp_filename = f"image_preview_{index}_{timestamp}_{random_suffix}.png"

            import folder_paths
            temp_dir = folder_paths.get_temp_directory()
            os.makedirs(temp_dir, exist_ok=True)
            full_path = os.path.join(temp_dir, temp_filename)
            pil_image.save(full_path)

            if debug_mode:
                print(f"🖼️ 生成预览图: {temp_filename}")
                print(f"📁 保存路径: {full_path}")

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
    
    def _get_cached_file_list(self, directory_path: str, image_extension: str, max_depth: int, debug_mode: bool) -> List[Dict[str, Any]]:
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
        files = self._scan_image_files(directory_path, image_extension, max_depth, debug_mode)
        
        # 更新缓存
        self._scan_cache[cache_key] = {
            'files': files,
            'timestamp': current_time
        }
        
        if debug_mode:
            print(f"🔄 缓存已更新 (扫描 {len(files)} 个文件)")
        
        return files
    
    def _scan_image_files(self, directory_path: str, image_extension: str, max_depth: int, debug_mode: bool) -> List[Dict[str, Any]]:
        """扫描图像文件"""
        image_files = []
        
        # 常见图像扩展名集合 (使用 Set，查询复杂度 O(1))
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.gif'}
        
        # 处理图像扩展名选项 (与batch_image_loader逻辑一致)
        if image_extension == "any":
            extensions = valid_image_extensions  # 使用常见图像扩展名集合
        else:
            extensions = {ext.strip().lower() for ext in image_extension.split('|') if ext.strip()}  # Set 推导式
        
        def scan_recursive(current_dir: str, current_depth: int):
            if current_depth > max_depth:
                return
            
            try:
                for item in os.listdir(current_dir):
                    item_path = os.path.join(current_dir, item)
                    
                    if os.path.isfile(item_path):
                        # 检查扩展名（不验证图像内容，提升扫描速度）
                        file_ext = os.path.splitext(item)[1].lower()
                        
                        # Set 查询复杂度 O(1)，高效匹配
                        if file_ext not in extensions:
                            continue
                        
                        # 直接添加文件信息，验证延迟到加载阶段
                        file_info = {
                            'path': item_path,
                            'filename': item,
                            'mtime': os.path.getmtime(item_path)
                        }
                        image_files.append(file_info)
                    
                    elif os.path.isdir(item_path):
                        scan_recursive(item_path, current_depth + 1)
                        
            except PermissionError:
                if debug_mode:
                    print(f"⚠️ 无权限访问目录: {current_dir}")
            except Exception as e:
                if debug_mode:
                    print(f"⚠️ 扫描目录出错 {current_dir}: {e}")
        
        scan_recursive(directory_path, 0)
        return image_files
    
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
    
    def _load_images(self, files: List[Dict[str, Any]], debug_mode: bool) -> Tuple[List[torch.Tensor], List[str]]:
        """加载图像文件"""
        images = []
        file_paths = []
        
        for file_info in files:
            image_path = file_info['path']
            try:
                if debug_mode:
                    print(f"📷 加载图像: {os.path.basename(image_path)}")
                
                # 使用与老节点相同的方式加载图像
                img = Image.open(image_path)
                img = ImageOps.exif_transpose(img)
                img = img.convert("RGB")
                
                # 转换为tensor
                img_array = np.array(img).astype(np.float32) / 255.0
                img_tensor = torch.from_numpy(img_array)[None,]
                
                images.append(img_tensor)
                file_paths.append(image_path)
                
            except Exception as img_error:
                if debug_mode:
                    print(f"⚠️ 加载图像失败，跳过: {os.path.basename(image_path)}, 错误: {img_error}")
                continue
        
        return images, file_paths

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SimpleImageBatchLoader": buding_SimpleImageBatchLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SimpleImageBatchLoader": "🖼️ 简化图像批量加载器",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
