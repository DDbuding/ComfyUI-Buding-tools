import os

class BudingInfiniteTextConcatenate:
    @classmethod
    def INPUT_TYPES(s):
        max_inputs = 20  # 支持20个输入
        
        inputs = {
            "required": {
                "delimiter": ("STRING", {
                    "default": ", ", 
                    "multiline": False,
                    "description": "分隔符：用于连接多个文本的符号"
                }),
                "text_count": ("INT", {
                    "default": 3, 
                    "min": 1, 
                    "max": max_inputs, 
                    "step": 1,
                    "description": "文本数量：要连接的文本输入数量（1-20）"
                }),
            }
        }
        
        # 按组组织输入参数
        optional = {}
        
        # 先添加所有文本内容
        for i in range(1, max_inputs + 1):
            optional[f"text_{i}"] = ("STRING", {
                "default": f"", 
                "multiline": False,
                "description": f"文本{i}：要连接的第{i}个文本内容"
            })
        
        # 添加启用开关
        for i in range(1, max_inputs + 1):
            optional[f"enabled_{i}"] = ("BOOLEAN", {
                "default": True,
                "description": f"启用{i}：是否在结果中包含文本{i}"
            })
        
        inputs["optional"] = optional
        
        return inputs

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("concatenated_text",)
    FUNCTION = "concatenate"
    CATEGORY = "buding_Tools/Text/Processing"

    @classmethod
    def VALIDATE_INPUTS(cls, delimiter=", ", text_count=3, **kwargs):
        return True

    def concatenate(self, delimiter=", ", text_count=3, **kwargs):
        """buding版无限文本连接节点（无过滤版）"""
        try:
            # 收集启用的文本输入
            text_list = []
            
            for i in range(1, text_count + 1):
                # 获取配置
                enabled_key = f"enabled_{i}"
                text_key = f"text_{i}"
                
                # 检查启用状态
                is_enabled = True
                if enabled_key in kwargs:
                    enabled_value = kwargs[enabled_key]
                    is_enabled = bool(enabled_value)
                
                # 获取文本内容
                text_value = kwargs.get(text_key, "") if text_key in kwargs else ""
                
                # 如果启用且文本不为空，添加到列表
                if is_enabled and text_value is not None:
                    if str(text_value).strip() != "":
                        text_list.append(str(text_value))
                    elif str(text_value) != "":
                        text_list.append(str(text_value))
            
            # 连接文本
            result = delimiter.join(text_list)
            
            return (result,)
            
        except Exception as e:
            return ("",)


NODE_CLASS_MAPPINGS = {
    "buding_Infinite Text Concatenate": BudingInfiniteTextConcatenate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_Infinite Text Concatenate": "🔗 buding_Infinite Text Concatenate",
}
