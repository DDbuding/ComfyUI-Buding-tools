"""
JSONDataExtractor - 数据解包器
在循环内部，将 JSON 字符串解包并转换为原生 ComfyUI 数据类型 (INT 和 STRING)
"""

import json

class buding_JSONDataExtractor:
    """
    JSON 数据提取器 - 将 JSON 字符串解包为 ComfyUI 原生数据类型
    这是连接 STRING 数据到 INT/STRING 输入的关键桥梁
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "current_item_json": ("STRING", {
                    "multiline": True,
                    "default": "{}",
                    "description": "当前项 JSON\n• 来自 JSONBatchIterator 的循环输出\n• 每次循环处理一个片段"
                }),
            },
        }
    
    RETURN_TYPES = ("INT", "STRING", "INT", "FLOAT", "FLOAT")
    RETURN_NAMES = ("DURATION_FRAMES_INT", "SEGMENT_TEXT_STRING", "INDEX_INT", "START_SEC", "END_SEC")
    FUNCTION = "extract_data"
    CATEGORY = "Buding-time"
    
    def extract_data(self, current_item_json):
        """
        从 JSON 字符串中提取数据并转换为原生类型
        
        Args:
            current_item_json: 单个片段的 JSON 字符串或已经是字典的对象
        
        Returns:
            DURATION_FRAMES_INT: 持续帧数 (INT) - 用于连接视频生成节点
            SEGMENT_TEXT_STRING: 字幕文本 (STRING) - 用于提示词组合
            INDEX_INT: 片段索引 (INT) - 用于调试和排序
            START_SEC: 开始时间 (FLOAT) - 原始时间信息
            END_SEC: 结束时间 (FLOAT) - 原始时间信息
        """
        print("\n=== 开始提取 JSON 数据 ===")
        print(f"输入数据类型: {type(current_item_json)}")
        print(f"输入数据内容: {str(current_item_json)[:200]}...")
        
        try:
            # 如果输入已经是字典，直接使用
            if isinstance(current_item_json, dict):
                item = current_item_json
            # 否则尝试解析 JSON 字符串
            elif isinstance(current_item_json, str):
                current_item_json = current_item_json.strip()
                if not current_item_json:
                    print("错误: 输入数据为空")
                    return (1, "", 0, 0.0, 0.0)
                item = json.loads(current_item_json)
            else:
                print(f"错误: 不支持的输入类型: {type(current_item_json)}")
                return (1, "", 0, 0.0, 0.0)
            
            if not isinstance(item, dict):
                print(f"错误: 期望输入是 JSON 对象，实际得到: {type(item)}")
                print(f"实际内容: {str(item)[:200]}")
                return (1, "", 0, 0.0, 0.0)
            
            # 提取数据，提供默认值并处理可能的类型错误
            try:
                duration_frames = int(item.get('duration_frames', 0)) or 1
                text = str(item.get('text', '')).strip()
                index = int(item.get('index', 0))
                start_sec = float(item.get('start_sec', 0.0))
                end_sec = float(item.get('end_sec', 0.0))
                
                # 确保结束时间不小于开始时间
                if end_sec < start_sec:
                    end_sec = start_sec + 1.0  # 默认1秒
                
                # 确保持续时间至少为1帧
                if duration_frames < 1:
                    duration_frames = 1
                    
            except (ValueError, TypeError) as e:
                print(f"数据提取错误: {e}")
                print(f"问题数据: {item}")
                return (1, "", 0, 0.0, 0.0)
            
            # 记录提取的数据
            print(f"提取片段 {index}:")
            print(f"  - 开始时间: {start_sec:.2f} 秒")
            print(f"  - 结束时间: {end_sec:.2f} 秒")
            print(f"  - 持续时间: {end_sec - start_sec:.2f} 秒")
            print(f"  - 帧数: {duration_frames}")
            print(f"  - 文本: '{text[:50]}{'...' if len(text) > 50 else ''}")
            print("=== 数据提取完成 ===\n")
            
            return (duration_frames, text, index, start_sec, end_sec)
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON 解析错误: {e}\n原始数据: {str(current_item_json)[:200]}"
            print(error_msg)
            return (1, "", 0, 0.0, 0.0)
        except Exception as e:
            import traceback
            error_msg = f"数据提取错误: {e}\n{traceback.format_exc()}"
            print(error_msg)
            return (1, "", 0, 0.0, 0.0)

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_JSONDataExtractor": buding_JSONDataExtractor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_JSONDataExtractor": "📊 JSONDataExtractor (JSON数据提取器)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
