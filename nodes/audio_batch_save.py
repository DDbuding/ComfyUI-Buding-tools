"""
音频批量保存节点
将AUDIOS列表批量保存为独立音频文件，支持停顿识别和自定义命名
"""

import os
import json
import torch
import torchaudio
from typing import List, Dict, Any, Union
import folder_paths


class AudioBatchSave:
    """音频批量保存节点"""
    
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audios": ("AUDIOS",),
                "filename_prefix": ("STRING", {
                    "default": "tts_output",
                    "multiline": False,
                    "tooltip": "文件名前缀，例如'tts_output' 会生成 tts_output_0000.wav"
                }),
                "output_subdir": ("STRING", {
                    "default": "tts_batch",
                    "multiline": False,
                    "tooltip": "输出子目录名称。将保存到ComfyUI/output/此目录/"
                }),
                "auto_name_detail": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "自动命名：文件名后拼接-角色名-台词前10汉字/20字符（过滤特殊符号）"
                }),
                "format": (["wav", "mp3", "flac"], {
                    "default": "wav",
                    "tooltip": "音频格式。wav=无损，mp3=压缩，flac=无损压缩"
                }),
                "start_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 999999,
                    "step": 1,
                    "tooltip": "起始编号"
                }),
                "preserve_pause": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否保存停顿音频"
                }),
                "overwrite": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "默认不覆盖：若文件已存在会自动跳号改名；开启后允许覆盖同名文件"
                }),
            },
        }
    
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("ABSOLUTE_PATHS", "SAVE_LOG")
    FUNCTION = "save_batch"
    OUTPUT_NODE = True
    CATEGORY = "buding_Tools/Audio"

    def save_batch(
        self,
        audios: List[Dict[str, Any]],
        filename_prefix: str,
        output_subdir: str,
        format: str,
        start_index: int,
        preserve_pause: bool,
        overwrite: bool,
        auto_name_detail: bool = False,
    ):
        """批量保存音频列表，支持过滤停顿。"""

        import re
        def filter_text_for_filename(text, max_hanzi=10, max_total=20):
            if not text:
                return ""
            # 过滤不适合做文件名的符号（包括中文标点和所有特殊字符）
            text = re.sub(r'[\\/:*?"<>|\r\n\t\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]', '', str(text))
            # 过滤中文标点符号
            text = re.sub(r'[：；，。！？【】《》〈〉「」『』〖〗【】（）〔〕｛｝「」『』【】《》〈〉《》〈〉]', '', text)
            # 过滤所有其他特殊符号和标点
            text = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', text)
            hanzi = re.findall(r'[\u4e00-\u9fff]', text)
            hanzi_part = ''.join(hanzi[:max_hanzi])
            remain = max_total - len(hanzi_part)
            # 去掉已取汉字部分
            rest = re.sub(r'[\u4e00-\u9fff]', '', text)
            rest = rest[:remain] if remain > 0 else ''
            result = (hanzi_part + rest)[:max_total]
            # 去除结尾空格
            result = result.rstrip()
            return result
        
        try:
            if not isinstance(audios, list):
                raise ValueError(f"期望 audios 是列表类型，但得到 {type(audios)}")

            output_subdir = (output_subdir or "").strip().strip('"').strip("'")
            drive, tail = os.path.splitdrive(output_subdir)
            if drive and tail and not (tail.startswith("\\") or tail.startswith("/")):
                # 兼容 Windows 的 "E:folder"（驱动器相对路径），用户通常期望是 "E:\\folder"
                output_subdir = drive + "\\" + tail.lstrip("\\/")

            full_output_dir = output_subdir if os.path.isabs(output_subdir) else os.path.join(self.output_dir, output_subdir)
            os.makedirs(full_output_dir, exist_ok=True)

            print(f"\n🎵 开始批量保存音频...")
            print(f"   输出目录: {full_output_dir}")
            print(f"   文件名前缀: {filename_prefix}")
            print(f"   格式: {format}")

            saved_files = []
            pause_count = 0
            dialog_count = 0
            file_counter = start_index

            for idx, audio in enumerate(audios):
                if not isinstance(audio, dict):
                    print(f"⚠️ 跳过第{idx}项，类型错误: {type(audio)}")
                    continue

                a_type = audio.get("type", "dialog")
                if a_type == "pause" and not preserve_pause:
                    print(f"⏭️ 跳过停顿音频 idx={idx}")
                    continue

                if a_type == "pause":
                    pause_count += 1
                else:
                    dialog_count += 1

                waveform = audio.get("waveform")
                sample_rate = int(audio.get("sample_rate", 44100))

                if waveform is None or not isinstance(waveform, torch.Tensor):
                    print(f"⚠️ 跳过第{idx}项，waveform无效")
                    continue

                if waveform.dim() == 3:
                    waveform_to_save = waveform.squeeze(0)
                elif waveform.dim() == 1:
                    waveform_to_save = waveform.unsqueeze(0)
                else:
                    waveform_to_save = waveform

                if waveform_to_save.dim() == 2 and waveform_to_save.shape[0] > 2:
                    # 如果是(batch, channels, samples)误传，尽量挤掉batch
                    waveform_to_save = waveform_to_save[0]

                # 主编号直接用 audio['index']，若无则用 file_counter
                main_index = audio.get("index")
                if isinstance(main_index, int):
                    main_index_str = f"{main_index:04d}"
                elif isinstance(main_index, str) and main_index.isdigit():
                    main_index_str = f"{int(main_index):04d}"
                else:
                    main_index_str = f"{file_counter:04d}"

                while True:
                    if a_type == "pause":
                        filename = f"{filename_prefix}_{main_index_str}_pause.{format}"
                    else:
                        if auto_name_detail:
                            role = audio.get("role") or ""
                            text = audio.get("text") or ""
                            role = filter_text_for_filename(role, 6, 12)  # 角色名最多6汉字/12字符
                            text_part = filter_text_for_filename(text, 10, 20)
                            # 获取原文行号
                            line_index = audio.get("index")
                            if isinstance(line_index, int):
                                line_index_str = f"-{line_index:02d}"
                            elif isinstance(line_index, str) and line_index.isdigit():
                                line_index_str = f"-{int(line_index):02d}"
                            else:
                                line_index_str = ""
                            detail = f"-{role}-{text_part}{line_index_str}" if (role or text_part or line_index_str) else ""
                            filename = f"{filename_prefix}_{main_index_str}{detail}.{format}"
                        else:
                            filename = f"{filename_prefix}_{main_index_str}.{format}"

                    filepath = os.path.join(full_output_dir, filename)
                    if overwrite or not os.path.exists(filepath):
                        break
                    # 若有重名，主编号递增（极少出现）
                    try:
                        next_index = int(main_index_str) + 1
                        main_index_str = f"{next_index:04d}"
                    except Exception:
                        main_index_str = f"{file_counter:04d}"

                try:
                    torchaudio.save(filepath, waveform_to_save.cpu(), sample_rate, format=format)
                except Exception as e:
                    print(f"❌ 保存失败: {filepath} | {e}")
                    continue

                if not os.path.exists(filepath):
                    print(f"❌ 保存失败(文件未生成): {filepath}")
                    continue

                duration = waveform_to_save.shape[-1] / sample_rate
                meta = {
                    "index": int(main_index_str),
                    "type": a_type,
                    "role": audio.get("role"),
                    "text": audio.get("text"),
                    "emotion_tag": audio.get("emotion_tag"),
                    "filename": filename,
                    "path": filepath,
                    "sample_rate": sample_rate,
                    "duration": duration,
                    "format": format
                }
                saved_files.append(meta)
                print(f"   ✓ 保存: {filename} ({duration:.2f}s) type={a_type}")

                file_counter += 1

            total_saved = len(saved_files)
            last_filename = saved_files[-1]["filename"] if saved_files else "None"
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_log = (
                f"📊 批量保存完成 | 🔢 总计: {total_saved} 个文件\n"
                f"📂 根目录: {full_output_dir}\n"
                f"🔚 结束于: {last_filename}\n"
                f"🕒 时间: {today}"
            )
            print(save_log)
            print(f"🎉 完成，成功保存 {len(saved_files)} 个文件 (不再生成报告文件)")
            
            # 返回所有保存文件的绝对路径（多行文本格式）和日志
            paths_text = "\n".join([m["path"] for m in saved_files])
            return (paths_text, save_log)

        except Exception as e:
            print(f"❌ 保存音频失败: {e}")
            import traceback
            traceback.print_exc()
            return ("", f"Error: {e}")


NODE_CLASS_MAPPINGS = {
    "🎵🎭 buding_AudioBatchSave": AudioBatchSave
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "🎵🎭 buding_AudioBatchSave": "🎵 Audio Batch Save (批量保存音频)"
}
