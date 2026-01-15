"""
buding_SmartAudioLoader - 智能音频批量加载器
版本: v1.0.0
功能: 音频时长筛选、格式标准化、元数据快速筛选、超长音频处理策略
依赖: mutagen (元数据读取), torchaudio (波形加载)
"""

import os
import json
import random
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# 核心依赖
try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    print("⚠️ mutagen未安装，音频元数据功能将受限")

try:
    import torchaudio
    TORCHAUDIO_AVAILABLE = True
except ImportError:
    TORCHAUDIO_AVAILABLE = False
    print("⚠️ torchaudio未安装，音频加载功能将受限")

import torch
import numpy as np

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

def audio_to_tensor(waveform: torch.Tensor, samplerate: int) -> torch.Tensor:
    """torchaudio waveform to ComfyUI/PyTorch Tensor"""
    # 确保波形格式为 [1, channels, samples]
    if waveform.dim() == 2:  # [channels, samples]
        waveform = waveform.unsqueeze(0)  # [1, channels, samples]
    elif waveform.dim() == 1:  # [samples]
        waveform = waveform.unsqueeze(0).unsqueeze(0)  # [1, 1, samples]
    return waveform

class buding_SmartAudioBatchLoader:
    """智能音频批量加载器"""
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数"""
        inputs = {
            "required": {
                "directory_path": ("STRING", {"default": "", "multiline": False, "tooltip": "要扫描的音频文件目录路径"}),
                "audio_extension": (
                    [".wav|.mp3|.flac", ".wav", ".mp3", ".flac", "any"], 
                    {"default": ".wav|.mp3|.flac", "tooltip": "音频格式筛选，使用 '|' 分隔。'any' 匹配所有格式"}
                ),
                "keywords": ("STRING", {"default": "", "multiline": True, "tooltip": "正向匹配关键词，每行一个（或关系）"}),
                "similarity_threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.1, "tooltip": "模糊匹配的最低相似度要求"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "启用调试输出模式"}),
                
                # 时长控制 (场景一)
                "min_duration": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 3600.0, "step": 0.1, "tooltip": "最小时长(秒)，排除过短音频"}),
            },
            "optional": {
                # 超长处理总开关 (场景一最终优化)
                "enable_exceedance_handling": ("BOOLEAN", {"default": True, "tooltip": "启用最大时长检查和处理"}),
                "max_duration": ("FLOAT", {"default": 20.0, "min": 0.0, "max": 3600.0, "step": 0.1, "tooltip": "最大时长(秒)，超过此阈值的文件将按策略处理"}),
                "on_max_duration_exceedance": (["Filter/Skip", "Pass_Through"], {"default": "Filter/Skip", "tooltip": "超长音频处理策略"}),
                
                # 声学质量筛选
                "min_rms_db": ("FLOAT", {"default": -40.0, "min": -100.0, "max": 0.0, "step": 1.0, "tooltip": "最小RMS电平(dB)，排除静音文件"}),
                
                # 性能与鲁棒性
                "scan_max_depth": ("INT", {"default": 10, "min": 1, "max": 100, "step": 1, "tooltip": "目录扫描最大深度，1表示只扫描当前目录"}),
                "on_io_error": (["停止并报错", "跳过并警告"], {"default": "停止并报错", "tooltip": "文件缺失等IO错误处理"}),
                "on_data_error": (["跳过并警告", "停止并报错"], {"default": "跳过并警告", "tooltip": "文件损坏等数据错误处理"}),
                
                # 通用功能（从文本加载器移植）
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
            }
        }
        return inputs
    
    RETURN_TYPES = ("AUDIO", "STRING", "STRING", "INT", "STRING", "FLOAT", "INT", "STRING")
    RETURN_NAMES = ("AUDIO_TENSOR", "SELECTED_PATH", "ALL_PATHS", "FILE_COUNT", "INFO_MAPPING_JSON", "DURATION", "SAMPLERATE", "REPORT_JSON")
    FUNCTION = "load_batch"
    CATEGORY = "buding_Tools/智能文件加载"
    
    @classmethod
    def IS_CHANGED(cls, directory_path, audio_extension, keywords, similarity_threshold, debug_mode=False, **kwargs):
        """检查输入是否改变"""
        param_string = f"{directory_path}_{audio_extension}_{keywords}_{similarity_threshold}_{str(kwargs)}"
        return hash(param_string)
    
    def load_batch(self, directory_path: str, keywords: str, audio_extension: str = ".wav|.mp3|.flac",
                   similarity_threshold: float = 0.7, debug_mode: bool = False, min_duration: float = 0.5,
                   enable_exceedance_handling: bool = True, max_duration: float = 20.0, 
                   on_max_duration_exceedance: str = "Filter/Skip", min_rms_db: float = -40.0,
                   scan_max_depth: int = 10, on_io_error: str = "停止并报错", on_data_error: str = "跳过并警告",
                   enable_mapping: bool = False, mapping_json: str = "", enable_negative_filter: bool = False,
                   negative_keywords: str = "", enable_time_filter: bool = False, min_age_days: str = "0.0",
                   max_age_days: str = "0.0", date_filter_mode: str = "修改时间", sort_mode: str = "文件名(数字优先)",
                   random_selection: bool = False, seed: int = 0, file_limit: int = 0, start_index: int = 0,
                   select_index: int = -1, **kwargs: Any) -> Tuple[torch.Tensor, str, str, int, str, float, int, str]:
        """智能音频批量加载主函数"""
        
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
        if not MUTAGEN_AVAILABLE:
            raise Exception("❌ mutagen库未安装，无法读取音频元数据。请安装: pip install mutagen")
        if not TORCHAUDIO_AVAILABLE:
            raise Exception("❌ torchaudio库未安装，无法加载音频文件。请安装: pip install torchaudio")
        
        # 初始化进度条和错误日志
        pbar = ComfyUIProgressBar(100)
        pbar.update(5, desc="初始化音频加载器...")
        error_log = []
        
        try:
            # 1. 快速扫描和元数据筛选
            all_file_infos = self._scan_and_filter_metadata(
                directory_path, audio_extension, keywords, similarity_threshold,
                min_duration, enable_exceedance_handling,
                max_duration, on_max_duration_exceedance, scan_max_depth, on_io_error,
                on_data_error, enable_mapping, mapping_json, enable_negative_filter,
                negative_keywords, enable_time_filter, min_age_days, max_age_days,
                date_filter_mode, debug_mode, error_log
            )
            pbar.update(70, desc=f"第一遍扫描完成，找到 {len(all_file_infos)} 个匹配文件")
            
            # 2. 应用排序和限制
            final_files = self._apply_limits_and_selection(
                all_file_infos, sort_mode, random_selection, seed, 
                file_limit, start_index, select_index, debug_mode
            )
            pbar.update(85, desc=f"排序和限制完成，最终 {len(final_files)} 个文件")
            
            # 3. 准备输出数据
            all_paths_list = [f['path'] for f in final_files]
            info_mapping = self._generate_info_mapping(final_files, debug_mode)
            
            # 4. 加载选中的音频
            selected_audio, selected_path, duration, samplerate = self._load_selected_audio(
                final_files, min_rms_db, debug_mode
            )
            
            # 5. 生成统计报告
            report_json = self._generate_report_json(
                final_files, final_files[0] if final_files else None, 
                {
                    "initial_files": len(all_file_infos),
                    "final_count": len(final_files),
                    "filter_efficiency": f"{len(final_files)/max(len(all_file_infos), 1)*100:.1f}%" if all_file_infos else "0%"
                },
                {
                    "min_duration": min_duration,
                    "max_duration": max_duration,
                    "enable_exceedance_handling": enable_exceedance_handling,
                    "on_max_duration_exceedance": on_max_duration_exceedance
                },
                debug_mode
            )
            
            pbar.update(100, desc="音频加载完成")
            
            # 6. 返回结果 (ComfyUI音频格式)
            return (
                {"waveform": selected_audio}, 
                selected_path, 
                json.dumps(all_paths_list, ensure_ascii=False), 
                len(final_files), 
                info_mapping, 
                duration, 
                samplerate, 
                report_json
            )
            
        except Exception as e:
            error_msg = f"❌ 智能音频加载失败: {str(e)}"
            if debug_mode:
                print(error_msg)
                import traceback
                traceback.print_exc()
            raise Exception(error_msg)
    
    def _scan_and_filter_metadata(self, root_dir: str, audio_extension: str, keywords: str,
                                 similarity_threshold: float, min_duration: float,
                                 enable_exceedance_handling: bool, max_duration: float,
                                 on_max_duration_exceedance: str, scan_max_depth: int, on_io_error: str,
                                 on_data_error: str, enable_mapping: bool, mapping_json: str,
                                 enable_negative_filter: bool, negative_keywords: str,
                                 enable_time_filter: bool, min_age_days: float, max_age_days: float,
                                 date_filter_mode: str, debug_mode: bool, error_log: List[str]) -> List[Dict]:
        """第一遍扫描：快速读取音频元数据进行筛选"""
        
        # 解析音频扩展名
        if audio_extension == "any":
            extensions = None  # 不限制扩展名
        else:
            extensions = [ext.strip() for ext in audio_extension.split('|') if ext.strip()]
        
        # 获取初始文件列表（支持扫描深度控制）
        all_files = []
        
        def scan_directory_with_depth(directory: str, current_depth: int):
            """递归扫描目录，控制深度"""
            if current_depth > scan_max_depth:
                return
            
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    if os.path.isfile(item_path):
                        all_files.append(item_path)
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
        
        # 扩展名筛选
        if extensions:
            filtered_files = []
            for file_path in all_files:
                file_ext = os.path.splitext(file_path)[1].lower()
                if file_ext in extensions:
                    filtered_files.append(file_path)
            all_files = filtered_files
        
        if debug_mode:
            print(f"📋 扩展名筛选后: {len(all_files)} 个文件")
        
        # 关键词筛选
        if keywords.strip():
            keyword_list = [kw.strip() for kw in keywords.split('\n') if kw.strip()]
            filtered_files = []
            for file_path in all_files:
                filename = os.path.basename(file_path)
                if self._match_keywords(filename, keyword_list, similarity_threshold):
                    filtered_files.append(file_path)
            all_files = filtered_files
        
        if debug_mode:
            print(f"🔍 关键词筛选后: {len(all_files)} 个文件")
        
        # 元数据筛选
        filtered_list = []
        for file_path in all_files:
            try:
                # 阶段1: 元数据读取
                audio_file = MutagenFile(file_path)
                
                if audio_file is None or not hasattr(audio_file, 'info'):
                    raise ValueError("无法解析音频元数据")
                
                # 获取基本信息
                duration = getattr(audio_file.info, 'length', 0)
                samplerate = getattr(audio_file.info, 'sample_rate', 0)
                channels = getattr(audio_file.info, 'channels', 1)
                
                if duration <= 0 or samplerate <= 0:
                    raise ValueError("无效的音频元数据")
                
                # 阶段2: 应用筛选规则
                
                # 1. 最小音频时长筛选 (始终生效)
                if duration < min_duration:
                    if debug_mode:
                        print(f"⏭️ 跳过过短音频: {os.path.basename(file_path)} ({duration:.2f}s < {min_duration}s)")
                    continue
                
                # 2. 目标采样率和声道数筛选
                # 3. 超长音频处理
                if enable_exceedance_handling and duration > max_duration:
                    if on_max_duration_exceedance == "Filter/Skip":
                        if debug_mode:
                            print(f"⏭️ 跳过超长音频: {os.path.basename(file_path)} ({duration:.2f}s > {max_duration}s)")
                        continue
                    # Pass_Through 模式继续执行
                
                # 收集信息
                file_info = {
                    'path': file_path,
                    'filename': os.path.basename(file_path),
                    'duration': duration,
                    'samplerate': samplerate,
                    'channels': channels,
                    'size': os.path.getsize(file_path),
                    'mtime': os.path.getmtime(file_path),
                    'ctime': os.path.getctime(file_path)
                }
                filtered_list.append(file_info)
                
            except Exception as e:
                if on_data_error == "停止并报错":
                    raise Exception(f"音频文件解析失败: {file_path} - {e}")
                else:
                    error_msg = f"⚠️ 音频文件损坏或无法解析，跳过: {os.path.basename(file_path)} - {e}"
                    error_log.append(error_msg)
                    if debug_mode:
                        print(error_msg)
                    continue
        
        if debug_mode:
            print(f"✅ 元数据筛选完成: {len(filtered_list)} 个文件通过筛选")
        
        return filtered_list
    
    def _match_keywords(self, filename: str, keywords: List[str], threshold: float) -> bool:
        """关键词匹配（简单实现）"""
        filename_lower = filename.lower()
        for keyword in keywords:
            if keyword.lower() in filename_lower:
                return True
        return False
    
    def _apply_limits_and_selection(self, files: List[Dict], sort_mode: str, random_selection: bool,
                                   seed: int, file_limit: int, start_index: int, select_index: int,
                                   debug_mode: bool) -> List[Dict]:
        """应用排序、随机选择和数量限制"""
        if not files:
            return []
        
        # 排序
        if sort_mode == "文件名(数字优先)":
            files.sort(key=lambda x: self._natural_sort_key(x['filename']))
        elif sort_mode == "文件名(字母)":
            files.sort(key=lambda x: x['filename'].lower())
        elif sort_mode == "修改时间(新到旧)":
            files.sort(key=lambda x: x['mtime'], reverse=True)
        elif sort_mode == "修改时间(旧到新)":
            files.sort(key=lambda x: x['mtime'])
        elif sort_mode == "文件大小(大到小)":
            files.sort(key=lambda x: x['size'], reverse=True)
        elif sort_mode == "文件大小(小到大)":
            files.sort(key=lambda x: x['size'])
        elif sort_mode == "随机排序":
            if seed == 0:
                seed = random.randint(0, 2**63 - 1)
            random.seed(seed)
            random.shuffle(files)
        
        # 随机选择
        if random_selection:
            if seed == 0:
                seed = random.randint(0, 2**63 - 1)
            random.seed(seed)
            files = [random.choice(files)] if files else []
        
        # 强制选择特定索引
        if select_index >= 0 and select_index < len(files):
            files = [files[select_index]]
        
        # 应用数量限制和起始索引
        if file_limit > 0:
            end_index = start_index + file_limit
            files = files[start_index:end_index]
        elif start_index > 0:
            files = files[start_index:]
        
        if debug_mode:
            print(f"📊 排序和限制应用完成: 最终 {len(files)} 个文件")
        
        return files
    
    def _natural_sort_key(self, filename: str) -> List:
        """自然排序键"""
        import re
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', filename)]
    
    def _load_selected_audio(self, final_files: List[Dict], min_rms_db: float, debug_mode: bool) -> Tuple[torch.Tensor, str, float, int]:
        """加载选中的音频文件"""
        if not final_files:
            return torch.zeros(1, 1, 1), "", 0.0, 0
        
        selected_file = final_files[0]
        selected_path = selected_file['path']
        
        try:
            # 加载波形数据
            waveform, sr = torchaudio.load(selected_path)
            
            # RMS检查
            if min_rms_db > -100:
                rms = torch.sqrt(torch.mean(waveform ** 2))
                rms_db = 20 * torch.log10(rms + 1e-8)
                if rms_db < min_rms_db:
                    if debug_mode:
                        print(f"⚠️ 音频RMS过低: {rms_db:.1f}dB < {min_rms_db}dB")
                    # 可以选择返回静音或跳过，这里返回静音
                    return torch.zeros(1, 1, 1), selected_path, selected_file['duration'], selected_file['samplerate']
            
            # 转换为ComfyUI格式
            audio_tensor = audio_to_tensor(waveform, sr)
            
            return audio_tensor, selected_path, selected_file['duration'], selected_file['samplerate']
            
        except Exception as e:
            error_msg = f"🚨 无法加载音频波形: {selected_path} - {e}"
            if debug_mode:
                print(error_msg)
            return torch.zeros(1, 1, 1), selected_path, 0.0, 0
    
    def _generate_info_mapping(self, files: List[Dict], debug_mode: bool) -> str:
        """生成信息映射JSON"""
        if not files:
            return "{}"
        
        mapping = {}
        for i, file_info in enumerate(files):
            mapping[str(i)] = {
                "path": file_info['path'],
                "filename": file_info['filename'],
                "duration": round(file_info['duration'], 3),
                "samplerate": file_info['samplerate'],
                "channels": file_info['channels'],
                "size": file_info['size']
            }
        
        return json.dumps(mapping, ensure_ascii=False, indent=2)
    
    def _generate_report_json(self, final_files: List[Dict], selected_file: Optional[Dict],
                             filter_stats: Dict, processing_info: Dict, debug_mode: bool) -> str:
        """生成完整的统计报告JSON"""
        if not final_files:
            return json.dumps({"error": "没有找到符合条件的音频文件"}, ensure_ascii=False)
        
        # 计算统计信息
        durations = [f['duration'] for f in final_files]
        samplerates = [f['samplerate'] for f in final_files]
        channels = [f['channels'] for f in final_files]
        
        # 格式分布
        format_distribution = {}
        for f in final_files:
            ext = os.path.splitext(f['path'])[1].lower()
            format_distribution[ext] = format_distribution.get(ext, 0) + 1
        
        report = {
            "selected_file": {
                "path": selected_file['path'] if selected_file else "",
                "filename": selected_file['filename'] if selected_file else "",
                "duration": selected_file['duration'] if selected_file else 0.0,
                "samplerate": selected_file['samplerate'] if selected_file else 0,
                "channels": selected_file['channels'] if selected_file else 0,
                "size": selected_file['size'] if selected_file else 0
            },
            "statistics": {
                "total_files": len(final_files),
                "exceeded_count": sum(1 for f in final_files if f['duration'] > processing_info.get('max_duration', 20.0)),
                "total_duration": round(sum(durations), 2),
                "avg_duration": round(sum(durations) / len(durations), 2) if durations else 0.0,
                "duration_range": {
                    "min": round(min(durations), 2) if durations else 0.0,
                    "max": round(max(durations), 2) if durations else 0.0
                },
                "samplerate_distribution": {str(sr): samplerates.count(sr) for sr in set(samplerates)},
                "channel_distribution": {"mono": channels.count(1), "stereo": channels.count(2)},
                "format_distribution": format_distribution
            },
            "filter_stats": filter_stats,
            "processing_info": processing_info
        }
        
        return json.dumps(report, ensure_ascii=False, indent=2)

# 节点注册
NODE_CLASS_MAPPINGS = {
    "buding_SmartAudioBatchLoader": buding_SmartAudioBatchLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SmartAudioBatchLoader": "🎵 buding_SmartAudioBatchLoader (智能音频批量加载器)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
