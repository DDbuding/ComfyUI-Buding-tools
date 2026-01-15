"""
🎬 批量视频合并节点 (V5 最终版)
================================

核心功能：
- 保存当前批次的视频分段到 [路径/文件名/] 子文件夹
- 自动检测分段数量，达到预期数量后自动合并
- 合并成品自动递增命名（永不覆盖历史作品）
- 支持可选的合并后删除分段（节省空间）
- 支持音频混合和元数据嵌入

核心参数：
  【输入图像与基础参数】
  - images: 视频帧的图像张量（批量处理）
  - fps: 视频播放速度（帧/秒）
  - video_path: 原始视频文件路径（可选，用于参考）

  【文件组织与存储】
  - filename_prefix: 项目名称，作为文件夹和文件前缀
  - custom_save_path: 保存的根目录（绝对路径），空则使用 ComfyUI 默认 output
  - expected_batch_count: 预期的总分段数量（需要与分割节点对应）

  【编码与质量】
  - video_format: 输出格式（mp4/mov/mkv）
  - crf: 视频压缩质量（0-51），低值质量好但文件大，19 为推荐值

  【处理选项】
  - merge_mode: 合并模式选择（expected_count/custom_count/all_segments）
  - force_merge: 强制立即合并所有分段（用于all_segments模式）
  - trim_tail_frames: 去掉每个分段视频尾部的帧数（0=不去掉）
  - custom_merge_count: 自定义合并数量（仅在merge_mode=custom_count时有效）
  - delete_segments: 合并完成后是否删除分段文件夹（可选）
  - seeds: 生成种子值（用于记录）
  - subject_descriptions: 视频主体描述
  - positive_prompts: 生成提示词记录

  【音频处理】
  - audio: 内存中的音频张量（可选）
  - audio_path: 外部音频文件路径（可选）

返回值：
  - FINAL_PATH: 最终合并视频的完整文件路径（合并成功时有效）
  - LOG_REPORT: 详细的处理日志和统计信息
  - IS_COMPLETE: 布尔值，True=合并完成，False=还在等待更多分段
"""

import os
import re
import subprocess
import folder_paths
import shutil
import uuid

# 尝试导入 torchaudio
try:
    import torchaudio
    TORCHAUDIO_AVAILABLE = True
except ImportError:
    TORCHAUDIO_AVAILABLE = False


