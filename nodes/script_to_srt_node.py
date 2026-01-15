import os
import re
import json
from datetime import timedelta
import folder_paths

# --- 辅助函数：时间转换 ---

def ms_to_srt_time(ms):
    """将毫秒转换为 SRT 标准时间格式 HH:MM:SS,ms"""
    ms = int(ms)
    if ms < 0: 
        ms = 0
        
    total_seconds = ms // 1000
    ms_part = ms % 1000

    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms_part:03}"

def seconds_to_srt_time(seconds):
    """将秒数（浮点数）转换为 SRT 标准时间格式 HH:MM:SS,ms"""
    return ms_to_srt_time(seconds * 1000)

# --- 核心解析器：统一输出结构 [{ "start_sec": X, "end_sec": Y, "text": "..." }] ---

def parse_text_mode(script_text, default_chars_per_second):
    """解析原始文本脚本并计算时间轴。"""
    lines = script_text.strip().split('\n')
    ms_per_char = 1000.0 / default_chars_per_second if default_chars_per_second > 0 else 100.0
    current_time_ms = 0.0
    parsed_data = []

    for line in lines:
        line = line.strip()
        if not line: 
            continue

        # 处理停顿标记：例如 -0.5s-
        delay_match = re.match(r'^-(\d+(\.\d+)?)s-$', line)
        if delay_match:
            try:
                delay_s = float(delay_match.group(1))
                current_time_ms += delay_s * 1000.0
            except:
                pass
            continue

        # 处理对话标记：例如 [s1] <内容>
        dialog_match = re.match(r'\[s\d+\]\s*(.+)', line)
        if dialog_match:
            content = dialog_match.group(1).strip()
            if not content: 
                continue
                
            duration_ms = len(content) * ms_per_char
            
            parsed_data.append({
                "start_sec": current_time_ms / 1000.0,
                "end_sec": (current_time_ms + duration_ms) / 1000.0,
                "text": content
            })
            current_time_ms += duration_ms
            
    return parsed_data

def parse_json_mode(json_timeline_input):
    """
    解析 JSON 结构化时间轴，自动过滤掉所有停顿标记。
    
    支持的停顿标记格式：
    1. id 字段包含 'pause'（不区分大小写）
    2. 字幕字段包含 '[停顿' 或 'pause'（不区分大小写）
    3. 文本内容为空的条目
    """
    try:
        # 确保输入是字符串
        if isinstance(json_timeline_input, str):
            data = json.loads(json_timeline_input)
        else:
            data = json_timeline_input

        if not isinstance(data, list):
            # 如果是单个对象，转换为列表
            data = [data]

        parsed_data = []
        skipped_count = 0
        
        for idx, item in enumerate(data, 1):
            if not isinstance(item, dict):
                print(f"警告：跳过第 {idx} 个条目，因为不是有效的字典格式")
                continue
                
            # 获取字幕文本（支持多种可能的字段名）
            text = str(item.get("text", item.get("字幕", item.get("subtitle", "")))).strip()
            
            # 检查是否为停顿标记
            item_id = str(item.get("id", "")).lower()
            is_pause = (
                "pause" in item_id or 
                any(marker in text.lower() for marker in ["[停顿", "pause"]) or
                not text  # 空文本也跳过
            )
            
            if is_pause:
                skipped_count += 1
                print(f"已跳过停顿标记：{item_id} - {text}" if text else "已跳过空文本条目")
                continue
                
            # 处理时间戳
            try:
                start = float(item.get("start", item.get("start_sec", 0)))
                end = item.get("end") or item.get("end_sec")
                
                # 如果没有结束时间，计算一个默认值
                if end is None:
                    duration = item.get("duration") or len(text) * 0.1  # 默认每秒10个字符
                    end = start + duration
                else:
                    end = float(end)
                
                # 确保结束时间大于开始时间
                if end <= start:
                    end = start + 1.0  # 默认显示1秒
                    print(f"警告：第 {idx} 条目的结束时间小于等于开始时间，已自动调整")
                
                parsed_data.append({
                    "start_sec": start,
                    "end_sec": end,
                    "text": text
                })
                
            except (ValueError, TypeError) as e:
                print(f"警告：跳过第 {idx} 个条目，时间戳格式错误 - {e}")
                continue
        
        print(f"处理完成：共处理 {len(data)} 个条目，跳过 {skipped_count} 个停顿/无效条目，保留 {len(parsed_data)} 个有效字幕")
        return parsed_data
        
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误：{e}")
        return []
    except Exception as e:
        print(f"处理 JSON 时间轴时发生意外错误：{str(e)}")
        import traceback
        traceback.print_exc()
        return []
            
    return parsed_data


