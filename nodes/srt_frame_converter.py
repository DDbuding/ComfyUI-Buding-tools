"""SRT帧数转换器 - 集成SRT解析、帧数限制和循环输出的综合节点"""
import os
import re
import json

class buding_SRTFrameConverter:
    """SRT帧数转换器"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "srt_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "description": "SRT字幕文本\n• 直接输入SRT格式的字幕内容"
                }),
                "srt_file_path": ("STRING", {
                    "default": "",
                    "description": "SRT文件路径\n• SRT字幕文件的绝对路径"
                }),
                "fps_value": ("INT", {
                    "default": 24,
                    "min": 1,
                    "max": 120,
                    "description": "视频帧率 (FPS)\n• 常用值: 24, 30, 60"
                }),
                "min_frames": ("INT", {
                    "default": 24,
                    "min": 1,
                    "max": 300,
                    "description": "最小帧数限制\n• 每个片段至少显示的帧数"
                }),
                "max_frames": ("INT", {
                    "default": 120,
                    "min": 1,
                    "max": 600,
                    "description": "最大帧数限制\n• 每个片段最多显示的帧数"
                }),
                "extra_frames": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 1000,
                    "description": "额外添加的帧数"
                }),
                "start_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "description": "起始索引\n• 从第几个片段开始处理 (0=第一个)"
                }),
                "count": ("INT", {
                    "default": -1,
                    "min": -1,
                    "description": "处理数量\n• -1=处理全部, 0=不处理, 1=只处理1个"
                }),
            },
        }

    RETURN_TYPES = ("INT", "STRING", "INT", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("持续帧数", "字幕文本", "片段索引", "开始时间", "结束时间", "处理日志")
    FUNCTION = "convert_srt_to_frames"
    CATEGORY = "Buding-time"
    OUTPUT_IS_LIST = (True, True, True, True, True, False)

    def convert_srt_to_frames(self, srt_text, srt_file_path, fps_value, min_frames, max_frames, extra_frames, start_index, count):
        try:
            # 获取SRT内容
            srt_content = self._get_srt_content(srt_text, srt_file_path)
            if not srt_content:
                return ([], [], [], [], [], "错误: 未找到有效的SRT内容")

            # 解析SRT
            segments = self._parse_srt(srt_content)
            if not segments:
                return ([], [], [], [], [], "错误: 无法解析SRT内容")

            # 应用帧数限制
            frame_data = self._apply_limits(segments, fps_value, min_frames, max_frames, extra_frames)

            # 切片处理
            sliced_data = self._slice_data(frame_data, start_index, count)

            # 转换为输出格式
            result = self._to_output_format(sliced_data)

            # 生成日志
            log = self._generate_log(sliced_data, fps_value, min_frames, max_frames)

            return result + (log,)

        except Exception as e:
            return ([], [], [], [], [], f"处理错误: {str(e)}")

    def _get_srt_content(self, srt_text, srt_file_path):
        """获取SRT内容"""
        if srt_file_path and os.path.exists(srt_file_path):
            with open(srt_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return srt_text if srt_text else None

    def _parse_srt(self, content):
        """解析SRT内容"""
        segments = []
        blocks = content.strip().split('\n\n')
        for block in blocks:
            lines = block.split('\n')
            if len(lines) >= 3:
                try:
                    time_line = lines[1]
                    if '-->' in time_line:
                        start, end = time_line.split('-->')
                        text = '\n'.join(lines[2:]).strip()
                        if text:
                            segments.append({
                                'start_sec': self._time_to_seconds(start.strip()),
                                'end_sec': self._time_to_seconds(end.strip()),
                                'text': text
                            })
                except:
                    continue
        return segments

    def _apply_limits(self, segments, fps, min_f, max_f, extra):
        """应用帧数限制"""
        result = []
        for i, seg in enumerate(segments):
            duration = seg['end_sec'] - seg['start_sec']
            original_frames = round(duration * fps)
            final_frames = max(min_f, min(max_f, original_frames)) + extra
            final_frames = min(final_frames, max_f) if max_f > 0 else final_frames
            adjusted_duration = final_frames / fps
            result.append({
                'index': i,
                'start_sec': seg['start_sec'],
                'end_sec': seg['start_sec'] + adjusted_duration,
                'duration_frames': final_frames,
                'text': seg['text']
            })
        return result

    def _slice_data(self, data, start, count):
        """切片处理"""
        if start >= len(data):
            return []
        end = len(data) if count == -1 else min(start + count, len(data))
        return data[start:end]

    def _to_output_format(self, data):
        """转换为输出格式"""
        frames = [item['duration_frames'] for item in data]
        texts = [item['text'] for item in data]
        indices = [item['index'] for item in data]
        starts = [item['start_sec'] for item in data]
        ends = [item['end_sec'] for item in data]
        return (frames, texts, indices, starts, ends)

    def _generate_log(self, data, fps, min_f, max_f):
        """生成处理日志"""
        lines = []
        lines.append("📋 SRT处理报告")
        lines.append("=" * 50)
        lines.append(f"🎞️ 视频帧率: {fps}")
        lines.append(f"⚙️ 帧数限制: Min={min_f}, Max={max_f}")
        lines.append(f"📏 总片段数: {len(data)} 个")
        lines.append("=" * 50)
        lines.append("")
        lines.append("[ID]  [时间段]   [帧数]   [文本内容]")
        lines.append("-" * 50)
        for item in data:
            idx = f"{item['index']:03d}"
            time_range = f"{item['start_sec']:.2f}s-{item['end_sec']:.2f}s"
            frames = f"{item['duration_frames']:3d}f"
            text = item['text'][:20] + ("..." if len(item['text']) > 20 else "")
            lines.append(f"{idx} | {time_range} | {frames} | {text}")
        lines.append("")
        lines.append("=" * 50)
        lines.append("✅ 处理完成！")
        lines.append("◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ◆ ◇ ")
        return "\n".join(lines)

    @staticmethod
    def _time_to_seconds(time_str):
        """时间转换"""
        if ',' in time_str:
            time_part, ms = time_str.split(',')
        else:
            time_part, ms = time_str, '000'
        h, m, s = map(int, time_part.split(':'))
        ms = ms.ljust(3, '0')[:3]
        return h * 3600 + m * 60 + s + int(ms) / 1000.0

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SRTFrameConverter": buding_SRTFrameConverter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SRTFrameConverter": "🎬 SRT帧数转换器",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]