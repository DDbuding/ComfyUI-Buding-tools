"""
批量运行控制器 (Batch Run Controller)
作为"中央司令部"，统一生成种子和分发提示词，
确保 KSampler 使用的参数和 Save 节点记录的参数 100% 一致。
"""

import random

class BatchRunController:

    def __init__(self):
        pass

    def parse_line_selector(self, line_selector, max_lines):
        """
        解析行选择器语法
        支持格式：
        - 空字符串：选择所有行
        - "1"：选择第1行
        - "1、3、5"：选择第1、3、5行
        - "1、3-5、7"：选择第1、3、4、5、7行
        """
        if not line_selector.strip():
            # 空字符串：选择所有行
            return list(range(max_lines))

        selected_lines = set()

        # 分割主要部分（用中文逗号、顿号或英文逗号）
        normalized = line_selector.replace('，', ',').replace('、', ',')
        parts = [p.strip() for p in normalized.split(',') if p.strip()]

        for part in parts:
            if '-' in part:
                # 处理范围，如"3-5"
                try:
                    range_parts = part.split('-')
                    if len(range_parts) == 2:
                        start = int(range_parts[0].strip())
                        end = int(range_parts[1].strip())
                        # 转换为0-based索引，范围包含结束值
                        start_idx = max(0, start - 1)
                        end_idx = min(max_lines, end)  # 不减1，因为range(end)不包含end
                        selected_lines.update(range(start_idx, end_idx))
                except (ValueError, IndexError):
                    continue  # 忽略无效的范围
            else:
                # 处理单个数字，如"1"
                try:
                    line_num = int(part.strip())
                    # 转换为0-based索引
                    line_idx = max(0, min(max_lines - 1, line_num - 1))
                    selected_lines.add(line_idx)
                except ValueError:
                    continue  # 忽略无效的数字

        return sorted(list(selected_lines))

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "tooltip": "🌱 基础种子：生成序列的起始数值。若行为选'fixed'，则锁定此值；若选'increment'，则从此值开始递增。"
                }),
                "seed_behavior": (["fixed", "increment", "random_increment", "random_each"], {
                    "default": "fixed",
                    "tooltip": "🎲 种子行为：\nFixed=固定种子（全部相同）\nIncrement=从base_seed开始递增\nRandom_Increment=随机前几位+末位递增\nRandom_Each=完全随机（每个种子不同）"
                }),

                # --- 核心输入区 ---
                "subject_descriptions": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "👤 主体/文件名描述输入口：用于智能文件命名（如：苏尘、红衣少女），每行一个。"
                }),
                "positive_prompts": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "📝 正向提示词输入口：请在此输入提示词，每行一个，对应每张图。"
                }),
                "line_selector": ("STRING", {
                    "default": "",
                    "tooltip": "🎯 行选择器：指定要处理的行号\n• 空=全部行\n• 1=第1行\n• 1、3、5=第1、3、5行\n• 1、3-5、7=第1、3、4、5、7行"
                }),
                "start_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 9999,
                    "tooltip": "📊 起始索引：从第几行开始处理（0-based，从0开始）"
                }),
                "max_rows": ("INT", {
                    "default": 1000,
                    "min": 1,
                    "max": 9999,
                    "tooltip": "📏 最大行数：最多处理多少行"
                }),

                # --- 行选择控制区 ---
                "start_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 9999,
                    "tooltip": "🔢 起始行索引：从第几行开始处理（从0开始计数）"
                }),
                "max_rows": ("INT", {
                    "default": 1000,
                    "min": 1,
                    "max": 9999,
                    "tooltip": "📏 最大行数：最多处理多少行"
                }),
                "line_selector": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "🎯 行选择器：指定要输出的行号\n• 为空：输出全部行\n• 单个数字：如'1'输出第1行\n• 多个数字：如'1、3、5'输出第1、3、5行\n• 范围：如'1、3-5、7'输出第1、3、4、5、7行"
                }),
                "auto_fill_missing": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "🔧 自动填充缺失项：当主体描述和提示词行数不一致时\n• 关闭：报错提示\n• 开启：自动用空格填充短的列表"
                }),
            }
        }

    # 优化输出端口名称，带有Emoji和用途提示，连线时一目了然
    RETURN_TYPES = ("INT", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = (
        "🌱 基础种子 (给KSampler)",   # INT: 连给 KSampler 的 seed
        "🔢 种子列表行",              # STRING: 种子列表（提示词行格式）
        "👤 主体描述行",              # STRING: 主体描述（提示词行格式）
        "📜 提示词行",                # STRING: 提示词（提示词行格式）
        "🔢 行号列表行",              # STRING: 行号列表（提示词行格式）
        "ℹ️ 调试信息"
    )
    OUTPUT_IS_LIST = (False, True, True, True, True, False)

    FUNCTION = "process_control"
    CATEGORY = "buding_Tools/逻辑控制"

    def process_control(self, base_seed, seed_behavior, subject_descriptions, positive_prompts,
                       start_index, max_rows, line_selector, auto_fill_missing):

        # --- 1. 解析输入文本 ---
        all_subjects_lines = [x.strip() for x in subject_descriptions.splitlines() if x.strip()]
        all_prompts_lines = [x.strip() for x in positive_prompts.splitlines() if x.strip()]

        # 检查两个列表长度是否一致
        subjects_count = len(all_subjects_lines)
        prompts_count = len(all_prompts_lines)

        if subjects_count != prompts_count:
            if not auto_fill_missing:
                raise ValueError(f"❌ 输入长度不匹配！\n"
                               f"主体描述行数: {subjects_count}\n"
                               f"提示词行数: {prompts_count}\n"
                               f"请确保两个输入的行数一致，或启用'自动填充缺失项'选项。")

            # 自动填充缺失项为单个空格
            max_lines = max(subjects_count, prompts_count)
            if subjects_count < max_lines:
                all_subjects_lines.extend([" "] * (max_lines - subjects_count))
            if prompts_count < max_lines:
                all_prompts_lines.extend([" "] * (max_lines - prompts_count))

        max_original_lines = len(all_prompts_lines)  # 现在两个列表长度一定一致

        # --- 2. 应用行选择器（基于原始行号）---
        if line_selector.strip():
            # 使用行选择器，选择特定的行
            selected_indices = self.parse_line_selector(line_selector, max_original_lines)
            selected_prompts = [all_prompts_lines[i] for i in selected_indices if i < len(all_prompts_lines)]
            selected_subjects = [all_subjects_lines[i] for i in selected_indices if i < len(all_subjects_lines)]
            # 行号从1开始
            selected_line_numbers = [i + 1 for i in selected_indices]
        else:
            # 不使用行选择器，选择所有行
            selected_indices = list(range(max_original_lines))
            selected_prompts = all_prompts_lines
            selected_subjects = all_subjects_lines
            selected_line_numbers = list(range(1, max_original_lines + 1))

        # --- 3. 应用起始索引和最大行数限制（基于已选择的行）---
        filtered_start = max(0, min(start_index, len(selected_prompts) - 1))
        filtered_end = min(filtered_start + max_rows, len(selected_prompts))
        final_prompts = selected_prompts[filtered_start:filtered_end]
        final_subjects = selected_subjects[filtered_start:filtered_end]
        final_line_numbers = selected_line_numbers[filtered_start:filtered_end]

        # --- 4. 计算最终批次大小 ---
        batch_size = max(len(final_prompts), len(final_subjects), 1)  # 至少为1

        # --- 2. 种子控制逻辑 ---
        final_base_seed = base_seed
        
        # 种子列表生成
        seed_list = []
        
        if seed_behavior == "fixed":
            # 第一种：固定种子 - 全部使用base_seed
            seed_list = [base_seed] * batch_size
            
        elif seed_behavior == "increment":
            # 第二种：递增种子 - base_seed开始递增
            seed_list = [base_seed + i for i in range(batch_size)]
            final_base_seed = base_seed
            
        elif seed_behavior == "random_increment":
            # 第三种：随机前几位+末位递增
            # 随机生成一个新的base_seed，然后对其递增
            final_base_seed = random.randint(0, 0xffffffffffffffff)
            seed_list = [final_base_seed + i for i in range(batch_size)]
            
        elif seed_behavior == "random_each":
            # 第四种：完全随机 - 每个种子完全不同
            seed_list = [random.randint(0, 0xffffffffffffffff) for _ in range(batch_size)]
            final_base_seed = seed_list[0] if seed_list else base_seed

        # 转换为字符串格式 "123\n124\n125"，供保存节点记录
        seeds_str = "\n".join(map(str, seed_list))

        # 生成行号列表 (对应选中的行号)
        line_indices_str = "\n".join(map(str, final_line_numbers))

        # --- 3. 文本透传逻辑 ---
        # 将所有输出都转换为列表格式（与easy-use的promptLine兼容）
        seeds_list = [str(s) for s in seed_list]
        subjects_list = [str(s) for s in final_subjects]
        prompts_list = [str(p) for p in final_prompts]
        line_indices_list = [str(i) for i in final_line_numbers]

        # --- 4. 生成调试信息 ---
        selector_info = f"行选择器: '{line_selector}'" if line_selector.strip() else "行选择器: 全部"
        
        # 根据种子行为生成对应的调试信息
        if seed_behavior == "fixed":
            seed_info = f"🌱 固定种子: {final_base_seed}"
        elif seed_behavior == "increment":
            seed_info = f"🌱 递增种子: {final_base_seed} → {final_base_seed + batch_size - 1}"
        elif seed_behavior == "random_increment":
            seed_info = f"🌱 随机+递增: {final_base_seed} → {final_base_seed + batch_size - 1}"
        elif seed_behavior == "random_each":
            seed_info = f"🌱 完全随机: {batch_size}个独立种子"
        else:
            seed_info = f"🌱 起始种子: {final_base_seed}"
            
        info = (f"🎮 自动推断批次: {batch_size} | 模式: {seed_behavior}\n"
                f"{seed_info}\n"
                f"📝 选中行号: {final_line_numbers}\n"
                f"{selector_info}")

        return (final_base_seed, seeds_list, subjects_list, prompts_list, line_indices_list, info)

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_BatchRunController": BatchRunController
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_BatchRunController": "🎮 Batch Run Controller (运行控制器)"
}