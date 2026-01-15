"""
FrameDurationLimiter - 帧数控制中心
将 SRT 时间轴转换为帧数，并应用用户设定的限制和切片
"""

import os
import json
import re
from datetime import timedelta

def parse_srt_time(time_str):
    """将 SRT 时间格式转换为秒数"""
    # SRT 格式: 00:00:01,470
    try:
        time_part, ms_part = time_str.split(',')
        hours, minutes, seconds = map(int, time_part.split(':'))
        milliseconds = int(ms_part)
        total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
        return total_seconds
    except:
        return 0.0

def parse_srt_file(srt_path):
    """解析 SRT 文件，返回字幕片段列表"""
    segments = []
    
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # 如果 UTF-8 失败，尝试其他编码
        with open(srt_path, 'r', encoding='gbk') as f:
            content = f.read()
    
    # 分割字幕块
    blocks = re.split(r'\n\s*\n', content.strip())
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # 提取时间信息
            time_line = lines[1]
            if '-->' in time_line:
                start_time, end_time = time_line.split(' --> ')
                start_sec = parse_srt_time(start_time.strip())
                end_sec = parse_srt_time(end_time.strip())
                
                # 提取文本内容
                text = '\n'.join(lines[2:])
                text = re.sub(r'<[^>]+>', '', text)  # 移除 HTML 标签
                text = text.strip()
                
                if text and end_sec > start_sec:
                    segments.append({
                        'start_sec': start_sec,
                        'end_sec': end_sec,
                        'duration_sec': end_sec - start_sec,
                        'text': text
                    })
    
    return segments

