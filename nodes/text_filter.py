"""
buding_文本过滤器 - 专门处理关键词匹配、去重、删除等过滤工作
独立节点，职责单一：关键词过滤、行去重、删除行或部分删除
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


def _deduplicate_keep_order(items: List[str]) -> List[str]:
    """保持顺序地去重"""
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _parse_keywords_field(value: str, delimiter: str = "") -> List[str]:
    """
    把关键字字段解析为关键字列表
    支持逗号、顿号、分号或换行作为分隔符，或使用自定义分隔符
    """
    if not value:
        return []
    text = str(value)
    if delimiter and delimiter.strip():
        parts = re.split(re.escape(delimiter), text)
    else:
        parts = re.split(r"[，,;\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def _line_matches_keywords(
    line: str,
    keywords: List[str],
    match_mode: str,
    match_logic: str,
    case_sensitive: bool,
) -> Tuple[bool, List[str]]:
    """
    判断一行是否匹配关键字集合
    返回 (matched, matched_keywords_list)
    """
    if not keywords:
        return (False, [])

    text = line if case_sensitive else line.lower()
    normalized_keywords = [k if case_sensitive else k.lower() for k in keywords]

    matched_keywords: List[str] = []

    if match_mode == "正则匹配":
        regexes = []
        for p in keywords:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                regexes.append(re.compile(p, flags))
            except re.error:
                continue
        
        for idx, rg in enumerate(regexes):
            if rg.search(line):
                matched_keywords.append(keywords[idx])
        
        matched = False
        if match_logic == "AND":
            matched = len(matched_keywords) == len(regexes) and len(regexes) > 0
        else:
            matched = len(matched_keywords) > 0
        return matched, matched_keywords

    for kw in normalized_keywords:
        if match_mode == "包含匹配":
            if kw in text:
                matched_keywords.append(kw)
        elif match_mode == "前缀匹配":
            if text.lstrip().startswith(kw):
                matched_keywords.append(kw)
        elif match_mode == "精确匹配":
            if text.strip() == kw:
                matched_keywords.append(kw)
        else:
            # 退化为包含匹配
            if kw in text:
                matched_keywords.append(kw)

    if match_logic == "AND":
        return (len(matched_keywords) == len(normalized_keywords) and len(normalized_keywords) > 0, matched_keywords)
    return (len(matched_keywords) > 0, matched_keywords)


def _dedup_lines(lines: List[str], dedup_mode: str) -> List[str]:
    """
    按指定模式对行进行去重
    dedup_mode:
    - "关闭"：不去重
    - "按全行去重"：完全相同的行只保留一次
    - "按首次出现后删除"：第一次出现的行保留，后续出现的删除
    """
    if dedup_mode == "关闭":
        return lines
    
    if dedup_mode == "按全行去重":
        return _deduplicate_keep_order(lines)
    
    if dedup_mode == "按首次出现后删除":
        # 与"按全行去重"相同的行为
        return _deduplicate_keep_order(lines)
    
    return lines


class buding_文本过滤器:
    """
    文本过滤器：专门处理关键词匹配、去重、删除等过滤工作
    职责：匹配关键词、去重、删除行或部分删除
    """
    CATEGORY = "Buding/TextStory/文本处理"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("过滤后文本",)
    FUNCTION = "filter_text"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "待过滤的文本（支持 STRING 或 BWF_TEXT_LIST）"
                }),
                "keywords": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "关键字列表，多行或用逗号/顿号/分号分隔；留空表示不进行关键词过滤"
                }),
                "keyword_delimiter": ("STRING", {
                    "default": "",
                    "tooltip": "关键字分隔符，留空自动识别（逗号/顿号/分号/换行）"
                }),
                "match_mode": (["包含匹配", "前缀匹配", "精确匹配", "正则匹配"], {
                    "default": "包含匹配",
                    "tooltip": "匹配模式：包含/前缀/精确/正则"
                }),
                "match_logic": (["OR", "AND"], {
                    "default": "OR",
                    "tooltip": "多关键字匹配逻辑：任一(OR) 或 全部(AND)"
                }),
                "case_sensitive": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否区分大小写（默认不区分）"
                }),
                "line_action": (["保留全部", "删除整行", "仅删除关键词"], {
                    "default": "删除整行",
                    "tooltip": "匹配后的操作：保留全部=不过滤；删除整行=删整行；仅删关键词=保留行但删除关键词文本"
                }),
                "deduplication": (["关闭", "按全行去重", "按首次出现后删除"], {
                    "default": "关闭",
                    "tooltip": "去重模式：关闭=不去重；按全行去重=完全相同行只保留一次；按首次出现后删除=同上"
                }),
                "remove_empty_lines": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否移除空白行"
                }),
            }
        }

    def filter_text(
        self,
        input_text,
        keywords,
        keyword_delimiter,
        match_mode,
        match_logic,
        case_sensitive,
        line_action,
        deduplication,
        remove_empty_lines,
    ):
        # 标准化输入为行列表（兼容字符串或列表）
        lines = [str(l) for l in _string_to_list(input_text) if l is not None]

        # 构建关键字列表
        kw_list = _parse_keywords_field(keywords, keyword_delimiter)
        kw_list = _deduplicate_keep_order(kw_list)

        kept_lines: List[str] = []

        for line in lines:
            # 判断是否匹配关键词
            matched, matched_keywords = _line_matches_keywords(line, kw_list, match_mode, match_logic, case_sensitive)

            if line_action == "保留全部":
                # 不过滤，保留所有行
                kept_lines.append(line)
            elif line_action == "删除整行":
                # 匹配则删除，否则保留
                if not matched:
                    kept_lines.append(line)
            elif line_action == "仅删除关键词":
                # 匹配则删除关键词文本，否则保留原行
                if matched:
                    new_text = line
                    if match_mode == "正则匹配":
                        for pat in kw_list:
                            try:
                                flags = 0 if case_sensitive else re.IGNORECASE
                                new_text = re.sub(pat, "", new_text, flags=flags)
                            except re.error:
                                continue
                    else:
                        for kw in matched_keywords:
                            if case_sensitive:
                                new_text = new_text.replace(kw, "")
                            else:
                                try:
                                    new_text = re.sub(re.escape(kw), "", new_text, flags=re.IGNORECASE)
                                except re.error:
                                    new_text = new_text.replace(kw, "")
                    kept_lines.append(new_text)
                else:
                    kept_lines.append(line)

        # 去重处理
        kept_lines = _dedup_lines(kept_lines, deduplication)

        # 可选：移除空行
        if remove_empty_lines:
            kept_lines = [ln for ln in kept_lines if ln and ln.strip()]

        filtered_text = "\n".join(kept_lines)
        return (filtered_text,)


# ComfyUI 节点注册信息
NODE_CLASS_MAPPINGS = {
    "buding_文本过滤器": buding_文本过滤器,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_文本过滤器": "Buding 文本过滤器",
}