def clean_dialog_text_line(text: str) -> str:
    """清理台词前后多余符号，仅去除行首行尾的引号/冒号等，不改中间内容。"""
    if not isinstance(text, str):
        text = str(text)
    txt = text.strip()
    # 去掉行首可能的冒号/引号/书名号/括号等
    txt = re.sub(r'^[\s:：、，;；“"『【（\(《]+', '', txt)
    # 去掉行尾可能的引号/书名号/括号等
    txt = re.sub(r'[\s:：、，;；”"』】）》]+$', '', txt)
    return txt

# --- 辅助函数：时间转换 ---

def ms_to_srt_time(ms):
    """
    将毫秒转换为 SRT 标准时间格式 HH:MM:SS,ms
    """
    # 确保输入是整数
    ms = int(ms)
    
    # 确保时间为非负值
    if ms < 0:
        ms = 0
        
    # 计算总秒数和毫秒部分
    total_seconds = ms // 1000
    ms_part = ms % 1000

    # 计算时分秒
    seconds = total_seconds % 60
    minutes = (total_seconds // 60) % 60
    hours = total_seconds // 3600
    
    # 格式化为 HH:MM:SS,ms
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms_part:03}"

# --- 集成节点类定义：ScriptToSRTWriter ---

class UniversalSRTWriter:
    """
    通用 SRT 写入器：支持原始文本脚本（自动计算时间）或 JSON 时间轴数据。
    """
    
    def __init__(self):
        # 默认输出目录：ComfyUI 配置的 output 目录（避免误写到 custom_nodes/output）
        self.output_dir = os.path.join(folder_paths.get_output_directory(), "subtitles")
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        print(f"SRT 文件将保存到: {self.output_dir}")

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                # 输入模式选择
                "input_mode": (["Text Mode", "JSON Mode"], {
                    "default": "Text Mode",
                    "tooltip": (
                        "输入模式：\n"
                        "• Text Mode：按行脚本格式，支持角色标记/停顿/语速估算\n"
                        "• JSON Mode：结构化时间轴，字段为 start/end/text"
                    )
                }),
                # 统一的输入字段，根据模式解释内容
                "input_text": ("STRING", {
                    "multiline": True, 
                    "default": "[s1] 示例文本。\n[s2] 第二句话。\n-0.5s-\n[s1] 这是第三句话。",
                    "tooltip": (
                        "输入内容：\n"
                        "• Text Mode 示例：\n"
                        "  [s1] 第一句话。\n"
                        "  [s2] 第二句话。\n"
                        "  -0.5s-\n"
                        "  [s1] 这是第三句话。\n\n"
                        "• JSON Mode 示例：\n"
                        "  [{\"start\":0.0,\"end\":2.5,\"text\":\"第一句话\"}, ...]"
                    )
                }),
                # 文件名前缀
                "filename_prefix": ("STRING", {
                    "default": "subtitle",
                    "tooltip": (
                        "输出文件名设置：\n"
                        "• 仅文件名：如 my_subtitle\n"
                        "• 可含子目录：如 subtitles/my_subtitle\n"
                        "• 无需填写 .srt 后缀，系统会自动添加"
                    )
                }),
                # 保存模式选择
                "save_mode": (["覆盖写入", "自动顺延"], {
                    "default": "覆盖写入",
                    "tooltip": (
                        "保存模式：\n"
                        "• 覆盖写入：如已有同名则覆盖\n"
                        "• 自动顺延：自动递增序号，如 subtitle001.srt, subtitle002.srt"
                    )
                }),
                "clean_dialog_text": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "清理台词首尾多余符号（去掉：/：“/”/空格等），不改时间轴"
                })
            },
            "optional": {
                # 语速参数只在 Text Mode 下生效
                "default_chars_per_second": ("FLOAT", {
                    "default": 10.0, 
                    "min": 1.0, 
                    "max": 50.0, 
                    "step": 0.1,
                    "display_name": "语速(字符/秒)",
                    "tooltip": (
                        "字幕显示速度（仅 Text Mode 有效）：\n"
                        "• 数值越大，自动估算时间越短\n"
                        "• 建议值：8-15 字符/秒\n"
                        "• JSON Mode 已带时间轴则忽略该参数"
                    )
                })
            }
        }

    # 节点输出类型和名称 (两个 STRING 输出)
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("SRT_FILEPATH", "SRT_PREVIEW", "SRT_LOG")
    
    FUNCTION = "process_and_save_srt"
    CATEGORY = "Utils/Scripting"

    def process_and_save_srt(self, input_mode, input_text, filename_prefix, save_mode, default_chars_per_second=10.0, clean_dialog_text=True):
        """
        处理并保存 SRT 文件
        
        参数:
            input_mode: 输入模式 ("Text Mode" 或 "JSON Mode")
            input_text: 输入文本或 JSON 字符串
            filename_prefix: 输出文件名前缀
            save_mode: 保存模式 ("覆盖写入" 或 "自动顺延")
            default_chars_per_second: 文本模式下的默认语速 (字符/秒)
            
        返回:
            (文件路径, SRT 预览内容)
        """
        try:
            # 1. 根据输入模式解析数据
            if input_mode == "Text Mode":
                parsed_data = parse_text_mode(input_text, default_chars_per_second)
            elif input_mode == "JSON Mode":
                parsed_data = parse_json_mode(input_text)
            else:
                return ("", f"错误：不支持的输入模式: {input_mode}", "")
                
            if not parsed_data:
                return ("", "错误：未解析到有效的字幕数据", "")
                
            # 2. 生成 SRT 内容
            srt_blocks = []
            for i, item in enumerate(parsed_data, 1):
                try:
                    srt_start = seconds_to_srt_time(item["start_sec"])
                    srt_end = seconds_to_srt_time(item["end_sec"])
                    text = clean_dialog_text_line(item["text"]) if clean_dialog_text else item["text"]
                    
                    srt_blocks.append(str(i))
                    srt_blocks.append(f"{srt_start} --> {srt_end}")
                    srt_blocks.append(text)
                    srt_blocks.append("")
                except Exception as e:
                    print(f"处理字幕项时出错: {item}, 错误: {e}")
                    continue
            
            srt_content = '\n'.join(srt_blocks).strip()
            
            # 3. 处理文件保存路径
            filename = f"{os.path.basename(filename_prefix)}.srt"
            rel_dir = os.path.dirname(filename_prefix)
            output_dir = os.path.join(self.output_dir, rel_dir) if rel_dir else self.output_dir
            os.makedirs(output_dir, exist_ok=True)
            
            base_filepath = os.path.join(output_dir, filename)
            filepath = base_filepath
            
            # 处理保存模式
            if save_mode == "自动顺延":
                # 自动顺延模式：类似图片保存的自动递增
                base_name = os.path.basename(filename_prefix)
                filepath = self._get_auto_increment_filepath(output_dir, base_name)
            elif save_mode == "覆盖写入":
                # 覆盖写入模式：直接使用原文件名
                filepath = base_filepath
            else:
                # 兼容旧版本的布尔值逻辑
                if isinstance(save_mode, bool):
                    if not save_mode and os.path.exists(filepath):
                        name, ext = os.path.splitext(base_filepath)
                        counter = 1
                        while os.path.exists(filepath):
                            filepath = f"{name}_{counter}{ext}"
                            counter += 1
            
            # 4. 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            print(f"SRT 文件已成功保存到: {filepath}")
            stats_log = (
                f"📊 统计信息 | 模式: {input_mode} | 段数: {len(parsed_data)} | 文件名: {os.path.basename(filepath)} | 路径: {os.path.dirname(filepath)}"
            )
            return (filepath, srt_content, stats_log)
            
        except Exception as e:
            error_msg = f"处理 SRT 时出错: {str(e)}"
            print(error_msg)
            return ("", error_msg, "")
    
    def _get_auto_increment_filepath(self, output_dir: str, base_name: str) -> str:
        """
        生成自动顺延的文件路径，类似 ComfyUI 图片保存机制
        
        参数:
            output_dir: 输出目录
            base_name: 基础文件名（不带扩展名）
            
        返回:
            完整的文件路径，包含自动递增的序号
        """
        import glob
        
        # 查找已存在的文件，匹配 base_name + 数字 + .srt 的模式
        pattern = os.path.join(output_dir, f"{base_name}*.srt")
        existing_files = glob.glob(pattern)
        
        # 提取已存在的序号
        max_index = 0
        for file_path in existing_files:
            filename = os.path.basename(file_path)
            # 移除 .srt 扩展名
            filename_without_ext = filename[:-4]
            
            # 检查是否以 base_name 开头
            if filename_without_ext.startswith(base_name):
                # 提取数字部分
                number_part = filename_without_ext[len(base_name):]
                if number_part.isdigit():
                    max_index = max(max_index, int(number_part))
        
        # 下一个序号，格式化为3位数字
        next_index = max_index + 1
        new_filename = f"{base_name}{next_index:03d}.srt"
        
        return os.path.join(output_dir, new_filename)

# --- ComfyUI 节点注册 ---

# 必须的字典，用于 ComfyUI 发现你的节点
NODE_CLASS_MAPPINGS = {
    "buding_Universal SRT Writer": UniversalSRTWriter
}

# 节点在菜单中显示的名称 (可选)
NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_Universal SRT Writer": "🎬 buding_Universal SRT Writer (支持文本/JSON)"
}
