"""
🎬 智能视频分块计算器 (v3.5 - 状态机版 + 文件名输出 + 空输出处理 + 重叠帧)
============================

核心功能：
- 自动读取视频总帧数（OpenCV）
- 支持强制帧率设置（16fps等）
- 计算"物理最少批次" = ceil(total_frames / max_frames_per_batch)
- 智能压缩策略：在 overflow_limit 范围内最大程度减少批次
- 多轮压缩循环，找最优方案
- 两种策略：均衡（推荐）vs 贪婪（传统）
- 状态机机制：基于视频路径跟踪处理进度，处理完自动解锁
- 详细的处理清单和科学推演

参数说明：
  - video_path: 视频文件的完整路径
  - max_frames_per_batch: 显存允许的单批帧数（ComfyUI 默认推荐 24）
  - overflow_limit: 智能压缩的容差值（帧数）
  - compression_strategy: 压缩策略（'balanced' 推荐 vs 'greedy'）
  - reset_cursor: 重置状态机游标（切换视频时使用）
  - force_fps: 强制帧率（0=原帧率，16=强制16fps等）
  - overlap_frames: 帧间重叠数量（0=无重叠，下一批从上一批结束处开始）

返回值：
  - 🔄总批次数(Count): 最终的总批次数
  - 📄文件名称: 视频文件名（不含扩展名）
  - 📁视频路径: 输入的视频路径（透传）
  - 🎯每批帧数(Cap): 最终每批的帧数上限
  - ⏭️跳过帧数: 当前批次的起始帧位置（状态机）
  - ℹ️分析报告: 详细的计算和压缩过程

工作流示例：
  Load Video
    └─ Path → video_path
  
  Batch Calculator (本节点)
    ├─ max_frames_per_batch: 24
    ├─ overflow_limit: 2
    ├─ force_fps: 16 (可选)
    ├─ 输出 Count → 后续处理节点的批次数
    ├─ 输出 Filename → 文件名处理节点
    ├─ 输出 Path → 其他需要路径的节点
    ├─ 输出 Cap → 后续处理节点的每批帧数
    └─ 输出 Skip → Load Video 的 skip_first_frames
"""

import os
import math
import hashlib
import folder_paths

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False


# 全局状态机存储（基于视频路径哈希）
_video_states = {}


