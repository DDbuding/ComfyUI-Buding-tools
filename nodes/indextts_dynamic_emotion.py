"""
🎭 IndexTTS Dynamic Emotion - 动态情绪TTS生成节点
支持 [角色名]<情绪>台词 格式的文本解析和情感向量生成

放置在 buding_Tools 插件中，独立于 IndexTTS 插件
通过字符串类型匹配 "EASY_INDEXTTS_MODEL" 与 IndexTTS 插件连接
"""
import re
import json
import numpy as np
import torch
import comfy.utils

# 情绪名称到向量索引的映射
# 向量格式: [Happy, Angry, Sad, Fear, Hate, Low, Surprise, Neutral]
EMOTION_INDEX = {
    # 中文情绪名
    "开心": 0, "高兴": 0, "快乐": 0, "喜悦": 0,
    "愤怒": 1, "生气": 1, "怒": 1,
    "悲伤": 2, "难过": 2, "伤心": 2, "悲": 2,
    "恐惧": 3, "害怕": 3, "惊恐": 3,
    "厌恶": 4, "讨厌": 4, "恶心": 4, "嫌弃": 4,
    "低落": 5, "沮丧": 5, "消沉": 5,
    "惊讶": 6, "吃惊": 6, "震惊": 6,
    "平静": 7, "中性": 7, "平淡": 7,
    # 英文情绪名
    "happy": 0, "joy": 0, "pleased": 0,
    "angry": 1, "anger": 1, "mad": 1,
    "sad": 2, "sadness": 2, "sorrow": 2,
    "fear": 3, "scared": 3, "afraid": 3,
    "hate": 4, "disgust": 4, "dislike": 4,
    "low": 5, "down": 5, "depressed": 5,
    "surprise": 6, "surprised": 6, "shocked": 6,
    "neutral": 7, "calm": 7, "normal": 7,
}

