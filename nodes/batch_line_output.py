"""
buding_行文本输出增强版 - 支持关键词筛选、单行/多行模式、随机种子控制
作者: Buding
功能: 从文本中按不同模式输出行数据，支持多关键词筛选、范围提取、随机种子控制
     单行模式：按关键词筛选，匹配时顺序/随机选一行
     多行模式：按行号范围提取，顺序/随机输出
"""

import random
from typing import Tuple, List


def _normalize_newlines(value: str) -> str:
    """统一换行符为 \\n"""
    return value.replace("\r\n", "\n").replace("\r", "\n")


class buding_行文本输出增强版:
    """
    行文本输出增强版节点：支持多关键词筛选、单行/多行模式、随机种子
    
    功能特点：
    - UTF-8 固定编码
    - 关键词筛选：支持单/多关键词，AND/OR 模式（"、"分隔）
    - 单行模式：按关键词筛选，无匹配或禁用随机时返回第一行；启用随机时随机选一行
    - 多行模式：按行索引范围提取，禁用随机按顺序输出；启用随机从范围内随机抽取
    - 随机种子控制：randomize=启用 自动生成，randomize=禁用 使用指定 seed
    - 智能回退：范围内不足时可选回退到全部行
    - 自动移除空行（无法关闭，默认行为）
    - 双输出：文本 + 统计日志
    """
    
    CATEGORY = "Buding/TextStory/文本处理"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("文本输出", "统计日志")
    FUNCTION = "output_lines"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_text": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "文本框输入（支持多行文本）"
                }),
                "output_mode": (["单行输出", "多行输出"], {
                    "default": "多行输出",
                    "tooltip": "单行输出=按关键词筛选输出一行；多行输出=按行号范围输出"
                }),
                "keyword_filter": ("STRING", {
                    "default": "",
                    "tooltip": "关键词过滤 - 单关键词：如 'ABC' | 多关键词 AND/OR 模式：用'、'分隔，如 'ABC、DEF' | 留空=所有行"
                }),
                "keyword_filter_mode": (["AND", "OR"], {
                    "default": "AND",
                    "tooltip": "AND=所有关键词都必须出现；OR=任意关键词出现即可"
                }),
                "start_line": ("INT", {
                    "default": 0,
                    "min": 0,
                    "tooltip": "【多行模式】起始行索引（0-based，0表示第一行）"
                }),
                "max_lines": ("INT", {
                    "default": 10,
                    "min": 0,
                    "max": 10000,
                    "tooltip": "【多行模式】最大输出行数（0=无限制，取范围内所有行）"
                }),
                "fallback_to_all": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "范围内行数不足时，是否回退到全部筛选行"
                }),
                "randomize": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "启用后自动生成随机种子"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子（randomize 禁用时生效；0=不使用随机）"
                }),
            }
        }
    
    def output_lines(self, file_text: str, output_mode: str, keyword_filter: str,
                     keyword_filter_mode: str, start_line: int, max_lines: int,
                     fallback_to_all: bool, randomize: bool, seed: int) -> Tuple[str, str]:
        """
        主处理函数
        """
        # 设置随机种子
        if randomize or seed == 0:
            used_seed = random.randint(1, 2147483647)
        else:
            used_seed = seed
        
        random.seed(used_seed)
        
        # 标准化换行符
        file_text = _normalize_newlines(file_text)
        
        # 读取所有行并移除空行
        all_lines = [line for line in file_text.split('\n') if line.strip()]
        total_lines = len(all_lines)
        
        if total_lines == 0:
            log = "统计日志：文本为空或全为空行\n扫描行数: 0\n输出行数: 0"
            return "", log
        
        # 第一步：按关键词筛选
        filtered_lines = self._filter_by_keywords(all_lines, keyword_filter, keyword_filter_mode)
        filtered_count = len(filtered_lines)
        
        if filtered_count == 0:
            log = self._generate_log(
                total_lines=total_lines,
                filtered_lines=0,
                output_lines=0,
                mode=output_mode,
                fallback=False
            )
            return "", log
        
        # 单行模式
        if output_mode == "单行输出":
            return self._single_line_mode(filtered_lines, total_lines, filtered_count, randomize)
        
        # 多行模式
        else:
            return self._multi_line_mode(filtered_lines, start_line, max_lines, 
                                        fallback_to_all, total_lines, filtered_count, randomize)
    
    def _filter_by_keywords(self, lines: List[str], keyword_filter: str, mode: str) -> List[str]:
        """
        按关键词筛选行
        """
        if not keyword_filter:
            return lines
        
        # 分割关键词
        keywords = [kw.strip() for kw in keyword_filter.split("、") if kw.strip()]
        
        if not keywords:
            return lines
        
        filtered = []
        for line in lines:
            if mode == "AND":
                # AND 模式：所有关键词都必须出现
                if all(kw in line for kw in keywords):
                    filtered.append(line)
            else:  # OR
                # OR 模式：任意关键词出现即可
                if any(kw in line for kw in keywords):
                    filtered.append(line)
        
        return filtered
    
    def _single_line_mode(self, filtered_lines: List[str], total_lines: int, 
                         filtered_count: int, randomize: bool) -> Tuple[str, str]:
        """
        单行模式：返回一行文本
        """
        if randomize:
            # 随机模式：从筛选行中随机选一行
            selected_line = random.choice(filtered_lines)
        else:
            # 顺序模式：返回第一行
            selected_line = filtered_lines[0]
        
        output_count = 1
        
        log = self._generate_log(
            total_lines=total_lines,
            filtered_lines=filtered_count,
            output_lines=output_count,
            mode="单行"
        )
        
        return selected_line, log
    
    def _multi_line_mode(self, filtered_lines: List[str], start_line: int, max_lines: int,
                         fallback_to_all: bool, total_lines: int, filtered_count: int,
                         randomize: bool) -> Tuple[str, str]:
        """
        多行模式：按范围提取行
        """
        # 使用 0-based 索引处理范围
        start_idx = max(0, start_line)
        
        # 计算范围内的行
        if max_lines == 0:
            # 无限制，取从 start_line 到末尾的所有行
            range_lines = filtered_lines[start_idx:]
        else:
            # 有限制，取 [start_idx, start_idx + max_lines)
            end_idx = min(start_idx + max_lines, len(filtered_lines))
            range_lines = filtered_lines[start_idx:end_idx]
        
        range_count = len(range_lines)
        fallback_used = False
        
        # 处理范围内不足的情况
        if range_count == 0:
            if fallback_to_all:
                range_lines = filtered_lines
                range_count = len(filtered_lines)
                fallback_used = True
            else:
                log = self._generate_log(
                    total_lines=total_lines,
                    filtered_lines=filtered_count,
                    output_lines=0,
                    mode="多行",
                    fallback=False
                )
                return "", log
        
        # 根据 randomize 决定输出方式
        if randomize:
            # 随机模式：从范围内随机选择行
            select_count = min(max_lines if max_lines > 0 else range_count, len(range_lines))
            if select_count > 0:
                selected_lines = random.sample(range_lines, min(select_count, len(range_lines)))
            else:
                selected_lines = []
        else:
            # 顺序模式：按顺序返回范围内的行
            selected_lines = range_lines
        
        output_text = '\n'.join(selected_lines)
        output_count = len(selected_lines)
        
        log = self._generate_log(
            total_lines=total_lines,
            filtered_lines=filtered_count,
            output_lines=output_count,
            mode="多行",
            fallback=fallback_used
        )
        
        return output_text, log
    
    def _generate_log(self, total_lines: int, filtered_lines: int, output_lines: int,
                      mode: str, fallback: bool = False) -> str:
        """
        生成统计日志
        """
        log_lines = [
            "=" * 50,
            f"【{mode}模式】统计日志",
            "=" * 50,
            f"扫描行数: {total_lines}",
            f"筛选行数: {filtered_lines}",
            f"输出行数: {output_lines}",
        ]
        
        if fallback:
            log_lines.append("状态: 已回退到全部筛选行")
        
        log_lines.append("=" * 50)
        
        return '\n'.join(log_lines)


NODE_CLASS_MAPPINGS = {
    "buding_行文本输出增强版": buding_行文本输出增强版,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_行文本输出增强版": "buding_行文本输出增强版",
}
