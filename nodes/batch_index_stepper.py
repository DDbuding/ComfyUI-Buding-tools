#!/usr/bin/env python3
"""
增强版批量索引步进器
自动计算批量处理的起始索引，实现全自动批量工作流
包含自动停止、历史统计、进度可视化等功能
"""

import random
import time
import traceback  # ✅ 规范化导入，避免异常处理中导入
from typing import Dict, Any

class buding_BatchIndexStepper:
    """增强版批量索引步进器 - 智能化批量处理的索引计算器"""
    
    # ✅ 使用字典管理多实例状态（key: instance_id, value: 状态字典）
    _instances_state = {}
    
    def __init__(self):
        """初始化实例状态，确保多实例独立计数"""
        self.instance_id = id(self)  # 使用对象地址作为唯一标识
        if self.instance_id not in buding_BatchIndexStepper._instances_state:
            buding_BatchIndexStepper._instances_state[self.instance_id] = {
                'current_batch_run': 0,
                'total_processed_batches': 0,
                'total_skipped_files': 0,
                'last_reset_time': time.time(),
                'task_start_time': None,  # 本次任务开始时间：最近一次批次推进(自增)的时间
                'last_seen_batch_run': None,  # 用于判断是否进入了新批次（避免同一批次重复刷新时间）
            }
    
    @classmethod
    def INPUT_TYPES(cls):
        """定义输入参数"""
        inputs = {
            "required": {
                "base_start_index": ("INT", {"default": 0, "min": 0, "step": 1, "tooltip": "初始起始索引，通常从0开始"}),
                "max_files_per_batch": ("INT", {"default": 3, "min": 1, "max": 100, "step": 1, "tooltip": "每批处理的文件数量"}),
                "reset_counter": ("BOOLEAN", {"default": False, "tooltip": "重置计数器到初始状态"}),
            },
            "optional": {
                "total_count": ("INT", {"default": 0, "min": 0, "max": 2147483647, "step": 1, "tooltip": "总文件数量，用于自动停止和进度计算（无上限，可自由填写）"}),
                "debug_mode": ("BOOLEAN", {"default": False, "tooltip": "启用调试输出"}),
            }
        }
        return inputs
    
    RETURN_TYPES = ("INT", "STRING", "STRING")
    RETURN_NAMES = ("calculated_start_index", "status_info", "history_info")
    OUTPUT_IS_LIST = (False, False, False)
    FUNCTION = "calculate_next_index"
    CATEGORY = "buding_Tools/批量控制"
    DESCRIPTION = "增强版批量索引步进器，支持自动停止、历史统计、进度可视化"
    
    @classmethod
    def IS_CHANGED(cls, base_start_index, max_files_per_batch, reset_counter, 
                   total_count=0, debug_mode=False):
        """✅ 智能参数追踪：包含所有参数和内部状态，避免无谓的随机刷新"""
        # ✅ 改进：包含所有参数 + 内部状态，让 ComfyUI 准确检测变化
        # 注意：由于 _instances_state 是全局的，这里使用类级别的统计信息
        key_params = {
            'base_start_index': base_start_index,
            'max_files_per_batch': max_files_per_batch,
            'reset_counter': reset_counter,
            'total_count': total_count,
            'debug_mode': debug_mode,
            # ← 追踪全局处理统计（表示是否有新批次完成）
            'total_processed_batches': cls._get_global_processed_batches(),
        }
        return hash(frozenset(key_params.items()))  # ✅ 使用 frozenset，避免 str() 转换
    
    @classmethod
    def _get_global_processed_batches(cls):
        """获取全局已处理批次数（用于 IS_CHANGED 追踪）"""
        total = 0
        for state in cls._instances_state.values():
            total += state.get('total_processed_batches', 0)
        return total
    
    def _perform_reset(self, debug_mode: bool = False):
        """执行重置操作（实例级别）"""
        buding_BatchIndexStepper._instances_state[self.instance_id] = {
            'current_batch_run': 0,
            'total_processed_batches': 0,
            'total_skipped_files': 0,
            'last_reset_time': time.time(),
            'task_start_time': None,  # 重置后，首次运行用 last_reset_time 显示；随后每次批次推进时刷新
            'last_seen_batch_run': None,
        }
        if debug_mode:
            print(f"🔄 实例 {self.instance_id} 计数器已重置")
    
    def calculate_next_index(self, base_start_index: int, max_files_per_batch: int, 
                            reset_counter: bool, total_count: int = 0, debug_mode: bool = False) -> Dict[str, Any]:
        """计算下一批的起始索引（✅ 已支持多实例独立计数）"""
        
        try:
            # ✅ 重置逻辑（通过 reset_counter 参数控制）
            if reset_counter:
                self._perform_reset(debug_mode)
            
            # ✅ 获取当前实例的状态
            state = buding_BatchIndexStepper._instances_state.get(self.instance_id)
            if not state:
                self.__init__()  # 重新初始化如果状态丢失
                state = buding_BatchIndexStepper._instances_state[self.instance_id]

            # ✅ 本次任务开始时间：每个批次“第一次执行”时记录一次
            # 说明：ComfyUI 可能在同一批次内多次执行该节点（预览/重复求值），这里用 last_seen_batch_run 去重。
            current_batch_for_display = state['current_batch_run']
            last_seen = state.get('last_seen_batch_run')
            if last_seen is None or last_seen != current_batch_for_display:
                state['last_seen_batch_run'] = current_batch_for_display
                state['task_start_time'] = time.time()
                if debug_mode:
                    print(
                        f"🕒 批次开始时间已记录: 批次={current_batch_for_display + 1}, "
                        f"时间={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(state['task_start_time']))}"
                    )

            # 记录当前批次（用于显示，不提前自增）
            current_batch_for_display = state['current_batch_run']
            
            # 计算当前批次的起始索引（严格对应当前正在处理的文件）
            calculated_index = base_start_index + (current_batch_for_display * max_files_per_batch)
            
            # 自动停止机制检查
            is_completed = False
            next_batch_index = calculated_index + max_files_per_batch
            
            if total_count > 0:
                if calculated_index >= total_count:
                    # 超出总数范围，锁定在最后一个有效索引
                    calculated_index = max(0, total_count - max_files_per_batch)
                    is_completed = True
                    current_batch_for_display = max(0, (total_count - 1) // max_files_per_batch)
                    
                    # 计算跳过的文件数
                    skipped_count = max(0, (base_start_index + (state['current_batch_run'] * max_files_per_batch)) - total_count)
                    state['total_skipped_files'] += skipped_count
            
            # 生成增强的历史信息
            history_info = self._generate_history_info(state, calculated_index, max_files_per_batch, total_count, debug_mode)
            
            # 生成可视化进度条
            progress_bar = self._generate_progress_bar(calculated_index, max_files_per_batch, total_count)

            # 开始时间字符串（来源：max_files_per_batch 变化触发）
            start_time_str = "未设置"
            if state.get('task_start_time') is not None:
                start_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(state['task_start_time']))
            
            # 将进度条整合到状态信息中
            if is_completed:
                processed_files = min(calculated_index + max_files_per_batch, total_count)
                status = (
                    f"✅ 已全部处理完成 | 总计{total_count}个文件 | 已处理{processed_files}个\n"
                    f"🕒 开始时间: {start_time_str}\n"
                    f"{progress_bar}"
                )
            elif current_batch_for_display == 0:
                end_index = min(calculated_index + max_files_per_batch - 1, total_count - 1 if total_count > 0 else calculated_index + max_files_per_batch - 1)
                if total_count > 0:
                    progress_files = min(calculated_index + max_files_per_batch, total_count)
                    status = (
                        f"🚀 正在处理：第1批 | 范围：文件{calculated_index}-{end_index} | 总进度：{progress_files}/{total_count}\n"
                        f"🕒 开始时间: {start_time_str}\n"
                        f"{progress_bar}"
                    )
                else:
                    status = (
                        f"🚀 正在处理：第1批 | 范围：文件{calculated_index}-{end_index} | 每批{max_files_per_batch}个文件\n"
                        f"🕒 开始时间: {start_time_str}\n"
                        f"{progress_bar}"
                    )
            else:
                end_index = min(calculated_index + max_files_per_batch - 1, total_count - 1 if total_count > 0 else calculated_index + max_files_per_batch - 1)
                if total_count > 0:
                    progress_files = min(calculated_index + max_files_per_batch, total_count)
                    status = (
                        f"🚀 正在处理：第{current_batch_for_display + 1}批 | 范围：文件{calculated_index}-{end_index} | 总进度：{progress_files}/{total_count}\n"
                        f"🕒 开始时间: {start_time_str}\n"
                        f"{progress_bar}"
                    )
                else:
                    status = (
                        f"🚀 正在处理：第{current_batch_for_display + 1}批 | 范围：文件{calculated_index}-{end_index} | 每批{max_files_per_batch}个文件\n"
                        f"🕒 开始时间: {start_time_str}\n"
                        f"{progress_bar}"
                    )
            
            # 调试输出
            if debug_mode:
                print(f"🔢 批量索引计算（多实例安全版）:")
                print(f"   实例 ID: {self.instance_id}")
                print(f"   基础起始索引: {base_start_index}")
                print(f"   每批文件数量: {max_files_per_batch}")
                print(f"   总文件数量: {total_count}")
                print(f"   当前显示批次: {current_batch_for_display + 1}")
                print(f"   计算起始索引: {calculated_index}")
                print(f"   状态信息: {status}")
                print(f"   历史信息: {history_info}")
            
            # 更新统计信息（仅在未完成时）
            if not is_completed:
                state['total_processed_batches'] += 1
                # 在返回结果后自增批次计数（为下一次运行做准备）
                state['current_batch_run'] += 1
            
            if debug_mode:
                if not is_completed:
                    print(f"   ✅ 当前批次处理完成，下一批次将使用: {state['current_batch_run']}")
                else:
                    print(f"   ⚠️ 已达到总数上限，停止自增")
            
            # 返回结果
            result = (calculated_index, status, history_info)
            return {"result": result, "ui": {}}
            
        except Exception as e:
            error_msg = f"❌ 批量索引计算失败: {str(e)}"
            if debug_mode:
                print(error_msg)
                traceback.print_exc()  # ✅ 直接使用顶部导入的 traceback
            
            # 异常情况返回安全的默认值
            history_info = f"错误: {error_msg}"
            result = (0, f"错误: {error_msg}", history_info)
            return {"result": result, "ui": {}}
    
    def _generate_history_info(self, state: Dict, calculated_index: int, max_files_per_batch: int, total_count: int, debug_mode: bool = False) -> str:
        """生成增强的历史统计信息"""
        # 格式化重置时间
        reset_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state['last_reset_time']))
        
        # 格式化任务开始时间
        task_start_str = "未开始"
        if state['task_start_time'] is not None:
            task_start_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state['task_start_time']))
        
        # 计算已处理文件数
        processed_files = min(calculated_index + max_files_per_batch, total_count) if total_count > 0 else state['total_processed_batches'] * max_files_per_batch
        remaining_files = max(0, total_count - processed_files) if total_count > 0 else 0
        
        history = (f"📊 历史统计:\n"
                  f"   累计处理批次: {state['total_processed_batches']}\n"
                  f"   已处理文件: {processed_files}{f'/{total_count}' if total_count > 0 else ''}\n"
                  f"   剩余文件: {remaining_files}\n"
                  f"   总计跳过文件: {state['total_skipped_files']}\n"
                  f"   本次任务开始时间: {task_start_str}\n"
                  f"   上次重置时间: {reset_time_str}")
        
        return history
    
    def _generate_progress_bar(self, calculated_index: int, max_files_per_batch: int, total_count: int) -> str:
        """生成可视化进度条"""
        if total_count <= 0:
            return "可视化进度条：░░░░░░░░░░░░░░░░ 0%"
        
        # 计算当前已处理的文件数（不超过总数）
        processed_count = min(calculated_index + max_files_per_batch, total_count)
        
        # 计算进度百分比
        progress = processed_count / total_count
        progress = max(0.0, min(1.0, progress))
        
        # 生成进度条
        bar_length = 20
        filled_length = int(bar_length * progress)
        empty_length = bar_length - filled_length
        
        progress_bar = "█" * filled_length + "░" * empty_length
        percentage = f"{progress:.0%}"
        
        return f"可视化进度条：{progress_bar} {percentage}"
    
    @classmethod
    def reset_all_counters(cls):
        """✅ 重置所有实例的计数器（类方法，可以从外部调用）"""
        cls._instances_state.clear()
        print("🔄 所有批量索引步进器实例的计数器已重置（包括历史统计）")
    
    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """✅ 获取所有实例的统计信息汇总"""
        total_batches = 0
        total_skipped = 0
        
        for state in cls._instances_state.values():
            total_batches += state.get('total_processed_batches', 0)
            total_skipped += state.get('total_skipped_files', 0)
        
        return {
            "num_instances": len(cls._instances_state),
            "total_processed_batches": total_batches,
            "total_skipped_files": total_skipped,
            "all_instances_state": cls._instances_state  # ← 返回所有实例的详细状态
        }

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_BatchIndexStepper": buding_BatchIndexStepper,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_BatchIndexStepper": "🔢 增强版批量索引步进器",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
