import os
import re
import shutil
import subprocess
import tempfile
from typing import List, Optional, Sequence, Tuple

import torch
import torchaudio
from torchaudio.transforms import Resample

import comfy.utils


class AudioStitcherABC:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "sources_A": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "A(片头): 留空则跳过，支持输入单个文件或目录，多行可混输",
                    "tooltip": "片头音频源：支持直接填文件完整路径，或填目录自动批量读取；可多行输入多个路径/目录，自动数字顺序排序。"
                }),
                "sources_B": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "B(正文): 必填，支持文件或目录，多行可混输",
                    "tooltip": "正文音频源：必须提供。支持填单个文件或目录（自动扫描支持的音频后缀），可多行混合输入；会按文件名数字优先排序。"
                }),
                "sources_C": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "C(片尾): 留空则跳过，支持文件/目录，多行可混输",
                    "tooltip": "片尾音频源：可选。支持文件或目录，多行混合输入；未提供则跳过片尾拼接。"
                }),
                "mode": ([
                    "批量_循环补齐 (Loop)",
                    "批量_索引对齐 (Index)",
                    "批量_1对N (A1+C1+所有B)",
                    "单条_仅首个 (Single)",
                ], {"default": "批量_索引对齐 (Index)", "tooltip": "批量：按模式循环/对齐；单条：只取各列表第1个文件快速预览"}),
                "limit_count": ("INT", {"default": 0, "min": 0, "max": 9999, "tooltip": "批量模式数量上限，0 表示不限制；单条模式无视该限制"}),
                "norm_A_dB": ("FLOAT", {"default": -3.0, "step": 0.5, "tooltip": "片头音量归一化目标 (dB)，单独作用于A"}),
                "norm_B_dB": ("FLOAT", {"default": -3.0, "step": 0.5, "tooltip": "正文音量归一化目标 (dB)，作用于B"}),
                "norm_C_dB": ("FLOAT", {"default": -3.0, "step": 0.5, "tooltip": "片尾音量归一化目标 (dB)，作用于C"}),
                "offset_A_B": ("FLOAT", {"default": -0.5, "step": 0.1, "label": "A-B 连接(负数重叠)", "tooltip": "A 与 B 的时间偏移：负数表示重叠混音，正数表示插入静音间隔"}),
                "offset_B_C": ("FLOAT", {"default": 1.0, "step": 0.1, "label": "B-C 连接(正数间隔)", "tooltip": "B 与 C 的时间偏移：负数重叠，正数留间隔"}),
                "trim_silence": ("BOOLEAN", {"default": True, "tooltip": "裁剪各片段首尾静音（-45dB 阈值，10ms 余量）"}),
                "edge_fade": ("INT", {"default": 10, "min": 0, "max": 2000, "tooltip": "整段首尾淡入/淡出时长（毫秒）。0 关闭淡变。"}),
                "save_file": ("BOOLEAN", {"default": True, "tooltip": "保存拼接结果到磁盘"}),
                "save_path": ("STRING", {"default": "", "placeholder": "C:/Output/Audio", "tooltip": "导出目录，留空则不保存"}),
                "naming_mode": (["前缀+序号", "B名称+扩展后缀"], {"default": "前缀+序号", "tooltip": "选择导出命名方式：\n- 前缀+序号：使用前缀+四位编号\n- B名称+扩展后缀：使用B文件名（或目录名）+可选后缀"}),
                "file_prefix": ("STRING", {"default": "Ep_", "tooltip": "命名方式为前缀+序号时的前缀，例如 Ep_0001.wav"}),
                "name_suffix": ("STRING", {"default": "", "tooltip": "命名方式为B名称+扩展后缀时使用，例如 B=女声1，后缀=S，结果为 S-女声1.wav；后缀留空则直接用B名。"}),
                "ffmpeg_fallback": ("BOOLEAN", {"default": True, "tooltip": "当 torchaudio 读取失败时，自动调用 ffmpeg 解码为 WAV 再拼接（需系统已安装 ffmpeg）。关闭可略微提升性能。"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "开启后输出详细调试日志，便于排查加载/拼接问题"}),
            }
        }

    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio_batch", "log_info")
    FUNCTION = "stitch"
    CATEGORY = "buding_Tools/音频处理"

    @staticmethod
    def _natural_key(name: str) -> List[object]:
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"([0-9]+)", name)]

    @classmethod
    def _gather_files(cls, raw: Sequence[str]) -> List[Tuple[str, str]]:
        if raw is None:
            return []
        valid_ext = (".wav", ".mp3", ".flac", ".m4a", ".ogg")
        file_list: List[Tuple[str, str]] = []
        paths: List[str] = []

        def clean_path(p: str) -> str:
            return str(p).strip().strip('"').strip("'")

        if isinstance(raw, str):
            paths = [clean_path(p) for p in raw.split("\n") if p.strip()]
        else:
            paths = [clean_path(p) for p in raw if str(p).strip()]

        for path in paths:
            if os.path.isfile(path) and path.lower().endswith(valid_ext):
                file_list.append((path, path))
            elif os.path.isdir(path):
                for fname in os.listdir(path):
                    if fname.lower().endswith(valid_ext):
                        file_list.append((os.path.join(path, fname), path))

        file_list.sort(key=lambda x: cls._natural_key(os.path.basename(x[0])))
        return file_list

    @staticmethod
    def _trim_silence_if_needed(wav: Optional[torch.Tensor], sr: int, enable: bool) -> Optional[torch.Tensor]:
        if wav is None or not enable:
            return wav
        mono = wav.abs().max(dim=0).values
        threshold = 10 ** (-45.0 / 20)
        mask = (mono > threshold).nonzero(as_tuple=False).flatten()
        if mask.numel() == 0:
            return wav
        start = mask[0].item()
        end = mask[-1].item() + 1
        margin = int(0.01 * sr)
        start = max(0, start - margin)
        end = min(mono.numel(), end + margin)
        if end - start <= 0:
            return wav
        return wav[:, start:end]

    @staticmethod
    def _decode_with_ffmpeg(path: str, target_sr: int) -> Tuple[Optional[torch.Tensor], Optional[str]]:
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return None, "未找到 ffmpeg 可执行文件"
        tmp_path = None
        try:
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            tmp_path = tmp_file.name
            tmp_file.close()

            cmd = [
                ffmpeg_bin,
                "-y",
                "-loglevel",
                "error",
                "-i",
                path,
                "-ar",
                str(target_sr),
                "-ac",
                "2",
                "-f",
                "wav",
                tmp_path,
            ]
            proc = subprocess.run(cmd, capture_output=True)
            if proc.returncode != 0:
                stderr = proc.stderr.decode("utf-8", errors="ignore") if proc.stderr else ""
                return None, f"ffmpeg 解码失败: {stderr.strip()}"

            wav, sr = torchaudio.load(tmp_path)
            wav = wav.float()
            if sr != target_sr:
                wav = Resample(sr, target_sr)(wav)
            if wav.shape[0] == 1:
                wav = wav.repeat(2, 1)
            elif wav.shape[0] > 2:
                wav = wav[:2, :]
            return wav, None
        except Exception as exc:  # noqa: BLE001
            return None, f"ffmpeg 解码异常: {exc}"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _load_clip(path: Optional[str], target_db: float, target_sr: int, trim_silence: bool, ffmpeg_fallback: bool) -> Tuple[Optional[torch.Tensor], Optional[str]]:
        if not path:
            return None, "未提供路径"
        try:
            wav, sr = torchaudio.load(path)
            wav = wav.float()
            if sr != target_sr:
                wav = Resample(sr, target_sr)(wav)
            if wav.shape[0] == 1:
                wav = wav.repeat(2, 1)
            elif wav.shape[0] > 2:
                wav = wav[:2, :]
            max_val = torch.max(torch.abs(wav)).item()
            if max_val > 0:
                target_amp = 10 ** (target_db / 20)
                wav = wav * (target_amp / max_val)
            wav = AudioStitcherABC._trim_silence_if_needed(wav, target_sr, trim_silence)
            return wav, None
        except Exception as exc:  # noqa: BLE001
            if not ffmpeg_fallback:
                return None, f"加载失败: {exc}"
            ffmpeg_wav, ffmpeg_err = AudioStitcherABC._decode_with_ffmpeg(path, target_sr)
            if ffmpeg_wav is None:
                return None, ffmpeg_err
            max_val = torch.max(torch.abs(ffmpeg_wav)).item()
            if max_val > 0:
                target_amp = 10 ** (target_db / 20)
                ffmpeg_wav = ffmpeg_wav * (target_amp / max_val)
            ffmpeg_wav = AudioStitcherABC._trim_silence_if_needed(ffmpeg_wav, target_sr, trim_silence)
            return ffmpeg_wav, None

    @staticmethod
    def _stitch_two(w1: Optional[torch.Tensor], w2: Optional[torch.Tensor], offset: float, sr: int) -> Optional[torch.Tensor]:
        if w1 is None:
            return w2
        if w2 is None:
            return w1
        offset_frames = int(abs(offset) * sr)
        len1, len2 = w1.shape[1], w2.shape[1]
        if offset < 0:  # overlap mix
            overlap = min(offset_frames, min(len1, len2))
            total = max(len1, len2 + len1 - overlap)
            out = torch.zeros((2, total), device=w1.device, dtype=w1.dtype)
            out[:, :len1] = w1
            start2 = max(0, len1 - overlap)
            valid2 = min(len2, total - start2)
            out[:, start2:start2 + valid2] += w2[:, :valid2]
            return out
        gap = torch.zeros((2, offset_frames), device=w1.device, dtype=w1.dtype)
        return torch.cat((w1, gap, w2), dim=1)

    def stitch(
        self,
        sources_A: Sequence[str],
        sources_B: Sequence[str],
        sources_C: Sequence[str],
        norm_A_dB: float,
        norm_B_dB: float,
        norm_C_dB: float,
        mode: str,
        offset_A_B: float,
        offset_B_C: float,
        trim_silence: bool,
        edge_fade: int,
        limit_count: int,
        save_file: bool,
        save_path: str,
        naming_mode: str,
        file_prefix: str,
        name_suffix: str,
        ffmpeg_fallback: bool,
        debug_mode: bool,
    ) -> Tuple[Optional[dict], str]:
        list_A = self._gather_files(sources_A)
        list_B = self._gather_files(sources_B)
        list_C = self._gather_files(sources_C)

        if not list_B:
            return None, "❌ 错误：B 源为空，无法拼接"

        target_sr = 44100
        mode_single = "单条" in mode or "Single" in mode
        mode_index = "索引" in mode
        mode_one_to_many = "1对N" in mode

        max_iter = len(list_B)
        if mode_single:
            max_iter = 1
        elif mode_index:
            valid_lengths = [l for l in [len(list_A), len(list_B), len(list_C)] if l > 0]
            max_iter = min(valid_lengths) if valid_lengths else 0
        elif mode_one_to_many:
            max_iter = len(list_B)

        if limit_count > 0 and not mode_single:
            max_iter = min(max_iter, limit_count)

        triplets = []
        for i in range(max_iter):
            idx_A = 0 if (mode_one_to_many or mode_single) else (i % len(list_A) if list_A else None)
            idx_B = 0 if mode_single else (i % len(list_B))
            idx_C = 0 if (mode_one_to_many or mode_single) else (i % len(list_C) if list_C else None)

            fA_path = list_A[idx_A][0] if idx_A is not None and list_A else None
            fB_path, fB_root = list_B[idx_B]
            fC_path = list_C[idx_C][0] if idx_C is not None and list_C else None
            triplets.append((fA_path, fB_path, fC_path, fB_root))

        if not triplets:
            return None, "⚠️ 没有可处理的任务，检查输入列表"

        if save_file and save_path:
            os.makedirs(save_path, exist_ok=True)

        output_tensors: List[torch.Tensor] = []
        success = 0
        failures: List[str] = []
        pbar = comfy.utils.ProgressBar(len(triplets))

        for idx, (pA, pB, pC, rootB) in enumerate(triplets):
            try:
                wav_A, err_A = self._load_clip(pA, norm_A_dB, target_sr, trim_silence, ffmpeg_fallback)
                wav_B, err_B = self._load_clip(pB, norm_B_dB, target_sr, trim_silence, ffmpeg_fallback)
                wav_C, err_C = self._load_clip(pC, norm_C_dB, target_sr, trim_silence, ffmpeg_fallback)

                if debug_mode:
                    print(f"[AudioStitcher] Task {idx+1}: A={pA}, B={pB}, C={pC}, rootB={rootB}")
                    if wav_A is None:
                        print(f"[AudioStitcher] A 加载失败或未提供: {err_A}")
                    if wav_B is None:
                        print(f"[AudioStitcher] B 加载失败或未提供: {err_B}")
                    if wav_C is None and pC:
                        print(f"[AudioStitcher] C 加载失败: {err_C}")

                if pA and wav_A is None:
                    raise RuntimeError(f"A 片段加载失败: {pA} ({err_A})")
                if wav_B is None:
                    raise RuntimeError(f"B 片段加载失败，无法拼接: {pB} ({err_B})")
                if pC and wav_C is None:
                    raise RuntimeError(f"C 片段加载失败: {pC} ({err_C})")

                current = self._stitch_two(wav_A, wav_B, offset_A_B, target_sr)
                final = self._stitch_two(current, wav_C, offset_B_C, target_sr)

                if final is None:
                    raise RuntimeError("拼接结果为空")

                if edge_fade > 0:
                    fade_len = int((edge_fade / 1000) * target_sr)
                    if fade_len * 2 < final.shape[1] and fade_len > 0:
                        fade_in = torch.linspace(0, 1, fade_len, device=final.device).unsqueeze(0).repeat(2, 1)
                        fade_out = torch.linspace(1, 0, fade_len, device=final.device).unsqueeze(0).repeat(2, 1)
                        final[:, :fade_len] *= fade_in
                        final[:, -fade_len:] *= fade_out

                output_tensors.append(final.unsqueeze(0))
                if save_file and save_path:
                    suffix = name_suffix.strip()
                    if naming_mode == "B名称+扩展后缀":
                        base_name_file = os.path.splitext(os.path.basename(pB or ""))[0]
                        base_name_dir = os.path.basename(rootB or "") if rootB else ""
                        # 如果根路径是目录，则优先用目录名；否则用文件名
                        base_name = base_name_dir if rootB and os.path.isdir(rootB) else base_name_file
                        base_name = base_name or "output"
                        if suffix:
                            fname_core = f"{suffix}-{base_name}-{idx + 1:04d}"
                        else:
                            fname_core = f"{base_name}-{idx + 1:04d}"
                    else:
                        fname_core = f"{file_prefix}{idx + 1:04d}"
                    fname = f"{fname_core}.wav"
                    torchaudio.save(os.path.join(save_path, fname), final.cpu(), target_sr)
                success += 1
            except Exception as exc:  # noqa: BLE001
                failures.append(f"Task {idx + 1}: {exc}")
            finally:
                pbar.update(1)

        if success == 0:
            error_msg = failures[0] if failures else "生成失败，未得到有效音频"
            raise RuntimeError(error_msg)

        if output_tensors:
            max_len = max(t.shape[2] for t in output_tensors)
            padded = []
            for t in output_tensors:
                if t.shape[2] < max_len:
                    pad_len = max_len - t.shape[2]
                    pad = torch.zeros((1, t.shape[1], pad_len), device=t.device, dtype=t.dtype)
                    t = torch.cat((t, pad), dim=2)
                padded.append(t)
            waveform = torch.cat(padded, dim=0)
            audio_batch = {"waveform": waveform, "sample_rate": target_sr}
        else:
            audio_batch = None

        fail_msg = f"\n❌ 失败: {len(failures)}" if failures else ""
        if failures:
            for msg in failures:
                print(msg)
        mode_str = "🟢 单条模式" if mode_single else f"🟠 批量模式 ({mode})"
        save_state = save_path if (save_file and save_path) else "未开启保存"

        log_text = (
            f"✅ 处理完成\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ 模式: {mode_str}\n"
            f"📥 队列: {len(triplets)} 个任务\n"
            f"📊 成功: {success} 个\n"
            f"💾 路径: {save_state}"
            f"{fail_msg}"
        )
        print(log_text)

        return audio_batch, log_text


NODE_CLASS_MAPPINGS = {
    "AudioStitcherABC": AudioStitcherABC,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "AudioStitcherABC": "🎵 Audio Stitcher (A-B-C)",
}