class VideoSaveAndMergeV5:
    """视频分段保存与自动合并 - V5 终极生产版"""

    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.temp_dir = folder_paths.get_temp_directory()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": (
                    "IMAGE",
                    {"tooltip": "视频帧的图像张量（批量处理）"}
                ),
                "fps": (
                    "FLOAT",
                    {
                        "default": 24.0,
                        "min": 0.01,
                        "max": 120.0,
                        "step": 0.1,
                        "tooltip": "视频播放速度（帧每秒）"
                    }
                ),
                "video_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "原始视频文件路径（可选，用于参考或获取元数据）"
                    }
                ),

                # --- 文件组织与存储 ---
                "filename_prefix": (
                    "STRING",
                    {
                        "default": "MyVideo",
                        "multiline": False,
                        "tooltip": "项目名称，用作文件夹和文件前缀"
                    }
                ),
                "custom_save_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "保存的根目录（绝对路径），空则使用 ComfyUI 默认 output"
                    }
                ),
                "expected_batch_count": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "forceInput": True,
                        "tooltip": "预期的总分段数量"
                    }
                ),

                # --- 编码与质量 ---
                "video_format": (
                    ["mp4", "mov", "mkv"],
                    {
                        "default": "mp4",
                        "tooltip": "输出格式"
                    }
                ),
                "crf": (
                    "INT",
                    {
                        "default": 19,
                        "min": 0,
                        "max": 51,
                        "tooltip": "视频压缩质量（0=最高质量但大文件，51=最低质量但小文件，19=推荐平衡值）"
                    }
                ),

                # --- 处理选项 ---
                "merge_mode": (
                    ["expected_count", "custom_count", "all_segments"],
                    {
                        "default": "expected_count",
                        "tooltip": "合并模式：expected_count=使用预期分段数量；custom_count=使用自定义数量；all_segments=全部合并（需配合force_merge使用）"
                    }
                ),
                "force_merge": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "强制立即合并所有现有分段（用于all_segments模式）"
                    }
                ),
                "trim_tail_frames": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 100,
                        "tooltip": "去掉每个分段视频尾部的帧数（0=不去掉，5=去掉最后5帧）"
                    }
                ),
                "custom_merge_count": (
                    "INT",
                    {
                        "default": 5,
                        "min": 1,
                        "max": 100,
                        "tooltip": "自定义合并数量（仅在merge_mode=custom_count时有效）"
                    }
                ),

                # --- 元数据记录 ---
                "seeds": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "生成种子值（用于记录）"
                    }
                ),
                "subject_descriptions": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "视频主体描述"
                    }
                ),
                "positive_prompts": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "生成提示词记录"
                    }
                ),
            },
            "optional": {
                "audio": ("AUDIO",),
                "audio_path": (
                    "STRING",
                    {
                        "default": "",
                        "forceInput": True,
                        "tooltip": "外部音频文件路径（可选）"
                    }
                ),
                "delete_segments": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "合并完成后自动删除临时分段文件夹以节省磁盘空间"
                    }
                ),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "BOOLEAN")
    RETURN_NAMES = ("最终路径(FINAL_PATH)", "处理日志(LOG_REPORT)", "是否完成(IS_COMPLETE)")
    FUNCTION = "save_and_merge"
    CATEGORY = "buding_Tools/Video"
    OUTPUT_NODE = True

    def save_and_merge(self, images, fps, video_path, filename_prefix, custom_save_path, expected_batch_count,
                       video_format, crf, merge_mode, force_merge, trim_tail_frames, custom_merge_count, seeds, subject_descriptions, positive_prompts,
                       audio=None, audio_path="", delete_segments=False):
        """
        核心保存与合并逻辑
        
        Args:
            images: 图像张量 (batch, h, w, c)
            fps: 帧率
            video_path: 原始视频路径（参考用）
            filename_prefix: 文件名前缀（同时作为分段子文件夹名）
            custom_save_path: 自定义保存路径
            expected_batch_count: 预期的总分段数量
            video_format: 输出格式
            crf: 压缩质量
            merge_mode: 合并模式 ('expected_count', 'custom_count', 'all_segments')
            force_merge: 强制立即合并（用于all_segments模式）
            trim_tail_frames: 去掉每个分段视频尾部的帧数
            custom_merge_count: 自定义合并数量（仅在merge_mode='custom_count'时有效）
            seeds, subject_descriptions, positive_prompts: 元数据
            audio: 可选的内存音频
            audio_path: 可选的外部音频路径
            delete_segments: 是否删除分段（默认False）
            
        Returns:
            (final_path, log_report, is_complete)
        """

        # ===== 第 0 步：环境检查 =====
        if shutil.which('ffmpeg') is None:
            return (
                "",
                "❌ 错误：未找到 FFmpeg\n"
                "请安装 FFmpeg 或将其添加到系统 PATH 环境变量\n"
                "下载: https://ffmpeg.org/download.html",
                False
            )

        # ===== 第 1 步：路径构建 =====
        # 根目录（存放最终的合并成品）
        root_dir = custom_save_path.strip('"').strip() if custom_save_path.strip() else self.output_dir
        try:
            os.makedirs(root_dir, exist_ok=True)
        except Exception as e:
            return ("", f"❌ 无法创建保存目录：{root_dir}\n错误：{e}", False)

        # 分段子目录（存放碎片视频）
        # 例如 D:/MyOutput/Dance/ 用来存 Dance_0001.mp4, Dance_0002.mp4...
        segment_dir = os.path.join(root_dir, filename_prefix)
        try:
            os.makedirs(segment_dir, exist_ok=True)
        except Exception as e:
            return ("", f"❌ 无法创建分段目录：{segment_dir}\n错误：{e}", False)

        # ===== 第 2 步：确定分段文件名（严格正则匹配） =====
        # 使用正则匹配：Prefix_0001.mp4, Prefix_0002.mp4...
        # 防止误匹配：DanceFloor 不会被识别为 Dance 的分段
        safe_prefix = re.escape(filename_prefix)
        segment_pattern = re.compile(rf"^{safe_prefix}_(\d{{4}})\.{video_format}$")

        existing_files = []
        try:
            for f in os.listdir(segment_dir):
                if segment_pattern.match(f):
                    existing_files.append(f)
        except Exception as e:
            return ("", f"❌ 无法扫描分段目录：{e}", False)

        # 递增计数：当前已有文件数 + 1
        # 注：如果需要支持并发，可改用 UUID，但 ComfyUI 默认串行队列无需担心
        current_index = len(existing_files) + 1
        segment_filename = f"{filename_prefix}_{current_index:04d}.{video_format}"
        segment_fullpath = os.path.join(segment_dir, segment_filename)

        # ===== 第 3 步：准备音频 =====
        target_audio = None
        temp_audio_clean = []

        if audio is not None and TORCHAUDIO_AVAILABLE:
            try:
                waveform = audio.get("waveform")
                if waveform.dim() == 3:
                    waveform = waveform[0]
                sr = audio.get("sample_rate", 44100)
                temp_audio_path = os.path.join(self.temp_dir, f"temp_{uuid.uuid4()}.wav")
                torchaudio.save(temp_audio_path, waveform, sr)
                target_audio = temp_audio_path
                temp_audio_clean.append(temp_audio_path)
            except Exception as e:
                pass  # 音频处理失败不中断，继续保存视频

        elif audio_path and os.path.exists(audio_path.strip('"')):
            target_audio = audio_path.strip('"')

        # ===== 第 4 步：视频编码与保存 =====
        batch, h, w, c = images.shape

        # 偶数修正（H.264 编码要求）
        if video_format in ['mp4', 'mov']:
            if w % 2 != 0:
                w -= 1
            if h % 2 != 0:
                h -= 1

        # 构建 FFmpeg 命令
        cmd = [
            'ffmpeg', '-y', '-loglevel', 'error',
            '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-s', f'{w}x{h}', '-pix_fmt', 'rgb24',
            '-r', str(fps), '-i', '-'
        ]

        # 添加音频（如果有）
        if target_audio:
            cmd.extend(['-i', target_audio, '-c:a', 'aac', '-shortest'])

        # 视频编码参数
        if video_format == 'mp4':
            cmd.extend([
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-crf', str(crf), '-preset', 'fast'
            ])
        else:
            cmd.extend([
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-crf', str(crf)
            ])

        # 添加元数据
        if seeds:
            cmd.extend(['-metadata', f'comment=Seeds: {seeds[:100]}'])

        cmd.append(segment_fullpath)

        # 执行编码
        try:
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            for i in range(batch):
                if process.poll() is not None:
                    break
                # 提取帧并转换为字节
                frame = images[i][:h, :w, :]
                frame_bytes = (frame * 255).clamp(0, 255).byte().cpu().numpy().tobytes()
                try:
                    process.stdin.write(frame_bytes)
                except:
                    break

            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise Exception(stderr.decode('utf-8', errors='ignore'))

        except Exception as e:
            return ("", f"❌ 保存分段失败：{e}", False)

        finally:
            # 清理临时音频文件
            for t in temp_audio_clean:
                try:
                    os.remove(t)
                except:
                    pass

        # ===== 第 5 步：检测与合并逻辑 =====
        # 重新扫描分段目录（包含刚保存的文件）
        final_files = []
        try:
            for f in os.listdir(segment_dir):
                if segment_pattern.match(f):
                    final_files.append(f)
        except Exception as e:
            return ("", f"❌ 无法重新扫描分段目录：{e}", False)

        final_files.sort()  # 确保顺序：0001, 0002, 0003...
        current_count = len(final_files)

        # ===== 根据模式确定合并数量 =====
        if merge_mode == "expected_count":
            target_count = expected_batch_count
        elif merge_mode == "custom_count":
            target_count = custom_merge_count
        elif merge_mode == "all_segments":
            if force_merge:
                target_count = current_count  # 立即合并所有现有分段
            else:
                target_count = float('inf')  # 永远等待，除非force_merge
        else:
            target_count = expected_batch_count  # 默认

        # 构建日志
        if merge_mode == "all_segments" and not force_merge:
            progress_display = f"∞ (等待强制合并)"
        else:
            progress_display = f"{target_count}"
            
        log = (
            f"✅ 分段 {current_index} 保存成功\n"
            f"📂 路径：{segment_fullpath}\n"
            f"📊 进度：{current_count} / {progress_display} ({merge_mode})"
        )

        # 如果未达到目标数量，返回分段路径并等待
        if current_count < target_count:
            return (segment_fullpath, log + "\n⏳ 等待其余分段...", False)

        # ===== 触发合并流程 =====
        log += "\n🚀 检测到所有分段就绪，开始合并..."

        # ===== 裁剪尾帧处理 =====
        videos_to_merge = final_files[:]  # 复制列表
        if trim_tail_frames > 0:
            log += f"\n✂️ 裁剪模式：去掉每个分段尾部 {trim_tail_frames} 帧"
            
            # 创建临时裁剪目录
            trim_dir = os.path.join(segment_dir, "trimmed_segments")
            os.makedirs(trim_dir, exist_ok=True)
            
            trimmed_files = []
            for i, video_file in enumerate(final_files):
                original_path = os.path.join(segment_dir, video_file)
                trimmed_path = os.path.join(trim_dir, f"trimmed_{i:04d}.{video_format}")
                
                # 获取视频帧数
                try:
                    probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries', 'stream=nb_read_packets', '-of', 'csv=p=0', original_path]
                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, encoding='utf-8')
                    if probe_result.returncode == 0:
                        original_frame_count = int(probe_result.stdout.strip())
                    else:
                        # 如果ffprobe失败，使用cv2作为备选
                        import cv2
                        cap = cv2.VideoCapture(original_path)
                        original_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        cap.release()
                except:
                    # 如果都失败，跳过裁剪
                    log += f"\n  ⚠️ {video_file} 无法获取帧数，跳过裁剪"
                    trimmed_files.append(video_file)
                    continue
                
                if original_frame_count <= trim_tail_frames:
                    log += f"\n  ⚠️ {video_file} 帧数({original_frame_count})小于等于裁剪帧数({trim_tail_frames})，跳过裁剪"
                    trimmed_files.append(video_file)
                    continue
                
                # 使用FFmpeg裁剪视频，去掉尾帧
                trim_cmd = [
                    'ffmpeg', '-y', '-i', original_path,
                    '-frames:v', str(original_frame_count - trim_tail_frames),
                    '-c:v', 'libx264', '-crf', str(crf), '-c:a', 'copy',
                    trimmed_path
                ]
                
                try:
                    result = subprocess.run(trim_cmd, capture_output=True, text=True, encoding='utf-8')
                    if result.returncode == 0:
                        trimmed_files.append(os.path.basename(trimmed_path))
                        log += f"\n  ✅ {video_file} → 裁剪完成 ({original_frame_count} → {original_frame_count - trim_tail_frames} 帧)"
                    else:
                        log += f"\n  ❌ {video_file} 裁剪失败: {result.stderr}"
                        return (segment_fullpath, log, False)
                except Exception as e:
                    log += f"\n  ❌ {video_file} 裁剪异常: {e}"
                    return (segment_fullpath, log, False)
            
            # 更新要合并的文件列表
            videos_to_merge = trimmed_files
            segment_dir_for_merge = trim_dir
        else:
            segment_dir_for_merge = segment_dir

        # A. 生成 FFmpeg concat 列表（使用安全路径转义）
        list_txt_path = os.path.join(segment_dir, "merge_list.txt")
        try:
            with open(list_txt_path, 'w', encoding='utf-8') as f:
                for video_file in videos_to_merge:
                    # 获取绝对路径
                    abs_path = os.path.abspath(os.path.join(segment_dir_for_merge, video_file))
                    # FFmpeg concat 转义：' -> '\'''
                    safe_path = abs_path.replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
        except Exception as e:
            return (segment_fullpath, f"❌ 列表文件生成失败：{e}", False)

        # B. 计算合并成品的文件名（防覆盖逻辑）
        # 目标格式：Prefix-merged_0001.mp4, Prefix-merged_0002.mp4...
        merge_pattern = re.compile(rf"^{safe_prefix}-merged_(\d{{4}})\.{video_format}$")

        max_merge_idx = 0
        try:
            if os.path.exists(root_dir):
                for f in os.listdir(root_dir):
                    m = merge_pattern.match(f)
                    if m:
                        idx = int(m.group(1))
                        if idx > max_merge_idx:
                            max_merge_idx = idx
        except Exception as e:
            return (segment_fullpath, f"❌ 无法扫描根目录：{e}", False)

        # 下一个序号
        new_merge_idx = max_merge_idx + 1
        merged_filename = f"{filename_prefix}-merged_{new_merge_idx:04d}.{video_format}"
        merged_fullpath = os.path.join(root_dir, merged_filename)

        # C. 执行 FFmpeg concat 合并（无损，仅流复制）
        merge_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_txt_path,
            "-c", "copy",  # 无损流复制，不重新编码
            merged_fullpath
        ]

        try:
            subprocess.run(merge_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            log += f"\n🎉 合并成功！\n💾 成品：{merged_filename}\n📂 位置：{merged_fullpath}"

            # D. 清理列表文件
            try:
                os.remove(list_txt_path)
            except:
                pass

            # E. (可选) 删除分段文件夹
            if delete_segments:
                try:
                    for f in final_files:
                        file_path = os.path.join(segment_dir, f)
                        os.remove(file_path)
                    # 尝试删除空的分段文件夹
                    if not os.listdir(segment_dir):
                        os.rmdir(segment_dir)
                    log += "\n🗑️ 分段文件已清理"
                except Exception as e:
                    log += f"\n⚠️ 清理分段失败（非致命）：{e}"

            return (merged_fullpath, log, True)

        except Exception as e:
            return (segment_fullpath, f"❌ 合并失败：{e}", False)


NODE_CLASS_MAPPINGS = {
    "buding_VideoSaveMerge_V5": VideoSaveAndMergeV5
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_VideoSaveMerge_V5": "🎬 Save & Auto Merge V5 (批量视频合并)"
}
