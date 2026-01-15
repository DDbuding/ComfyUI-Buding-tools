"""
buding_SmartAudioSegmenter - 智能音频切割器
兼顾最高精度（SRT）和最大灵活性（纯文本）
"""

import os
import re
import json
import math
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# 尝试导入音频处理库
try:
    import torchaudio
    import torch
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("⚠️ torchaudio 未安装，将使用基础功能")

# 尝试导入 Whisper
try:
    import whisper
    WHISPER_AVAILABLE = True
    print("✅ openai-whisper 可用")
except ImportError:
    WHISPER_AVAILABLE = False
    print("⚠️ whisper 未安装，纯文本模式不可用")

# ComfyUI 进度条
try:
    from comfy.utils import ProgressBar
    COMFYUI_PROGRESSBAR = True
except ImportError:
    class ProgressBar:
        def __init__(self, total, *args, **kwargs):
            self.total = total
        def update(self, value=1, *args, **kwargs):
            pass
    COMFYUI_PROGRESSBAR = False

# SRT 格式识别正则
SRT_REGEX = re.compile(r'\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}')

# JSON 格式识别正则
JSON_REGEX = re.compile(r'^\s*\[\s*\{.*\}\s*\]\s*$', re.MULTILINE | re.DOTALL)

def is_srt_format(text: str) -> bool:
    """检查输入文本是否为 SRT 格式"""
    return bool(SRT_REGEX.search(text.strip()))

def is_json_format(text: str) -> bool:
    """检查输入文本是否为 JSON 格式"""
    try:
        # 先检查基本格式
        if not JSON_REGEX.match(text.strip()):
            return False
        
        # 尝试解析 JSON
        data = json.loads(text)
        if not isinstance(data, list):
            return False
        
        # 检查每个条目的必需字段
        for item in data:
            if not isinstance(item, dict):
                return False
            # 检查是否有时间字段
            if 'start' not in item or 'end' not in item:
                return False
            # 检查是否有文本字段（支持多种命名）
            if not any(key in item for key in ['字幕', 'text', 'content', 'dialogue']):
                return False
        
        return True
    except (json.JSONDecodeError, TypeError):
        return False

def parse_json_segments(text: str) -> List[Dict]:
    """解析 JSON 格式的字幕片段"""
    try:
        data = json.loads(text)
        segments = []
        
        for i, item in enumerate(data):
            # 提取文本（支持多种字段名）
            text_content = ""
            for key in ['字幕', 'text', 'content', 'dialogue']:
                if key in item:
                    text_content = str(item[key])
                    break
            
            # 提取时间信息
            start_sec = float(item['start'])
            end_sec = float(item['end'])
            duration_sec = float(item.get('duration_sec', end_sec - start_sec))
            
            # 提取 ID
            segment_id = item.get('id', f"segment_{i+1}")
            
            if start_sec < end_sec and text_content:
                segments.append({
                    "index": i + 1,
                    "id": segment_id,
                    "text": text_content,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "duration_sec": duration_sec,
                    "source": "json_timestamp",
                    "metadata": {k: v for k, v in item.items() 
                               if k not in ['start', 'end', 'duration_sec', '字幕', 'text', 'content', 'dialogue']}
                })
        
        return segments
    except Exception as e:
        raise ValueError(f"JSON 解析失败: {str(e)}")

