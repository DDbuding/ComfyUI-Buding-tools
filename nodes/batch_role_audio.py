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


class buding_BatchRoleAudio:
    """
    🎭🎵🎧 批量角色音频处理器 (v2.0 完整优化版)
    
    核心特性：
    - 根据文本中的标签 [s1][s2] 等自动匹配并加载音频
    - 支持 20 个角色槽位，每个对应独立的音频通道
    - 智能除噪器：自动处理 [s1]=旁白、[s1]:旁白 等格式干扰
    - 三层匹配策略：精确匹配、前缀匹配、包含匹配
    - 最小时长过滤：避免加载太短导致TTS参考不足
    - 两层随机系统：seed固定情感+random_selection真正随机
    - 详细的增强日志，显示候选文件和当前选择
    - TTL缓存机制：30秒自动过期，防止陈旧数据
    - IS_CHANGED()方法：正确通知ComfyUI何时需要重新执行
    """
    
    _path_cache = {}
    _cache_timestamp = 0
    _cache_ttl = 30

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        """
        优化后的参数结构：
        - required: 核心参数（库路径、文本、角色配置）
        - optional: 高级配置（采样率、随机性、缓存等）
        
        核心改进：roles_config 合并了 role_1-10，用户只需填写一个多行文本框
        支持换行分隔、自动注释跳过、不足10个时自动补充静音
        """
        return {
            "required": {
                "segment_text": (
                    "STRING",
                    {"multiline": True, "default": "[s1]旁白：很久很久以前...", "tooltip": "包含 [s1][s2] 等标签的文本段落"}
                ),
                "library_root": (
                    "STRING",
                    {"default": "E:/MyAudioLib", "tooltip": "音频库根目录路径"}
                ),
                "roles_config": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "[s1] 旁白\n[s2] 郑行德\n[s3] 林天羽\n[s4] 云青红",
                        "tooltip": "角色配置清单（每行一个）。格式：[s1] 角色名\n支持：空行跳过、#注释行、自动补充至20角色\n例：\n[s1] 旁白\n[s2] 主角\n# 这是注释行\n[s3] 配角\n不足20个会用静音补充"
                    }
                ),
                "scan_max_depth": (
                    "INT",
                    {"default": 3, "min": 1, "max": 10, "tooltip": "扫描音频库时的最大文件夹深度"}
                ),
                "match_mode": (
                    ["精确匹配", "前缀匹配", "包含匹配"],
                    {"default": "包含匹配", "tooltip": "精确=完全相等 | 前缀=文件名以角色名开头 | 包含=文件名包含角色名（推荐用于情感多样性）"}
                ),
                "min_duration_seconds": (
                    "FLOAT",
                    {"default": 0.5, "min": 0.0, "max": 300.0, "tooltip": "过滤掉时长小于此值的音频文件（保证TTS情感参考充分，建议≥0.5秒）"}
                ),
            },
            "optional": {
                "volume_normalization": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "启用后自动归一化音频音量到0.95峰值，避免爆音"}
                ),
                "target_sample_rate": (
                    "INT",
                    {"default": 44100, "min": 16000, "max": 48000, "tooltip": "目标采样率（Hz）。常用值：44100、48000"}
                ),
                "random_selection": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "ON=每次真随机选择不同文件 | OFF=用seed值固定选择某个情感组合"}
                ),
                "seed": (
                    "INT",
                    {"default": 0, "min": 0, "max": 0xffffffffffffffff, "tooltip": "随机种子。random_selection=OFF时：用此值固定选择｜random_selection=ON时：此参数被忽略"}
                ),
                "max_duration_seconds": (
                    "FLOAT",
                    {"default": 30.0, "min": 0.0, "tooltip": "最大音频时长（秒）。超过此长度的音频会被截断。0表示不限制"}
                ),
                "fade_ms": (
                    "INT",
                    {"default": 10, "min": 0, "max": 100, "tooltip": "淡入淡出时长（毫秒）。用于平滑音频开始和结束。0表示无淡入淡出"}
                ),
                "always_reload": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "强制重新扫描文件库，忽略30秒缓存。加新文件后勾选此项一次"}
                ),
                "debug_mode": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "启用调试输出。显示完整的扫描、匹配、过滤、选择过程。用于诊断问题"}
                ),
            }
        }

    RETURN_TYPES = tuple(["AUDIO"] * 20 + ["STRING", "INT"])
    RETURN_NAMES = tuple([f"audio_{i}" for i in range(1, 21)] + ["log_report", "used_seed"])
    FUNCTION = "process_batch_roles"
    CATEGORY = "buding_Tools/Audio"

    @classmethod
    def IS_CHANGED(cls, segment_text, library_root, scan_max_depth, match_mode, 
                   min_duration_seconds, random_selection, seed, always_reload,
                   roles_config, **kwargs):
        """
        检查输入是否改变 - 完整包含所有会影响输出的参数
        关键作用：让 ComfyUI 判断是否需要重新执行这个节点
        """
        if always_reload:
            return float("nan")  # 强制重新加载，返回 NaN 让 ComfyUI 总是执行
        
        # 使用 frozenset 哈希所有影响输出的参数
        key_params = {
            'segment_text': segment_text,
            'library_root': library_root,
            'scan_max_depth': scan_max_depth,
            'match_mode': match_mode,
            'min_duration_seconds': min_duration_seconds,
            'random_selection': random_selection,
            'seed': seed,
            'roles_config': roles_config,
        }
        return hash(frozenset(key_params.items()))

    def process_batch_roles(self, **kwargs):
        """
        核心处理函数。
        
        工作流：
        1. 解析 roles_config 多行文本框
        2. 扫描音频库（带 TTL 缓存）
        3. 循环加载各角色
        4. 生成增强日志表格
        5. 返回 10 个音频 + 日志 + 使用的种子
        """
        segment_text = kwargs.get("segment_text", "")
        library_root = kwargs.get("library_root", "").strip().strip('"\'')
        roles_config = kwargs.get("roles_config", "")
        always_reload = kwargs.get("always_reload", False)
        debug_mode = kwargs.get("debug_mode", False)
        seed = kwargs.get("seed", 0)
        random_selection = kwargs.get("random_selection", False)

        # 如果强制重新加载，清除缓存
        if always_reload:
            self._path_cache.clear()
            self._cache_timestamp = 0
            if debug_mode:
                print("[DEBUG] always_reload=True，已清除缓存")

        # 解析 roles_config 文本框
        roles_list = self._parse_roles_config(roles_config, debug_mode)
        
        if debug_mode:
            print(f"[DEBUG] 解析出 {len(roles_list)} 个角色")
            for i, (tag, name) in enumerate(roles_list, 1):
                print(f"[DEBUG]   角色{i}: {tag} -> {name}")

        # 扫描库路径（使用 TTL 缓存）
        all_audio_files = self._quick_scan(library_root, kwargs.get("scan_max_depth", 3), debug_mode)

        if debug_mode:
            print(f"[DEBUG] 库路径: {library_root}")
            print(f"[DEBUG] 扫描到 {len(all_audio_files)} 个音频文件")

        results_audio = []
        log_data = []
        total_duration = 0.0

        # 循环处理 20 个槽位（不足的用静音补充）
        for i in range(1, 21):
            audio_out = None
            status = "⚪ 跳过"
            hit_path = "-"
            dur = 0.0
            candidates = []
            selected_file = None
            role_cfg = ""

            # 如果在 roles_list 范围内，取相应配置
            if i <= len(roles_list):
                tag, name = roles_list[i - 1]
                role_cfg = f"{tag} {name}"

                if debug_mode:
                    print(f"[DEBUG] 角色 {i}: 标签={tag}, 名称={name}")

                if tag in segment_text and name:
                    # 第1步：匹配文件
                    matched_files = self._find_files(name, all_audio_files, kwargs)

                    if debug_mode:
                        print(f"[DEBUG] 角色 {i}({name}): 匹配到 {len(matched_files)} 个文件")

                    # 第2步：按最小时长过滤
                    min_dur = kwargs.get("min_duration_seconds", 0.5)
                    valid_files = self._filter_by_duration(matched_files, min_dur, debug_mode)

                    if debug_mode:
                        print(f"[DEBUG] 角色 {i}({name}): 过滤后 {len(valid_files)} 个文件（最小时长={min_dur}s）")

                    if valid_files:
                        candidates = valid_files

                        # 第3步：选择文件
                        if random_selection:
                            # 真正随机选择（不使用种子）
                            selected_file = random.choice(valid_files)
                        else:
                            # 用种子固定选择
                            random.seed(seed + i)
                            selected_file = random.choice(valid_files)

                        if debug_mode:
                            print(f"[DEBUG] 角色 {i}({name}): 选中 {os.path.basename(selected_file)}")

                        # 第4步：加载音频
                        audio_out, dur = self._load_audio_ffmpeg(selected_file, kwargs)
                        if audio_out:
                            status = "✅ 成功"
                            hit_path = os.path.basename(selected_file)
                            total_duration += dur
                        else:
                            status = "❌ 损坏"
                            hit_path = f"加载失败：{os.path.basename(selected_file)}"
                    else:
                        # 匹配到但都过滤掉了
                        status = "⚠️ 过短"
                        hit_path = f"找到 {len(matched_files)} 个，但都 <{min_dur}s"
                else:
                    if tag not in segment_text:
                        status = "⚪ 跳过"
                        hit_path = f"文本中无 {tag} 标签"

            # 智能防错：无匹配时输出静音
            if audio_out is None:
                audio_out = self._create_silent(kwargs.get("target_sample_rate", 44100))

            results_audio.append(audio_out)
            log_data.append({
                "id": i,
                "name": role_cfg,
                "status": status,
                "dur": dur,
                "path": hit_path,
                "candidates": candidates[:5],  # 最多显示5个候选
                "selected": selected_file
            })

        # 生成增强日志表格
        log_report = self._generate_enhanced_log(log_data, total_duration, seed, kwargs)

        return tuple(results_audio + [log_report, seed])

    def _parse_roles_config(self, roles_config, debug_mode=False):
        """
        解析 roles_config 多行文本框
        
        支持两种格式：
        1. 每行一个角色：
           [s1] 旁白
           [s2] 主角
        
        2. 一行多个角色（用顿号、逗号分隔）：
           [s1] 旁白、[s2] 苏尘、[s3] 系统提示音
        
        返回列表：[(tag, name), (tag, name), ...]
        
        特点：
        - 支持注释行（#开头）
        - 跳过空行
        - 自动智能除噪（= : - 等干扰字符）
        - 支持一行多个角色（自动分割）
        - 返回列表（可能少于20个，主程序会自动补充静音）
        """
        roles_list = []
        
        for line in roles_config.split('\n'):
            line = line.strip()
            
            # 跳过空行和注释行
            if not line or line.startswith('#'):
                continue
            
            # 首先尝试分割一行中的多个角色（用顿号、逗号分隔）
            # 查找所有 [sX] 模式
            role_pattern = r'\[s\d+\][^\[]*'
            matches = re.findall(role_pattern, line)
            
            if matches:
                # 一行中有多个角色
                for match_str in matches:
                    # 解析每个角色：[sX] 角色名 或 [sX]=角色名 或 [sX]:角色名
                    role_match = re.match(r"(\[s\d+\])[\s=:-]*(.*)", match_str.strip())
                    if role_match:
                        tag = role_match.group(1)
                        name = role_match.group(2).strip()
                        # 移除尾部的分隔符（顿号、逗号等）
                        name = re.sub(r'[、,，]+$', '', name).strip()
                        
                        if name:  # 只有当名字非空时才添加
                            roles_list.append((tag, name))
                            if debug_mode:
                                print(f"[DEBUG] 解析角色: {tag} -> {name}")
            elif debug_mode:
                print(f"[DEBUG] 无法解析行: {line}")
        
        if debug_mode:
            print(f"[DEBUG] 最终解析出 {len(roles_list)} 个角色")
        
        return roles_list

    def _quick_scan(self, root, depth, debug_mode=False):
        """
        快速扫描音频库，带 TTL 缓存
        缓存在 30 秒后自动过期
        """
        now = time.time()
        key = f"{root}_{depth}"
        
        # 检查缓存是否存在且未过期
        if key in self._path_cache:
            cache_age = now - self._cache_timestamp
            if cache_age < self._cache_ttl:
                if debug_mode:
                    print(f"[DEBUG] 使用缓存的文件列表（年龄: {cache_age:.1f}s）")
                return self._path_cache[key]
            else:
                if debug_mode:
                    print(f"[DEBUG] 缓存已过期（年龄: {cache_age:.1f}s > TTL: {self._cache_ttl}s），重新扫描")

        # 缓存未命中或已过期，执行扫描
        exts = {'.wav', '.mp3', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
        found = []
        if not os.path.exists(root):
            if debug_mode:
                print(f"[DEBUG] 库路径不存在: {root}")
            return found

        try:
            for r, d, files in os.walk(root):
                curr_depth = len(Path(r).relative_to(Path(root)).parts)
                if curr_depth > depth:
                    d[:] = []
                    continue
                for f in files:
                    if os.path.splitext(f)[1].lower() in exts:
                        found.append(os.path.join(r, f))
        except Exception as e:
            if debug_mode:
                print(f"[ERROR] 扫描库路径失败: {e}")
            return []

        # 更新缓存
        self._path_cache[key] = found
        self._cache_timestamp = now
        
        if debug_mode:
            print(f"[DEBUG] 扫描完成，找到 {len(found)} 个文件")
        
        return found

    def _find_files(self, name, files, kwargs):
        """
        根据角色名称查找匹配的音频文件
        支持三种匹配模式：精确匹配、前缀匹配、包含匹配
        """
        mode = kwargs.get("match_mode", "包含匹配")
        name = name.lower()
        res = []

        for f in files:
            fn = os.path.basename(f).lower()
            fn_noext = os.path.splitext(fn)[0]

            matched = False

            if mode == "精确匹配":
                # 精确匹配：文件名（去扩展名）完全相同
                if name == fn_noext:
                    matched = True
            elif mode == "前缀匹配":
                # 前缀匹配：文件名以角色名开头（最严格）
                if fn_noext.startswith(name):
                    matched = True
            else:  # 包含匹配（默认）
                # 包含匹配：文件名包含角色名（最宽松）
                if name in fn:
                    matched = True

            if matched:
                res.append(f)

        return res

    def _filter_by_duration(self, files, min_duration, debug_mode=False):
        """
        按最小时长过滤文件
        避免加载太短的音频（无法提供有效的TTS参考）
        """
        if min_duration <= 0:
            return files

        valid = []
        for f in files:
            try:
                # 使用 ffprobe 快速获取时长
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'csv=p=0', f],
                    capture_output=True, text=True, timeout=5
                )
                duration = float(result.stdout.strip())
                
                if duration >= min_duration:
                    valid.append(f)
                elif debug_mode:
                    print(f"[DEBUG] 过滤掉短音频: {os.path.basename(f)} ({duration:.2f}s < {min_duration}s)")
            except Exception as e:
                if debug_mode:
                    print(f"[DEBUG] 检测音频时长失败 {os.path.basename(f)}: {e}")
                # 检测失败时保守处理：包含这个文件
                valid.append(f)

        return valid

    def _load_audio_ffmpeg(self, path, kwargs):
        """使用 FFmpeg 加载并处理音频"""
        sr = kwargs.get("target_sample_rate", 44100)
        max_d = kwargs.get("max_duration_seconds", 30.0)
        fade_ms = kwargs.get("fade_ms", 10)

        tmp_p = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_p = tmp.name

            # 构建 FFmpeg 命令
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

            # 执行 FFmpeg
            subprocess.run(cmd, capture_output=True, check=True, timeout=15)

            # 读取转换后的 WAV 文件
            with wave.open(tmp_p, 'rb') as wf:
                audio_np = np.frombuffer(wf.readframes(-1), dtype=np.int16).astype(np.float32) / 32768.0

            # 音量标准化：峰值归一化到 0.95
            if kwargs.get("volume_normalization", True) and len(audio_np) > 0:
                peak = np.max(np.abs(audio_np))
                if peak > 0:
                    audio_np *= (0.95 / peak)

            # 转换为 ComfyUI 格式
            audio_tensor = torch.from_numpy(audio_np).unsqueeze(0).unsqueeze(0)
            return {
                "waveform": audio_tensor,
                "sample_rate": sr
            }, len(audio_np) / sr

        except Exception as e:
            print(f"[ERROR] 加载音频失败 {path}: {e}")
            return None, 0

        finally:
            # 清理临时文件
            if tmp_p and os.path.exists(tmp_p):
                try:
                    os.unlink(tmp_p)
                except:
                    pass

    def _create_silent(self, sr):
        """创建 100ms 静音张量（防错机制）"""
        samples = int(sr * 0.1)
        return {
            "waveform": torch.zeros(1, 1, samples),
            "sample_rate": sr
        }

    def _shorten_name(self, name):
        """文件名中截断：前3---后3"""
        if len(name) <= 12:
            return name
        base, ext = os.path.splitext(name)
        return f"{base[:3]}---{base[-3:]}{ext}"

    def _shorten_path(self, path, depth=3):
        """路径层级截断：只留末尾N层"""
        parts = path.replace('\\', '/').strip('/').split('/')
        if len(parts) <= depth:
            return "/" + "/".join(parts)
        return "../" + "/".join(parts[-depth:])

    def _align_text(self, text, width):
        """解决中英文混排对齐的硬核函数"""
        stext = str(text)
        # 计算中文字符数量
        count = len(re.findall(r'[\u4e00-\u9fff]', stext))
        # 实际占用宽度 = 字符长度 + 中文额外占位
        return stext.ljust(width - count)

    def _generate_enhanced_log(self, data, total, seed, kwargs):
        """
        生成简洁美观的 ASCII 表格日志
        采用"四大杀手锏"设计：
        1. 废除子列表，用 (等X个文件) 表示候选数量
        2. 使用半角符号边界，避免中文字符对齐问题
        3. 强制列宽，使用 ljust 对齐
        4. 文件名用"前3---后3"缩减，路径用末尾3层
        """
        log = "=" * 90 + "\n"
        log += "🎭 批量角色音频加载报告 [种子: %d]\n" % seed
        log += "=" * 90 + "\n\n"

        # 基础配置行
        min_dur = kwargs.get("min_duration_seconds", 0.5)
        random_sel = kwargs.get("random_selection", False)
        match_mode = kwargs.get("match_mode", "包含匹配")
        log += "配置: 模式=%s | 随机选择=%s | 最小时长=%.1fs\n\n" % (
            match_mode, 
            "ON" if random_sel else "OFF",
            min_dur
        )

        # 表头行
        log += "ID | 角色名称   | 状态   | 时长  | 命中文件          | 所在位置\n"
        log += "---|------------|--------|-------|-------------------|--------------------------\n"

        effective_count = 0
        total_dur_check = 0.0

        for d in data:
            # 提取显示名称（去掉 [sX] 和干扰字符）
            name_match = re.match(r"(\[s\d+\])[\s=:-]*(.*)", d['name'])
            show_name = (name_match.group(2) if name_match else d['name'])[:10]
            show_name = self._align_text(show_name, 12)

            # 状态和时长
            status = d['status'][:6]
            dur = d['dur']
            dur_str = ("%.1fs" % dur) if dur > 0 else "0.0s"
            dur_str = self._align_text(dur_str, 7)

            # 命中文件处理
            if d['path'] == "-":
                file_str = "[-]"
            elif d['path'].startswith("["):
                # 诊断信息：文本无标签、库无匹配等
                file_str = self._align_text(d['path'][:20], 22)
            else:
                # 真实文件：显示缩减后的名字 + 候选数量
                fname = os.path.basename(d['path'])
                short_fname = self._shorten_name(fname)
                
                if d['candidates'] and len(d['candidates']) > 1:
                    file_str = "%s (等%d个)" % (short_fname, len(d['candidates']))
                else:
                    file_str = short_fname
                
                file_str = self._align_text(file_str, 22)

            # 所在位置处理
            if d['path'] == "-" or d['path'].startswith("["):
                path_str = "-"
            else:
                path_str = self._shorten_path(d['path'], depth=3)
                path_str = self._align_text(path_str, 28)

            # 组装一行
            log += "%02d | %s | %s | %s | %s | %s\n" % (
                d['id'], show_name, status, dur_str, file_str, path_str
            )

            # 统计
            if d['status'] == "✅ 成功":
                effective_count += 1
                total_dur_check += d['dur']

        log += "---|------------|--------|-------|-------------------|--------------------------\n\n"

        # 统计行
        log += "📊 统计: %d角色已加载 | 总时长: %.2fs | 模式: %s(%s)\n" % (
            effective_count,
            total_dur_check,
            "随机选择" if random_sel else "种子固定",
            "ON" if random_sel else "OFF"
        )
        log += "💡 提示: 文件名已开启[前3---后3]缩减模式，路径仅显示末尾3层。\n"
        log += "=" * 90 + "\n"

        return log


# 节点注册
NODE_CLASS_MAPPINGS = {"buding_BatchRoleAudio": buding_BatchRoleAudio}
NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_BatchRoleAudio": "🎭🎵🎧 批量角色音频处理器(v1.5完整优化版)"
}
