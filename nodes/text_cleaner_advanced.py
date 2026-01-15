"""
buding_文本净化器增强版 - 在原有净化器基础上增加文本筛选功能
作者: Buding
功能: 删除行首前缀、符号容器、清理空格，以及文本筛选处理
"""

import re
from typing import List


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
    删除行内的符号容器（《》、（）、【】等）及其内容，保留容器外的文本
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


class buding_文本净化器增强版:
    """
    文本净化器增强版：在原有净化功能基础上增加文本筛选功能
    职责：前缀删除、容器删除、空格清理、文本筛选
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
                    "tooltip": "待净化的原始文本"
                }),
                "strip_prefix": (["不处理", "删除前缀", "仅提取前缀"], {
                    "default": "删除前缀",
                    "tooltip": "前缀处理模式：不处理=保持原样；删除前缀=移除行首编号；仅提取前缀=只保留前缀"
                }),
                "strip_brackets": (["不处理", "删除括号内容", "仅提取括号内容"], {
                    "default": "删除括号内容",
                    "tooltip": "括号处理模式：不处理=保持原样；删除内容=删除指定括号类型内的文字；仅提取=只保留指定括号类型内的内容"
                }),
                "brackets_to_strip": ("STRING", {
                    "default": "()、[]、（）",
                    "tooltip": "要处理的括号类型（用「、」分隔），可选：()、[]、（）、【】；例如：()、[]  表示只处理圆括号和方括号"
                }),
                "strip_excess_spaces": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否清理多余空格（行首尾和连续空格）"
                }),
                "remove_empty_lines": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否移除空白行"
                }),
                "filter_mode": (["不处理", "删除用户输入的文本", "删除含用户输入文本的行"], {
                    "default": "不处理",
                    "tooltip": "文本筛选模式：不处理=保持原样；删除文本=删除行内的指定文本；删除整行=如果行内有指定文本则删整行"
                }),
                "filter_text": ("STRING", {
                    "default": "",
                    "tooltip": "要筛选的文本列表（用「、」分隔），如：【】、《》、###；留空则不处理"
                }),
            }
        }

    def clean_text(self, input_text, strip_prefix, strip_brackets, brackets_to_strip, 
                   strip_excess_spaces, remove_empty_lines, filter_mode, filter_text):
        # 标准化输入为行列表
        lines = [str(l) for l in _string_to_list(input_text) if l is not None]
        
        result_lines: List[str] = []
        
        for line in lines:
            # 第一步：前缀处理
            if strip_prefix == "删除前缀":
                line = _strip_prefix_enhanced(line)
            elif strip_prefix == "仅提取前缀":
                original = line
                line_no_prefix = _strip_prefix_enhanced(line)
                if line_no_prefix != original:
                    line = original[:len(original) - len(line_no_prefix)].strip()
                else:
                    line = ""
            
            # 第二步：括号处理
            if strip_brackets == "删除括号内容":
                line = self._strip_brackets_content(line, brackets_to_strip)
            elif strip_brackets == "仅提取括号内容":
                line = self._extract_brackets_content(line, brackets_to_strip)
            
            # 第三步：文本筛选（新增功能）
            if filter_mode == "删除用户输入的文本":
                line = self._filter_text_content(line, filter_text)
            elif filter_mode == "删除含用户输入文本的行":
                if self._has_filter_text(line, filter_text):
                    line = ""
            
            # 第四步：空格清理
            if strip_excess_spaces:
                line = _strip_excess_spaces(line)
            
            # 可选：移除空行
            if remove_empty_lines and not line.strip():
                continue
            
            result_lines.append(line)
        
        cleaned_text = "\n".join(result_lines)
        return (cleaned_text,)
    
    def _strip_brackets_content(self, line: str, brackets_to_strip: str) -> str:
        """
        删除指定括号类型内的内容
        brackets_to_strip: 用「、」分隔的括号类型，如：()、[]、（）、【】
        """
        if not line or not brackets_to_strip:
            return line
        
        # 解析用户指定的括号类型
        bracket_types = [s.strip() for s in brackets_to_strip.split('、') if s.strip()]
        
        if not bracket_types:
            return line
        
        # 根据括号类型删除内容
        for btype in bracket_types:
            if btype == "()":
                line = re.sub(r"\([^)]*\)", "", line)
            elif btype == "[]":
                line = re.sub(r"\[[^\]]*\]", "", line)
            elif btype == "（）":
                line = re.sub(r"（[^）]*）", "", line)
            elif btype == "【】":
                line = re.sub(r"【[^】]*】", "", line)
            elif btype == "《》":
                line = re.sub(r"《[^》]*》", "", line)
        
        return line
    
    def _extract_brackets_content(self, line: str, brackets_to_strip: str) -> str:
        """
        提取指定括号类型内的内容，删除其他部分
        brackets_to_strip: 用「、」分隔的括号类型，如：()、[]、（）、【】
        """
        if not line or not brackets_to_strip:
            return line
        
        # 解析用户指定的括号类型
        bracket_types = [s.strip() for s in brackets_to_strip.split('、') if s.strip()]
        
        if not bracket_types:
            return line
        
        # 根据括号类型提取内容
        containers = []
        for btype in bracket_types:
            if btype == "()":
                containers.extend(re.findall(r"\(([^)]*)\)", line))
            elif btype == "[]":
                containers.extend(re.findall(r"\[([^\]]*)\]", line))
            elif btype == "（）":
                containers.extend(re.findall(r"（([^）]*)）", line))
            elif btype == "【】":
                containers.extend(re.findall(r"【([^】]*)】", line))
            elif btype == "《》":
                containers.extend(re.findall(r"《([^》]*)》", line))
        
        if containers:
            return "".join(containers)
        else:
            return ""
    
    def _has_filter_text(self, line: str, filter_text: str) -> bool:
        """
        检测行内是否有指定的筛选文本（用户输入）
        支持整行任何位置的文本匹配
        """
        if not line or not filter_text:
            return False
        
        # 解析用户指定的文本（支持「、」分隔）
        filter_items = [s.strip() for s in filter_text.split('、') if s.strip()]
        
        if not filter_items:
            return False
        
        # 检测是否行内包含这些文本
        for item in filter_items:
            if item in line:
                return True
        
        return False
    
    def _filter_text_content(self, line: str, filter_text: str) -> str:
        """
        删除行内指定的文本内容（用户输入）
        支持整行任何位置的文本删除
        """
        if not line or not filter_text:
            return line
        
        # 解析用户指定的文本（支持「、」分隔）
        filter_items = [s.strip() for s in filter_text.split('、') if s.strip()]
        
        if not filter_items:
            return line
        
        # 逐个删除匹配的文本
        for item in filter_items:
            if item in line:
                line = line.replace(item, "")
        
        return line


# ComfyUI 节点注册信息
NODE_CLASS_MAPPINGS = {
    "buding_文本净化器增强版": buding_文本净化器增强版,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_文本净化器增强版": "Buding 文本净化器增强版",
}
