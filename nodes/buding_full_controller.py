import os

class BudingFullTextController:
    @classmethod
    def INPUT_TYPES(s):
        inputs = {
            "required": {
                "main_text": ("STRING", {
                    "default": "", 
                    "multiline": True,
                    "description": "主文本内容，用于检查其他文本是否包含在内"
                }),
            }
        }
        
        # 为text2-text20添加检查文本输入
        optional = {}
        for i in range(2, 21):  # text2 到 text20
            optional[f"check_text_{i}"] = ("STRING", {
                "default": f"", 
                "multiline": False,
                "description": f"检查文本{i}：如果此文本出现在主文本中，则对应的enable_{i}输出为True"
            })
            
        inputs["optional"] = optional
        return inputs

    RETURN_TYPES = ("BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN", "BOOLEAN")
    RETURN_NAMES = ("enable_2", "enable_3", "enable_4", "enable_5", "enable_6", "enable_7", "enable_8", "enable_9", "enable_10", "enable_11", "enable_12", "enable_13", "enable_14", "enable_15", "enable_16", "enable_17", "enable_18", "enable_19", "enable_20")
    FUNCTION = "check_all_texts"
    CATEGORY = "buding_Tools/Text/Control"

    def check_all_texts(self, main_text="", **kwargs):
        """buding版完整文本控制器 - 支持text2-text20"""
        try:
            # 检查text2-text20（共19个）
            enable_states = []
            
            for i in range(2, 21):  # text2 到 text20
                check_key = f"check_text_{i}"
                check_text = kwargs.get(check_key, "") if check_key in kwargs else ""
                
                # 检查文本是否在主文本中
                is_contained = check_text.lower() in main_text.lower() if check_text.strip() else False
                enable_states.append(is_contained)
                
            # 返回19个独立的布尔值
            return tuple(enable_states)
            
        except Exception as e:
            return tuple([False] * 19)


NODE_CLASS_MAPPINGS = {
    "buding_Full Text Controller": BudingFullTextController,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_Full Text Controller": "🎯 buding_Full Text Controller",
}