class VideoBatchCalculator:
    """智能视频分块计算器 - v3.3 (状态机版 + 强制帧率 + 文件名输出)"""

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "视频文件的完整路径"
                    }
                ),
                "max_frames_per_batch": (
                    "INT",
                    {
                        "default": 61,
                        "min": 1,
                        "max": 1000,
                        "step": 1,
                        "tooltip": "单批最多加载的帧数（受显存限制，默认 61）"
                    }
                ),
                "overflow_limit": (
                    "INT",
                    {
                        "default": 2,
                        "min": 0,
                        "max": 100,
                        "step": 1,
                        "tooltip": "智能压缩的容差值（帧数），超过此值就不压缩。0=不压缩"
                    }
                ),
                "compression_strategy": (
                    ["balanced", "greedy"],
                    {
                        "default": "balanced",
                        "tooltip": "'balanced' = 推荐（性能和显存平衡）; 'greedy' = 传统（最少批次）"
                    }
                ),
                "reset_cursor": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "重置状态机游标（切换新视频时使用）"
                    }
                ),
                "overlap_frames": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 100,
                        "step": 1,
                        "tooltip": "帧间重叠数量（0=无重叠，下一批从上一批结束处开始）"
                    }
                ),
                "force_fps": (
                    "FLOAT",
                    {
                        "default": 0.0,
                        "min": 0.0,
                        "max": 120.0,
                        "step": 0.1,
                        "tooltip": "强制帧率（0=使用原视频帧率，16=强制16fps等）"
                    }
                ),
            }
        }

    RETURN_TYPES = ("INT", "STRING", "STRING", "INT", "INT", "STRING")
    RETURN_NAMES = ("🔄总批次数(Count)", "📄文件名称", "📁视频路径", "🎯每批帧数(Cap)", "⏭️跳过帧数", "ℹ️分析报告")
    FUNCTION = "calculate_batches"
    CATEGORY = "buding_Tools/Video"
    OUTPUT_NODE = False

    def calculate_batches(self, video_path, max_frames_per_batch, 
                         overflow_limit, compression_strategy, reset_cursor, force_fps, overlap_frames):
        """
        智能计算最优的分批方案（状态机版）
        
        Args:
            video_path: 视频文件路径
            max_frames_per_batch: 显存允许的单批帧数
            overflow_limit: 压缩容差值（帧数）
            compression_strategy: 压缩策略
            reset_cursor: 是否重置状态机游标
            force_fps: 强制帧率（0=原帧率）
            overlap_frames: 帧间重叠数量
            
        Returns:
            (count, filename, video_path, cap, skip_first_frames, report)
        """

        # ===== 第 0 步：环境检查 =====
        report_lines = ["🎬 智能视频分块计算器 v3.5 (状态机版)\n"]
        report_lines.append("=" * 50)

        # ===== 第 1 步：读取视频帧数 =====
        if not video_path or not os.path.exists(video_path):
            report_lines.append("\n❌ 错误：视频文件不存在")
            report_lines.append(f"   路径: {video_path}")
            filename = os.path.splitext(os.path.basename(video_path))[0] if video_path else ""
            return (0, filename, video_path, 0, 0, "\n".join(report_lines))

        if not OPENCV_AVAILABLE:
            report_lines.append("\n❌ 错误：OpenCV 不可用，无法读取视频帧数")
            filename = os.path.splitext(os.path.basename(video_path))[0]
            return (0, filename, video_path, 0, 0, "\n".join(report_lines))

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                report_lines.append("\n❌ 错误：无法打开视频文件")
                filename = os.path.splitext(os.path.basename(video_path))[0]
                return (0, filename, video_path, 0, 0, "\n".join(report_lines))
            
            # 获取原始帧数和帧率
            original_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            original_fps = cap.get(cv2.CAP_PROP_FPS)
            duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS) if cap.get(cv2.CAP_PROP_FPS) > 0 else 0
            cap.release()
            
            # 计算最终帧数
            if force_fps > 0:
                total_frames = int(duration * force_fps)
                report_lines.append(f"\n📊 视频信息（强制帧率）:")
                report_lines.append(f"   路径: {video_path}")
                report_lines.append(f"   原帧数: {original_frame_count} ({original_fps:.2f}fps)")
                report_lines.append(f"   时长: {duration:.2f}秒")
                report_lines.append(f"   强制帧率: {force_fps}fps")
                report_lines.append(f"   计算帧数: {total_frames} ({duration:.2f} * {force_fps})")
            else:
                total_frames = original_frame_count
                report_lines.append(f"\n📊 视频信息（原帧率）:")
                report_lines.append(f"   路径: {video_path}")
                report_lines.append(f"   总帧数: {total_frames} ({original_fps:.2f}fps)")
            
            if total_frames <= 0:
                report_lines.append("\n❌ 错误：计算得到无效帧数")
                report_lines.append(f"   帧数: {total_frames}")
                filename = os.path.splitext(os.path.basename(video_path))[0]
                return (0, filename, video_path, 0, 0, "\n".join(report_lines))
                
        except Exception as e:
            report_lines.append(f"\n❌ 错误：读取视频失败 - {str(e)}")
            filename = os.path.splitext(os.path.basename(video_path))[0]
            return (0, filename, video_path, 0, 0, "\n".join(report_lines))

        # 提取文件名（不含扩展名）
        filename = os.path.splitext(os.path.basename(video_path))[0]
        report_lines.append(f"   文件名: {filename}")

        # ===== 第 2 步：状态机管理 =====
        video_hash = hashlib.md5(video_path.encode()).hexdigest()
        
        if reset_cursor or video_hash not in _video_states:
            _video_states[video_hash] = {
                'frame_cursor': 0,
                'last_video_path': video_path
            }
            report_lines.append(f"\n🔄 状态机：初始化/重置游标为 0")
        else:
            report_lines.append(f"\n🔄 状态机：当前游标 = {_video_states[video_hash]['frame_cursor']}")
        
        current_cursor = _video_states[video_hash]['frame_cursor']
        skip_first_frames = current_cursor

        # 检查是否已处理完
        if current_cursor >= total_frames:
            report_lines.append(f"\n✅ 视频已处理完成！")
            report_lines.append(f"   游标 {current_cursor} >= 总帧数 {total_frames}")
            report_lines.append(f"   无更多批次需要处理")
            # 清除该视频的状态，允许切换新视频
            if video_hash in _video_states:
                del _video_states[video_hash]
            filename = os.path.splitext(os.path.basename(video_path))[0]
            # 返回 0 批次，表示处理完成，无更多批次
            return (0, filename, video_path, 0, 0, "\n".join(report_lines))

        # ===== 第 3 步：计算剩余帧数的分批方案 =====
        remaining_frames = total_frames - current_cursor
        report_lines.append(f"   剩余帧数: {remaining_frames} (总 {total_frames} - 已处理 {current_cursor})")

        # 计算物理最少批次（基于剩余帧数）
        min_batches = math.ceil(remaining_frames / max_frames_per_batch)
        min_frames_needed = math.ceil(remaining_frames / min_batches)

        report_lines.append(f"\n🔍 物理最少批次计算（剩余帧数）：")
        report_lines.append(f"   剩余帧数 ÷ 单批上限 = {remaining_frames} ÷ {max_frames_per_batch}")
        report_lines.append(f"   = {remaining_frames / max_frames_per_batch:.2f}")
        report_lines.append(f"   向上取整 → 最少批次 = {min_batches}")
        report_lines.append(f"   此时每批需 = ceil({remaining_frames}/{min_batches}) = {min_frames_needed} 帧")

        # ===== 第 4 步：智能压缩逻辑 =====
        final_batches = min_batches
        final_cap = min_frames_needed
        compression_happened = False
        compression_gain = 0

        if overflow_limit > 0 and min_batches > 1:
            report_lines.append(f"\n🚀 智能压缩（多轮尝试）：")
            report_lines.append(f"   压缩容差: {overflow_limit} 帧")
            report_lines.append(f"   策略: {compression_strategy}")
            
            # 尝试逐步减少批次
            for try_batches in range(min_batches - 1, 0, -1):
                needed_cap = math.ceil(remaining_frames / try_batches)
                overflow = needed_cap - max_frames_per_batch

                report_lines.append(f"\n   试验: 减至 {try_batches} 批")
                report_lines.append(f"      每批需 = ceil({remaining_frames}/{try_batches}) = {needed_cap} 帧")
                report_lines.append(f"      溢出 = {needed_cap} - {max_frames_per_batch} = {overflow} 帧")

                # 检查是否在容差范围内
                if overflow <= overflow_limit:
                    report_lines.append(f"      ✅ 在容差内（{overflow} ≤ {overflow_limit}）→ 接受")
                    final_batches = try_batches
                    final_cap = needed_cap
                    compression_gain = min_batches - try_batches
                    compression_happened = True
                else:
                    report_lines.append(f"      ❌ 超出容差（{overflow} > {overflow_limit}）→ 停止")
                    break

        # ===== 第 5 步：更新状态机 =====
        # 计算本次实际处理的帧数（最后一批可能更少）
        actual_batch_frames = min(final_cap, remaining_frames)
        # 考虑重叠帧数：下一批起始位置 = 当前批次结束位置 - 重叠帧数
        # 确保不出现负数（重叠帧数不应大于批次大小）
        effective_overlap = min(overlap_frames, actual_batch_frames - 1) if actual_batch_frames > 0 else 0
        new_cursor = current_cursor + actual_batch_frames - effective_overlap
        _video_states[video_hash]['frame_cursor'] = max(0, new_cursor)  # 确保游标不小于0

        report_lines.append(f"\n🔄 状态机更新：")
        report_lines.append(f"   本次处理: {actual_batch_frames} 帧")
        report_lines.append(f"   重叠帧数: {effective_overlap}")
        report_lines.append(f"   游标推进: {current_cursor} → {max(0, new_cursor)}")

        # ===== 第 6 步：生成最终报告 =====
        # 重新组织报告结构：建议在前，详细信息在后
        final_report_lines = []
        final_report_lines.append("🎬 智能视频分块计算器 v3.5 (状态机版)\n")
        final_report_lines.append("=" * 50)

        # 💡 建议（放在最前面）
        final_report_lines.append(f"\n💡 建议:")
        final_report_lines.append(f"   - 每批加载 {final_cap} 帧，共 {final_batches} 批")
        final_report_lines.append(f"   - Load Video 的 skip_first_frames 设置为 {skip_first_frames}")
        final_report_lines.append(f"   - 实际每批加载的帧数会自动调整（最后一批可能更少）")
        if overlap_frames > 0:
            final_report_lines.append(f"   - 重叠处理：相邻批次间重叠 {overlap_frames} 帧，便于连续分析")

        # ✅ 本次批次方案
        final_report_lines.append(f"\n✅ 本次批次方案：")
        final_report_lines.append(f"   每批帧数: {final_cap}")
        final_report_lines.append(f"   总批次数: {final_batches}")
        final_report_lines.append(f"   跳过帧数: {skip_first_frames}")
        if overlap_frames > 0:
            final_report_lines.append(f"   重叠帧数: {overlap_frames} (下一批将重叠 {min(overlap_frames, final_cap-1)} 帧)")

        if compression_happened:
            ratio = (1 - final_batches / min_batches) * 100
            final_report_lines.append(f"   压缩收益: 减少 {compression_gain} 批（节省 {ratio:.1f}%）")
        else:
            final_report_lines.append(f"   无法压缩（已是物理最少）")

        # 📋 本次处理清单
        final_report_lines.append(f"\n📋 本次处理清单：")
        batch_remaining = remaining_frames
        current_batch_cursor = current_cursor
        for i in range(1, final_batches + 1):
            batch_frames = min(final_cap, batch_remaining)
            final_report_lines.append(f"   第 {i} 批: 加载 {batch_frames} 帧 (从帧 {current_batch_cursor} 开始)")
            batch_remaining -= batch_frames
            current_batch_cursor += batch_frames

        # 现在添加之前的详细信息（从第3行开始，跳过标题和分隔线）
        final_report_lines.extend(report_lines[2:])

        return (final_batches, filename, video_path, final_cap, skip_first_frames, "\n".join(final_report_lines))


NODE_CLASS_MAPPINGS = {
    "buding_VideoBatchCalculator_v3": VideoBatchCalculator
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_VideoBatchCalculator_v3": "🎬 Batch Calculator V3 (状态机分块)"
}