def save_audio_with_format(waveform, sample_rate, filepath: str, format: str):
    """根据格式保存音频文件"""
    try:
        if format.lower() == "wav":
            torchaudio.save(filepath, waveform, sample_rate)
        elif format.lower() == "mp3":
            # 先保存为 WAV，然后转换为 MP3（需要 ffmpeg）
            temp_wav = filepath.replace(".mp3", "_temp.wav")
            torchaudio.save(temp_wav, waveform, sample_rate)
            
            # 使用 ffmpeg 转换为 MP3
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-i", temp_wav, 
                "-codec:a", "libmp3lame", "-qscale:a", "2", 
                filepath
            ], check=True, capture_output=True)
            
            # 删除临时文件
            if os.path.exists(temp_wav):
                os.remove(temp_wav)
                
        elif format.lower() == "flac":
            torchaudio.save(filepath, waveform, sample_rate, 
                          encoding="PCM_S16", bits_per_sample=16)
        else:
            # 默认保存为 WAV
            torchaudio.save(filepath, waveform, sample_rate)
            
    except Exception as e:
        print(f"⚠️ 无法保存为 {format} 格式，使用 WAV 格式: {str(e)}")
        # 降级为 WAV
        wav_path = filepath.replace(f".{format}", ".wav")
        torchaudio.save(wav_path, waveform, sample_rate)
        return wav_path
    
    return filepath

def get_supported_input_formats() -> List[str]:
    """获取支持的输入音频格式"""
    formats = ["wav", "mp3", "flac", "ogg", "m4a", "aac"]
    
    # 检查是否安装了额外的解码器
    try:
        import ffmpeg
        # 如果有 ffmpeg，支持更多格式
        formats.extend(["wma", "ape", "dsd"])
    except ImportError:
        pass
    
    return formats

def read_srt_file(srt_file_path: str) -> str:
    """读取 SRT 文件内容"""
    if not srt_file_path or srt_file_path.strip() == "":
        return ""
    
    try:
        # 处理相对路径
        if not os.path.isabs(srt_file_path):
            # 尝试相对于当前工作目录
            if os.path.exists(srt_file_path):
                file_path = srt_file_path
            else:
                # 尝试相对于 ComfyUI output 目录
                comfyui_output = "output"
                potential_path = os.path.join(comfyui_output, srt_file_path)
                if os.path.exists(potential_path):
                    file_path = potential_path
                else:
                    raise FileNotFoundError(f"找不到 SRT 文件: {srt_file_path}")
        else:
            file_path = srt_file_path
        
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"✅ 成功读取 SRT 文件: {file_path}")
        return content
        
    except FileNotFoundError as e:
        print(f"❌ SRT 文件不存在: {str(e)}")
        return ""
    except UnicodeDecodeError:
        # 尝试其他编码
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                content = f.read()
            print(f"✅ 成功读取 SRT 文件 (GBK编码): {file_path}")
            return content
        except Exception as e:
            print(f"❌ 读取 SRT 文件失败 (编码错误): {str(e)}")
            return ""
    except Exception as e:
        print(f"❌ 读取 SRT 文件失败: {str(e)}")
        return ""

def srt_time_to_seconds(time_str: str) -> float:
    """将 SRT 时间格式转换为秒数"""
    try:
        # 移除可能的空格和特殊字符
        time_str = time_str.strip().replace(' ', '')
        # 分割时间部分
        parts = re.split(r'[: ,]', time_str)
        if len(parts) >= 4:
            h, m, s, ms = map(int, parts[:4])
            return h * 3600 + m * 60 + s + ms / 1000.0
    except:
        pass
    return 0.0

