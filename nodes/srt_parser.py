import os
import re
import json
from datetime import datetime, timedelta

class SRTParser:
    """
    解析SRT字幕文件并转换为JSON格式
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "srt_file_path": ("STRING", {
                    "multiline": False, 
                    "default": "",
                    "dynamicPrompts": False,
                    "description": "SRT字幕文件路径\n• 字幕文件的绝对路径\n• 支持.srt格式文件"
                }),
                "encoding": (["utf-8", "gbk", "utf-16", "utf-8-sig"], {
                    "default": "utf-8-sig",
                    "description": "文件编码格式\n• utf-8-sig: 推荐，用于带BOM的UTF-8文件\n• utf-8: 标准UTF-8\n• gbk: 中文GBK编码\n• utf-16: Unicode编码"
                }),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("JSON_OUTPUT",)
    FUNCTION = "parse_srt"
    CATEGORY = "Buding-time/字幕处理"
    OUTPUT_NODE = True
    
    def parse_srt(self, srt_file_path, encoding="utf-8-sig"):
        """
        解析SRT文件并转换为JSON格式
        
        Args:
            srt_file_path (str): SRT文件路径
            encoding (str): 文件编码
            
        Returns:
            tuple: 包含JSON字符串的元组
        """
        print(f"\n=== 开始解析SRT文件 ===")
        print(f"文件路径: {srt_file_path}")
        print(f"编码: {encoding}")
        
        # 检查文件是否存在
        if not os.path.exists(srt_file_path):
            error_msg = f"错误: 文件不存在 - {srt_file_path}"
            print(error_msg)
            return (json.dumps([{"error": error_msg}]), )
        
        try:
            # 尝试使用指定编码打开文件
            with open(srt_file_path, 'r', encoding=encoding) as f:
                content = f.read()
                
            # 使用更健壮的正则表达式匹配SRT块
            pattern = r'(\d+)\r?\n(\d{2}:\d{2}:\d{2}[,\.]\d{3}) --> (\d{2}:\d{2}:\d{2}[,\.]\d{3})\r?\n([\s\S]*?)(?=\r?\n\r?\n\d+\r?\n|\Z)'
            matches = re.findall(pattern, content, re.MULTILINE)
            
            if not matches:
                print("警告: 未找到有效的SRT内容，尝试备用解析方法...")
                # 备用解析方法
                blocks = content.strip().split('\n\n')
                matches = []
                for block in blocks:
                    lines = block.split('\n')
                    if len(lines) >= 3:
                        try:
                            idx = int(lines[0].strip())
                            time_line = lines[1].strip()
                            text = '\n'.join(lines[2:]).strip()
                            
                            # 解析时间
                            if '-->' in time_line:
                                start_time, end_time = time_line.split('-->', 1)
                                matches.append((str(idx), start_time.strip(), end_time.strip(), text))
                        except (ValueError, IndexError):
                            continue
            
            if not matches:
                error_msg = "错误: 无法解析SRT文件内容，可能是格式不正确"
                print(error_msg)
                return (json.dumps([{"error": error_msg}]), )
                
            print(f"找到 {len(matches)} 个字幕块")
            
            result = []
            for i, (idx, start, end, text) in enumerate(matches):
                try:
                    # 清理文本
                    text = text.strip()
                    
                    # 转换时间格式
                    start_sec = self.time_to_seconds(start)
                    end_sec = self.time_to_seconds(end)
                    
                    # 创建字幕项
                    item = {
                        "id": f"s{idx}" if idx.strip().isdigit() else f"s{i+1}",
                        "字幕": text,
                        "start": round(start_sec, 2),
                        "end": round(end_sec, 2),
                        "duration_sec": round(end_sec - start_sec, 2)
                    }
                    
                    # 检查是否是空字幕或间隔
                    if not text.strip() or text.strip().lower() in ['', ' ', '\n']:
                        item["id"] = "pause"
                        item["字幕"] = f"[停顿 {item['duration_sec']:.1f}秒]"
                    
                    result.append(item)
                    
                except Exception as e:
                    print(f"警告: 解析字幕块 {i+1} 时出错: {str(e)}")
                    continue
            
            # 添加间隔信息
            if len(result) > 1:
                for i in range(1, len(result)):
                    gap = result[i]["start"] - result[i-1]["end"]
                    if gap > 0.1:  # 只添加有意义的间隔
                        gap_item = {
                            "id": f"pause_{i}",
                            "字幕": f"[间隔 {gap:.1f}秒]",
                            "start": result[i-1]["end"],
                            "end": result[i]["start"],
                            "duration_sec": round(gap, 2)
                        }
                        result.insert(i*2-1, gap_item)
            
            # 转换为JSON字符串
            json_output = json.dumps(result, ensure_ascii=False, indent=2)
            print(f"\n=== SRT解析完成 ===")
            print(f"共解析出 {len(result)} 个时间片段")
            
            # 打印前几个片段作为示例
            print("\n前3个时间片段:")
            for i, item in enumerate(result[:3]):
                print(f"{i+1}. ID: {item['id']}")
                print(f"   时间: {item['start']:.2f}s - {item['end']:.2f}s ({(item['end']-item['start']):.2f}s)")
                print(f"   文本: {item['字幕'][:50]}{'...' if len(item['字幕']) > 50 else ''}")
            
            if len(result) > 3:
                print(f"... 以及另外 {len(result)-3} 个片段")
            
            return (json_output, )
            
        except Exception as e:
            import traceback
            error_msg = f"解析SRT文件时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            return (json.dumps([{"error": error_msg}]), )
    
    @staticmethod
    def time_to_seconds(time_str):
        """将SRT时间格式转换为秒"""
        # 处理逗号或点作为毫秒分隔符
        if ',' in time_str:
            time_part, ms = time_str.split(',')
        elif '.' in time_str:
            time_part, ms = time_str.split('.')
        else:
            time_part = time_str
            ms = '000'
            
        # 解析时间部分
        h, m, s = map(int, time_part.split(':'))
        # 确保毫秒是3位数
        ms = ms.ljust(3, '0')[:3]
        
        return h * 3600 + m * 60 + s + int(ms) / 1000.0

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SRTParser": SRTParser,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SRTParser": "📝 SRT字幕解析器 (Buding-time)",
}

# 导出的类名
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
