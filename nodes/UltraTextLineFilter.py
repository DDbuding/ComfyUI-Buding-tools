"""
✂️ Ultra Text Line Filter (究极文本行筛选)
功能：
1. 多维度筛选：语言特征、关键词(OR)、指定行号(OR)
2. 强力排除：丢弃关键词(黑名单)
3. 智能默认：若未激活任何筛选条件，则默认保留所有行
4. 基础清洗：强制去除首尾空格，可选去除空行
"""

import re

class UltraTextLineFilter:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),

                # 1. 语言特征筛选 (OR 规则之一)
                # 默认第一项是 Disable，即默认不开启语言筛选
                "language_mode": ([
                    "🌑 不按语言筛选 (Disable)",
                    "🇨🇳 行尾是中文 (Tail is Chinese)",
                    "🇺🇸 行尾是英文 (Tail is English)"
                ],),

                # 2. 关键词包含 (OR 规则之二)
                "include_keywords": ("STRING", {"default": "", "multiline": False, "placeholder": "关键词A、关键词B (留空不生效)"}),

                # 3. 指定行号 (OR 规则之三)
                "specific_lines": ("STRING", {"default": "", "multiline": False, "placeholder": "1、3-5、9 (留空不生效)"}),

                # 4. 关键词丢弃 (黑名单 - 强否决)
                "discard_keywords": ("STRING", {"default": "", "multiline": False, "placeholder": "排除词A、排除词B (优先级最高)"}),

                # 5. 基础清洗
                "remove_empty": ("BOOLEAN", {"default": True, "label": "🗑️ 移除空行"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("📄筛选结果",)
    FUNCTION = "filter_process"
    CATEGORY = "buding_Tools/文本处理"

    # --- 语言检测逻辑 ---
    def is_chinese_char(self, char):
        code = ord(char)
        # 汉字 + 中文标点
        if 0x4E00 <= code <= 0x9FFF: return True
        if code in [0xFF0C, 0x3002, 0xFF1F, 0xFF01, 0x3001, 0xFF1B, 0xFF1A, 0x201C, 0x201D, 0x2018, 0x2019, 0xFF08, 0xFF09, 0x3010, 0x3011, 0x300A, 0x300B, 0x2026, 0x2014]: return True
        return False

    def is_english_char(self, char):
        code = ord(char)
        # 字母 + 英文标点
        if 65 <= code <= 90 or 97 <= code <= 122: return True
        if char in ",.?!;:\"'()[]<>": return True
        return False

    def check_language(self, line, mode):
        """倒序扫描找强特征"""
        if "Disable" in mode: return False

        for char in reversed(line):
            if self.is_chinese_char(char):
                return "Chinese" in mode
            if self.is_english_char(char):
                return "English" in mode
        return False

    # --- 行号解析逻辑 ---
    def parse_specific_lines(self, line_str, total_lines):
        if not line_str.strip():
            return set()
        selected_indices = set()
        # 兼容中英文分隔符
        parts = re.split(r'[、,，]', line_str)
        for part in parts:
            part = part.strip()
            if not part: continue
            try:
                if '-' in part: # 处理 3-5
                    start, end = part.split('-')
                    s_idx, e_idx = int(start) - 1, int(end) - 1
                    for i in range(s_idx, e_idx + 1):
                        if 0 <= i < total_lines: selected_indices.add(i)
                else: # 处理 1
                    idx = int(part) - 1
                    if 0 <= idx < total_lines: selected_indices.add(idx)
            except ValueError:
                continue
        return selected_indices

    # --- 核心处理 ---
    def filter_process(self, text, language_mode, include_keywords, specific_lines, discard_keywords, remove_empty):

        raw_lines = text.splitlines()
        result_lines = []

        # 1. 解析参数
        includes = [k.strip() for k in re.split(r'[、,，]', include_keywords) if k.strip()]
        discards = [k.strip() for k in re.split(r'[、,，]', discard_keywords) if k.strip()]
        target_indices = self.parse_specific_lines(specific_lines, len(raw_lines))

        # 2. 判断是否激活了"白名单"逻辑
        # 如果语言也是Disable，包含词也空，行号也空 -> 视为"无筛选模式" (全选)
        any_whitelist_active = (
            ("Disable" not in language_mode) or
            (len(includes) > 0) or
            (len(target_indices) > 0)
        )

        for i, line in enumerate(raw_lines):
            processed_line = line.strip()

            # 空行处理
            if not processed_line:
                if remove_empty: continue
                # 如果要保留空行，且没激活筛选，则保留
                # 如果激活了筛选，除非指定了空行所在的行号，否则通常丢弃空行
                if not any_whitelist_active:
                    result_lines.append("")
                    continue
                elif i in target_indices:
                    result_lines.append("")
                    continue
                else:
                    continue

            # === 步骤 A: 白名单 (OR 逻辑) ===
            is_selected = False

            if not any_whitelist_active:
                # 没有任何筛选条件 -> 默认保留
                is_selected = True
            else:
                # 1. 命中指定行号?
                if i in target_indices: is_selected = True

                # 2. 命中包含词?
                if not is_selected and includes:
                    for inc in includes:
                        if inc in processed_line:
                            is_selected = True
                            break

                # 3. 命中语言特征?
                if not is_selected and "Disable" not in language_mode:
                    if self.check_language(processed_line, language_mode):
                        is_selected = True

            if not is_selected: continue

            # === 步骤 B: 黑名单 (一票否决) ===
            should_discard = False
            if discards:
                for disc in discards:
                    if disc in processed_line:
                        should_discard = True
                        break

            if should_discard: continue

            result_lines.append(processed_line)

        final_text = "\n".join(result_lines)
        print(f"✂️ [UltraFilter] 输入 {len(raw_lines)} 行 -> 输出 {len(result_lines)} 行")
        return (final_text,)

NODE_CLASS_MAPPINGS = {
    "buding_UltraTextLineFilter": UltraTextLineFilter
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_UltraTextLineFilter": "✂️ Ultra Line Filter (究极行筛选)"
}