def get_available_whisper_models() -> List[str]:
    """获取可用的 Whisper 模型列表"""
    if not WHISPER_AVAILABLE:
        return ["none"]
    
    # 使用标准 whisper 模型列表
    models = ["none", "tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]
    
    return models

class buding_SmartAudioSegmenter:
    """
    智能音频切割器 - 支持 SRT + Whisper 双重模式
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        # 动态获取可用的 Whisper 模型
        available_models = get_available_whisper_models()
        # 获取支持的输出格式
        output_formats = ["wav", "mp3", "flac"]
        
        return {
            "required": {
                "audio": ("AUDIO", {}),
                "reference_input": ("STRING", {
                    "multiline": True,
                    "default": '''1
00:00:00,000 --> 00:00:02,000
第一句话

2
00:00:02,000 --> 00:00:04,000
第二句话''',
                    "tooltip": "支持多种格式：\n• SRT 字幕格式\n• JSON 时间轴格式\n• 纯文本脚本\n• 可连接 TextFileLoader 节点输出\n\n支持自动格式识别"
                }),
                "input_format": (["auto", "srt", "json", "text"], {
                    "default": "auto",
                    "tooltip": "auto: 自动识别格式\nsrt: 强制按 SRT 解析\njson: 强制按 JSON 解析\ntext: 强制按纯文本处理"
                }),
                "whisper_model": (available_models, {
                    "default": available_models[0] if available_models else "none",
                    "tooltip": "Whisper 模型选择\n纯文本模式时使用"
                }),
                "language": (["auto", "zh", "en", "ja", "ko"], {
                    "default": "auto",
                    "tooltip": "音频语言识别\nauto: 自动检测"
                }),
                "output_dir": ("STRING", {
                    "default": "output/audio_segments",
                    "tooltip": "切割音频的保存目录"
                }),
            },
            "optional": {
                "format": (output_formats, {
                    "default": "wav",
                    "tooltip": "输出音频格式\n• wav: 无损兼容性最佳\n• mp3: 压缩文件小\n• flac: 无损高质量"
                }),
                "overwrite": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否覆盖已存在的文件\n• False: 跳过已存在文件\n• True: 强制重新生成所有文件"
                }),
                "time_tolerance": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.1,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "时间容忍度（秒）\n用于 Whisper 验证"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("SEGMENTS_JSON", "OUTPUT_DIR_PATH", "PROCESS_REPORT")
    FUNCTION = "segment_audio"
    CATEGORY = "Buding-time/Audio"
    DESCRIPTION = "智能音频切割器 - 支持 SRT 时间戳和 Whisper 强制对齐"
    
    def segment_audio(self, audio, reference_input: str, input_format: str, 
                      whisper_model: str, language: str, output_dir: str,
                      format: str = "wav", overwrite: bool = False, 
                      time_tolerance: float = 0.5) -> Tuple[str, str, str]:
        
        pbar = ProgressBar(100)
        
        try:
            # Step 1: 格式识别
            if COMFYUI_PROGRESSBAR:
                print("🔍 正在分析输入格式...")
            pbar.update(5)

            # 智能格式检测
            if input_format == "auto":
                if is_srt_format(reference_input):
                    format_detected = "srt"
                elif is_json_format(reference_input):
                    format_detected = "json"
                else:
                    format_detected = "text"
            else:
                format_detected = input_format
            
            if COMFYUI_PROGRESSBAR:
                print(f"🔍 检测到 {format_detected.upper()} 格式...")
            pbar.update(10)
            
            # 根据格式处理
            if format_detected == "srt":
                segments_data = self._process_srt_mode(reference_input, audio, pbar)
            elif format_detected == "json":
                segments_data = self._process_json_mode(reference_input, audio, pbar)
            else:  # text
                segments_data = self._process_text_mode(reference_input, audio, whisper_model, language, pbar)
            
            # Step 2: 音频切割
            if COMFYUI_PROGRESSBAR:
                print("🔍 开始音频切割...")
            pbar.update(60)
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # 检查覆盖选项
            if not overwrite:
                # 检查已存在的文件
                existing_files = []
                for segment in segments_data:
                    filename = f"segment_{segment['index']:03d}.{format}"
                    filepath = output_path / filename
                    if filepath.exists():
                        existing_files.append(filename)
                        segment["skipped"] = True
                        segment["audio_path"] = str(filepath)
                        segment["audio_filename"] = filename
                
                if existing_files:
                    print(f"⚠️ 发现 {len(existing_files)} 个已存在文件，跳过处理")
                    print(f"   文件: {', '.join(existing_files[:5])}{'...' if len(existing_files) > 5 else ''}")
            
            # 只处理不存在的文件
            segments_to_process = [seg for seg in segments_data if not seg.get("skipped", False)]
            
            if segments_to_process:
                # 切割音频
                segments_data = self._cut_audio_segments(audio, segments_data, output_path, format, pbar)
            else:
                print("✅ 所有文件已存在，跳过音频切割")
                pbar.update(90)
            
            # Step 3: 生成报告
            if COMFYUI_PROGRESSBAR:
                print("🔍 生成处理报告...")
            pbar.update(90)
            segments_json = json.dumps(segments_data, ensure_ascii=False, indent=2)
            process_report = self._generate_report(segments_data, format_detected, whisper_model)
            
            pbar.update(100)
            if COMFYUI_PROGRESSBAR:
                print("🎉 处理完成！")
            
            return (segments_json, str(output_path), process_report)
            
        except Exception as e:
            error_msg = f"❌ 音频切割失败: {str(e)}"
            print(error_msg)
            return (json.dumps([], ensure_ascii=False), "", error_msg)
    
    def _process_json_mode(self, json_text: str, audio, pbar: ProgressBar) -> List[Dict]:
        """JSON 模式处理 - 直接使用时间戳"""
        if COMFYUI_PROGRESSBAR:
            print("🔍 解析 JSON 时间轴...")
        pbar.update(15)
        
        try:
            segments = parse_json_segments(json_text)
            
            if COMFYUI_PROGRESSBAR:
                print(f"🔍 JSON 解析完成，共 {len(segments)} 个片段")
            pbar.update(25)
            return segments
            
        except Exception as e:
            raise ValueError(f"JSON 格式解析失败: {str(e)}")
    
    def _process_srt_mode(self, srt_text: str, audio, pbar: ProgressBar) -> List[Dict]:
        """SRT 模式处理 - 直接使用时间戳"""
        if COMFYUI_PROGRESSBAR:
            print("🔍 解析 SRT 时间轴...")
        pbar.update(15)
        
        segments = []
        blocks = re.split(r'\n\s*\n', srt_text.strip())
        
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            
            # 解析时间轴
            time_line = lines[1]
            if " --> " not in time_line:
                continue
            
            start_str, end_str = time_line.split(" --> ")
            start_sec = srt_time_to_seconds(start_str.strip())
            end_sec = srt_time_to_seconds(end_str.strip())
            
            # 提取文本
            text = "\n".join(lines[2:]).strip()
            
            if start_sec < end_sec and text:
                segments.append({
                    "index": len(segments) + 1,
                    "text": text,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "duration_sec": end_sec - start_sec,
                    "source": "srt_timestamp"
                })
        
        if COMFYUI_PROGRESSBAR:
            print(f"🔍 SRT 解析完成，共 {len(segments)} 个片段")
        pbar.update(25)
        return segments
    
    def _process_text_mode(self, text: str, audio, whisper_model: str, language: str, pbar: ProgressBar) -> List[Dict]:
        """纯文本模式 - 使用 Whisper 强制对齐"""
        if not WHISPER_AVAILABLE:
            raise ImportError("Whisper 未安装，无法使用纯文本模式")
        
        if COMFYUI_PROGRESSBAR:
            print("🔍 加载 Whisper 模型...")
        pbar.update(15)
        
        try:
            # 使用标准 whisper，参考 comfyui-edgetts 的实现
            model = whisper.load_model(whisper_model)
            
            if COMFYUI_PROGRESSBAR:
                print("🔍 开始语音识别...")
            pbar.update(20)
            
            # 获取音频数据并保存临时文件
            if AUDIO_AVAILABLE:
                waveform = audio["waveform"]
                sample_rate = audio["sample_rate"]
                
                # 转换为单声道
                if waveform.dim() == 3:
                    waveform = waveform.squeeze(0)
                if waveform.shape[0] > 1:
                    waveform = waveform.mean(dim=0, keepdim=True)
                
                # 保存临时文件
                temp_file = f"temp_whisper_input_{os.getpid()}.wav"
                torchaudio.save(temp_file, waveform, sample_rate)
                
                # 标准 whisper 识别
                result = model.transcribe(
                    temp_file, 
                    language=None if language == "auto" else language,
                    word_timestamps=True,
                    verbose=False
                )
                
                result_segments = result["segments"]
                
                # 清理临时文件
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            else:
                raise ImportError("torchaudio 未安装，无法处理音频")
            
            if COMFYUI_PROGRESSBAR:
                print("🔍 Whisper 识别完成，开始文本对齐...")
            pbar.update(40)
            
            # 文本对齐逻辑
            ref_texts = [line.strip() for line in text.split('\n') if line.strip()]
            segments = []
            
            current_word_index = 0
            for i, ref_text in enumerate(ref_texts):
                if current_word_index >= len(result_segments):
                    break
                
                # 找到最匹配的 Whisper 片段
                best_segment = result_segments[current_word_index]
                
                segments.append({
                    "index": i + 1,
                    "text": ref_text,
                    "start_sec": best_segment["start"],
                    "end_sec": best_segment["end"],
                    "duration_sec": best_segment["end"] - best_segment["start"],
                    "source": "whisper_alignment",
                    "confidence": best_segment.get("avg_logprob", 0)
                })
                
                current_word_index += 1
            
            if COMFYUI_PROGRESSBAR:
                print(f"🔍 Whisper 对齐完成，共 {len(segments)} 个片段")
            pbar.update(25)
            return segments
            
        except Exception as e:
            raise Exception(f"Whisper 处理失败: {str(e)}")
    
    def _cut_audio_segments(self, audio, segments_data: List[Dict], output_path: Path, 
                           format: str, pbar: ProgressBar) -> List[Dict]:
        """切割音频片段"""
        if not AUDIO_AVAILABLE:
            print("⚠️ 音频处理库不可用，跳过文件保存")
            return segments_data
        
        waveform = audio["waveform"]
        sample_rate = audio["sample_rate"]
        total_samples = waveform.shape[-1]
        
        progress_per_segment = 30 / len(segments_data) if segments_data else 0
        
        for i, segment in enumerate(segments_data):
            start_sample = int(segment["start_sec"] * sample_rate)
            end_sample = int(segment["end_sec"] * sample_rate)
            
            # 边界检查
            start_sample = max(0, min(start_sample, total_samples))
            end_sample = max(start_sample, min(end_sample, total_samples))
            
            # 提取片段
            segment_waveform = waveform[..., start_sample:end_sample]
            
            # 保存文件（使用新的格式保存函数）
            filename = f"segment_{segment['index']:03d}.{format}"
            filepath = output_path / filename
            
            try:
                saved_path = save_audio_with_format(
                    segment_waveform.squeeze(0), 
                    sample_rate, 
                    str(filepath), 
                    format
                )
                # 更新实际保存的路径（可能因为格式转换而改变）
                segment["audio_path"] = saved_path
                segment["audio_filename"] = os.path.basename(saved_path)
            except Exception as e:
                print(f"⚠️ 保存片段 {i+1} 失败: {str(e)}")
                # 保存为备用 WAV
                backup_filename = f"segment_{segment['index']:03d}_backup.wav"
                backup_path = output_path / backup_filename
                torchaudio.save(str(backup_path), segment_waveform.squeeze(0), sample_rate)
                segment["audio_path"] = str(backup_path)
                segment["audio_filename"] = backup_filename
            
            if COMFYUI_PROGRESSBAR:
                print(f"🔍 切割片段 {i+1}/{len(segments_data)} 完成")
            pbar.update(60 + i * progress_per_segment)
        
        return segments_data
    
    def _generate_report(self, segments_data: List[Dict], format_type: str, whisper_model: str) -> str:
        """生成处理报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("🎵 Buding Smart Audio Segmenter - 处理报告")
        lines.append("=" * 80)
        
        # 基本信息
        lines.append(f"📋 输入格式: {format_type.upper()}")
        if format_type == "text":
            lines.append(f"🤖 Whisper 模型: {whisper_model}")
        lines.append(f"📊 处理片段数: {len(segments_data)}")
        lines.append("")
        
        # 时间轴统计
        if segments_data:
            total_duration = sum(seg["duration_sec"] for seg in segments_data)
            lines.append("⏱️ 时间轴统计:")
            lines.append(f"   总时长: {total_duration:.2f} 秒")
            lines.append(f"   平均片段时长: {total_duration/len(segments_data):.2f} 秒")
            lines.append("")
            
            # 片段详情
            lines.append("📝 片段详情:")
            lines.append("-" * 80)
            for seg in segments_data:
                start_time = self._seconds_to_time_str(seg["start_sec"])
                end_time = self._seconds_to_time_str(seg["end_sec"])
                lines.append(f"片段 {seg['index']:3d}: {start_time} --> {end_time} ({seg['duration_sec']:.2f}s)")
                lines.append(f"        {seg['text'][:50]}{'...' if len(seg['text']) > 50 else ''}")
                if seg.get("id"):
                    lines.append(f"        ID: {seg['id']}")
                if seg.get("metadata"):
                    lines.append(f"        元数据: {seg['metadata']}")
                lines.append("")
        
        # ASCII 时间轴
        lines.append("📊 时间轴可视化:")
        lines.append("-" * 80)
        timeline = self._generate_timeline(segments_data)
        lines.append(timeline)
        
        # 格式说明
        lines.append("")
        lines.append("📖 格式说明:")
        if format_type == "srt":
            lines.append("   • SRT 字幕格式 - 精确时间戳切割")
        elif format_type == "json":
            lines.append("   • JSON 时间轴格式 - 灵活元数据支持")
        elif format_type == "text":
            lines.append("   • 纯文本 + Whisper - 自动语音识别对齐")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def _generate_timeline(self, segments_data: List[Dict]) -> str:
        """生成 ASCII 时间轴可视化"""
        if not segments_data:
            return "无片段数据"
        
        # 计算总时长
        total_duration = max(seg["end_sec"] for seg in segments_data)
        timeline_width = 60  # ASCII 时间轴宽度
        
        lines = []
        lines.append("时间轴 (秒):")
        lines.append("┌" + "─" * timeline_width + "┐")
        
        # 时间刻度
        for i in range(0, int(total_duration) + 1, max(1, int(total_duration) // 10)):
            pos = int(i / total_duration * timeline_width) if total_duration > 0 else 0
            lines.append("│" + " " * pos + str(i) + " " * (timeline_width - pos - len(str(i))) + "│")
        
        lines.append("└" + "─" * timeline_width + "┘")
        lines.append("")
        
        # 片段标记
        lines.append("片段分布:")
        for i, seg in enumerate(segments_data):
            start_pos = int(seg["start_sec"] / total_duration * timeline_width) if total_duration > 0 else 0
            end_pos = int(seg["end_sec"] / total_duration * timeline_width) if total_duration > 0 else 0
            
            timeline_line = "│" + " " * start_pos
            timeline_line += "█" * (end_pos - start_pos)
            timeline_line += " " * (timeline_width - end_pos)
            timeline_line += "│"
            
            lines.append(f"片段{i+1:2d}: {timeline_line}")
            lines.append(f"        {seg['start_sec']:.1f}s - {seg['end_sec']:.1f}s ({seg['duration_sec']:.1f}s)")
        
        return "\n".join(lines)
    
    def _seconds_to_time_str(self, seconds: float) -> str:
        """将秒数转换为时间字符串"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

# 节点映射
NODE_CLASS_MAPPINGS = {
    "buding_SmartAudioSegmenter": buding_SmartAudioSegmenter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SmartAudioSegmenter": "🎵 Buding - 智能音频切割器（SRT+Whisper）",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
