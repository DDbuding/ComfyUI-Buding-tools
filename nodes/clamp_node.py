import os

class ValueClamper:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_value": ("INT,FLOAT,*",),
                "max_value": ("INT,FLOAT", {"default": 113, "min": 0, "step": 1}),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("clamped_value",)
    FUNCTION = "clamp_value"
    CATEGORY = "buding_Tools/Math/Utility"

    def clamp_value(self, input_value, max_value):
        """数值限制节点 - 实现min(input, max)功能"""
        try:
            # 处理输入值
            if isinstance(input_value, list):
                # 如果是列表，获取长度
                actual_value = len(input_value)
                print(f"输入是列表，长度为: {actual_value}")
            elif isinstance(input_value, (int, float)):
                # 如果是数值，直接使用
                actual_value = input_value
                print(f"输入是数值: {actual_value}")
            else:
                # 尝试转换为数值
                try:
                    actual_value = float(input_value)
                    print(f"输入已转换为数值: {actual_value}")
                except:
                    # 如果无法转换，获取长度
                    try:
                        actual_value = len(input_value)
                        print(f"输入转换失败，使用长度: {actual_value}")
                    except:
                        actual_value = 0
                        print(f"无法处理输入，使用默认值: {actual_value}")
            
            # 执行限制操作
            if actual_value >= max_value:
                result = max_value
                print(f"{actual_value} >= {max_value}, 返回: {result}")
            else:
                result = int(actual_value)
                print(f"{actual_value} < {max_value}, 返回: {result}")
            
            return (result,)
            
        except Exception as e:
            print(f"数值限制失败: {e}")
            return (0,)


NODE_CLASS_MAPPINGS = {
    "buding_Value Clamper": ValueClamper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_Value Clamper": "📐 buding_Value Clamper",
}
