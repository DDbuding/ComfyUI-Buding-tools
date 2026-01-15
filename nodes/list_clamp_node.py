import os

class ListValueClamper:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_list": ("*",),
                "max_value": ("INT,FLOAT", {"default": 77, "min": 0, "step": 1}),
            }
        }

    RETURN_TYPES = ("INT", "FLOAT", "STRING", "*")
    RETURN_NAMES = ("clamped_int_list", "clamped_float_list", "clamped_string_list", "clamped_list")
    OUTPUT_IS_LIST = (True, True, True, True)
    FUNCTION = "clamp_list_values"
    CATEGORY = "buding_Tools/List/Utility"

    def clamp_list_values(self, input_list, max_value):
        """对列表中每个元素应用数值限制 - 修复版"""
        try:
            print(f"=== 列表数值限制 ===")
            print(f"最大值: {max_value} (类型: {type(max_value)})")
            
            # 确保输入是列表
            if not isinstance(input_list, list):
                print(f"输入不是列表，转换为列表")
                input_list = [input_list]
            
            print(f"输入列表长度: {len(input_list)}")
            
            # 处理列表中的每个元素
            clamped_int_values = []
            clamped_float_values = []
            clamped_string_values = []
            clamped_values = []
            
            for i, value in enumerate(input_list):
                try:
                    # 转换为数值
                    if isinstance(value, (int, float)):
                        num_value = value
                    else:
                        # 处理字符串数值
                        num_value = float(str(value))
                    
                    # 应用限制逻辑
                    if num_value >= max_value:
                        clamped_value = max_value
                    else:
                        clamped_value = num_value
                    
                    print(f"  元素 {i}: {num_value} → {clamped_value} (类型: {type(clamped_value)})")
                    
                    clamped_int_values.append(int(clamped_value))
                    clamped_float_values.append(float(clamped_value))
                    clamped_string_values.append(str(int(clamped_value)))  # 整数字符串以确保兼容性
                    clamped_values.append(clamped_value)
                    
                except Exception as e:
                    print(f"  元素 {i} 处理失败: {e}, 使用默认值0")
                    # 添加默认值
                    clamped_int_values.append(0)
                    clamped_float_values.append(0.0)
                    clamped_string_values.append("0")
                    clamped_values.append(0)
            
            print(f"处理完成，输出 {len(clamped_values)} 个元素")
            print(f"整数列表: {clamped_int_values}")
            print(f"字符串列表: {clamped_string_values}")
            
            return (clamped_int_values, clamped_float_values, clamped_string_values, clamped_values)
            
        except Exception as e:
            print(f"列表数值限制失败: {e}")
            # 返回空列表而不是错误
            return ([], [], [], [])


NODE_CLASS_MAPPINGS = {
    "buding_List Value Clamper": ListValueClamper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_List Value Clamper": "📋 buding_List Value Clamper",
}
