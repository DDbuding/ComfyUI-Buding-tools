"""
🎭🎵 BatchRoleAudio V2 - 半自动角色音频加载器

核心改进：
1. 自动提取文本中的 [角色名]，无需手动配置 [s1] [s2]
2. 支持可选 roles_mapping（角色名→路径映射）
3. 自动在 library_root 下查找角色名文件夹（后备机制）
4. 输出字典格式 {"角色名": audio}，直接对接 IndexTTS Dynamic Emotion
5. 灵活性：可映射特殊路径，也可完全自动

版本: v2.0
日期: 2025-12-28
"""

import os
import re
import random
import torch
import numpy as np
import subprocess
import tempfile
import wave
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class BatchRoleAudioV2:
    """
    🎭🎵 批量角色音频加载器 V2（半自动版）
    
    工作流程：
    1. 自动扫描文本，提取所有 [角色名]
    2. 为每个角色查找音频：
       - 优先：roles_mapping 中的手动映射路径
       - 后备：library_root 下自动查找角色名文件夹
    3. 每个角色随机选择一个参考音频
    4. 输出字典 {"角色名": audio}，直接给 Dynamic Emotion
    
    关键特性：
    - 零编号：不再需要 [s1] [s2]，直接用中文角色名
    - 半自动：可选手动映射，也可完全自动
    - 完美对接：输出格式直接匹配 Dynamic Emotion 输入
    - 灵活扩展：支持无限个角色（不再限制20个）
    """
    
    _path_cache = {}
    _cache_timestamp = 0
    _cache_ttl = 30

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "[旁白]<开心>很久很久以前...\n[苏尘]<愤怒>你在说什么！",
                        "tooltip": "包含 [角色]<情绪>台词 格式的文本。节点会自动提取所有 [角色名]"
                    }
                ),
                "library_root": (
                    "STRING",
                    {
                        "default": "E:/音频库/",
                        "tooltip": "音频库根目录。自动模式下会在此目录下查找角色名文件夹"
                    }
                ),
                "scan_max_depth": (
                    "INT",
                    {"default": 3, "min": 1, "max": 10, "tooltip": "扫描音频库时的最大文件夹深度"}
                ),
                "match_mode": (
                    ["精确匹配", "前缀匹配", "包含匹配"],
                    {"default": "包含匹配", "tooltip": "精确=完全相等 | 前缀=文件名以角色名开头 | 包含=文件名包含角色名"}
                ),
                "min_duration_seconds": (
                    "FLOAT",
                    {"default": 0.5, "min": 0.0, "max": 300.0, "tooltip": "过滤掉时长小于此值的音频文件"}
                ),
            },
            "optional": {
                "roles_mapping": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "",
                        "tooltip": "可选：角色名→路径映射\n格式：角色名: 路径\n例：\n旁白: E:/special/narrator/\n苏尘: E:/male/angry/\n留空则完全自动查找"
                    }
                ),
                "volume_normalization": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "启用后自动归一化音频音量到0.95峰值"}
                ),
                "target_sample_rate": (
                    "INT",
                    {"default": 44100, "min": 16000, "max": 48000, "tooltip": "目标采样率（Hz）"}
                ),
                "random_selection": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "ON=每次真随机 | OFF=用seed固定"}
                ),
                "seed": (
                    "INT",
                    {"default": 0, "min": 0, "max": 0xffffffffffffffff, "tooltip": "随机种子"}
                ),
                "max_duration_seconds": (
                    "FLOAT",
                    {"default": 30.0, "min": 0.0, "tooltip": "最大音频时长（秒）。0表示不限制"}
                ),
                "fade_ms": (
                    "INT",
                    {"default": 10, "min": 0, "max": 100, "tooltip": "淡入淡出时长（毫秒）"}
                ),
                "always_reload": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "强制重新扫描文件库"}
                ),
                "debug_mode": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "启用调试输出"}
                ),
            }
        }

    RETURN_TYPES = ("ROLE_AUDIOS", "STRING")
    RETURN_NAMES = ("role_audios", "log_report")
    FUNCTION = "process_roles_v2"
    CATEGORY = "buding_Tools/Audio"

    @classmethod
    def IS_CHANGED(cls, text, library_root, roles_mapping, random_selection, seed, always_reload, **kwargs):
        if always_reload:
            return float("nan")
        
        key_params = {
            'text': text,
            'library_root': library_root,
            'roles_mapping': roles_mapping,
            'random_selection': random_selection,
            'seed': seed,
        }
        return hash(frozenset(key_params.items()))

    def process_roles_v2(self, **kwargs):
        """
        V2 核心处理流程
        """
        text = kwargs.get("text", "")
        library_root = kwargs.get("library_root", "").strip().strip('"\'')
        roles_mapping_text = kwargs.get("roles_mapping", "")
        always_reload = kwargs.get("always_reload", False)
        debug_mode = kwargs.get("debug_mode", False)
        seed = kwargs.get("seed", 0)
        random_selection = kwargs.get("random_selection", False)

        # 清除缓存
        if always_reload:
            self._path_cache.clear()
            self._cache_timestamp = 0
            if debug_mode:
                print("[V2 DEBUG] 已清除缓存")

        # 第1步：自动提取角色名
        role_names = self._extract_role_names(text, debug_mode)
        
        if debug_mode:
            print(f"[V2 DEBUG] 自动提取到 {len(role_names)} 个角色: {role_names}")

        # 第2步：解析可选的 roles_mapping
        roles_mapping_dict = self._parse_roles_mapping(roles_mapping_text, debug_mode)
        
        if debug_mode and roles_mapping_dict:
            print(f"[V2 DEBUG] 手动映射: {roles_mapping_dict}")

        # 第3步：扫描音频库（一次性）
        if debug_mode:
            print(f"[V2 DEBUG] 开始扫描音频库: {library_root}")
        
        all_audio_files = self._scan_audio_files_cached(
            library_root, 
            kwargs.get("scan_max_depth", 3),
            always_reload,
            debug_mode
        )
        
        if debug_mode:
            print(f"[V2 DEBUG] 音频库共扫描到 {len(all_audio_files)} 个文件")

        # 第4步：为每个角色匹配音频文件
        role_audios = {}
        log_data = []
        total_duration = 0.0
        match_mode = kwargs.get("match_mode", "包含匹配")

        for role_name in role_names:
            # 优先：手动映射路径
            if role_name in roles_mapping_dict:
                role_path = roles_mapping_dict[role_name]
                if os.path.exists(role_path):
                    audio_files = self._scan_audio_files(role_path, kwargs.get("scan_max_depth", 3), debug_mode)
                    if debug_mode:
                        print(f"[V2 DEBUG] 角色 '{role_name}' 使用手动映射: {role_path}, 找到 {len(audio_files)} 个文件")
                else:
                    if debug_mode:
                        print(f"[V2 WARNING] 手动映射路径不存在: {role_path}")
                    audio_files = []
            else:
                # 自动匹配：从所有文件中按文件名匹配
                audio_files = self._match_files_by_name(role_name, all_audio_files, match_mode, debug_mode)
                if debug_mode:
                    print(f"[V2 DEBUG] 角色 '{role_name}' 自动匹配到 {len(audio_files)} 个文件")

            # 过滤最小时长
            min_dur = kwargs.get("min_duration_seconds", 0.5)
            valid_files = self._filter_by_duration(audio_files, min_dur, debug_mode)

            if not valid_files:
                log_data.append({
                    "role": role_name,
                    "status": "⚠️ 无有效音频" if audio_files else "❌ 未找到",
                    "path": "-",
                    "duration": 0.0,
                    "candidates": len(audio_files)
                })
                continue

            # 选择音频文件
            if random_selection:
                selected_file = random.choice(valid_files)
            else:
                random.seed(seed + hash(role_name))
                selected_file = random.choice(valid_files)

            if debug_mode:
                print(f"[V2 DEBUG] 角色 '{role_name}' 选中: {os.path.basename(selected_file)}")

            # 加载音频
            audio_data, duration = self._load_audio_ffmpeg(selected_file, kwargs)
            
            if audio_data:
                role_audios[role_name] = audio_data
                total_duration += duration
                log_data.append({
                    "role": role_name,
                    "status": "✅ 成功",
                    "path": os.path.basename(selected_file),
                    "duration": duration,
                    "candidates": len(valid_files)
                })
            else:
                log_data.append({
                    "role": role_name,
                    "status": "❌ 加载失败",
                    "path": os.path.basename(selected_file),
                    "duration": 0.0,
                    "candidates": len(valid_files)
                })

        # 生成日志报告
        log_report = self._generate_log_report(log_data, total_duration, seed, len(role_names), kwargs)

        if debug_mode:
            print(f"[V2 DEBUG] 最终输出 {len(role_audios)} 个角色音频")

        return (role_audios, log_report)

    def _extract_role_names(self, text: str, debug_mode: bool = False) -> List[str]:
        """
        自动提取文本中的所有 [角色名]
        返回去重后的角色列表
        """
        # 正则匹配所有 [xxx] 格式
        pattern = r'\[([^\]]+)\]'
        matches = re.findall(pattern, text)
        
        # 去重并保持顺序
        seen = set()
        role_names = []
        for match in matches:
            if match not in seen:
                seen.add(match)
                role_names.append(match)
        
        if debug_mode:
            print(f"[V2 DEBUG] 提取角色: {role_names}")
        
        return role_names

    def _parse_roles_mapping(self, roles_mapping_text: str, debug_mode: bool = False) -> Dict[str, str]:
        """
        解析可选的 roles_mapping 参数
        格式：角色名: 路径
        例：
        旁白: E:/audio/narrator/
        苏尘: E:/audio/male/
        """
        mapping = {}
        
        if not roles_mapping_text.strip():
            return mapping
        
        for line in roles_mapping_text.split('\n'):
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
            
            # 解析 角色名: 路径
            if ':' in line:
                parts = line.split(':', 1)
                role_name = parts[0].strip()
                role_path = parts[1].strip().strip('"\'')
                
                if role_name and role_path:
                    mapping[role_name] = role_path
                    if debug_mode:
                        print(f"[V2 DEBUG] 映射: {role_name} → {role_path}")
        
        return mapping

    def _find_role_path(self, role_name: str, roles_mapping: Dict[str, str], 
                        library_root: str, debug_mode: bool = False) -> Optional[str]:
        """
        ⚠️ 已废弃：此方法不再使用
        新逻辑：直接扫描所有音频文件，按文件名匹配
        """
        pass

    def _scan_audio_files_cached(self, root: str, max_depth: int, force_reload: bool, debug_mode: bool = False) -> List[str]:
        """
        带缓存的音频文件扫描（TTL 30秒）
        """
        now = time.time()
        cache_key = f"{root}_{max_depth}"
        
        # 检查缓存
        if not force_reload and cache_key in self._path_cache:
            cache_age = now - self._cache_timestamp
            if cache_age < self._cache_ttl:
                if debug_mode:
                    print(f"[V2 DEBUG] 使用缓存 (年龄: {cache_age:.1f}s)")
                return self._path_cache[cache_key]
            elif debug_mode:
                print(f"[V2 DEBUG] 缓存过期 (年龄: {cache_age:.1f}s)")
        
        # 扫描文件
        files = self._scan_audio_files(root, max_depth, debug_mode)
        
        # 更新缓存
        self._path_cache[cache_key] = files
        self._cache_timestamp = now
        
        if debug_mode:
            print(f"[V2 DEBUG] 扫描完成，找到 {len(files)} 个文件")
        
        return files

    def _match_files_by_name(self, role_name: str, files: List[str], match_mode: str, debug_mode: bool = False) -> List[str]:
        """
        根据角色名匹配文件名
        支持三种模式：精确匹配、前缀匹配、包含匹配
        """
        role_name_lower = role_name.lower()
        matched = []
        
        for f in files:
            filename = os.path.basename(f).lower()
            filename_noext = os.path.splitext(filename)[0]
            
            is_match = False
            
            if match_mode == "精确匹配":
                if filename_noext == role_name_lower:
                    is_match = True
            elif match_mode == "前缀匹配":
                if filename_noext.startswith(role_name_lower):
                    is_match = True
            else:  # 包含匹配（默认）
                if role_name_lower in filename:
                    is_match = True
            
            if is_match:
                matched.append(f)
        
        if debug_mode and matched:
            print(f"[V2 DEBUG] 角色 '{role_name}' 匹配到文件示例: {os.path.basename(matched[0])}")
        
        return matched

    def _scan_audio_files(self, path: str, max_depth: int, debug_mode: bool = False) -> List[str]:
        """
        扫描指定路径下的所有音频文件
        """
        exts = {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
        found = []
        
        if not os.path.exists(path):
            return found

        try:
            for root, dirs, files in os.walk(path):
                curr_depth = len(Path(root).relative_to(Path(path)).parts)
                if curr_depth > max_depth:  # 修复：应该是 > 而不是 >=
                    dirs[:] = []
                    continue
                
                for f in files:
                    if os.path.splitext(f)[1].lower() in exts:
                        found.append(os.path.join(root, f))
        except Exception as e:
            if debug_mode:
                print(f"[V2 ERROR] 扫描失败 {path}: {e}")
        
        return found

    def _filter_by_duration(self, files: List[str], min_duration: float, debug_mode: bool = False) -> List[str]:
        """
        按最小时长过滤文件
        """
        if min_duration <= 0:
            return files

        valid = []
        for f in files:
            try:
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'csv=p=0', f],
                    capture_output=True, text=True, timeout=5
                )
                duration = float(result.stdout.strip())
                
                if duration >= min_duration:
                    valid.append(f)
                elif debug_mode:
                    print(f"[V2 DEBUG] 过滤短音频: {os.path.basename(f)} ({duration:.2f}s)")
            except Exception as e:
                if debug_mode:
                    print(f"[V2 DEBUG] 检测时长失败 {os.path.basename(f)}: {e}")
                valid.append(f)  # 保守处理

        return valid

    def _load_audio_ffmpeg(self, path: str, kwargs: dict) -> Tuple[Optional[dict], float]:
        """
        使用 FFmpeg 加载音频
        返回: (audio_dict, duration)
        """
        sr = kwargs.get("target_sample_rate", 44100)
        max_d = kwargs.get("max_duration_seconds", 30.0)
        fade_ms = kwargs.get("fade_ms", 10)

        tmp_p = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_p = tmp.name

            cmd = ['ffmpeg', '-y', '-i', path]

            if max_d > 0:
                cmd.extend(['-t', str(max_d)])

            if fade_ms > 0:
                f = fade_ms / 1000.0
                fade_out_start = max(0, max_d - f) if max_d > 0 else 1
                cmd.extend([
                    '-af',
                    f'afade=t=in:st=0:d={f},afade=t=out:st={fade_out_start}:d={f}'
                ])

            cmd.extend(['-ar', str(sr), '-ac', '1', '-f', 'wav', tmp_p])

            subprocess.run(cmd, capture_output=True, check=True, timeout=15)

            with wave.open(tmp_p, 'rb') as wf:
                audio_np = np.frombuffer(wf.readframes(-1), dtype=np.int16).astype(np.float32) / 32768.0

            # 音量标准化
            if kwargs.get("volume_normalization", True) and len(audio_np) > 0:
                peak = np.max(np.abs(audio_np))
                if peak > 0:
                    audio_np *= (0.95 / peak)

            audio_tensor = torch.from_numpy(audio_np).unsqueeze(0).unsqueeze(0)
            return {
                "waveform": audio_tensor,
                "sample_rate": sr
            }, len(audio_np) / sr

        except Exception as e:
            print(f"[V2 ERROR] 加载音频失败 {path}: {e}")
            return None, 0

        finally:
            if tmp_p and os.path.exists(tmp_p):
                try:
                    os.unlink(tmp_p)
                except:
                    pass

    def _generate_log_report(self, log_data: List[dict], total_duration: float, 
                            seed: int, total_roles: int, kwargs: dict) -> str:
        """
        生成日志报告
        """
        log = "=" * 90 + "\n"
        log += "🎭🎵 批量角色音频加载报告 V2 [种子: %d]\n" % seed
        log += "=" * 90 + "\n\n"

        # 配置信息
        match_mode = kwargs.get("match_mode", "包含匹配")
        random_sel = kwargs.get("random_selection", False)
        min_dur = kwargs.get("min_duration_seconds", 0.5)
        
        log += "配置: 模式=%s | 随机=%s | 最小时长=%.1fs\n" % (
            match_mode,
            "ON" if random_sel else "OFF",
            min_dur
        )
        log += "提取: 文本中发现 %d 个角色\n\n" % total_roles

        # 表头
        log += "角色名称       | 状态      | 时长    | 候选数 | 命中文件\n"
        log += "---------------|-----------|---------|--------|--------------------------\n"

        success_count = 0
        for d in log_data:
            role_name = d['role'][:12].ljust(15)
            status = d['status'][:10].ljust(10)
            dur_str = ("%.2fs" % d['duration']).ljust(8) if d['duration'] > 0 else "-".ljust(8)
            candidates = str(d['candidates']).ljust(7)
            path = d['path'][:30] if len(d['path']) <= 30 else d['path'][:27] + "..."
            
            log += "%s | %s | %s | %s | %s\n" % (role_name, status, dur_str, candidates, path)
            
            if d['status'] == "✅ 成功":
                success_count += 1

        log += "---------------|-----------|---------|--------|--------------------------\n\n"

        # 统计
        log += "📊 统计: %d/%d 角色成功加载 | 总时长: %.2fs\n" % (
            success_count, total_roles, total_duration
        )
        log += "💡 提示: 输出格式为字典 {\"角色名\": audio}，可直接连接到 IndexTTS Dynamic Emotion 节点\n"
        log += "=" * 90 + "\n"

        return log


# 节点注册
NODE_CLASS_MAPPINGS = {"buding_BatchRoleAudioV2": BatchRoleAudioV2}
NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_BatchRoleAudioV2": "🎭🎵 buding_BatchRoleAudio V2 (半自动角色音频)"
}
