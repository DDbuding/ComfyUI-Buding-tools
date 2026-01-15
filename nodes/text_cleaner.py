"""
buding_文本净化器 - 专门处理文本前缀、符号容器、空格等净化工作
独立节点，职责单一：删除行首前缀、删除符号容器（《》、（）等）、清理空格
"""

import re
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


def _strip_prefix_enhanced(line: str) -> str:
    """
    删除行首的各种前缀格式，返回删除前缀后的文本
    支持：
    - 中文数字 + 点：一.、二.、三. 等
    - 阿拉伯数字 + 可选字母 + 点：1.、1a.、2b. 等
    - 数字 + 中文括号：（1）、（1a）等
    - 圆括号：(1)、(1a) 等
    """
    if not line:
        return line
    
    # 模式1：中文数字 + 分隔符
    m1 = re.match(r"^\s*[一二三四五六七八九十百千万]+[\.\-、\)）\]]+\s*(.*)$", line)
    if m1:
        return m1.group(1)
    
    # 模式2：数字 + 可选字母 + 分隔符（1. 1a. 2b. 等）
    m2 = re.match(r"^\s*\d+[a-zA-Z]{0,2}[\.\-、\)）\]]+\s*(.*)$", line)
    if m2:
        return m2.group(1)
    
    # 模式3：中文括号式前缀 （1）、（1a）等
    m3 = re.match(r"^\s*[\（\(]\d+[a-zA-Z]{0,2}[\）\)]\s*(.*)$", line)
    if m3:
        return m3.group(1)
    
    # 模式4：纯数字点式前缀 1.、2.、10. 等
    m4 = re.match(r"^\s*\d+[\.\)）]\s*(.*)$", line)
    if m4:
        return m4.group(1)
    
    return line


def _strip_brackets_content(line: str) -> str:
    """
    删除行内的符号容器（《》和（））及其内容，保留容器外的文本
    例如：《月白素雅汉服》中的女子 → 中的女子
    """
    if not line:
        return line
    
    # 删除 《...》
    line = re.sub(r"《[^》]*》", "", line)
    
    # 删除 【...】
    line = re.sub(r"【[^】]*】", "", line)
    
    # 删除 （...）
    line = re.sub(r"（[^）]*）", "", line)
    
    # 删除 (...)
    line = re.sub(r"\([^)]*\)", "", line)
    
    # 删除 [...]
    line = re.sub(r"\[[^\]]*\]", "", line)
    
    return line


def _strip_excess_spaces(line: str) -> str:
    """
    清理多余空格：
    - 删除行头尾空格
    - 多个连续空格→单个空格
    """
    if not line:
        return line
    line = line.strip()
    line = re.sub(r" +", " ", line)
    return line


class buding_文本净化器:
    """
    文本净化器：专门处理前缀删除、符号容器删除、空格清理等
    职责：剥离（strip），不涉及关键词过滤
    """
    CATEGORY = "Buding/TextStory/文本处理"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("净化后文本",)
    FUNCTION = "clean_text"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "待净化的原始文本（支持 STRING 或 BWF_TEXT_LIST）"
                }),
                "strip_prefix": (["不处理", "删除前缀", "仅提取前缀"], {
                    "default": "删除前缀",
                    "tooltip": "前缀处理模式：不处理=保持原样；删除前缀=移除行首编号；仅提取前缀=只保留前缀，删除正文"
                }),
                "strip_brackets": (["不处理", "删除容器内容", "仅提取容器内容"], {
                    "default": "删除容器内容",
                    "tooltip": "容器处理模式：删除内容=删《》和（）中的文字；仅提取=只保留容器内内容"
                }),
                "strip_excess_spaces": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否清理多余空格（行首尾和连续空格）"
                }),
                "remove_empty_lines": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否移除空白行"
                }),
            }
        }

    def clean_text(self, input_text, strip_prefix, strip_brackets, strip_excess_spaces, remove_empty_lines):
        # 标准化输入为行列表（兼容字符串或列表）
        lines = [str(l) for l in _string_to_list(input_text) if l is not None]
        
        result_lines: List[str] = []
        
        for line in lines:
            # 前缀处理
            if strip_prefix == "删除前缀":
                line = _strip_prefix_enhanced(line)
            elif strip_prefix == "仅提取前缀":
                # 提取前缀（保留前缀，删除正文）
                original = line
                line_no_prefix = _strip_prefix_enhanced(line)
                # 如果有前缀（即删除后不同），则只保留前缀部分
                if line_no_prefix != original:
                    line = original[:len(original) - len(line_no_prefix)].strip()
                else:
                    line = ""  # 无前缀，提取模式下返回空
            # 否则 "不处理"，保持 line 不变
            
            # 容器处理
            if strip_brackets == "删除容器内容":
                line = _strip_brackets_content(line)
            elif strip_brackets == "仅提取容器内容":
                # 提取容器内的内容，删除容器外
                # 例如 《月白素雅汉服》中的女子 → 月白素雅汉服
                containers = []
                containers.extend(re.findall(r"《([^》]*)》", line))
                containers.extend(re.findall(r"【([^】]*)】", line))
                containers.extend(re.findall(r"（([^）]*)）", line))
                containers.extend(re.findall(r"\(([^)]*)\)", line))
                containers.extend(re.findall(r"\[([^\]]*)\]", line))
                if containers:
                    line = "".join(containers)
                else:
                    line = ""  # 无容器，提取模式下返回空
            # 否则 "不处理"，保持 line 不变
            
            # 空格清理
            if strip_excess_spaces:
                line = _strip_excess_spaces(line)
            
            # 可选：移除空行
            if remove_empty_lines and not line.strip():
                continue
            
            result_lines.append(line)
        
        # 若启用了移除空行但某行变空，不再添加
        cleaned_text = "\n".join(result_lines)
        return (cleaned_text,)


# ComfyUI 节点注册信息
NODE_CLASS_MAPPINGS = {
    "buding_文本净化器": buding_文本净化器,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_文本净化器": "Buding 文本净化器",
}
