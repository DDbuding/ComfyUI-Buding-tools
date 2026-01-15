"""
SmartPromptComposer - 智能提示词组合器
执行智能 Prompt 组合逻辑，并透传帧数
"""

class buding_SmartPromptComposer:
    """
    智能提示词组合器 - 根据不同情况组合提示词
    支持基础提示词 + 字幕文本，或使用自定义提示词
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "description": "基础提示词\n• 视频的基础风格描述\n• 例如: '动漫风格, 高质量, 详细'"
                }),
                "segment_text": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "description": "字幕文本\n• 来自 JSONDataExtractor\n• 将添加到基础提示词后"
                }),
                "custom_prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "description": "自定义提示词\n• 来自 EasyUse-提示词行节点\n• 如果为空或 '.'，则使用 基础提示词 + 字幕文本\n• 如果有内容，则直接使用此提示词"
                }),
                "duration_frames": ("INT", {
                    "default": 24,
                    "min": 1,
                    "description": "持续帧数\n• 来自 JSONDataExtractor\n• 将透传给视频生成节点"
                }),
            },
            "optional": {
                "separator": ("STRING", {
                    "default": ", ",
                    "description": "分隔符\n• 基础提示词和字幕文本之间的连接符"
                }),
                "clean_text": ("BOOLEAN", {
                    "default": True,
                    "label_on": "清理",
                    "label_off": "保留",
                    "description": "是否清理字幕文本\n• 移除特殊字符和多余空格"
                }),
            },
        }
    
    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("FINAL_PROMPT", "DURATION_FRAMES_INT")
    FUNCTION = "compose_prompt"
    CATEGORY = "Buding-time"
    
    def compose_prompt(self, base_prompt, segment_text, custom_prompt, duration_frames, separator=", ", clean_text=True):
        """
        组合最终的提示词
        
        Args:
            base_prompt: 基础提示词
            segment_text: 字幕文本
            custom_prompt: 自定义提示词
            duration_frames: 持续帧数
            separator: 分隔符
            clean_text: 是否清理文本
        
        Returns:
            FINAL_PROMPT: 最终组合的提示词
            DURATION_FRAMES_INT: 透传的帧数
        """
        
        # 清理基础提示词
        base_prompt = base_prompt.strip()
        
        # 处理字幕文本
        segment_text = segment_text.strip()
        if clean_text and segment_text:
            # 移除常见的字幕标记和特殊字符
            import re
            segment_text = re.sub(r'\[s\d+\]', '', segment_text)  # 移除 [s1] 标记
            segment_text = re.sub(r'<[^>]+>', '', segment_text)  # 移除 HTML 标签
            segment_text = re.sub(r'\([^)]*\)', '', segment_text)  # 移除括号内容
            segment_text = re.sub(r'\s+', ' ', segment_text)  # 合并多个空格
            segment_text = segment_text.strip()
        
        # 判断使用哪种提示词组合方式
        custom_prompt = custom_prompt.strip()
        
        if custom_prompt and custom_prompt != ".":
            # 使用自定义提示词
            final_prompt = custom_prompt
            print(f"使用自定义提示词: {final_prompt[:50]}...")
        else:
            # 使用基础提示词 + 字幕文本
            if base_prompt and segment_text:
                final_prompt = base_prompt + separator + segment_text
                print(f"组合提示词: {base_prompt[:30]}... + {segment_text[:30]}...")
            elif base_prompt:
                final_prompt = base_prompt
                print(f"仅使用基础提示词: {final_prompt[:50]}...")
            elif segment_text:
                final_prompt = segment_text
                print(f"仅使用字幕文本: {final_prompt[:50]}...")
            else:
                final_prompt = ""
                print("警告: 所有提示词都为空")
        
        # 确保帧数有效
        if duration_frames < 1:
            duration_frames = 1
        
        return (final_prompt, duration_frames)

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SmartPromptComposer": buding_SmartPromptComposer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SmartPromptComposer": "🎭 SmartPromptComposer (智能提示词合成器)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
