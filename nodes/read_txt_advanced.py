"""
buding_读取TXT文件增强版 - 支持目录扫描、多关键词AND模式过滤、多种输出模式
作者: Buding
功能: 从目录中读取TXT文件，支持单/多关键词过滤、按前缀提取单行或多行批量输出
     多关键词用"、"分割，AND逻辑（所有关键词都必须在文件名中出现）
"""

import os
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any


def _normalize_newlines(value: str) -> str:
    """统一换行符为 \n"""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _split_filename_keywords(value: str) -> List[str]:
    if not value:
        return []
    parts = [kw.strip() for kw in value.split("、") if kw.strip()]
    return parts


def _match_filename_keywords(filename: str, keywords: List[str], match_mode: str) -> bool:
    if not keywords:
        return True
    if match_mode == "精准匹配":
        stem = Path(filename).stem
        return all(kw == stem for kw in keywords)
    return all(kw in filename for kw in keywords)


def _is_separator_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    parts = stripped.split()
    if len(parts) < 10:
        return False
    return all(part in {"◆", "◇"} for part in parts)


class buding_读取TXT文件增强版:
    """
    增强版TXT读取节点：支持目录扫描、文件过滤、灵活的输出模式
    
    功能特点：
    - UTF-8固定编码，无需用户选择
    - 支持目录扫描，可控制扫描深度（0-10层）
    - 文件名关键词过滤：支持单关键词或多关键词 AND 模式
      * 单关键词：如 "动漫" 匹配包含"动漫"的文件
      * 多关键词：用"、"分隔，如 "动漫、前缀" 匹配同时包含"动漫"和"前缀"的文件
      * AND 逻辑：所有关键词都必须在文件名中，顺序无关
    - 两种输出模式：单行输出（按前缀提取）、多行输出（按行号范围）
    - 自动移除空行（无法关闭，默认行为）
    - 双输出：文本 + 统计日志
    """
    
    CATEGORY = "Buding/TextStory/文本处理"
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("文本输出", "统计日志", "标题输出")
    FUNCTION = "read_advanced"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory_path": ("STRING", {
                    "default": "output/文本保存",
                    "tooltip": "文件夹路径（绝对或相对路径）"
                }),
                "scan_depth": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 10,
                    "tooltip": "扫描深度：0=仅当前目录，1=含1层子目录，以此类推"
                }),
                "filename_keyword": ("STRING", {
                    "default": "",
                    "tooltip": "文件名关键词过滤 - 单关键词：如 'ABC' | 多关键词 AND 模式：用'、'分隔，如 'ABC、DEF'（同时包含ABC和DEF）| 留空=所有.txt文件"
                }),
                "output_mode": (["单行输出", "多行输出"], {
                    "default": "多行输出",
                    "tooltip": "单行输出=按前缀提取；多行输出=按行号范围提取"
                }),
                "prefix_text": ("STRING", {
                    "default": "",
                    "tooltip": "【单行模式】前缀文本（如'1.'），提取该前缀后的内容"
                }),
                "start_line": ("INT", {
                    "default": 0,
                    "min": 0,
                    "tooltip": "【多行模式】起始行索引（0-based，0表示第一行）"
                }),
                "max_lines": ("INT", {
                    "default": 100,
                    "min": 1,
                    "max": 10000,
                    "tooltip": "【多行模式】最大输出行数（0表示无限制）"
                }),
                "always_reload": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "开启后始终重新读取（绕过ComfyUI缓存；用于你修改TXT后也能立即生效）"
                }),
                "filter_header_mode": (["不开启", "模式1：第一个空行", "模式2：最后一个空行"], {
                    "default": "不开启",
                    "tooltip": "过滤标题模式：模式1识别第一个空行以上为标题；模式2识别最后一个空行以上为标题"
                }),
                "filter_separator": ("BOOLEAN", {"default": False, "tooltip": "开启后仅输出最后两条分隔行之间的内容"}),
                "filename_match_mode": (["包含匹配", "精准匹配"], {"default": "包含匹配", "tooltip": "匹配方式：包含=只要关键词出现即可；精准=文件名（不含扩展名）需完全等于关键词"}),
            }
        }

    @classmethod
    def IS_CHANGED(
        cls,
        directory_path: str,
        scan_depth: int,
        filename_keyword: str,
        output_mode: str,
        prefix_text: str,
        start_line: int,
        max_lines: int,
        always_reload: bool = False,
        filter_header_mode: str = "不开启",
        filter_separator: bool = False,
        **kwargs,
    ):
        if always_reload:
            return float("nan")

        key_params = {
            "directory_path": directory_path,
            "scan_depth": scan_depth,
            "filename_keyword": filename_keyword,
            "output_mode": output_mode,
            "prefix_text": prefix_text,
            "start_line": start_line,
            "max_lines": max_lines,
            "filter_header_mode": filter_header_mode,
            "filter_separator": filter_separator,
            "filename_match_mode": filename_match_mode,
        }
        return hash(frozenset(key_params.items()))
    
    def _scan_txt_files(self, directory: Path, keyword: str = "", max_depth: int = 0,
                        current_depth: int = 0, match_mode: str = "包含匹配") -> List[Path]:
        """
        递归扫描目录下的TXT文件
        
        Args:
            directory: 目录路径
            keyword: 文件名关键词过滤
            max_depth: 最大扫描深度
            current_depth: 当前扫描深度
            
        Returns:
            符合条件的TXT文件列表
        """
        files = []
        
        if not directory.exists() or not directory.is_dir():
            return files
        
        try:
            for item in directory.iterdir():
                if item.is_file() and item.suffix.lower() == ".txt":
                    if keyword:
                        keywords = _split_filename_keywords(keyword)
                        if _match_filename_keywords(item.name, keywords, match_mode):
                            files.append(item)
                    else:
                        files.append(item)
                
                elif item.is_dir() and current_depth < max_depth:
                    # 递归扫描子目录
                    sub_files = self._scan_txt_files(item, keyword, max_depth, current_depth + 1)
                    files.extend(sub_files)
        except (PermissionError, OSError) as e:
            pass  # 忽略权限错误
        
        return files

    def _read_file_lines(self, file_path: Path, keep_empty_lines: bool = False) -> Tuple[List[str], str]:
        """
        读取文件，可选择是否保留空行
        
        Args:
            file_path: 文件路径
            keep_empty_lines: 是否保留空行
            
        Returns:
            (行列表, 读取状态信息)
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            normalized = _normalize_newlines(content)
            
            # 分割行
            all_lines = normalized.split("\n")
            
            if keep_empty_lines:
                # 保留所有行，只去除首尾空白
                lines = [line.rstrip() for line in all_lines]
            else:
                # 移除空行（原有逻辑）
                lines = [line.strip() for line in all_lines if line.strip()]
            
            return lines, f"✓ 读取成功（原始{len(all_lines)}行，有效{len(lines)}行）"
        except Exception as e:
            return [], f"✗ 读取失败：{str(e)}"
    
    def _extract_by_prefix(self, lines: List[str], prefix: str) -> Tuple[str, Dict[str, int]]:
        """
        按前缀提取单行内容
        
        Args:
            lines: 行列表
            prefix: 前缀文本（如"1."）
            
        Returns:
            (提取的文本, 统计信息字典)
        """
        stats = {
            "scanned_lines": len(lines),
            "matched_lines": 0,
            "output_lines": 0,
        }
        
        if not prefix:
            return "", stats
        
        # 查找以前缀开头的行
        for line in lines:
            if line.startswith(prefix):
                # 提取前缀后的文本
                content = line[len(prefix):].lstrip()
                stats["matched_lines"] = 1
                stats["output_lines"] = 1
                return content, stats
        
        return "", stats
    
    def _extract_by_range(self, lines: List[str], start_line: int = 0, max_lines: int = 0) -> Tuple[str, Dict[str, int]]:
        """
        按行号范围提取多行内容
        
        Args:
            lines: 行列表
            start_line: 起始行索引（0-based，0表示第一行）
            max_lines: 最大行数（0表示无限制）
            
        Returns:
            (提取的文本, 统计信息字典)
        """
        stats = {
            "scanned_lines": len(lines),
            "matched_lines": len(lines),
            "output_lines": 0,
            "last_file_name": "",
            "last_file_line": 0
        }
        
        # 使用 0-based 索引直接处理
        start_idx = max(0, start_line)
        
        # 确定结束位置
        if max_lines <= 0:
            # 无限制
            selected_lines = lines[start_idx:]
        else:
            end_idx = start_idx + max_lines
            selected_lines = lines[start_idx:end_idx]
        
        stats["output_lines"] = len(selected_lines)
        output_text = "\n".join(selected_lines)
        
        return output_text, stats
    
    def _filter_header_content_v2(self, dir_path: Path, filename_keyword: str, scan_depth: int,
                                  mode: str, match_mode: str) -> Tuple[List[str], str]:
        """
        过滤标题内容 v2：支持两种模式
        Mode 1: 过滤掉第一个空行以上的内容
        Mode 2: 过滤掉最后一个空行以上的内容
        """
        if mode == "不开启":
            return None, ""

        filtered_lines = []
        header_lines = []
        
        txt_files = self._scan_txt_files(
            dir_path,
            keyword=filename_keyword.strip(),
            max_depth=scan_depth,
            match_mode=match_mode
        )
        
        for file_path in sorted(txt_files):
            lines, status = self._read_file_lines(file_path, keep_empty_lines=True)
            
            target_idx = -1
            if mode == "模式1：第一个空行":
                for i, line in enumerate(lines):
                    if line.strip() == "":
                        target_idx = i
                        break
            elif mode == "模式2：最后一个空行":
                for i in range(len(lines) - 1, -1, -1):
                    if lines[i].strip() == "":
                        target_idx = i
                        break
            
            if target_idx >= 0:
                header_lines.extend(lines[:target_idx])
                content_lines = lines[target_idx + 1:]
            else:
                content_lines = lines
            
            content_lines = [line for line in content_lines if line.strip()]
            filtered_lines.extend(content_lines)
        
        header_content = "\n".join(header_lines).strip()
        return filtered_lines, header_content
    
    def _generate_log(
        self,
        mode: str,
        scanned_count: int,
        stats: Dict[str, Any],
        file_count: int = 1,
        file_names: List[str] | None = None,
        directory: Path | None = None,
    ) -> str:
        """
        生成统计日志
        """
        names = file_names or []
        dir_str = str(directory) if directory else ""
        
        # 限制文件名显示数量
        max_display = 20
        display_names = names[:max_display]
        
        name_list_str = ""
        for i, name in enumerate(display_names):
            name_list_str += f"   {i+1:02d}. {name}\n"
        
        if len(names) > max_display:
            name_list_str += f"   ... (还有 {len(names) - max_display} 个文件未显示)\n"

        log = (
            f"📥 批量读取统计 | ✅ 文件总数: {file_count}\n"
            f"📂 根目录: {dir_str}\n"
            f"📉 数据量: 扫描 {scanned_count} 行 -> 筛选输出 {stats.get('output_lines', 0)} 行\n"
            f"----------------------------------------\n"
            f"🏷️ 文件名清单 (前 {max_display} 个):\n"
            f"{name_list_str}"
            f"----------------------------------------\n"
            f"📍 结束位置: {stats.get('last_file_name', '未知')}\n"
            f"📌 结束行号: 第 {stats.get('last_file_line', 0)} 行 (文件内行号)"
        )
        
        return log
    
    def read_advanced(
        self,
        directory_path: str,
        scan_depth: int,
        filename_keyword: str,
        output_mode: str,
        prefix_text: str,
        start_line: int,
        max_lines: int,
        always_reload: bool,
        filter_header_mode: str = "不开启",
        filter_separator: bool = False,
        filename_match_mode: str = "包含匹配",
    ) -> Tuple[str, str, str]:
        """
        主处理函数
        
        Args:
            directory_path: 目录路径
            scan_depth: 扫描深度
            filename_keyword: 文件名关键词
            output_mode: 输出模式
            prefix_text: 前缀文本（单行模式用）
            start_line: 开始行号（多行模式用）
            max_lines: 最大行数（多行模式用）
            
        Returns:
            (文本输出, 统计日志, 标题内容)
        """
        # 扩展路径
        dir_path = Path(directory_path).expanduser()
        
        # 验证目录
        if not dir_path.exists():
            return "", f"❌ 错误: 目录不存在\n路径: {dir_path}", ""
        
        if not dir_path.is_dir():
            return "", f"❌ 错误: 输入的不是目录\n路径: {dir_path}", ""
        
        # 扫描文件
        txt_files = self._scan_txt_files(
            dir_path,
            keyword=filename_keyword.strip(),
            max_depth=scan_depth,
            match_mode=filename_match_mode
        )
        
        if not txt_files:
            keyword_info = f"（关键词: '{filename_keyword}'）" if filename_keyword else ""
            return "", f"⚠️  未找到匹配的TXT文件\n目录: {dir_path}\n{keyword_info}", ""
        
        # 读取所有文件的内容
        all_lines = []
        file_stats = [] # 改为列表存储 (文件名, 行数)
        file_names = []
        header_content = ""  # 初始化标题内容
        
        for file_path in sorted(txt_files):
            lines, status = self._read_file_lines(file_path)
            all_lines.extend(lines)
            file_stats.append((file_path.name, len(lines)))
            file_names.append(file_path.name)
        
        total_scanned = sum(count for name, count in file_stats)
        
        # 分隔行过滤逻辑 (优先级最高)
        if filter_separator:
            separator_idxs = [i for i, line in enumerate(all_lines) if _is_separator_line(line)]
            if len(separator_idxs) >= 2:
                start = separator_idxs[-2] + 1
                end = separator_idxs[-1]
                all_lines = all_lines[start:end]
            else:
                all_lines = []

        # 过滤标题（如果启用）
        if filter_header_mode != "不开启":
            v2_lines, header_content = self._filter_header_content_v2(
                dir_path,
                filename_keyword,
                scan_depth,
                filter_header_mode,
                filename_match_mode,
            )
            if v2_lines is not None:
                all_lines = v2_lines
        else:
            header_content = ""  # 未开启过滤时，标题输出为空
        
        # 根据模式提取内容
        if output_mode == "单行输出":
            if not prefix_text:
                return "", f"❌ 错误: 单行输出模式需要指定前缀文本", ""
            
            output_text, stats = self._extract_by_prefix(all_lines, prefix_text.strip())
            
            if not output_text:
                return "", (
                    f"⚠️  未找到匹配的前缀\n"
                    f"前缀: '{prefix_text}'\n"
                    f"扫描行数: {total_scanned}"
                ), ""
            
            # 计算单行模式的结束位置
            # 找到匹配行在 all_lines 中的索引
            try:
                match_idx = -1
                for i, line in enumerate(all_lines):
                    if line.startswith(prefix_text.strip()):
                        match_idx = i
                        break
                
                if match_idx >= 0:
                    curr_idx = 0
                    for f_name, f_count in file_stats:
                        if curr_idx + f_count > match_idx:
                            stats["last_file_name"] = f_name
                            stats["last_file_line"] = match_idx - curr_idx + 1
                            break
                        curr_idx += f_count
            except: pass

        else:  # 多行输出
            output_text, stats = self._extract_by_range(all_lines, start_line, max_lines)
            if not output_text:
                return "", (
                    f"⚠️  行号范围无效或超出范围\n"
                    f"起始行: {start_line}, 最大行数: {max_lines}\n"
                    f"总行数: {total_scanned}"
                )
            
            # 计算多行模式的结束位置
            last_idx = start_line + stats["output_lines"] - 1
            if last_idx >= 0 and last_idx < len(all_lines):
                curr_idx = 0
                for f_name, f_count in file_stats:
                    if curr_idx + f_count > last_idx:
                        stats["last_file_name"] = f_name
                        stats["last_file_line"] = last_idx - curr_idx + 1
                        break
                    curr_idx += f_count
        
        # 生成日志
        log = self._generate_log(
            output_mode,
            total_scanned,
            stats,
            len(txt_files),
            file_names=file_names,
            directory=dir_path,
        )
        
        return output_text, log, header_content


# 节点注册信息
NODE_CLASS_MAPPINGS = {
    "buding_读取TXT文件增强版": buding_读取TXT文件增强版,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_读取TXT文件增强版": "buding_读取TXT文件增强版",
}
