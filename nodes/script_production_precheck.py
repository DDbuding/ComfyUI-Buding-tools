import re
from collections import Counter
import unicodedata
import comfy.utils

class ScriptProductionPrecheck:
    """
    剧本生产预检报告节点
    分析剧本文本，生成按戏份权重排序的角色分析报告
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "script_text": ("STRING", {
                    "multiline": True,
                    "default": "[苏尘]<平静>这是示例剧本。\n[翠儿]<开心>你好！\n-2s-\n[旁白]<叙事>故事开始了...",
                    "tooltip": "输入剧本文本，格式：[角色名]<情绪>台词内容；停顿用 -Xs- 表示"
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("precheck_report",)
    FUNCTION = "analyze_script"
    CATEGORY = "buding_Tools/Analysis"

    def analyze_script(self, script_text):
        """
        分析剧本文本，生成预检报告
        """
        if not script_text or not script_text.strip():
            return ("❌ 错误：剧本文本为空，请输入有效的剧本内容",)

        try:
            # 1. 解析剧本，提取角色和台词
            segments = self._parse_script_segments(script_text)

            if not segments:
                return ("❌ 错误：未找到有效的剧本段落，请检查格式",)

            # 2. 统计角色台词频率和收集信息
            role_counts = Counter()
            total_chars = 0
            pause_count = 0
            long_sentence_warnings = []

            # 定义基础情绪集合（后续所有不在此列表中的都是特殊情绪）
            base_emotions = {
                # 维度1：开心相关
                "开心", "轻微", "中等", "强烈", "雀跃", "兴奋",
                "开心-轻微", "开心-中等", "开心-强烈",
                # 维度2：愤怒相关
                "愤怒", "中等", "强烈", "生气", "不满",
                "愤怒-中等", "愤怒-强烈",
                # 维度3：悲伤相关
                "悲伤", "中等", "强烈", "难过", "沮丧",
                "悲伤-中等", "悲伤-强烈",
                # 维度7：惊讶相关
                "惊讶", "中等", "震惊", "意外",
                "惊讶-中等",
                # 其他常见基础情绪
                "平静", "正常", "普通", "自然", "中性", "叙事",
                "深沉", "威严", "恭敬", "好奇", "警惕", "冷静"
            }

            # 收集所有情绪出现情况
            all_emotions = Counter()  # 情绪 -> 出现次数
            special_emotion_details = {}  # 特殊情绪 -> {"count": 次数, "occurrences": [(角色, 行号), ...]}
            role_actions = {}  # 收集每个角色的动作关键词

            for seg in segments:
                if seg["type"] == "pause":
                    pause_count += 1
                elif seg["type"] == "dialog":
                    role = seg["role"]
                    text = seg["text"]
                    emotion = seg.get("emotion", "")
                    action = seg.get("action", "")

                    role_counts[role] += 1
                    total_chars += len(text)

                    # 收集动作关键词
                    if role not in role_actions:
                        role_actions[role] = set()
                    if action:
                        role_actions[role].add(action)

                    # 检测情绪（区分基础情绪和特殊情绪）
                    if emotion:
                        all_emotions[emotion] += 1
                        # 如果不是基础情绪，则为特殊情绪
                        if emotion not in base_emotions:
                            if emotion not in special_emotion_details:
                                special_emotion_details[emotion] = {"count": 0, "occurrences": []}
                            special_emotion_details[emotion]["count"] += 1
                            special_emotion_details[emotion]["occurrences"].append((role, seg["line_num"]))

                    # 检测超长句（按字符数）
                    if len(text) > 35:  # 35字符约等于15-20字
                        long_sentence_warnings.append(f"{role} ({len(text)}字)")

            # 3. 按台词数量降序排序
            sorted_role_tuples = role_counts.most_common()
            total_dialogs = sum(role_counts.values())

            # 4. 生成报告
            report_lines = []

            # 标题
            report_lines.append("=" * 90)
            report_lines.append("🎭🎵 剧组角色配音报告 | 核心模式: 批量配音准备")
            report_lines.append("-" * 90)

            # 全角色检索名录
            if sorted_role_tuples:
                sorted_names = [role for role, count in sorted_role_tuples]
                names_str = "、".join(sorted_names)
                report_lines.append(f"📌 全角色检索名录 (共 {len(sorted_names)} 名, 按台词浓度由高到低排序):")
                report_lines.append(names_str)
                report_lines.append("")

            # 统计概览
            estimated_duration = self._estimate_duration(total_chars, pause_count)
            report_lines.append(f"统计概览: 对话总数 {total_dialogs} 条 | 停顿间隔 {pause_count} 处 | 总字数 {total_chars} 字 | 预计时长 {estimated_duration}")
            report_lines.append("-" * 90)

            # 建议音色选型清单
            if sorted_role_tuples:
                report_lines.append("✅ 建议音色选型清单 (按戏份权重排序):")
                report_lines.append("")
                report_lines.append("No. | 角色           | 台词数 | 戏份占比 | 建议音色特质        | 基于分析的关键词")
                report_lines.append("--- | -------------- | ------ | -------- | ------------------ | ----------------------------------------------------")

                for i, (role, count) in enumerate(sorted_role_tuples, 1):
                    percentage = (count / total_dialogs * 100) if total_dialogs > 0 else 0
                    voice_trait_full = self._suggest_voice_trait(role, count, percentage, role_actions.get(role, set()))
                    
                    # 拆分音色特质和关键词
                    if " 依据: " in voice_trait_full:
                        trait_part, keyword_part = voice_trait_full.split(" 依据: ", 1)
                    else:
                        trait_part = voice_trait_full
                        keyword_part = ""
                    
                    # 使用精确对齐格式化表格行
                    role_display = role[:20]  # 预留20个字符，但实际显示宽度为14
                    trait_display = trait_part[:30]  # 预留30个字符，但实际显示宽度为18
                    
                    no_str = self.pad_string(str(i), 3, "right")
                    role_str = self.pad_string(role_display, 14, "left")
                    count_str = self.pad_string(f"{count} 句", 6, "left")
                    percent_str = self.pad_string(f"{percentage:>6.1f}%", 8, "left")
                    trait_str = self.pad_string(trait_display, 18, "left")
                    
                    report_lines.append(f"{no_str} | {role_str} | {count_str} | {percent_str} | {trait_str} | {keyword_part}")

                report_lines.append("")

            # 异常监测
            report_lines.append("⚠️ 异常监测 (风险规避):")

            if long_sentence_warnings:
                warnings_str = "、".join(long_sentence_warnings[:3])  # 最多显示3个
                if len(long_sentence_warnings) > 3:
                    warnings_str += f"等共 {len(long_sentence_warnings)} 处"
                report_lines.append(f"- [超长句预警]: {warnings_str} -> 建议手动切分或增加断句。")

            # 特殊情绪提醒（动态识别）
            if special_emotion_details:
                report_lines.append("- [特殊情绪提醒]: ")
                for emotion, details in special_emotion_details.items():
                    count = details["count"]
                    occurrences = details["occurrences"]
                    # 按角色分组统计
                    role_line_map = {}
                    for role, line_num in occurrences:
                        if role not in role_line_map:
                            role_line_map[role] = []
                        role_line_map[role].append(line_num)

                    # 生成角色-行号列表
                    role_line_strs = []
                    for role in sorted(role_line_map.keys()):
                        line_nums = sorted(role_line_map[role])
                        line_str = f"{role}-{','.join(map(str, line_nums))}"
                        role_line_strs.append(line_str)

                    roles_line_str = "、".join(role_line_strs)
                    emotion_desc = self._get_emotion_risk_description(emotion)
                    report_lines.append(f"  * {emotion} (共 {count} 处): {roles_line_str}{emotion_desc}")

            if not long_sentence_warnings and not special_emotion_details:
                report_lines.append("- 无异常检测到，剧本质量良好")

            report_lines.append("=" * 90)

            final_report = "\n".join(report_lines)
            return (final_report,)

        except Exception as e:
            import traceback
            error_msg = f"❌ 分析过程中出现错误: {str(e)}\n{traceback.format_exc()}"
            return (error_msg,)

    def _parse_script_segments(self, script_text):
        """
        解析剧本文本，提取段落信息
        支持格式：
        [角色名]<情绪>(动作):台词内容
        -Xs- (停顿)
        """
        segments = []
        lines = script_text.strip().split('\n')

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            # 检查是否是停顿标记
            pause_match = re.match(r'-(\d+(?:\.\d+)?)s?-', line)
            if pause_match:
                duration = float(pause_match.group(1))
                segments.append({
                    "type": "pause",
                    "duration": duration,
                    "line_num": line_num
                })
                continue

            # 检查是否是对话行：支持 [角色]<情绪>(动作):台词 或 [角色]<情绪>台词
            dialog_match = re.match(r'^\[([^\]]+)\](?:<([^>]+)>)?(?:\(([^)]+)\))?(?::)?(.+)$', line)
            if dialog_match:
                role = dialog_match.group(1).strip()
                emotion = dialog_match.group(2).strip() if dialog_match.group(2) else ""
                action = dialog_match.group(3).strip() if dialog_match.group(3) else ""
                text = dialog_match.group(4).strip()

                segments.append({
                    "type": "dialog",
                    "role": role,
                    "emotion": emotion,
                    "action": action,
                    "text": text,
                    "line_num": line_num
                })

        return segments

    def _estimate_duration(self, total_chars, pause_count):
        """
        估算总时长
        基于经验：中文普通语速约200-250字/分钟，考虑停顿
        """
        # 基础语速：200字/分钟 = 3.33字/秒
        base_duration_seconds = total_chars / 3.33

        # 停顿时间：假设平均每个停顿2秒
        pause_duration_seconds = pause_count * 2

        total_seconds = base_duration_seconds + pause_duration_seconds

        # 转换为分秒格式
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)

        if minutes > 0:
            return f"{minutes}'{seconds:02d}\""
        else:
            return f"{seconds}\""

    def _suggest_voice_trait(self, role, count, percentage, actions):
        """
        基于角色名、戏份占比和动作关键词建议音色特质
        """
        # 基于角色名的关键词分析
        role_lower = role.lower()
        actions_str = "、".join(actions) if actions else ""

        # 特定角色分析
        if "苏尘" in role or "尘" in role:
            return "[磁性/青年/松弛] 依据: 眼神慵懒、坏笑、挑眉、哼曲"
        elif "宋子阳" in role:
            return "[青年/热血/跳脱] 依据: 雀跃、坏笑、挑眉、挥臂"
        elif "甘文豪" in role:
            return "[斯文/推演/睿智] 依据: 推眼镜、思索、分析、扫码"
        elif "甘桑" in role:
            return "[好奇/憨厚/活泼] 依据: 戳头盔、打量、追蛐蛐、扒铠甲"
        elif "旁白" in role or "叙事" in role:
            return "[稳重/叙事/史诗] 依据: 无明显动作标签，语气厚重"
        elif "蓝公公" in role:
            return "[年长/深沉/威严] 依据: 宫廷背景、声音沙哑、释然"
        elif "王重" in role:
            return "[狠戾/反派/中年] 依据: 勒马、挥刀、眼神狠厉、冷笑"
        elif "系统提示音" in role:
            return "[机械/中性/无情] 依据: 叮咚、系统音、无感情"
        elif "室友" in role:
            return "[少年/随意/慵懒] 依据: 叼棒棒糖、咂嘴、摇头"
        elif "里正张全剩" in role:
            return "[苍老/恭敬/局促] 依据: 躬身、行礼、侧身引路"
        elif "翠儿" in role:
            return "[甜美/少女/羞涩] 依据: 娇羞、脸颊泛红、低头跺脚"
        elif "士兵" in role:
            if "兵长" in role:
                return "[急促/冷淡/警惕] 依据: 捂住嘴、低声、厌恶"
            else:
                return "[粗犷/恐惧/惊慌] 依据: 变调、惨叫、瞳孔骤缩"
        elif "村民" in role:
            return "[龙套/通用/好奇] 依据: 踮脚张望、惊奇"

        # 基于动作关键词的通用分析
        if actions:
            action_keywords = {
                "推眼镜": "[斯文/睿智/中年]",
                "坏笑": "[玩世/不恭/青年]",
                "挑眉": "[自信/傲娇/青年]",
                "挥臂": "[热血/激昂/青年]",
                "躬身": "[恭敬/局促/年长]",
                "娇羞": "[甜美/少女/羞涩]",
                "惨叫": "[恐惧/惊慌/通用]",
                "冷笑": "[狠戾/阴沉/中年]",
                "释然": "[深沉/威严/年长]",
                "思索": "[睿智/沉稳/中年]"
            }
            matched_traits = []
            for action in actions:
                for keyword, trait in action_keywords.items():
                    if keyword in action:
                        matched_traits.append(trait)
                        break
            if matched_traits:
                unique_traits = list(set(matched_traits))
                trait_str = "/".join([t.strip("[]") for t in unique_traits])
                return f"[{trait_str}] 依据: {actions_str}"

        # 基于戏份占比的默认建议
        if percentage > 40:
            return "[主角/磁性/鲜明] 依据: 戏份占比最高"
        elif percentage > 20:
            return "[重要/特色/突出] 依据: 戏份占比中等"
        elif percentage > 5:
            return "[配角/自然/均衡] 依据: 戏份占比一般"
        else:
            return "[龙套/通用/统一] 依据: 戏份占比较低，可用通用音色"

    def _get_emotion_risk_description(self, emotion):
        """
        为特殊情绪提供风险描述
        """
        risk_descriptions = {
            "狂喜": "。情绪峰值极高，注意防破音",
            "狂笑": "。情绪峰值极高，注意防破音",
            "暴怒": "。爆发性情绪，注意参数调节",
            "咆哮": "。爆发性情绪，注意参数调节",
            "嘶吼": "。爆发性情绪，注意参数调节",
            "惊恐": "。情绪波动较大，注意试听",
            "恐惧": "。情绪波动较大，注意试听",
            "惨叫": "。情绪波动较大，注意试听",
            "慵懒": "。注意声音厚度和清晰度",
            "低落": "。注意声音厚度和清晰度",
            "崩溃": "。极端情绪，建议重点试听",
            "尖叫": "。极端情绪，建议重点试听",
            "绝望": "。极端情绪，建议重点试听",
            "癫狂": "。极端情绪，建议重点试听"
        }
        return risk_descriptions.get(emotion, "。特殊情绪，建议重点试听")

    def get_display_width(self, s):
        """计算字符串在终端/等宽字体下的实际显示宽度"""
        width = 0
        for char in s:
            if unicodedata.east_asian_width(char) in ('W', 'F', 'A'):
                width += 2  # 中文/全角占2位
            else:
                width += 1  # 英文/半角占1位
        return width

    def pad_string(self, s, target_width, align="left"):
        """根据字符数进行填充对齐（适用于Markdown表格）"""
        current_len = len(s)
        if current_len >= target_width:
            return s[:target_width]  # 截断过长的内容
        padding = " " * (target_width - current_len)
        if align == "left":
            return s + padding
        elif align == "right":
            return padding + s
        else:
            return s

# 节点注册
NODE_CLASS_MAPPINGS = {
    "buding_ScriptProductionPrecheck": ScriptProductionPrecheck,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_ScriptProductionPrecheck": "🎭🎵 Script Production Precheck (剧组角色配音报告)",
}