def parse_json_data(json_input):
    """解析 JSON 数据，返回字幕片段列表"""
    try:
        if isinstance(json_input, str):
            if os.path.exists(json_input):
                # 如果是文件路径，读取文件
                with open(json_input, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                # 如果是 JSON 字符串，直接解析
                data = json.loads(json_input)
        else:
            data = json_input
        
        segments = []
        
        for item in data:
            if isinstance(item, dict):
                # 获取时间信息
                start = float(item.get('start', item.get('start_sec', 0)))
                end = float(item.get('end', item.get('end_sec', 0)))
                
                # 获取文本
                text = str(item.get('text', item.get('字幕', ''))).strip()
                
                # 过滤停顿标记
                if ('pause' in str(item.get('id', '')).lower() or 
                    '[停顿' in text.lower() or 
                    not text):
                    continue
                
                if text and end > start:
                    segments.append({
                        'start_sec': start,
                        'end_sec': end,
                        'duration_sec': end - start,
                        'text': text
                    })
        
        return segments
        
    except Exception as e:
        print(f"解析 JSON 数据时出错: {e}")
        return []

class buding_FrameDurationLimiter:
    """
    帧数限制器 - 将时间轴转换为帧数并应用限制
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "srt_or_json_input": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "description": "输入 SRT 文件路径或 JSON 数据\n• SRT: 文件绝对路径\n• JSON: JSON 字符串或文件路径"
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
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("FRAME_DATA_JSON",)
    FUNCTION = "process_frames"
    CATEGORY = "Buding-time"
    
    def process_frames(self, srt_or_json_input, fps_value, min_frames, max_frames, extra_frames, start_index, count):
        """
        处理时间轴数据并转换为帧数
        
        Args:
            srt_or_json_input: SRT 文件路径或 JSON 数据
            fps_value: 帧率
            min_frames: 最小帧数
            max_frames: 最大帧数
            extra_frames: 额外添加的帧数
            start_index: 起始索引
            count: 处理数量 (-1 表示全部)
        
        Returns:
            FRAME_DATA_JSON: 包含帧数信息的 JSON 字符串
        """
        print("\n=== 开始处理帧数限制 ===")
        print(f"输入数据: {srt_or_json_input[:200]}...")
        
        try:
            # 判断输入类型
            if not srt_or_json_input or not srt_or_json_input.strip():
                print("警告: 输入数据为空")
                return (json.dumps([], ensure_ascii=False),)
            
            input_data = srt_or_json_input.strip()
            segments = []
            
            # 检查是否是文件路径
            if os.path.exists(input_data) and input_data.endswith('.srt'):
                print(f"检测到 SRT 文件: {input_data}")
                segments = parse_srt_file(input_data)
            else:
                # 尝试解析为 JSON
                print("尝试解析为 JSON 数据...")
                try:
                    data = json.loads(input_data)
                    if isinstance(data, list):
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                                
                            # 跳过停顿片段
                            if str(item.get('id', '')).lower() == 'pause' or '[停顿' in str(item.get('字幕', '')).lower():
                                continue
                                
                            start = float(item.get('start', 0))
                            end = float(item.get('end', 0))
                            text = str(item.get('字幕', item.get('text', ''))).strip()
                            
                            if text and end > start:
                                segments.append({
                                    'start_sec': start,
                                    'end_sec': end,
                                    'duration_sec': end - start,
                                    'text': text,
                                    'id': str(item.get('id', f's{len(segments) + 1}'))
                                })
                    
                    print(f"成功解析 {len(segments)} 个字幕片段")
                    
                except json.JSONDecodeError as e:
                    print(f"JSON 解析错误: {e}")
                    return (json.dumps([], ensure_ascii=False),)
            
            if not segments:
                print("警告: 没有找到有效的字幕片段")
                return (json.dumps([], ensure_ascii=False),)
            
            # 转换为帧数
            frame_data = []
            print(f"\n=== 开始处理 {len(segments)} 个字幕片段 ===")
            print(f"帧率: {fps_value} FPS, 最小帧数: {min_frames}, 最大帧数: {max_frames}, 额外帧数: {extra_frames}")
            
            for i, segment in enumerate(segments):
                try:
                    # 获取片段信息
                    start_sec = segment.get('start_sec', 0)
                    duration_sec = segment.get('duration_sec', 0)
                    text = segment.get('text', '').strip()
                    
                    if not text:
                        print(f"\n片段 {i+1}: 跳过空文本片段")
                        continue
                    
                    # 计算原始帧数
                    duration_frames_raw = round(duration_sec * fps_value)
                    
                    # 记录原始数据
                    print(f"\n片段 {i+1} (ID: {segment.get('id', 'N/A')}):")
                    print(f"  文本: {text[:50]}{'...' if len(text) > 50 else ''}")
                    print(f"  开始时间: {start_sec:.2f} 秒")
                    print(f"  结束时间: {segment.get('end_sec', 0):.2f} 秒")
                    print(f"  原始时长: {duration_sec:.2f} 秒")
                    print(f"  原始帧数: {duration_frames_raw} 帧")
                    
                    # 应用帧数限制
                    final_duration = max(min_frames, min(max_frames, duration_frames_raw)) + extra_frames
                    
                    # 确保最终帧数不会超过最大限制
                    if final_duration > max_frames and max_frames > 0:
                        print(f"  警告: 总帧数 {final_duration} 超过最大限制 {max_frames}，已限制为 {max_frames}")
                        final_duration = max_frames
                    
                    # 记录应用限制后的数据
                    if final_duration != duration_frames_raw:
                        print(f"  ! 应用限制: {duration_frames_raw} -> {final_duration} 帧")
                        if final_duration == min_frames:
                            print(f"    原因: 低于最小帧数限制 ({min_frames} 帧)")
                        elif final_duration == max_frames:
                            print(f"    原因: 超过最大帧数限制 ({max_frames} 帧)")
                    else:
                        print(f"  最终帧数: {final_duration} 帧 (未触发限制)")
                    
                    # 计算调整后的时间
                    adjusted_duration = final_duration / fps_value
                    adjusted_end = start_sec + adjusted_duration
                    
                    # 构建输出项
                    frame_data.append({
                        'index': i,
                        'start_sec': start_sec,
                        'end_sec': adjusted_end,
                        'duration_sec': adjusted_duration,
                        'duration_frames': final_duration,
                        'text': text,
                        'original_duration': duration_sec,
                        'original_frames': duration_frames_raw
                    })
                    
                except Exception as e:
                    print(f"处理片段 {i+1} 时出错: {str(e)}")
                    continue
            
            if not frame_data:
                print("警告: 没有生成有效的帧数据")
                return (json.dumps([], ensure_ascii=False),)
            
            # 应用切片
            total_segments = len(frame_data)
            if start_index >= total_segments:
                print(f"\n警告: 起始索引 {start_index} 超出范围 (总共 {total_segments} 个片段)")
                return (json.dumps([], ensure_ascii=False),)
            
            end_index = total_segments if count == -1 else min(start_index + count, total_segments)
            sliced_data = frame_data[start_index:end_index]
            
            # 输出汇总信息
            print("\n" + "="*50)
            print("处理完成:")
            print(f"  原始片段数: {total_segments}")
            print(f"  处理片段范围: {start_index+1}-{end_index} (共 {len(sliced_data)} 个片段)")
            print(f"  总帧数: {sum(item['duration_frames'] for item in sliced_data)} 帧")
            print("="*50)
            
            # 输出前几个片段的详细信息
            if sliced_data:
                print("\n前 3 个片段的详细信息:")
                for i, item in enumerate(sliced_data[:3]):
                    print(f"\n片段 {i+1} (索引: {item['index']}):")
                    print(f"  开始时间: {item['start_sec']:.2f} 秒")
                    print(f"  结束时间: {item['end_sec']:.2f} 秒")
                    print(f"  持续时间: {item['duration_sec']:.2f} 秒")
                    print(f"  帧数: {item['duration_frames']} 帧")
                    print(f"  原始帧数: {item.get('original_frames', 'N/A')} 帧")
                    print(f"  文本: {item['text'][:50]}{'...' if len(item['text']) > 50 else ''}")
                
                if len(sliced_data) > 3:
                    print(f"\n... 以及另外 {len(sliced_data)-3} 个片段")
            
            # 返回格式化的 JSON 字符串
            return (json.dumps(sliced_data, ensure_ascii=False, indent=2),)
            
        except Exception as e:
            import traceback
            error_msg = f"处理帧数时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            return (json.dumps([], ensure_ascii=False),)

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_FrameDurationLimiter": buding_FrameDurationLimiter,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_FrameDurationLimiter": "⏱️ 帧长限制器",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
