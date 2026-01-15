"""
buding_容器内容提取器 - 提取指定符号容器内的文本
独立节点，职责单一：从容器中提取文本内容，支持自定义符号对和换行/空格排列模式
"""

import re
import random
from typing import List, Tuple, Optional


def _normalize_newlines(value: str) -> str:
    """统一换行符"""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _string_to_list(value) -> List[str]:
    """兼容字符串或列表输入"""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return _normalize_newlines(value).split("\n")
    return [str(value)]


def _parse_container_pairs(container_spec: str) -> List[Tuple[str, str]]:
    """
    解析用户输入的容器符号对
    格式：（）、【】、《》 或 (.)、[.]、{.} 等
    返回 (left, right) 对的列表
    
    映射规则：
    - （）→ (\uff08, \uff09)
    - 【】→ (\u3010, \u3011)
    - 《》→ (\u300a, \u300b)
    - ()  → (, )
    - []  → [, ]
    - {}  → {, }
    - ""  → ", "
    - ''  → ', '
    """
    if not container_spec:
        return []
    
    # 内置映射
    builtin_pairs = {
        "（）": ("（", "）"),
        "【】": ("【", "】"),
        "《》": ("《", "》"),
        "()": ("(", ")"),
        "[]": ("[", "]"),
        "{}": ("{", "}"),
        '""': ('"', '"'),
        "''": ("'", "'"),
    }
    
    pairs: List[Tuple[str, str]] = []
    
    # 按"、"分隔
    specs = container_spec.split("、")
    for spec in specs:
        spec = spec.strip()
        if not spec:
            continue
        
        # 先检查内置映射
        if spec in builtin_pairs:
            pairs.append(builtin_pairs[spec])
        else:
            # 用户自定义格式：尝试分割为两个字符（如果长度为2或以上）
            if len(spec) >= 2:
                # 假设第一个字符是左，最后一个字符是右（用于复合字符如括号）
                left = spec[0]
                right = spec[-1]
                pairs.append((left, right))
    
    return pairs


def _extract_from_containers(text: str, container_pairs: List[Tuple[str, str]]) -> List[str]:
    """
    从文本中提取所有容器内的内容，按文本中出现的顺序
    返回 (content, position) 元组列表，然后按位置排序
    """
    matches_with_pos: List[Tuple[int, str]] = []
    
    for left, right in container_pairs:
        try:
            # 转义特殊正则字符
            escaped_left = re.escape(left)
            escaped_right = re.escape(right)
            # 非贪心匹配容器内的内容
            pattern = escaped_left + r"(.*?)" + escaped_right
            
            # 使用 finditer 获取每个匹配的位置和内容
            for match in re.finditer(pattern, text):
                # match.start() 是左括号的位置
                pos = match.start()
                content = match.group(1)
                matches_with_pos.append((pos, content))
        except re.error:
            # 如果正则出错，跳过此容器对
            continue
    
    # 按位置排序，然后只返回内容
    matches_with_pos.sort(key=lambda x: x[0])
    extracted = [content for pos, content in matches_with_pos]
    
    return extracted


class buding_容器内容提取器:
    """
    容器内容提取器：从指定的符号容器中提取文本内容
    支持自定义容器符号、换行或空格排列模式
    """
    CATEGORY = "Buding/TextStory/文本处理"
    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("提取的内容", "提取数量")
    FUNCTION = "extract_containers"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "待提取的原始文本（支持 STRING 或 BWF_TEXT_LIST）"
                }),
                "container_symbols": ("STRING", {
                    "default": "（）、【】、《》",
                    "tooltip": "容器符号对，用顿号分隔。预设：（）、【】、《》、()、[]、{}、\"\"、''"
                }),
                "sort_mode": (["按顺序输出", "倒叙输出", "随机顺序输出"], {
                    "default": "按顺序输出",
                    "tooltip": "输出顺序：按顺序输出=提取顺序；倒叙输出=反向排列；随机顺序输出=随机打乱"
                }),
                "arrangement_mode": (["换行排列", "空格排列"], {
                    "default": "空格排列",
                    "tooltip": "提取出的文本排列模式：换行排列=每个内容占一行；空格排列=多个内容用空格分隔"
                }),
                "remove_duplicates": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否去重（重复的提取内容只保留一次）"
                }),
                "remove_empty": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否移除空白内容"
                }),
            }
        }

    def extract_containers(
        self,
        input_text,
        container_symbols,
        sort_mode,
        arrangement_mode,
        remove_duplicates,
        remove_empty,
    ):
        # 标准化输入为单个字符串
        lines = _string_to_list(input_text)
        combined_text = "\n".join(lines)
        
        # 解析容器符号对
        container_pairs = _parse_container_pairs(container_symbols)
        if not container_pairs:
            return ("", 0)
        
        # 提取所有容器内的内容
        extracted = _extract_from_containers(combined_text, container_pairs)
        
        # 移除空白内容
        if remove_empty:
            extracted = [e.strip() for e in extracted if e and e.strip()]
        else:
            extracted = [e.strip() for e in extracted]
        
        # 去重
        if remove_duplicates:
            seen = set()
            unique_extracted: List[str] = []
            for item in extracted:
                if item not in seen:
                    seen.add(item)
                    unique_extracted.append(item)
            extracted = unique_extracted
        
        # 按排序模式处理
        if sort_mode == "倒叙输出":
            extracted = extracted[::-1]
        elif sort_mode == "随机顺序输出":
            random.shuffle(extracted)
        # 按顺序输出：保持原样
        
        # 按排列模式组织输出
        if arrangement_mode == "换行排列":
            result_text = "\n".join(extracted)
        else:  # 空格排列
            result_text = " ".join(extracted)
        
        return (result_text, len(extracted))


# ComfyUI 节点注册信息
NODE_CLASS_MAPPINGS = {
    "buding_容器内容提取器": buding_容器内容提取器,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_容器内容提取器": "Buding 容器内容提取器",
}
