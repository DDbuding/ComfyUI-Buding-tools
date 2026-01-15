"""
JSONBatchIterator - 循环驱动器
接收 FRAME_DATA_JSON，将其解码为 Python 列表，并作为返回值，触发 ComfyUI 调度器的循环
"""

import json

class buding_JSONBatchIterator:
    """
    JSON 批量迭代器 - 将 JSON 数据转换为可迭代的列表
    这是 ComfyUI 循环机制的核心驱动器
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "frame_data_json": ("STRING", {
                    "multiline": True,
                    "default": "[]",
                    "description": "帧数据 JSON\n• 来自 FrameDurationLimiter 的输出\n• 格式: [{\"index\": 0, \"duration_frames\": 24, \"text\": \"...\"}, ...]"
                }),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("CURRENT_ITEM_JSON",)
    FUNCTION = "iterate_batch"
    CATEGORY = "Buding-time"
    
    # 关键：这告诉 ComfyUI 这个输出是列表，会触发循环
    # 对于单个输出，使用 (True,)
    OUTPUT_IS_LIST = (True,)
    
    # 告诉 ComfyUI 这个节点有动态输出数量
    OUTPUT_NODE = True
    
    def iterate_batch(self, frame_data_json):
        # 确保输入是字符串
        if not isinstance(frame_data_json, str):
            frame_data_json = str(frame_data_json)
        
        # 尝试去除可能的 BOM 字符
        if frame_data_json.startswith('\ufeff'):
            frame_data_json = frame_data_json[1:]
        """
        将 JSON 字符串解码为列表，并返回每个元素的 JSON 字符串
        
        Args:
            frame_data_json: 包含帧数据的 JSON 字符串
        
        Returns:
            CURRENT_ITEM_JSON: 每个片段的 JSON 字符串列表（用于驱动循环）
        """
        print("\n=== 开始处理 JSON 批量迭代 ===")
        print(f"输入数据: {frame_data_json[:200]}...")
        
        try:
            # 解析 JSON 数据
            # 确保输入是有效的 JSON 字符串
            frame_data_json = frame_data_json.strip()
            if not frame_data_json:
                print("错误: 输入数据为空")
                return ["{}"]
                
            try:
                frame_data = json.loads(frame_data_json)
            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {e}")
                print(f"原始数据: {frame_data_json[:200]}...")
                return ["{}"]
            
            if not isinstance(frame_data, list):
                error_msg = f"错误: 期望输入是 JSON 数组，实际得到: {type(frame_data)}"
                print(error_msg)
                return ["{}"]
            
            if not frame_data:
                print("警告: 输入数据是空列表，返回包含一个空对象的列表")
                return (["{}"], )  # 返回包含一个空对象的列表
            
            # 为每个元素创建单独的 JSON 字符串
            item_list = []
            for item in frame_data:
                if not isinstance(item, dict):
                    print(f"警告: 跳过非字典项: {item}")
                    continue
                    
                # 确保所有必要的字段都存在
                item_data = {
                    'index': int(item.get('index', 0)),
                    'start_sec': float(item.get('start_sec', 0.0)),
                    'end_sec': float(item.get('end_sec', 0.0)),
                    'duration_sec': float(item.get('duration_sec', 0.0)),
                    'duration_frames': int(item.get('duration_frames', 24)),
                    'text': str(item.get('text', '')).strip()
                }
                
                try:
                    item_json = json.dumps(item_data, ensure_ascii=False)
                    item_list.append(item_json)
                except Exception as e:
                    print(f"警告: 无法序列化项 {item_data.get('index', 'unknown')}: {e}")
                    continue
            
            # 确保返回的列表不为空
            if not item_list:
                print("警告: 没有有效的处理项，返回包含一个空对象的列表")
                return (["{}"], )
                
            print(f"迭代器准备就绪: 将处理 {len(item_list)} 个片段")
            for i, item in enumerate(item_list[:3]):  # 只打印前3项用于调试
                print(f"  - 项 {i+1}: {item[:100]}{'...' if len(item) > 100 else ''}")
            if len(item_list) > 3:
                print(f"  - ...共 {len(item_list)} 项")
                
            # 返回一个元组，包含一个列表
            return (item_list, )
            
        except json.JSONDecodeError as e:
            error_msg = f"JSON 解析错误: {e}\n原始数据: {frame_data_json[:200]}..."
            print(error_msg)
            print("返回默认空对象列表")
            return (["{}"], )  # 返回包含一个空对象的列表
        except Exception as e:
            import traceback
            error_msg = f"迭代器处理错误: {e}\n{traceback.format_exc()}"
            print(error_msg)
            print("返回默认空对象列表")
            return (["{}"], )  # 返回包含一个空对象的列表

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_JSONBatchIterator": buding_JSONBatchIterator,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_JSONBatchIterator": "🔄 JSONBatchIterator (JSON批量迭代器)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
