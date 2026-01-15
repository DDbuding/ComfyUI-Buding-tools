"""
Buding-time 基础音频切分器
最小依赖，仅使用 Python 标准库
"""
import os
import json
import math
from pathlib import Path

class buding_BasicAudioSegmenter:
    """
    基础音频切分器 - 仅使用文件信息和文本处理
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_path": ("STRING", {"default": "", "multiline": False}),
                "script_text": ("STRING", {"default": "", "multiline": True}),
                "segment_duration": ("FLOAT", {"default": 10.0, "min": 1.0, "max": 60.0, "step": 1.0}),
                "total_duration": ("FLOAT", {"default": 60.0, "min": 1.0, "max": 3600.0, "step": 1.0}),
            },
            "optional": {
                "output_dir": ("STRING", {"default": "", "multiline": False}),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("segments_info", "output_files")
    FUNCTION = "segment_audio"
    CATEGORY = "Buding-time/Audio"
    
    def segment_audio(self, audio_path, script_text, segment_duration=10.0, 
                     total_duration=60.0, output_dir=""):
        """
        基础音频切分 - 仅基于时长和文本分配
        """
        try:
            # 验证输入
            if not audio_path:
                raise ValueError("音频路径不能为空")
            
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"音频文件不存在: {audio_path}")
            
            print(f"🎵 开始处理音频: {audio_path}")
            
            # 设置输出目录
            if not output_dir:
                output_dir = Path(audio_path).parent / "segments"
            else:
                output_dir = Path(output_dir)
            
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 处理脚本文本
            script_lines = []
            if script_text.strip():
                script_lines = [line.strip() for line in script_text.strip().split('\n') if line.strip()]
            
            if not script_lines:
                # 如果没有脚本，生成默认文本
                script_lines = [f"音频片段 {i+1}" for i in range(int(total_duration / segment_duration))]
            
            # 计算分段
            num_segments = math.ceil(total_duration / segment_duration)
            segments = []
            
            for i in range(num_segments):
                start_time = i * segment_duration
                end_time = min((i + 1) * segment_duration, total_duration)
                
                # 分配文本（轮询或重复）
                if i < len(script_lines):
                    text = script_lines[i]
                else:
                    text = script_lines[i % len(script_lines)] if script_lines else f"片段 {i+1}"
                
                segments.append({
                    "segment_id": i + 1,
                    "start": round(start_time, 2),
                    "end": round(end_time, 2),
                    "duration": round(end_time - start_time, 2),
                    "text": text
                })
            
            # 生成切分信息
            result = {
                "total_segments": len(segments),
                "total_duration": round(total_duration, 2),
                "method": "basic_time_based",
                "audio_file": str(audio_path),
                "segments": segments
            }
            
            # 保存结果
            result_file = output_dir / "segmentation_result.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            # 生成输出文件信息
            segment_files = []
            for i, segment in enumerate(segments):
                segment_filename = f"segment_{i+1:04d}.txt"
                segment_path = output_dir / segment_filename
                
                with open(segment_path, 'w', encoding='utf-8') as f:
                    f.write(f"片段 {i+1}\n")
                    f.write(f"时间: {segment['start']:.2f}s - {segment['end']:.2f}s\n")
                    f.write(f"时长: {segment['duration']:.2f}s\n")
                    f.write(f"文本: {segment['text']}\n")
                
                segment_files.append({
                    "segment_id": segment["segment_id"],
                    "filename": segment_filename,
                    "path": str(segment_path),
                    "info": "文本信息文件"
                })
            
            output_info = {
                "result_file": str(result_file),
                "segment_files": segment_files,
                "note": "这是基础版本的音频切分，基于固定时长。无音频分析功能。"
            }
            
            print(f"🎉 处理完成！共生成 {len(segments)} 个片段")
            
            return json.dumps(result, ensure_ascii=False, indent=2), json.dumps(output_info, ensure_ascii=False, indent=2)
            
        except Exception as e:
            error_msg = f"❌ 音频切分失败: {str(e)}"
            print(error_msg)
            return error_msg, "{}"

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_BasicAudioSegmenter": buding_BasicAudioSegmenter
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_BasicAudioSegmenter": "🎵 Buding-time 基础音频切分器"
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
