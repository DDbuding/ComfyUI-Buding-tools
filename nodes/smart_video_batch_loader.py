"""
buding_SmartVideoBatchLoader - 智能视频批量加载器
专为视频AI工作流设计的高性能批量视频处理节点

设计原则：
- 减法优化：专注于核心职责（加载与筛选）
- 元数据驱动：避免复杂计算，提升性能
- 两遍扫描：先元数据筛选，再视频加载
- 依赖最小：优先使用Decord，降级到OpenCV

核心功能：
- 分辨率和帧率筛选
- 时域切片 (Full_Video/Time_Slice/Chunk_Mode)
- 帧采样控制 (Full_FPS/Every_Nth_Frame)
- 文件大小和时长安全检查
- 8端口精简输出设计

版本: v1.0.0
更新日期: 2024-12-12
"""

import os
import json
import time
import random
import hashlib
from typing import List, Dict, Any, Tuple, Optional

# 核心依赖检查
try:
    import decord
    DECORD_AVAILABLE = True
except ImportError:
    DECORD_AVAILABLE = False
    print("⚠️ decord未安装，视频加载功能将受限")

# 降级依赖检查
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

# ComfyUI核心依赖
import torch

def video_to_tensor(frames, fps):
    """视频帧转换为ComfyUI张量格式"""
    # 确保帧格式为 [batch, frames, height, width, channels]
    if isinstance(frames, list):
        frames = torch.stack(frames)
    
    # 如果是 [frames, height, width, channels]，添加batch维度
    if frames.dim() == 4:
        frames = frames.unsqueeze(0)
    
    return frames