# 默认情绪预设（基准值0.37，Neutral维度保持0）
DEFAULT_EMOTION_PRESETS = {
    "无情绪": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "开心": [0.37, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "愤怒": [0.0, 0.37, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "悲伤": [0.0, 0.0, 0.37, 0.0, 0.0, 0.0, 0.0, 0.0],
    "恐惧": [0.0, 0.0, 0.0, 0.37, 0.0, 0.0, 0.0, 0.0],
    "厌恶": [0.0, 0.0, 0.0, 0.0, 0.37, 0.0, 0.0, 0.0],
    "低落": [0.0, 0.0, 0.0, 0.0, 0.0, 0.37, 0.0, 0.0],
    "惊讶": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.37, 0.0],
    "平静": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
}


def process_audio_input(audio):
    """处理音频输入，转换为 (wave, sr) 格式"""
    if isinstance(audio, dict) and "waveform" in audio and "sample_rate" in audio:
        wave = audio["waveform"]
        sr = int(audio["sample_rate"])
        if isinstance(wave, torch.Tensor):
            if wave.dim() == 3:
                wave = wave[0, 0].detach().cpu().numpy()
            elif wave.dim() == 1:
                wave = wave.detach().cpu().numpy()
            else:
                wave = wave.flatten().detach().cpu().numpy()
        elif isinstance(wave, np.ndarray):
            if wave.ndim == 3:
                wave = wave[0, 0]
            elif wave.ndim == 2:
                wave = wave[0]
        return wave.astype(np.float32), sr
    elif isinstance(audio, tuple) and len(audio) == 2:
        wave, sr = audio
        if isinstance(wave, torch.Tensor):
            wave = wave.detach().cpu().numpy()
        return wave.astype(np.float32), int(sr)
    else:
        raise ValueError("AUDIO input must be ComfyUI dict or (wave, sr)")


def load_custom_presets(custom_json: str):
    """解析用户提供的自定义预设JSON，返回有效预设和警告信息。"""
    presets = {}
    warnings = []
    if not custom_json or not custom_json.strip():
        return presets, warnings
    try:
        data = json.loads(custom_json)
        if not isinstance(data, dict):
            warnings.append("custom_presets_json 需要是对象类型，例如 {\"开心\": [0.37, ...]}")
            return presets, warnings
        for key, value in data.items():
            if not isinstance(value, (list, tuple)) or len(value) != 8:
                warnings.append(f"预设 {key} 必须是长度为8的数组，已跳过")
                continue
            try:
                vec = [float(v) for v in value]
            except Exception:
                warnings.append(f"预设 {key} 包含非数字内容，已跳过")
                continue
            vec[7] = 0.0  # Neutral维度强制为0
            presets[key] = vec
    except Exception as e:
        warnings.append(f"解析 custom_presets_json 失败: {e}")
    return presets, warnings


def resolve_emotion_vector(tag: str, presets: dict, base_value: float, intensity_scale: float, custom_keys: set):
    """根据标签解析情绪向量，支持预设、自定义名称和组合标签。"""
    tag = (tag or "").strip()
    base_zero = [0.0] * 8
    if tag == "" or tag == "无情绪":
        return base_zero, "none", None, False

    # 直接命中预设（包含自定义）
    if tag in presets:
        vec = presets[tag]
        vec = [v * intensity_scale for v in vec]
        vec[7] = 0.0
        source = "custom_preset" if tag in custom_keys else "default_preset"
        return vec, source, None, True

    warnings = []
    emotion_vector = [0.0] * 8
    recognized = False

    # 组合解析：情绪名 + 可选强度，支持 '+' 连接
    parts = tag.split("+")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = re.match(r"([a-zA-Z\u4e00-\u9fff:_\-]+)([\d.]*)", part)
        if not match:
            warnings.append(f"未识别的情绪片段: {part}")
            continue
        name = match.group(1)
        value_str = match.group(2)

        if name in presets:
            vec = presets[name]
            emotion_vector = [max(a, b) for a, b in zip(emotion_vector, vec)]
            recognized = True
            continue

        name_key = name.lower()
        if name_key in EMOTION_INDEX:
            idx = EMOTION_INDEX[name_key]
            try:
                val = float(value_str) if value_str else base_value
            except Exception:
                val = base_value
            emotion_vector[idx] = max(emotion_vector[idx], val)
            recognized = True
        else:
            warnings.append(f"未识别的情绪名称: {name}")

    if not recognized:
        return base_zero, "unrecognized", warnings or ["标签未被识别，已使用0向量"], False

    emotion_vector = [v * intensity_scale for v in emotion_vector]
    emotion_vector[7] = 0.0
    return emotion_vector, "parsed", warnings if warnings else None, True


def parse_dynamic_text(text: str):
    """
    解析动态情绪文本格式
    支持格式: [角色名]<情绪>台词
    """
    segments = []
    lines = text.strip().split('\n')
    for i, line in enumerate(lines):
        raw_line = line
        line = line.strip()
        if not line:
            continue

        pause_match = re.match(r'^-(\d+(?:\.\d+)?)s-$', line)
        if pause_match:
            pause_duration = float(pause_match.group(1))
            segments.append({
                "type": "pause",
                "duration": pause_duration,
                "src_line": i + 1
            })
            continue

        pattern = r'^\[([^\]]+)\](?:<([^>]*)>)?(.*)$'
        match = re.match(pattern, line)

        if match:
            role_name = match.group(1).strip()
            emotion_tag = match.group(2) or ""
            dialog_text = match.group(3).strip()
            segments.append({
                "type": "dialog",
                "role": role_name,
                "emotion_tag": emotion_tag,
                "text": dialog_text,
                "src_line": i + 1
            })
        else:
            segments.append({
                "type": "dialog",
                "role": "__DEFAULT__",
                "emotion_tag": "",
                "text": line,
                "src_line": i + 1
            })
    return segments


def _parse_name_list(raw: str):
    return {name.strip() for name in (raw or "").split("、") if name.strip()}


def _parse_line_selectors(raw: str):
    selected = set()
    warnings = []
    for token in [t.strip() for t in (raw or "").split("、") if t.strip()]:
        if "-" in token:
            try:
                start_str, end_str = token.split("-", 1)
                start = int(start_str)
                end = int(end_str)
                if start > end:
                    start, end = end, start
                selected.update(range(start, end + 1))
            except Exception:
                warnings.append(f"无法解析段落范围: {token}")
        else:
            try:
                selected.add(int(token))
            except Exception:
                warnings.append(f"无法解析段落编号: {token}")
    return selected, warnings


class buding_IndexTTSDynamicEmotion:
    """
    🎭 IndexTTS Dynamic Emotion - 动态情绪TTS生成
    
    支持格式: [角色名]<情绪>台词
    - 角色名: 与 ROLE_AUDIOS 字典中的键匹配
    - 情绪: 支持中英文情绪名，可组合，可设强度
    - 台词: 要合成的文本内容
    
    示例:
    [旁白]<平静>这是一个美好的早晨。
    [小明]<开心>今天天气真不错！
    [小红]<愤怒0.8+惊讶0.3>你怎么又迟到了？
    -2s-
    [小明]<悲伤>对不起...
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "indextts_model": ("EASY_INDEXTTS_MODEL", {
                    "tooltip": "IndexTTS模型加载器输出的模型句柄"
                }),
                "role_audios": ("ROLE_AUDIOS", {
                    "tooltip": "批量角色音频输出的角色字典，键=角色名，值=参考音频"
                }),
                "default_role": ("STRING", {
                    "default": "旁白",
                    "multiline": False,
                    "tooltip": "默认角色名：当文本未指定角色或角色未找到时使用"
                }),
                "text": ("STRING", {
                    "multiline": True,
                    "default": "[旁白]<平静>这是示例文本。\n[角色A]<开心>你好！",
                    "tooltip": "按行输入：[角色]<情绪>台词；停顿写 -1.5s-"
                }),
                "base_emotion": ("FLOAT", {
                    "default": 0.37,
                    "min": 0.1,
                    "max": 1.4,
                    "step": 0.01,
                    "display": "slider",
                    "tooltip": "基础情绪强度(安全值)，配合情绪名或解析用"
                }),
                "emotion_intensity": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 4.0,
                    "step": 0.05,
                    "display": "slider",
                    "tooltip": "全局情绪强度倍数(0.5内敛,1默认,2-3强烈)"
                }),
                "emo_weight": ("FLOAT", {
                    "default": 0.6,
                    "min": 0.0,
                    "max": 1.6,
                    "step": 0.05,
                    "display": "slider",
                    "tooltip": "IndexTTS情绪影响权重(0=忽略情绪,0.6保守推荐,1.6极强)"
                }),
                "default_emotion": ("STRING", {
                    "default": "无情绪",
                    "multiline": False,
                    "tooltip": "未标注行使用的情绪(例如 无情绪/开心/悲伤/自定义预设名)"
                }),
                "include_roles": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "仅生成指定角色，多个角色用“、”分隔；留空表示全部"
                }),
                "exclude_roles": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "排除角色，多个角色用“、”分隔；优先级高于指定角色"
                }),
                "include_segments": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "仅生成指定段落，支持逗号格式如 1、3、5 或范围 3-6"
                }),
                "custom_presets_json": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "tooltip": "自定义情绪预设JSON，键=情绪名，值=8维数组；Neutral维度会强制为0"
                }),
                "sampling_preset": (["自定义", "平衡", "稳定", "创意", "极速"], {
                    "default": "自定义",
                    "tooltip": "采样预设：平衡/稳定/创意/极速，一键覆盖采样参数；自定义则使用下方手动参数"
                }),
                "unload_model": ("BOOLEAN", {"default": False, "tooltip": "生成后是否卸载模型以省显存（频繁生成建议关闭以免反复加载）"}),
                "do_sample": ("BOOLEAN", {"default": True, "tooltip": "采样开关：开=采样(配合temp/top_p)，关=贪心/beam为主更稳"}),
                "temperature": ("FLOAT", {"default": 0.8, "min": 0.1, "max": 2.0, "step": 0.05, "tooltip": "采样温度：小=稳定, 大=多样"}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "核采样阈值：0.9默认，低值更稳"}),
                "top_k": ("INT", {"default": 30, "min": 0, "max": 100, "step": 1, "tooltip": "top-k采样：0关闭, 30默认"}),
                "num_beams": ("INT", {"default": 3, "min": 1, "max": 10, "step": 1, "tooltip": "beam search数量：大=更稳但更慢"}),
                "repetition_penalty": ("FLOAT", {"default": 10.0, "min": 1.0, "max": 10.0, "step": 0.1, "tooltip": "重复惩罚：大值避免啰嗦"}),
                "length_penalty": ("FLOAT", {"default": 0.0, "min": -2.0, "max": 2.0, "step": 0.1, "tooltip": "长度惩罚：>0更短，<0更长"}),
                "max_mel_tokens": ("INT", {
                    "default": 1815,
                    "min": 50,
                    "max": 1815,
                    "step": 5,
                    "tooltip": "Mel长度上限：1815为官方上限；长句/歌曲可 1500-1815；追求速度可 800-1200（可能截断）"
                }),
                "max_tokens_per_sentence": ("INT", {
                    "default": 120,
                    "min": 0,
                    "max": 600,
                    "step": 5,
                    "tooltip": "文本token上限：普通句子 80-150；长句对白 150-300；极长台词可 300-600，但速度会下降"
                }),
                "speech_speed": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05, "tooltip": "语速倍率：0.8慢语速，1.0正常，1.2快"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffff, "tooltip": "随机种子：0为随机，可填固定值复现结果"}),
            }
        }

    RETURN_TYPES = ("AUDIO", "AUDIOS", "INT", "STRING", "STRING")
    RETURN_NAMES = ("merged_audio", "audio_list", "seed", "subtitle", "emotion_log")
    FUNCTION = "generate"
    CATEGORY = "buding_Tools/TTS"
    
    def generate(self, indextts_model, role_audios, default_role, text, base_emotion,
                 emotion_intensity, emo_weight, default_emotion, include_roles,
                 exclude_roles, include_segments, custom_presets_json,
                 sampling_preset, unload_model, do_sample, temperature, top_p,
                 top_k, num_beams, repetition_penalty, length_penalty,
                 max_mel_tokens, max_tokens_per_sentence, speech_speed,
                 seed):

        segments = parse_dynamic_text(text)

        if not segments:
            raise ValueError("没有找到有效的文本段落")

        include_roles_set = _parse_name_list(include_roles)
        exclude_roles_set = _parse_name_list(exclude_roles)
        include_lines_set, selector_warnings = _parse_line_selectors(include_segments)

        specified_mode_skip_pause = bool(include_roles_set) or bool(include_lines_set)

        # 角色匹配统计（用于日志/报告）：在“段落筛选(include_segments)”后、在“角色过滤(include/exclude)”前统计
        roles_in_text = set()
        for seg in segments:
            src_line = seg.get("src_line", 0)
            if include_lines_set and src_line not in include_lines_set:
                continue
            if seg.get("type") != "dialog":
                continue
            role_name = seg.get("role") or "__DEFAULT__"
            resolved_role = default_role if role_name == "__DEFAULT__" else role_name
            roles_in_text.add(resolved_role)

        matched_roles = {r for r in roles_in_text if r in role_audios}
        missing_roles = sorted([r for r in roles_in_text if r not in role_audios])

        if roles_in_text:
            print(
                f"角色匹配(段落筛选后): {len(matched_roles)}/{len(roles_in_text)} | "
                f"匹配角色: {', '.join(sorted(matched_roles)) if matched_roles else '无'}"
            )
            if missing_roles:
                print(f"未找到角色(将回退默认角色): {', '.join(missing_roles)}")

        custom_presets, preset_warnings = load_custom_presets(custom_presets_json)
        presets = {**DEFAULT_EMOTION_PRESETS, **custom_presets}
        custom_keys = set(custom_presets.keys())

        stats = {
            "dialog_count": 0,
            "pause_count": 0,
            "custom_hit": 0,
            "default_hit": 0,
            "raw_voice_hit": 0,
            "matched_roles": matched_roles,
            "loaded_roles": set(),
            "unrecognized": [],
            "warnings": preset_warnings[:] + selector_warnings,
            "total_time": 0.0,
        }

        filtered_segments = []
        for seg in segments:
            src_line = seg.get("src_line", 0)
            if include_lines_set and src_line not in include_lines_set:
                continue

            if seg["type"] != "dialog":
                if specified_mode_skip_pause and seg.get("type") == "pause":
                    continue
                filtered_segments.append(seg)
                continue

            role_name = seg.get("role") or "__DEFAULT__"
            resolved_role = default_role if role_name == "__DEFAULT__" else role_name

            if exclude_roles_set and resolved_role in exclude_roles_set:
                continue
            if include_roles_set and resolved_role not in include_roles_set:
                continue

            seg_copy = dict(seg)
            seg_copy["role"] = resolved_role
            filtered_segments.append(seg_copy)

        segments = filtered_segments

        if not segments:
            raise ValueError("过滤后没有可生成的段落")

        # 预加载/缓存：仅对本次实际会用到的角色做一次 process_audio_input，并缓存到内存（CPU）
        roles_to_load = set()
        for seg in segments:
            if seg.get("type") != "dialog":
                continue
            role_name = seg.get("role") or default_role
            # 若缺失则在生成时回退 default_role，这里也尽量对 default_role 做预加载
            if role_name in role_audios:
                roles_to_load.add(role_name)
            else:
                roles_to_load.add(default_role)

        if include_roles_set or exclude_roles_set or include_lines_set:
            filter_notes = []
            if include_roles_set:
                filter_notes.append(f"仅角色={ '、'.join(sorted(include_roles_set)) }")
            if exclude_roles_set:
                filter_notes.append(f"排除角色={ '、'.join(sorted(exclude_roles_set)) }")
            if include_lines_set:
                filter_notes.append(f"段落={ '、'.join(str(i) for i in sorted(include_lines_set)) }")
            print(f"筛选条件: {' | '.join(filter_notes)}")

        print(
            f"实际将加载角色({len(roles_to_load)}): "
            f"{', '.join(sorted(roles_to_load)) if roles_to_load else '无'}"
        )

        ref_audio_cache = {}
        for role_name in sorted(roles_to_load):
            if role_name not in role_audios:
                raise ValueError(f"角色 '{role_name}' 不存在于 role_audios，且无法回退")
            print(f"预加载角色音色: {role_name}")
            ref_audio_cache[role_name] = process_audio_input(role_audios[role_name])

        stats["loaded_roles"] = set(ref_audio_cache.keys())

        sampling_presets = {
            "平衡": {
                "temperature": 0.8,
                "top_p": 0.9,
                "top_k": 30,
                "num_beams": 3,
                "repetition_penalty": 10.0,
                "length_penalty": 0.0,
                "note": "通用平衡"
            },
            "稳定": {
                "temperature": 0.6,
                "top_p": 0.85,
                "top_k": 20,
                "num_beams": 4,
                "repetition_penalty": 8.0,
                "length_penalty": 0.2,
                "note": "更保守防跑偏"
            },
            "创意": {
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 50,
                "num_beams": 1,
                "repetition_penalty": 7.0,
                "length_penalty": -0.1,
                "note": "更多样但略不稳"
            },
            "极速": {
                "temperature": 0.8,
                "top_p": 0.9,
                "top_k": 0,
                "num_beams": 1,
                "repetition_penalty": 8.0,
                "length_penalty": 0.0,
                "note": "少beam少top_k提速"
            }
        }

        # 采样参数实际值（可能被预设覆盖）
        temp_val = temperature
        top_p_val = top_p
        top_k_val = top_k
        num_beams_val = num_beams
        rep_val = repetition_penalty
        len_pen_val = length_penalty

        preset_note = "自定义"
        if sampling_preset in sampling_presets:
            p = sampling_presets[sampling_preset]
            temp_val = p["temperature"]
            top_p_val = p["top_p"]
            top_k_val = p["top_k"]
            num_beams_val = p["num_beams"]
            rep_val = p["repetition_penalty"]
            len_pen_val = p["length_penalty"]
            preset_note = f"{sampling_preset}({p['note']})"

        parse_info_lines = []
        detail_rows = []
        all_waves = []
        all_audios = []
        all_subtitles = []
        current_time = 0.0
        current_sr = None

        pbar = comfy.utils.ProgressBar(len(segments))

        dialog_counter = 0

        import time
        start_time = time.time()


        for seg_idx, segment in enumerate(segments):
            seg_start_time = time.time()
            src_line = segment.get("src_line", seg_idx + 1)
            if segment["type"] == "pause":
                if specified_mode_skip_pause:
                    pbar.update(1)
                    continue
                stats["pause_count"] += 1
                pause_duration = segment["duration"]
                sample_rate = current_sr if current_sr else 22050
                silence_samples = int(pause_duration * sample_rate)
                silence_wave = np.zeros(silence_samples, dtype=np.float32)
                silence_tensor = torch.from_numpy(silence_wave).unsqueeze(0).unsqueeze(0)

                all_waves.append(silence_wave)
                all_audios.append({
                    "waveform": silence_tensor,
                    "sample_rate": int(sample_rate),
                    "type": "pause",
                    "index": src_line,
                    "duration": pause_duration
                })

                all_subtitles.append({
                    "id": "pause",
                    "index": src_line,
                    "字幕": f"[停顿 {pause_duration}秒]",
                    "start": round(current_time, 2),
                    "end": round(current_time + pause_duration, 2)
                })
                current_time += pause_duration
                pbar.update(1)
                continue

            role_name = segment["role"]
            dialog_text = segment["text"]
            raw_tag = (segment.get("emotion_tag") or "").strip()
            effective_tag = raw_tag if raw_tag else default_emotion

            if role_name not in role_audios:
                print(f"警告: 角色 '{role_name}' 未找到，使用默认角色 '{default_role}'")
                role_name = default_role

            if role_name is None:
                raise ValueError("没有可用的角色音频")

            ref_audio = ref_audio_cache.get(role_name)
            if ref_audio is None:
                # 理论上不会发生（已预加载），保底兜底
                ref_audio = process_audio_input(role_audios[role_name])
                ref_audio_cache[role_name] = ref_audio

            emo_vector, source, warn, recognized = resolve_emotion_vector(
                effective_tag, presets, base_emotion, emotion_intensity, custom_keys
            )

            if source == "custom_preset":
                stats["custom_hit"] += 1
            elif source == "default_preset":
                stats["default_hit"] += 1
            elif source == "unrecognized":
                stats["unrecognized"].append(effective_tag)

            if warn:
                stats["warnings"].extend(warn if isinstance(warn, list) else [warn])

            has_emotion = any(v > 0 for v in emo_vector)
            emo_vector_param = emo_vector if has_emotion else None

            if emo_vector_param is None:
                stats["raw_voice_hit"] += 1

            print(f"生成: 角色={role_name}, 情绪={effective_tag if has_emotion else '默认'}, 来源={source}, 文本={dialog_text[:30]}...")

            sr, wave, sub = indextts_model.generate(
                text=dialog_text,
                reference_audio=ref_audio,
                mode="Auto",
                do_sample=do_sample,
                temperature=temp_val,
                top_p=top_p_val,
                top_k=top_k_val,
                num_beams=num_beams_val,
                repetition_penalty=rep_val,
                length_penalty=len_pen_val,
                max_mel_tokens=max_mel_tokens,
                max_tokens_per_sentence=max_tokens_per_sentence,
                speech_speed=speech_speed,
                emo_text=None,
                emo_ref_audio=None,
                emo_vector=emo_vector_param,
                emo_weight=emo_weight,
                seed=seed,
                return_subtitles=True,
                use_random=False,
                use_qwen=False
            )

            if current_sr is None:
                current_sr = sr

            wave_np = np.asarray(wave, dtype=np.float32)
            all_waves.append(wave_np)

            dialog_counter += 1
            segment_duration = len(wave_np) / float(sr)
            stats["total_time"] += segment_duration

            audio_tensor = torch.from_numpy(wave_np).unsqueeze(0).unsqueeze(0)
            all_audios.append({
                "waveform": audio_tensor,
                "sample_rate": int(sr),
                "type": "dialog",
                "index": src_line,
                "role": role_name,
                "text": dialog_text,
                "emotion_tag": effective_tag,
                "emotion_vector": emo_vector
            })

            if sub:
                try:
                    sub_data = json.loads(sub)
                    for item in sub_data:
                        item["id"] = role_name
                        item["index"] = src_line
                        item["start"] = round(current_time + item.get("start", 0), 2)
                        item["end"] = round(current_time + item.get("end", segment_duration), 2)
                    all_subtitles.extend(sub_data)
                except Exception:
                    all_subtitles.append({
                        "id": role_name,
                        "index": src_line,
                        "字幕": dialog_text,
                        "start": round(current_time, 2),
                        "end": round(current_time + segment_duration, 2)
                    })
            else:
                all_subtitles.append({
                    "id": role_name,
                    "index": src_line,
                    "字幕": dialog_text,
                    "start": round(current_time, 2),
                    "end": round(current_time + segment_duration, 2)
                })

            vector_preview = ", ".join([f"{v:.2f}" for v in emo_vector])
            icon = "✅" if source in ("default_preset", "custom_preset", "parsed") else "⚠️"
            tag_display = effective_tag or "无"
            detail_rows.append(
                f"{src_line:>3} | {icon:^4} | {role_name:<8} | {tag_display:<10} | [{vector_preview}] | {segment_duration:>6.2f}s"
            )
            detail_rows.append(f"      {dialog_text}")
            detail_rows.append("")

            current_time += segment_duration
            stats["dialog_count"] += 1
            seg_end_time = time.time()
            print(f"段落 {src_line} 处理时间: {seg_end_time - seg_start_time:.2f}秒")
            pbar.update(1)

        loaded_roles_list = sorted(stats["loaded_roles"]) if isinstance(stats.get("loaded_roles"), set) else []
        print(
            f"实际加载角色数量: {len(loaded_roles_list)} | "
            f"加载角色: {', '.join(loaded_roles_list) if loaded_roles_list else '无'}"
        )

        final_wave = np.concatenate(all_waves) if all_waves else np.array([])
        merged_tensor = torch.from_numpy(final_wave.astype(np.float32)).unsqueeze(0).unsqueeze(0)
        merged_audio = {"waveform": merged_tensor, "sample_rate": int(current_sr or 22050)}

        final_subtitle = json.dumps(all_subtitles, ensure_ascii=False) if all_subtitles else ""

        filter_note_parts = []
        if include_roles_set:
            filter_note_parts.append(f"仅角色: { '、'.join(sorted(include_roles_set)) }")
        if exclude_roles_set:
            filter_note_parts.append(f"排除角色: { '、'.join(sorted(exclude_roles_set)) }")
        if include_lines_set:
            filter_note_parts.append(f"段落: { '、'.join(str(i) for i in sorted(include_lines_set)) }")

        header = [
            "=" * 90,
            f"🎭🎵 动态情绪生成报告 | 种子: {seed} | 角色匹配数量: {len(stats['matched_roles'])} | 实际加载角色数量: {len(stats['loaded_roles'])}",
            f"采样预设: {preset_note} | temp={temp_val} top_p={top_p_val} top_k={top_k_val} beams={num_beams_val} rep={rep_val} len_pen={len_pen_val}",
            (f"筛选: {' | '.join(filter_note_parts)}" if filter_note_parts else "筛选: 全部"),
            f"对话: {stats['dialog_count']} 条 | 停顿: {stats['pause_count']} 条 | 总数：{stats['dialog_count'] + stats['pause_count']} 条 | 默认预设命中: {stats['default_hit']} | 自定义情绪音色命中: {stats['custom_hit']} | 原始采样音色应用: {stats['raw_voice_hit']}",
            "-" * 90,
            "  Idx | 状态 | 角色       | 情绪标签     | 情绪向量值                                       |   时长",
            "--- | ---- | ---------- | ------------ | ------------------------------------------------ | ------",
        ]
        summary_lines = header + detail_rows
        summary_lines.append("-" * 90)
        if stats["unrecognized"]:
            summary_lines.append(f"⚠️ 未识别情绪: {', '.join(stats['unrecognized'])}")
        if stats["warnings"]:
            summary_lines.append("警告:")
            for w in stats["warnings"]:
                summary_lines.append(f"- {w}")
        parse_info = "\n".join(summary_lines)

        if unload_model:
            indextts_model.unload_model()

        end_time = time.time()
        print(f"🎭🎵 总生成时间: {end_time - start_time:.2f}秒 | 平均每段: {(end_time - start_time)/len(segments):.2f}秒")

        return (merged_audio, all_audios, seed, final_subtitle, parse_info)

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_IndexTTSDynamicEmotion": buding_IndexTTSDynamicEmotion,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_IndexTTSDynamicEmotion": "🎭 IndexTTS动态情绪生成器 (Buding-tools)",
}

# 导出的类名
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
