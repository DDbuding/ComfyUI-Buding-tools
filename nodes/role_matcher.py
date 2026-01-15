import re
import time
from functools import wraps

def lightweight_performance_monitor(func):
    """极轻量级性能监控，只在调试模式下启用"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # 只在调试模式下监控
        if len(args) > 3 and args[3]:  # debug_mode是第4个参数
            start_time = time.time()
            result = func(self, *args, **kwargs)
            elapsed = time.time() - start_time
            print(f"[性能] {func.__name__}: {elapsed:.3f}秒")
            return result
        else:
            return func(self, *args, **kwargs)
    return wrapper

class buding_RoleMatcher:
    """
    角色匹配器：根据关键词识别文本中的角色，输出布尔值控制信号
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        # 动态生成15个关键词输入
        keyword_inputs = {}
        for i in range(1, 16):
            keyword_inputs[f"keyword_{i}"] = ("STRING", {"default": ""})
        
        return {
            "required": {
                "segment_text": ("STRING", {
                    "multiline": True,
                    "tooltip": "当前循环中的字幕文本，用于角色识别"
                }),
                "match_mode": (["精确匹配", "模糊匹配", "包含匹配"], {
                    "default": "精确匹配",
                    "tooltip": "精确匹配: 严格按照用户输入识别，包括符号\n模糊匹配: 去除空格和标点后比较\n包含匹配: 字符串包含关系"
                }),
                "case_sensitive": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否区分大小写，如 [老布丁] vs [老布丁]"
                }),
                "debug_mode": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "开启后会在控制台显示匹配详情和统计信息"
                }),
            },
            "optional": keyword_inputs
        }
    
    RETURN_TYPES = tuple(["BOOLEAN"] * 15)
    RETURN_NAMES = tuple([f"match_{i}" for i in range(1, 16)])
    OUTPUT_IS_LIST = (False,) * 15
    FUNCTION = "match_roles"
    CATEGORY = "buding_Tools/Audio/Control"
    
    @lightweight_performance_monitor
    def match_roles(self, segment_text, match_mode, case_sensitive, debug_mode, **kwargs):
        """
        匹配文本中的角色关键词
        
        参数:
            segment_text: 要匹配的文本内容
            match_mode: 匹配模式
            case_sensitive: 是否大小写敏感
            debug_mode: 是否开启调试模式
            **kwargs: 15个关键词参数
            
        返回:
            15个布尔值的元组，对应每个关键词的匹配结果
        """
        try:
            # 提取关键词列表
            keywords = []
            for i in range(1, 16):
                keyword = kwargs.get(f"keyword_{i}", "").strip()
                keywords.append(keyword)
            
            # 执行匹配
            results = []
            for keyword in keywords:
                match_result = self._match_single_text(
                    segment_text, keyword, match_mode, case_sensitive
                )
                results.append(match_result)
            
            # 调试输出
            if debug_mode:
                self._debug_output(segment_text, keywords, results, match_mode, case_sensitive)
            
            return tuple(results)
            
        except Exception as e:
            print(f"❌ 角色匹配器错误: {e}")
            # 出错时返回全False
            return tuple([False] * 15)
    
    def _match_single_text(self, text, keyword, mode, case_sensitive):
        """
        匹配单个关键词
        
        参数:
            text: 文本内容
            keyword: 关键词
            mode: 匹配模式
            case_sensitive: 是否大小写敏感
            
        返回:
            bool: 匹配结果
        """
        # 空关键词直接返回False
        if not keyword or not keyword.strip():
            return False
        
        # 处理大小写敏感
        if not case_sensitive:
            text = text.lower()
            keyword = keyword.lower()
        
        # 根据模式进行匹配
        if mode == "精确匹配":
            # 精确匹配：严格按照用户输入识别，包括符号
            return keyword in text
        elif mode == "模糊匹配":
            # 改进的模糊匹配算法
            return self._improved_fuzzy_match(text, keyword)
        else:  # 包含匹配
            # 包含匹配：字符串包含关系
            return keyword in text
    
    def _debug_output(self, text, keywords, results, mode, case_sensitive):
        """
        调试信息输出
        
        参数:
            text: 输入文本
            keywords: 关键词列表
            results: 匹配结果列表
            mode: 匹配模式
            case_sensitive: 大小写敏感设置
        """
        print("\n🎭 === 角色匹配调试信息 ===")
        print(f"📝 输入文本: {text[:100]}{'...' if len(text) > 100 else ''}")
        print(f"🔍 匹配模式: {mode}")
        print(f"📐 大小写敏感: {'是' if case_sensitive else '否'}")
        
        # 统计信息
        valid_keywords = [kw for kw in keywords if kw]
        matched_count = sum(results)
        total_valid = len(valid_keywords)
        
        print(f"📊 统计信息:")
        print(f"  • 有效关键词数量: {total_valid}/15")
        print(f"  • 匹配成功数量: {matched_count}")
        if total_valid > 0:
            print(f"  • 匹配成功率: {matched_count/total_valid*100:.1f}%")
        
        # 详细匹配结果
        print(f"🔍 详细匹配结果:")
        for i, (keyword, result) in enumerate(zip(keywords, results), 1):
            if keyword:  # 只显示非空关键词
                status = "✅ 匹配" if result else "❌ 未匹配"
                print(f"  {status} keyword_{i:2d}: '{keyword}' → {result}")
        
        print("🎭 === 调试信息结束 ===\n")
    
    def _improved_fuzzy_match(self, text, keyword):
        """
        改进的模糊匹配算法
        
        参数:
            text: 文本内容
            keyword: 关键词
            
        返回:
            bool: 匹配结果
        """
        # 空关键词直接返回False
        if not keyword or not keyword.strip():
            return False
            
        # 简单的包含检查
        if keyword.lower() in text.lower():
            return True
            
        # 提取核心字符（只保留字母和数字）
        clean_text = re.sub(r'[^a-z0-9]', '', text.lower())
        clean_keyword = re.sub(r'[^a-z0-9]', '', keyword.lower())
        
        # 如果清理后的关键词为空，返回False
        if not clean_keyword:
            return False
            
        # 检查清理后的关键词是否在清理后的文本中
        if clean_keyword in clean_text:
            return True
            
        # 对于短关键词（<=3字符），使用更宽松的匹配
        if len(clean_keyword) <= 3:
            # 检查是否包含关键词的所有字符
            for char in clean_keyword:
                if char not in clean_text:
                    return False
            return True
            
        # 对于长关键词，检查是否有至少70%的字符连续出现
        # 使用滑动窗口方法
        window_size = max(2, len(clean_keyword) // 2)
        for i in range(len(clean_text) - window_size + 1):
            window = clean_text[i:i+window_size]
            # 计算窗口与关键词的相似度
            common_chars = sum(1 for c in window if c in clean_keyword)
            if common_chars / window_size >= 0.7:
                return True
                
        return False


NODE_CLASS_MAPPINGS = {
    "buding_RoleMatcher": buding_RoleMatcher,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_RoleMatcher": "🎭 buding_RoleMatcher (角色匹配器)",
}