class buding_SmartVideoBatchLoader:
    """智能视频批量加载器"""
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数 - 继承音频加载器设计，减法优化"""
        inputs = {
            "required": {
                "directory_path": ("STRING", {"default": "", "multiline": False, "tooltip": "要扫描的视频文件目录路径"}),
                "video_container": (
                    [".mp4|.mov|.avi", ".mp4", ".mov", ".avi", "any"], 
                    {"default": ".mp4|.mov|.avi", "tooltip": "视频容器格式筛选，使用 '|' 分隔。'any' 匹配所有格式"}
                ),
                "keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "正向匹配关键词，每行一个（或关系）"}),
                "similarity_threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "模糊匹配的最低相似度要求"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "启用调试输出模式"}),
                
                # 视频参数标准化 (核心功能)
                "target_fps": ("INT", {"default": 30, "min": 1, "max": 120, "step": 1, "tooltip": "目标帧率(fps)"}),
                "min_width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1, "tooltip": "最小宽度(像素)，0表示不限制"}),
                "max_width": ("INT", {"default": 99999, "min": 0, "max": 8192, "step": 1, "tooltip": "最大宽度(像素)，99999表示不限制"}),
                "min_height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1, "tooltip": "最小高度(像素)，0表示不限制"}),
                "max_height": ("INT", {"default": 99999, "min": 0, "max": 8192, "step": 1, "tooltip": "最大高度(像素)，99999表示不限制"}),
                
                # 时长控制 (核心功能)
                "min_duration": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 3600.0, "step": 0.1, "tooltip": "最小时长(秒)，排除过短视频"}),
            },
            "optional": {
                # 超长处理总开关 (核心功能优化)
                "enable_exceedance_handling": ("BOOLEAN", {"default": True, "tooltip": "启用最大时长检查和处理"}),
                "max_duration": ("FLOAT", {"default": 300.0, "min": 0.0, "max": 3600.0, "step": 0.1, "tooltip": "最大时长(秒)，超过此阈值的文件将按策略处理"}),
                "on_max_duration_exceedance": (["Filter/Skip", "Pass_Through"], {"default": "Filter/Skip", "tooltip": "超长视频处理策略"}),
                
                # 文件大小安全检查 (核心功能)
                "max_filesize_mb": ("FLOAT", {"default": 500.0, "min": 0.0, "max": 10000.0, "step": 1.0, "tooltip": "最大文件大小(MB)，超过将被跳过"}),
                
                # 性能与鲁棒性
                "scan_max_depth": ("INT", {"default": 10, "min": 1, "max": 100, "step": 1, "tooltip": "目录扫描最大深度，1表示只扫描当前目录"}),
                "on_io_error": (["停止并报错", "跳过并警告"], {"default": "停止并报错", "tooltip": "文件缺失等IO错误处理"}),
                "on_data_error": (["跳过并警告", "停止并报错"], {"default": "跳过并警告", "tooltip": "文件损坏等数据错误处理"}),
                
                # 通用功能（从音频加载器继承语义）
                "enable_mapping": ("BOOLEAN", {"default": False, "tooltip": "是否启用语义映射"}),
                "mapping_json": ("STRING", {"default": "{\n  \"temp_01\": \"角色A\",\n  \"temp_02\": \"角色B\",\n  \"draft\": \"草稿版\",\n  \"final\": \"最终版\"\n}", "multiline": True, "tooltip": "JSON格式的映射表"}),
                "enable_negative_filter": ("BOOLEAN", {"default": False, "tooltip": "启用反向匹配模式"}),
                "negative_keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "反向排除关键词"}),
                "enable_time_filter": ("BOOLEAN", {"default": False, "tooltip": "启用时间戳筛选功能"}),
                "min_age_days": ("STRING", {"default": "0.0", "tooltip": "文件最小年龄（天），0表示不限制"}),
                "max_age_days": ("STRING", {"default": "0.0", "tooltip": "文件最大年龄（天），0表示今天"}),
                "date_filter_mode": (["修改时间", "创建时间"], {"default": "修改时间", "tooltip": "时间戳筛选类型"}),
                "sort_mode": (["文件名(数字优先)", "文件名(字母)", "修改时间(新到旧)", "修改时间(旧到新)", "文件大小(大到小)", "文件大小(小到大)", "随机排序"], {"default": "文件名(数字优先)", "tooltip": "文件排序方式"}),
                "random_selection": ("BOOLEAN", {"default": False, "tooltip": "是否随机选择文件"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "tooltip": "随机种子，0表示自动生成"}),
                "file_limit": ("INT", {"default": 0, "min": 0, "max": 10000, "step": 1, "tooltip": "输出列表最大文件数量，0表示不限制"}),
                "start_index": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "从列表的哪个索引开始输出"}),
                "select_index": ("INT", {"default": -1, "min": -1, "step": 1, "tooltip": "强制选中列表中的特定索引文件，-1禁用"}),
                
                # 视频特有功能（减法优化后保留的核心）
                "extraction_mode": (["Full_Video", "Time_Slice", "Chunk_Mode"], {"default": "Full_Video", "tooltip": "视频提取模式：完整视频/时间切片/分块模式"}),
                "start_time_sec": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 3600.0, "step": 0.1, "tooltip": "时间切片开始时间(秒)"}),
                "end_time_sec": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 3600.0, "step": 0.1, "tooltip": "时间切片结束时间(秒)"}),
                "chunk_duration_sec": ("FLOAT", {"default": 10.0, "min": 1.0, "max": 300.0, "step": 0.1, "tooltip": "分块模式的每块时长(秒)"}),
                "frame_sampling_mode": (["Full_FPS", "Every_Nth_Frame"], {"default": "Full_FPS", "tooltip": "帧采样模式：完整帧率/间隔采样"}),
                "nth_frame": ("INT", {"default": 1, "min": 1, "max": 30, "step": 1, "tooltip": "间隔采样的帧间隔，仅在Every_Nth_Frame模式下有效"}),
                "enable_statistics": ("BOOLEAN", {"default": True, "tooltip": "启用统计信息输出"}),
                
                # 高级选项
                "exclude_keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "排除关键词，多行输入"}),
                "case_sensitive": ("BOOLEAN", {"default": False, "tooltip": "关键词匹配大小写敏感"}),
                "enable_hash_cache": ("BOOLEAN", {"default": True, "tooltip": "启用文件哈希缓存加速"}),
            }
        }
        return inputs
    
    RETURN_TYPES = (
        "VIDEO_TENSOR", "STRING", "STRING", "INT", "STRING", "FLOAT", "INT", "STRING"
    )
    
    RETURN_NAMES = (
        "VIDEO_TENSOR", "SELECTED_PATH", "ALL_PATHS", "FILE_COUNT", "INFO_MAPPING_JSON", "DURATION", "FPS", "REPORT_JSON"
    )
    
    FUNCTION = "load_batch"
    CATEGORY = "buding_Tools/智能文件加载"
    
    def load_batch(self, directory_path: str, keywords: str, video_container: str = ".mp4|.mov|.avi",
                   similarity_threshold: float = 0.7, debug_mode: bool = False,
                   target_fps: int = 30, min_width: int = 0, max_width: int = 99999,
                   min_height: int = 0, max_height: int = 99999, min_duration: float = 0.1,
                   enable_exceedance_handling: bool = True, max_duration: float = 300.0,
                   on_max_duration_exceedance: str = "Filter/Skip", max_filesize_mb: float = 500.0,
                   scan_max_depth: int = 10, on_io_error: str = "停止并报错", on_data_error: str = "跳过并警告",
                   enable_mapping: bool = False, mapping_json: str = "", enable_negative_filter: bool = False,
                   negative_keywords: str = "", enable_time_filter: bool = False, min_age_days: str = "0.0",
                   max_age_days: str = "0.0", date_filter_mode: str = "修改时间", sort_mode: str = "文件名(数字优先)",
                   random_selection: bool = False, seed: int = 0, file_limit: int = 0, start_index: int = 0,
                   select_index: int = -1, extraction_mode: str = "Full_Video", start_time_sec: float = 0.0,
                   end_time_sec: float = 10.0, chunk_duration_sec: float = 10.0, frame_sampling_mode: str = "Full_FPS",
                   nth_frame: int = 1, enable_statistics: bool = True, exclude_keywords: str = "",
                   case_sensitive: bool = False, enable_hash_cache: bool = True, **kwargs: Any) -> Tuple[torch.Tensor, str, str, int, str, float, int, str]:
        """主加载入口 - 继承音频加载器的架构"""
        
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
            min_width = int(min_width) if min_width else 0
        except (ValueError, TypeError):
            min_width = 0
            
        try:
            max_width = int(max_width) if max_width else 99999
        except (ValueError, TypeError):
            max_width = 99999
            
        try:
            min_height = int(min_height) if min_height else 0
        except (ValueError, TypeError):
            min_height = 0
            
        try:
            max_height = int(max_height) if max_height else 99999
        except (ValueError, TypeError):
            max_height = 99999
            
        try:
            target_fps = int(target_fps) if target_fps else 30
        except (ValueError, TypeError):
            target_fps = 30
            
        try:
            max_filesize_mb = float(max_filesize_mb) if max_filesize_mb else 500.0
        except (ValueError, TypeError):
            max_filesize_mb = 500.0
        
        try:
            # 参数验证
            self._validate_inputs(**kwargs)
            
            # 第一遍扫描：快速元数据筛选
            all_file_infos = self._scan_and_filter_metadata(**kwargs)
            
            if not all_file_infos:
                self._debug_print("没有找到符合条件的视频文件", **kwargs)
                return self._return_empty_result(**kwargs)
            
            # 第二遍：加载选中的视频
            selected_video = self._load_selected_video(all_file_infos, **kwargs)
            
            # 格式化输出
            return self._format_outputs(selected_video, all_file_infos, **kwargs)
            
        except Exception as e:
            error_msg = f"buding_SmartVideoBatchLoader错误: {str(e)}"
            self._debug_print(error_msg, **kwargs)
            
            if kwargs.get('on_data_error', '跳过并警告') == '停止并报错':
                raise Exception(error_msg)
            else:
                return self._return_empty_result(**kwargs)
    
    def _validate_inputs(self, **kwargs):
        """输入参数验证 - 继承通用验证框架"""
        directory_path = kwargs.get('directory_path', '').strip()
        if not directory_path:
            raise ValueError("目录路径不能为空")
        
        if not os.path.exists(directory_path):
            raise ValueError(f"目录不存在: {directory_path}")
        
        if not os.path.isdir(directory_path):
            raise ValueError(f"路径不是目录: {directory_path}")
        
        # 视频特有参数验证
        start_time = kwargs.get('start_time_sec', 0.0)
        end_time = kwargs.get('end_time_sec', 10.0)
        if start_time >= end_time:
            raise ValueError("起始时间必须小于结束时间")
        
        min_duration = kwargs.get('min_duration', 0.1)
        max_duration = kwargs.get('max_duration', 3600.0)
        if min_duration >= max_duration:
            raise ValueError("最小时长必须小于最大时长")
        
        # 分辨率验证
        min_width = kwargs.get('min_width', 0)
        max_width = kwargs.get('max_width', 99999)
        if min_width > max_width:
            raise ValueError("最小宽度不能大于最大宽度")
        
        min_height = kwargs.get('min_height', 0)
        max_height = kwargs.get('max_height', 99999)
        if min_height > max_height:
            raise ValueError("最小高度不能大于最大高度")
    
    def _scan_and_filter_metadata(self, **kwargs) -> List[Dict[str, Any]]:
        """第一遍扫描：快速元数据筛选 - 适配视频元数据"""
        directory_path = kwargs.get('directory_path', '').strip()
        video_container = kwargs.get('video_container', '.mp4|.mov|.avi')
        keywords = [k.strip() for k in kwargs.get('keywords', '').split('\n') if k.strip()]
        exclude_keywords = [k.strip() for k in kwargs.get('exclude_keywords', '').split('\n') if k.strip()]
        similarity_threshold = kwargs.get('similarity_threshold', 0.7)
        max_depth = kwargs.get('scan_max_depth', 100)
        
        # 视频筛选参数
        target_fps = kwargs.get('target_fps', 30)
        min_width = kwargs.get('min_width', 0)
        max_width = kwargs.get('max_width', 99999)
        min_height = kwargs.get('min_height', 0)
        max_height = kwargs.get('max_height', 99999)
        min_duration = kwargs.get('min_duration', 0.1)
        max_duration = kwargs.get('max_duration', 3600.0)
        enable_exceedance_handling = kwargs.get('enable_exceedance_handling', True)
        on_max_duration_exceedance = kwargs.get('on_max_duration_exceedance', 'Filter/Skip')
        
        # 文件大小限制
        max_filesize_mb = kwargs.get('max_filesize_mb', 100.0)
        min_filesize_mb = kwargs.get('min_filesize_mb', 0.01)
        
        self._debug_print(f"开始扫描目录: {directory_path}", **kwargs)
        self._debug_print(f"视频格式: {video_container}, 目标帧率: {target_fps}", **kwargs)
        
        # 解析支持的扩展名
        if video_container == "any":
            extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm']
        else:
            extensions = [ext.strip() for ext in video_container.split('|')]
        
        # 扫描文件
        all_files = []
        scanned_count = 0
        
        for root, dirs, files in os.walk(directory_path):
            current_depth = root[len(directory_path):].count(os.sep)
            if current_depth > max_depth:
                continue
            
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = os.path.splitext(file)[1].lower()
                
                if file_ext in extensions:
                    scanned_count += 1
                    
                    try:
                        # 快速安全检查
                        if not self._quick_safety_check(file_path, min_filesize_mb, max_filesize_mb, **kwargs):
                            continue
                        
                        # 关键词匹配
                        if keywords and not self._match_keywords(file, keywords, similarity_threshold, kwargs.get('case_sensitive', False)):
                            continue
                        
                        if exclude_keywords and self._match_keywords(file, exclude_keywords, 1.0, kwargs.get('case_sensitive', False)):
                            continue
                        
                        # 获取视频元数据
                        video_info = self._get_video_metadata(file_path, **kwargs)
                        if not video_info:
                            continue
                        
                        # 应用视频筛选条件
                        if self._apply_video_filters(video_info, target_fps, min_width, max_width, 
                                                    min_height, max_height, min_duration, max_duration,
                                                    enable_exceedance_handling, on_max_duration_exceedance, **kwargs):
                            all_files.append(video_info)
                    
                    except Exception as e:
                        self._debug_print(f"处理文件失败 {file_path}: {e}", **kwargs)
                        continue
        
        self._debug_print(f"扫描完成: 总扫描{scanned_count}个文件，筛选出{len(all_files)}个有效视频", **kwargs)
        
        # 应用排序和限制
        return self._apply_limits_and_selection(all_files, **kwargs)
    
    def _quick_safety_check(self, file_path: str, min_size_mb: float, max_size_mb: float, **kwargs) -> bool:
        """快速安全检查 - 文件大小验证"""
        try:
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)
            
            if size_mb < min_size_mb:
                self._debug_print(f"文件太小: {file_path} ({size_mb:.2f}MB < {min_size_mb}MB)", **kwargs)
                return False
            
            if size_mb > max_size_mb:
                self._debug_print(f"文件过大: {file_path} ({size_mb:.2f}MB > {max_size_mb}MB)", **kwargs)
                return False
            
            return True
        except Exception as e:
            self._debug_print(f"文件大小检查失败 {file_path}: {e}", **kwargs)
            return False
    
    def _get_video_metadata(self, video_path: str, **kwargs) -> Optional[Dict[str, Any]]:
        """获取视频元数据 - 使用Decord快速读取"""
        try:
            if DECORD_AVAILABLE:
                return self._get_metadata_with_decord(video_path, **kwargs)
            elif OPENCV_AVAILABLE:
                return self._get_metadata_with_opencv(video_path, **kwargs)
            else:
                self._debug_print(f"无可用的视频读取库: {video_path}", **kwargs)
                return None
        except Exception as e:
            self._debug_print(f"获取视频元数据失败 {video_path}: {e}", **kwargs)
            return None
    
    def _get_metadata_with_decord(self, video_path: str, **kwargs) -> Optional[Dict[str, Any]]:
        """使用Decord获取视频元数据"""
        try:
            vr = decord.VideoReader(video_path)
            
            # 获取基本信息
            fps = vr.get_avg_fps()
            width, height = vr[0].shape[1], vr[0].shape[0]  # 第一帧的尺寸
            duration = len(vr) / fps if fps > 0 else 0
            
            # 获取文件大小
            file_size = os.path.getsize(video_path)
            
            return {
                'path': video_path,
                'filename': os.path.basename(video_path),
                'width': width,
                'height': height,
                'fps': fps,
                'duration': duration,
                'frame_count': len(vr),
                'size': file_size,
                'container': os.path.splitext(video_path)[1].lower(),
                'reader_type': 'decord'
            }
        except Exception as e:
            self._debug_print(f"Decord读取失败 {video_path}: {e}", **kwargs)
            return None
    
    def _get_metadata_with_opencv(self, video_path: str, **kwargs) -> Optional[Dict[str, Any]]:
        """使用OpenCV获取视频元数据（降级方案）"""
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                return None
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            
            cap.release()
            
            # 获取文件大小
            file_size = os.path.getsize(video_path)
            
            return {
                'path': video_path,
                'filename': os.path.basename(video_path),
                'width': width,
                'height': height,
                'fps': fps,
                'duration': duration,
                'frame_count': frame_count,
                'size': file_size,
                'container': os.path.splitext(video_path)[1].lower(),
                'reader_type': 'opencv'
            }
        except Exception as e:
            self._debug_print(f"OpenCV读取失败 {video_path}: {e}", **kwargs)
            return None
    
    def _apply_video_filters(self, video_info: Dict[str, Any], target_fps: int, 
                           min_width: int, max_width: int, min_height: int, max_height: int,
                           min_duration: float, max_duration: float,
                           enable_exceedance_handling: bool, on_max_duration_exceedance: str, 
                           **kwargs) -> bool:
        """应用视频筛选条件"""
        try:
            # 帧率筛选
            fps = video_info.get('fps', 0)
            if fps <= 0:
                self._debug_print(f"无效帧率: {video_info['path']}", **kwargs)
                return False
            
            # 帧率容差检查（允许轻微偏差）
            fps_tolerance = kwargs.get('fps_tolerance', 0.1)
            if abs(fps - target_fps) > fps_tolerance:
                self._debug_print(f"帧率不匹配: {video_info['path']} ({fps} vs {target_fps})", **kwargs)
                return False
            
            # 分辨率筛选
            width = video_info.get('width', 0)
            height = video_info.get('height', 0)
            
            if width < min_width or width > max_width:
                self._debug_print(f"宽度不符合: {video_info['path']} ({width}x{height})", **kwargs)
                return False
            
            if height < min_height or height > max_height:
                self._debug_print(f"高度不符合: {video_info['path']} ({width}x{height})", **kwargs)
                return False
            
            # 时长筛选
            duration = video_info.get('duration', 0)
            
            if duration < min_duration:
                self._debug_print(f"时长过短: {video_info['path']} ({duration:.2f}s < {min_duration}s)", **kwargs)
                return False
            
            # 超长视频处理
            if enable_exceedance_handling and duration > max_duration:
                if on_max_duration_exceedance == 'Filter/Skip':
                    self._debug_print(f"时长超限被跳过: {video_info['path']} ({duration:.2f}s > {max_duration}s)", **kwargs)
                    return False
                else:  # Pass_Through
                    self._debug_print(f"时长超限但通过: {video_info['path']} ({duration:.2f}s)", **kwargs)
            
            return True
            
        except Exception as e:
            self._debug_print(f"筛选条件应用失败: {e}", **kwargs)
            return False
    
    def _match_keywords(self, filename: str, keywords: List[str], threshold: float, case_sensitive: bool = False) -> bool:
        """关键词匹配 - 完全继承音频加载器逻辑"""
        if not keywords:
            return True
        
        # 文件名清理
        import re
        clean_name = re.sub(r'[^\w\u4e00-\u9fff]', '_', filename)
        if not case_sensitive:
            clean_name = clean_name.lower()
            keywords = [k.lower() for k in keywords]
        
        # 精确匹配
        for keyword in keywords:
            if keyword in clean_name:
                return True
        
        # 模糊匹配（简单实现）
        for keyword in keywords:
            # 简单的包含匹配
            if any(part in clean_name for part in keyword.split('_') if part):
                return True
        
        return False
    
    def _apply_limits_and_selection(self, file_list: List[Dict[str, Any]], **kwargs) -> List[Dict[str, Any]]:
        """应用数量限制和选择 - 继承通用逻辑"""
        if not file_list:
            return file_list
        
        # 排序 - 继承音频加载器的排序模式
        sort_mode = kwargs.get('sort_mode', '文件名(数字优先)')
        
        if sort_mode == "文件名(数字优先)":
            # 数字优先排序
            import re
            def natural_key(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
            file_list.sort(key=lambda x: natural_key(x['filename']))
        elif sort_mode == "文件名(字母)":
            file_list.sort(key=lambda x: x['filename'].lower())
        elif sort_mode == "修改时间(新到旧)":
            file_list.sort(key=lambda x: x.get('mtime', 0), reverse=True)
        elif sort_mode == "修改时间(旧到新)":
            file_list.sort(key=lambda x: x.get('mtime', 0))
        elif sort_mode == "文件大小(大到小)":
            file_list.sort(key=lambda x: x.get('size', 0), reverse=True)
        elif sort_mode == "文件大小(小到大)":
            file_list.sort(key=lambda x: x.get('size', 0))
        elif sort_mode == "随机排序":
            seed = kwargs.get('seed', 0)
            if seed == 0:
                import time
                seed = int(time.time())
            random.seed(seed)
            random.shuffle(file_list)
        
        # 随机选择
        if kwargs.get('random_selection', False):
            seed = kwargs.get('seed', 0)
            if seed == 0:
                import time
                seed = int(time.time())
            random.seed(seed)
            file_list = [random.choice(file_list)]
        
        # 数量限制
        file_limit = kwargs.get('file_limit', 0)
        if file_limit > 0:
            file_list = file_list[:file_limit]
        
        # 起始索引
        start_index = kwargs.get('start_index', 0)
        if start_index > 0:
            file_list = file_list[start_index:]
        
        # 强制选择特定索引
        select_index = kwargs.get('select_index', -1)
        if select_index >= 0 and select_index < len(file_list):
            file_list = [file_list[select_index]]
        
        return file_list
    
    def _load_selected_video(self, file_list: List[Dict[str, Any]], **kwargs) -> Optional[Dict[str, Any]]:
        """加载选中的视频 - 第二遍扫描"""
        if not file_list:
            return None
        
        # 选择第一个文件（可以扩展为随机选择等）
        selected_file = file_list[0]
        
        try:
            # 提取视频片段
            video_tensor = self._extract_video_segment(selected_file, **kwargs)
            
            if video_tensor is not None:
                return {
                    'tensor': video_tensor,
                    'info': selected_file
                }
            else:
                return None
                
        except Exception as e:
            self._debug_print(f"视频加载失败 {selected_file['path']}: {e}", **kwargs)
            return None
    
    def _extract_video_segment(self, video_info: Dict[str, Any], **kwargs) -> Optional[torch.Tensor]:
        """视频片段提取 - 核心I/O功能"""
        try:
            video_path = video_info['path']
            extraction_mode = kwargs.get('extraction_mode', 'Full_Video')
            start_time = kwargs.get('start_time_sec', 0.0)
            end_time = kwargs.get('end_time_sec', 10.0)
            frame_sampling_mode = kwargs.get('frame_sampling_mode', 'Full_FPS')
            nth_frame = kwargs.get('nth_frame', 1)
            
            if DECORD_AVAILABLE:
                return self._extract_with_decord(video_path, extraction_mode, start_time, end_time, 
                                               frame_sampling_mode, nth_frame, **kwargs)
            elif OPENCV_AVAILABLE:
                return self._extract_with_opencv(video_path, extraction_mode, start_time, end_time,
                                               frame_sampling_mode, nth_frame, **kwargs)
            else:
                raise ImportError("无可用的视频读取库")
                
        except Exception as e:
            self._debug_print(f"视频片段提取失败: {e}", **kwargs)
            return None
    
    def _extract_with_decord(self, video_path: str, extraction_mode: str, start_time: float, 
                           end_time: float, frame_sampling_mode: str, nth_frame: int, **kwargs) -> Optional[torch.Tensor]:
        """使用Decord提取视频片段"""
        try:
            vr = decord.VideoReader(video_path)
            fps = vr.get_avg_fps()
            total_frames = len(vr)
            
            # 计算帧索引范围
            if extraction_mode == "Time_Slice":
                start_frame = max(0, int(start_time * fps))
                end_frame = min(total_frames, int(end_time * fps))
            elif extraction_mode == "Chunk_Mode":
                chunk_duration = kwargs.get('chunk_duration_sec', 10.0)
                start_frame = 0
                end_frame = min(total_frames, int(chunk_duration * fps))
            else:  # Full_Video
                start_frame = 0
                end_frame = total_frames
            
            # 提取帧
            frame_indices = list(range(start_frame, end_frame))
            
            if not frame_indices:
                self._debug_print(f"无效的帧范围: {start_frame}-{end_frame}", **kwargs)
                return None
            
            # 应用帧采样
            if frame_sampling_mode == "Every_Nth_Frame" and nth_frame > 1:
                frame_indices = frame_indices[::nth_frame]
            
            # 批量读取帧
            frames = vr.get_batch(frame_indices)
            
            # 转换为PyTorch张量
            if isinstance(frames, decord.nd.NDArray):
                frames = torch.from_numpy(frames.asnumpy())
            
            # 确保格式为 [frames, height, width, channels]
            if frames.dim() == 4 and frames.shape[-1] in [1, 3, 4]:
                # Decord通常是 [frames, height, width, channels]
                pass
            else:
                # 转换格式
                frames = frames.permute(0, 2, 3, 1) if frames.dim() == 4 else frames
            
            return video_to_tensor(frames, fps)
            
        except Exception as e:
            self._debug_print(f"Decord提取失败: {e}", **kwargs)
            return None
    
    def _extract_with_opencv(self, video_path: str, extraction_mode: str, start_time: float,
                           end_time: float, frame_sampling_mode: str, nth_frame: int, **kwargs) -> Optional[torch.Tensor]:
        """使用OpenCV提取视频片段（降级方案）"""
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                return None
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # 计算帧索引范围
            if extraction_mode == "Time_Slice":
                start_frame = max(0, int(start_time * fps))
                end_frame = min(total_frames, int(end_time * fps))
            elif extraction_mode == "Chunk_Mode":
                chunk_duration = kwargs.get('chunk_duration_sec', 10.0)
                start_frame = 0
                end_frame = min(total_frames, int(chunk_duration * fps))
            else:  # Full_Video
                start_frame = 0
                end_frame = total_frames
            
            # 提取帧
            frames = []
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            frame_indices = list(range(start_frame, end_frame))
            
            # 应用帧采样
            if frame_sampling_mode == "Every_Nth_Frame" and nth_frame > 1:
                frame_indices = frame_indices[::nth_frame]
            
            for frame_idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if ret:
                    # OpenCV是BGR格式，转换为RGB
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(torch.from_numpy(frame))
                else:
                    break
            
            cap.release()
            
            if not frames:
                return None
            
            # 堆叠帧并转换为张量
            frames_tensor = torch.stack(frames)  # [frames, height, width, channels]
            
            return video_to_tensor(frames_tensor, fps)
            
        except Exception as e:
            self._debug_print(f"OpenCV提取失败: {e}", **kwargs)
            return None
    
    def _format_outputs(self, selected_video: Optional[Dict[str, Any]], 
                        all_files: List[Dict[str, Any]], **kwargs) -> Tuple:
        """格式化输出 - 8端口设计"""
        if selected_video is None:
            return self._return_empty_result(**kwargs)
        
        video_tensor = selected_video['tensor']
        video_info = selected_video['info']
        
        # 主要输出
        selected_path = video_info['path']
        all_paths = json.dumps([f['path'] for f in all_files], ensure_ascii=False)
        file_count = len(all_files)
        duration = video_info.get('duration', 0.0)
        fps = int(video_info.get('fps', 0))
        
        # 详细信息映射
        info_mapping = {}
        if kwargs.get('enable_info_mapping', True):
            info_mapping = self._generate_info_mapping(all_files, **kwargs)
        info_mapping_json = json.dumps(info_mapping, ensure_ascii=False, indent=2)
        
        # 统计报告
        report_json = "{}"
        if kwargs.get('enable_statistics', True):
            report_json = self._generate_report_json(video_info, all_files, **kwargs)
        
        return (
            video_tensor,
            selected_path,
            all_paths,
            file_count,
            info_mapping_json,
            duration,
            fps,
            report_json
        )
    
    def _return_empty_result(self, **kwargs) -> Tuple:
        """返回空结果 - 继承音频加载器设计"""
        empty_tensor = torch.zeros(1, 1, 1, 1, 3)  # [batch, frames, height, width, channels]
        
        return (
            empty_tensor,
            "",  # SELECTED_PATH
            "[]",  # ALL_PATHS
            0,  # FILE_COUNT
            "{}",  # INFO_MAPPING_JSON
            0.0,  # DURATION
            0,  # FPS
            "{}"  # REPORT_JSON
        )
    
    def _generate_info_mapping(self, file_list: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """生成详细信息映射 - 适配视频信息"""
        mapping = {}
        
        for i, file_info in enumerate(file_list):
            filename = file_info['filename']
            mapping[filename] = {
                'path': file_info['path'],
                'index': i,
                'width': file_info.get('width', 0),
                'height': file_info.get('height', 0),
                'fps': file_info.get('fps', 0),
                'duration': file_info.get('duration', 0),
                'frame_count': file_info.get('frame_count', 0),
                'size_mb': round(file_info.get('size', 0) / (1024 * 1024), 2),
                'container': file_info.get('container', ''),
                'reader_type': file_info.get('reader_type', 'unknown')
            }
        
        return mapping
    
    def _generate_report_json(self, selected_file: Dict[str, Any], 
                              all_files: List[Dict[str, Any]], **kwargs) -> str:
        """生成统计报告 - 适配视频统计"""
        try:
            # 计算统计信息
            total_files = len(all_files)
            total_duration = sum(f.get('duration', 0) for f in all_files)
            total_size = sum(f.get('size', 0) for f in all_files)
            
            # 分辨率分布
            resolution_counts = {}
            fps_counts = {}
            format_counts = {}
            
            for file_info in all_files:
                # 分辨率统计
                resolution = f"{file_info.get('width', 0)}x{file_info.get('height', 0)}"
                resolution_counts[resolution] = resolution_counts.get(resolution, 0) + 1
                
                # 帧率统计
                fps = int(file_info.get('fps', 0))
                fps_counts[f"{fps}fps"] = fps_counts.get(f"{fps}fps", 0) + 1
                
                # 格式统计
                container = file_info.get('container', '')
                format_counts[container] = format_counts.get(container, 0) + 1
            
            # 构建报告
            report = {
                "selected_file": {
                    "path": selected_file['path'],
                    "filename": selected_file['filename'],
                    "width": selected_file.get('width', 0),
                    "height": selected_file.get('height', 0),
                    "fps": selected_file.get('fps', 0),
                    "duration": round(selected_file.get('duration', 0), 2),
                    "frame_count": selected_file.get('frame_count', 0),
                    "size_mb": round(selected_file.get('size', 0) / (1024 * 1024), 2),
                    "container": selected_file.get('container', ''),
                    "reader_type": selected_file.get('reader_type', 'unknown')
                },
                "statistics": {
                    "total_files": total_files,
                    "total_duration": round(total_duration, 2),
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "avg_duration": round(total_duration / total_files, 2) if total_files > 0 else 0,
                    "avg_size_mb": round(total_size / total_files / (1024 * 1024), 2) if total_files > 0 else 0,
                    "resolution_distribution": resolution_counts,
                    "fps_distribution": fps_counts,
                    "format_distribution": format_counts
                },
                "processing_info": {
                    "target_fps": kwargs.get('target_fps', 30),
                    "extraction_mode": kwargs.get('extraction_mode', 'Full_Video'),
                    "frame_sampling_mode": kwargs.get('frame_sampling_mode', 'Full_FPS'),
                    "nth_frame": kwargs.get('nth_frame', 1),
                    "video_container": kwargs.get('video_container', '.mp4|.mov|.avi'),
                    "decord_available": DECORD_AVAILABLE,
                    "opencv_available": OPENCV_AVAILABLE
                },
                "filter_stats": {
                    "initial_scan_count": kwargs.get('initial_count', total_files),
                    "final_count": total_files,
                    "filter_efficiency": f"{100.0}%"  # 这里可以添加更详细的筛选统计
                }
            }
            
            return json.dumps(report, ensure_ascii=False, indent=2)
            
        except Exception as e:
            self._debug_print(f"生成报告失败: {e}", **kwargs)
            return json.dumps({"error": f"报告生成失败: {str(e)}"}, ensure_ascii=False)
    
    def _debug_print(self, message: str, **kwargs):
        """调试输出 - 完全继承"""
        if kwargs.get('debug_mode', False):
            print(f"[DEBUG] buding_SmartVideoBatchLoader: {message}")

# 节点注册
NODE_CLASS_MAPPINGS = {
    "buding_SmartVideoBatchLoader": buding_SmartVideoBatchLoader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SmartVideoBatchLoader": "🎬 buding_SmartVideoBatchLoader (智能视频批量加载器)"
}
