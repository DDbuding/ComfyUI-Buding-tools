import os

class EnsureInteger:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_value": ("*",),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("integer_value",)
    FUNCTION = "convert_to_int"
    CATEGORY = "buding_Tools/Utils/Type Conversion"

    def convert_to_int(self, input_value):
        """确保输出为整数类型"""
        try:
            print(f"=== 确保整数类型 ===")
            print(f"输入值: {input_value} (类型: {type(input_value)})")
            
            # 处理不同类型的输入
            if isinstance(input_value, int):
                result = input_value
            elif isinstance(input_value, float):
                result = int(input_value)
            elif isinstance(input_value, list):
                if len(input_value) > 0:
                    # 如果是列表，取第一个元素
                    first_element = input_value[0]
                    if isinstance(first_element, (int, float)):
                        result = int(first_element)
                    else:
                        result = int(float(str(first_element)))
                else:
                    result = 0
            else:
                # 尝试转换字符串或其他类型
                result = int(float(str(input_value)))
            
            print(f"转换结果: {result} (类型: {type(result)})")
            return (result,)
            
        except Exception as e:
            print(f"类型转换失败: {e}")
            print(f"返回默认值: 0")
            return (0,)


NODE_CLASS_MAPPINGS = {
    "buding_Ensure Integer": EnsureInteger,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_Ensure Integer": "🔢 buding_Ensure Integer",
}
