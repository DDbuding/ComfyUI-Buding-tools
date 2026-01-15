import os

class ListConditionalMax:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_list": ("*",),
                "threshold_value": ("INT,FLOAT", {"default": 77, "min": 0, "step": 1}),
            }
        }

    RETURN_TYPES = ("INT", "FLOAT", "STRING")
    RETURN_NAMES = ("result_int", "result_float", "result_string")
    FUNCTION = "get_conditional_max"
    CATEGORY = "buding_Tools/List/Utility"

    def get_conditional_max(self, input_list, threshold_value):
        """列表条件最大值节点 - 修复版"""
        try:
            print(f"=== 列表条件最大值处理 ===")
            print(f"阈值: {threshold_value}")
            print(f"阈值类型: {type(threshold_value)}")
            
            # 确保输入是列表
            if not isinstance(input_list, list):
                print(f"输入不是列表，转换为列表")
                input_list = [input_list]
            
            if len(input_list) == 0:
                print(f"输入列表为空，返回0")
                return (0, 0.0, "0")
            
            print(f"输入列表长度: {len(input_list)}")
            
            # 转换列表元素为数值
            numeric_values = []
            for i, value in enumerate(input_list):
                try:
                    if isinstance(value, (int, float)):
                        num_value = value
                    else:
                        # 处理字符串数值
                        num_value = float(str(value))
                    numeric_values.append(num_value)
                    print(f"  元素 {i}: {num_value} (类型: {type(num_value)})")
                except Exception as e:
                    print(f"  元素 {i} 转换失败: {e}, 跳过")
            
            if len(numeric_values) == 0:
                print(f"没有有效数值，返回0")
                return (0, 0.0, "0")
            
            print(f"有效数值: {numeric_values}")
            
            # 检查是否有元素大于或等于阈值
            has_element_ge_threshold = any(value >= threshold_value for value in numeric_values)
            
            if has_element_ge_threshold:
                # 如果有元素 >= 阈值，返回阈值
                result = threshold_value
                print(f"存在元素 >= {threshold_value}，返回阈值: {result}")
            else:
                # 如果所有元素都 < 阈值，返回列表中的最大值
                result = max(numeric_values)
                print(f"所有元素 < {threshold_value}，返回最大值: {result}")
            
            # 确保返回正确的类型
            int_result = int(result)
            float_result = float(result)
            string_result = str(int_result)  # 返回整数字符串以确保兼容性
            
            print(f"返回值 - 整数: {int_result}, 浮点: {float_result}, 字符串: '{string_result}'")
            
            return (int_result, float_result, string_result)
            
        except Exception as e:
            print(f"列表条件最大值处理失败: {e}")
            return (0, 0.0, "0")


NODE_CLASS_MAPPINGS = {
    "buding_List Conditional Max": ListConditionalMax,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_List Conditional Max": "📊 buding_List Conditional Max",
}
