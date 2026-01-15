"""
视频批量保存节点 (终极全能版)
功能：
1. 核心：将图片序列转为视频 (H.264/MP4)
2. 音频：支持【连线输入AUDIO数据】或【填写音频路径】
3. 修复：自动修正奇数分辨率，防止 FFmpeg 报错
4. 属性：将 Seed/Prompt 写入 Windows 属性面板
5. 命名：支持行号和自定义前缀，与图片保存节点对齐
"""

import os
import re
import torch
import numpy as np
import subprocess
import folder_paths
import shutil
import uuid
from datetime import datetime

# 尝试导入 torchaudio 用于处理内存音频
try:
    import torchaudio
    TORCHAUDIO_AVAILABLE = True
except ImportError:
    TORCHAUDIO_AVAILABLE = False

class VideoBatchSave:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.temp_dir = folder_paths.get_temp_directory() # 获取临时目录
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "输入图像张量 [B, H, W, C]"}),
                "fps": ("FLOAT", {"default": 24.0, "min": 0.01, "max": 120.0, "step": 0.1, "tooltip": "视频帧率 (Frames Per Second)"}),
                "filename_prefix": ("STRING", {"default": "video", "multiline": False, "tooltip": "文件名前缀"}),
                "output_subdir": ("STRING", {"default": "Video_Batch", "multiline": False, "tooltip": "输出子目录名称"}),
                "video_format": (["mp4", "webm", "mov", "gif"], {"default": "mp4", "tooltip": "视频封装格式"}),
                "crf": ("INT", {"default": 19, "min": 0, "max": 51, "tooltip": "画质控制 (CRF): 0=无损, 19=优质, 23=普通, 28=低画质。数值越小画质越高，文件越大。"}),
                "auto_name_detail": ("BOOLEAN", {"default": False, "tooltip": "自动命名：启用后将种子和提示词信息自动添加到文件名中"}),
                
                # --- 元数据输入 ---
                "seeds": ("STRING", {"default": "", "multiline": True, "forceInput": False, "tooltip": "种子信息，对应视频属性的【流派/标记】字段"}),
                "subject_descriptions": ("STRING", {"default": "", "multiline": True, "forceInput": False, "tooltip": "主体描述，对应视频属性的【标题】字段"}),
                "positive_prompts": ("STRING", {"default": "", "multiline": True, "forceInput": False, "tooltip": "提示词信息，对应视频属性的【备注】字段"}),
                "line_indices": ("STRING", {"default": "", "multiline": True, "forceInput": False, "tooltip": "行号列表，对应文本的行号（通常从控制器获取）"}),
            },
            "optional": {
                # --- 音频二选一 ---
                "audio": ("AUDIO", {"tooltip": "优先使用：连接 Load Audio 或 TTS 节点的输出"}),
                "audio_path": ("STRING", {"default": "", "forceInput": True, "tooltip": "备用：如果没有连线音频数据，则使用此处的本地文件路径"}),
                "auto_name_prefix": ("STRING", {"default": "", "multiline": False, "tooltip": "自动命名前缀：在文件名最前面追加此文本"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("ABSOLUTE_PATHS", "SAVE_LOG")
    FUNCTION = "save_video"
    CATEGORY = "buding_Tools/Video"

    def save_video(self, images, fps, filename_prefix, output_subdir, video_format, 
                   crf, auto_name_detail, seeds, subject_descriptions, positive_prompts, 
                   line_indices, audio=None, audio_path="", auto_name_prefix=""):
        
        # 0. 检查 FFmpeg
        if shutil.which('ffmpeg') is None:
            print("❌ 错误: 未在系统路径中找到 ffmpeg！")
            return ("Error: ffmpeg not found",)

        # 临时文件列表 (用于最后清理)
        temp_files_to_delete = []

        try:
            # --- 1. 音频源处理逻辑 ---
            target_audio_file = ""

            # 情况 A: 连线了 AUDIO 节点 (优先级最高)
            if audio is not None and TORCHAUDIO_AVAILABLE:
                waveform = audio.get("waveform")
                sample_rate = audio.get("sample_rate", 44100)

                if waveform is not None:
                    if waveform.dim() == 3: # [Batch, Channels, Samples]
                        waveform = waveform[0]
                    
                    temp_audio_name = f"temp_audio_{uuid.uuid4()}.wav"
                    temp_audio_path = os.path.join(self.temp_dir, temp_audio_name)
                    
                    try:
                        torchaudio.save(temp_audio_path, waveform, sample_rate)
                        target_audio_file = temp_audio_path
                        temp_files_to_delete.append(temp_audio_path)
                        print(f"🎵 已转换内存音频为临时文件: {temp_audio_name}")
                    except Exception as ae:
                        print(f"⚠️ 警告: 转换音频失败: {ae}")
            
            elif audio is not None and not TORCHAUDIO_AVAILABLE:
                print("⚠️ 警告: 检测到音频连线但未安装 torchaudio，无法处理内存音频。")

            # 情况 B: 没连线，但填了路径
            if not target_audio_file and audio_path and os.path.exists(audio_path):
                target_audio_file = audio_path.strip().strip('"')

            # --- 2. 路径与元数据解析 ---
            full_output_dir = os.path.join(self.output_dir, output_subdir)
            os.makedirs(full_output_dir, exist_ok=True)

            def extract_first(data):
                if isinstance(data, list):
                    for item in data:
                        if str(item).strip(): return str(item).strip()
                    return ""
                lines = [l.strip() for l in str(data).splitlines() if l.strip()]
                return lines[0] if lines else ""

            curr_subject = extract_first(subject_descriptions)
            curr_seed = extract_first(seeds)
            curr_prompt = extract_first(positive_prompts)
            curr_line_index_raw = extract_first(line_indices)
            
            # 格式化行号
            if not curr_line_index_raw:
                content_index_str = "0001"
            else:
                try:
                    val = int(float(curr_line_index_raw))
                    content_index_str = f"{val:04d}"
                except:
                    content_index_str = str(curr_line_index_raw)

            # --- 3. 文件名生成 ---
            def clean_name(t, l=20): 
                if not t: return ""
                t = re.sub(r'[\\/:*?"<>|]', '', str(t))
                return t[:l].strip()

            main_index = 1
            ext = video_format.lower()
            while True:
                main_index_str = f"{main_index:04d}"
                if auto_name_detail:
                    s_clean = clean_name(curr_subject, 15)
                    p_clean = clean_name(curr_prompt, 20)
                    detail = ""
                    if s_clean: detail += f"({s_clean})"
                    if p_clean: detail += f"{p_clean}"
                    
                    prefix_part = f"{auto_name_prefix}_" if auto_name_prefix.strip() else ""
                    filename = f"{prefix_part}{content_index_str}{detail}-{main_index_str}.{ext}"
                else:
                    filename = f"{filename_prefix}_{content_index_str}_{main_index_str}.{ext}"
                
                filepath = os.path.join(full_output_dir, filename)
                if not os.path.exists(filepath): break
                main_index += 1

            # --- 4. 分辨率修正 (偶数化) ---
            if images.dim() == 3:
                images = images.unsqueeze(0)
            batch, h, w, c = images.shape
            if ext in ['mp4', 'mov']:
                if w % 2 != 0: w -= 1
                if h % 2 != 0: h -= 1

            # --- 5. 构建 FFmpeg 命令 ---
            cmd = [
                'ffmpeg', '-y',
                '-loglevel', 'error', # 关键修复：减少输出，防止管道阻塞死锁
                '-f', 'rawvideo', '-vcodec', 'rawvideo',
                '-s', f'{w}x{h}', '-pix_fmt', 'rgb24',
                '-r', str(fps), '-i', '-'
            ]

            # 注入音频参数
            if target_audio_file:
                cmd.extend(['-i', target_audio_file])
                cmd.extend(['-c:a', 'aac', '-shortest'])

            # 视频编码参数
            if ext == 'mp4':
                cmd.extend(['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', str(crf), '-preset', 'fast'])
            elif ext == 'webm':
                cmd.extend(['-c:v', 'libvpx-vp9', '-crf', str(crf), '-b:v', '0'])
            elif ext == 'mov':
                cmd.extend(['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', str(crf)])
            elif ext == 'gif':
                cmd.extend(['-vf', f'fps={fps},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse'])

            # 嵌入 Windows 属性元数据
            if ext in ['mp4', 'mov']:
                title_val = f"({curr_seed}){curr_subject}" if curr_seed else curr_subject
                cmd.extend(['-metadata', f'title={title_val}'])
                cmd.extend(['-metadata', f'comment={curr_prompt}'])
                cmd.extend(['-metadata', f'description={curr_prompt}'])
                cmd.extend(['-metadata', 'artist=ComfyUI'])
                cmd.extend(['-metadata', f'genre={curr_seed}'])

            cmd.append(filepath)

            # --- 6. 执行处理 ---
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            
            for i in range(batch):
                # 检查进程是否还在运行
                if process.poll() is not None:
                    break
                    
                frame = images[i][:h, :w, :] # 裁剪
                frame_np = (frame * 255).clamp(0, 255).byte().cpu().numpy()
                if c == 4: frame_np = frame_np[:, :, :3]
                
                try:
                    process.stdin.write(frame_np.tobytes())
                except (BrokenPipeError, IOError):
                    break

            # 使用 communicate 安全地关闭并读取错误信息，避免死锁
            stdout_data, stderr_data = process.communicate()

            if process.returncode != 0:
                stderr_msg = stderr_data.decode(errors='ignore')
                print(f"❌ FFmpeg 错误输出:\n{stderr_msg}")
                raise Exception(f"FFmpeg 编码失败 (错误码 {process.returncode})。请检查控制台输出。")

            print(f"🎬 视频保存成功: {filename}")
            
            # 生成日志
            today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_log = (
                f"📊 批量保存完成 | 🔢 总计: 1 个文件\n"
                f"📂 根目录: {full_output_dir}\n"
                f"🔚 结束于: {filename}\n"
                f"🕒 时间: {today}"
            )
            print(save_log)
            
            return (filepath, save_log)

        except Exception as e:
            print(f"❌ Video Save Error: {e}")
            import traceback
            traceback.print_exc()
            return (f"Error: {e}", f"Error: {e}")
        
        finally:
            # --- 7. 清理临时音频文件 ---
            for temp_f in temp_files_to_delete:
                try:
                    if os.path.exists(temp_f):
                        os.remove(temp_f)
                        print(f"🧹 已清理临时文件: {os.path.basename(temp_f)}")
                except Exception:
                    pass

NODE_CLASS_MAPPINGS = {
    "buding_VideoBatchSave": VideoBatchSave
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_VideoBatchSave": "🎬 Video Batch Save (批量保存视频)"
}

