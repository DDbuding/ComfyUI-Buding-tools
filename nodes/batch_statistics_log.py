import os
import re
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

class buding_BatchStatisticsLog:
    """
    📊 批量统计日志节点
    汇总输入、加载、保存等环节的日志，生成标准化的任务报告。
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_logs": ("STRING", {"default": "", "multiline": True, "tooltip": "输入来自各个加载/保存节点的日志信息"}),
                "target_path": ("STRING", {"default": "output/任务报告", "tooltip": "报告保存的目录路径"}),
                "filename_prefix": ("STRING", {"default": "Task_Report_", "tooltip": "报告文件名的前缀"}),
                "mode": (["追加写入", "覆盖写入", "自动顺延"], {"default": "自动顺延"}),
                "report_title": ("STRING", {"default": "", "multiline": False, "tooltip": "自定义报告标题，留空则使用默认标题"}),
                "header_text": ("STRING", {"default": "", "multiline": True, "tooltip": "在标题行下方、统计内容上方显示的自定义文本"}),
                "footer_text": ("STRING", {"default": "", "multiline": True, "tooltip": "在报告结尾追加的自定义文本"}),
                "prepend_newline": ("BOOLEAN", {"default": True, "tooltip": "追加写入时，在内容前补两个换行"}),
                "auto_create_dirs": ("BOOLEAN", {"default": True, "tooltip": "目录不存在时自动创建"}),
            }
        }

    RETURN_TYPES = ("STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("文件路径", "写入成功", "报告预览")
    FUNCTION = "generate_report"
    CATEGORY = "buding_Tools/Log"

    def generate_report(self, input_logs: str, target_path: str, filename_prefix: str, mode: str,
                        report_title: str, header_text: str, footer_text: str, 
                        prepend_newline: bool, auto_create_dirs: bool):
        try:
            # 1. 路径处理
            if not target_path or target_path.strip() == "":
                target_path = "output/任务报告"
                
            dir_path = Path(target_path).expanduser()
            if auto_create_dirs and not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)

            # 2. 文件名与序号逻辑
            if mode == "追加写入":
                # 追加模式：从文件内容提取序号
                full_path = dir_path / f"{filename_prefix}.txt"
                index = self._get_next_index_append_mode(full_path)
                index_str = f"{index:04d}"
                file_name = f"{filename_prefix}.txt"
                write_mode = "a"
            else:
                # 自动顺延和覆盖模式：使用原逻辑
                index = self._get_next_index(dir_path, filename_prefix)
                index_str = f"{index:04d}"
                
                if mode == "自动顺延":
                    file_name = f"{filename_prefix}{index_str}.txt"
                    write_mode = "w"
                else:  # 覆盖写入
                    file_name = f"{filename_prefix}.txt"
                    write_mode = "w"
                    index_str = "0001"  # 覆盖模式下标题序号默认为0001
            
            full_path = dir_path / file_name
            
            # 3. 解析输入日志
            parsed_data = self._parse_logs(input_logs)
            
            # 4. 构建报告内容
            report_content = self._build_report(index_str, report_title, header_text, parsed_data, footer_text)
            
            # 5. 保存文件
            # 设定分隔符 (加长版)
            separator = "◆ ◇ " * 35 + "◆"
            # 分隔符仅放在最后一行
            final_content = f"{report_content}\n{separator}"

            if write_mode == "a" and full_path.exists():
                # 追加模式下，先补两个换行
                with open(full_path, "a", encoding="utf-8") as f:
                    f.write("\n\n")
                
            with open(full_path, write_mode, encoding="utf-8") as f:
                f.write(final_content)
            
            # 6. 生成预览
            preview = final_content.strip()
            if len(preview) > 1000:
                preview = preview[:1000] + "\n\n... (内容过长已截取)"
                
            return (str(full_path), True, preview)

        except Exception as e:
            import traceback
            error_msg = f"生成报告失败: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            # 即使失败也返回预览，方便调试
            return ("", False, error_msg)

    def _get_next_index(self, directory: Path, prefix: str) -> int:
        """扫描目录获取下一个序号"""
        import glob
        try:
            pattern = os.path.join(str(directory), f"{prefix}*.txt")
            files = glob.glob(pattern)
            
            max_idx = 0
            for f in files:
                name = os.path.basename(f)
                # 提取前缀后的数字部分
                match = re.search(rf"{re.escape(prefix)}(\d+)", name)
                if match:
                    try:
                        idx = int(match.group(1))
                        if idx > max_idx:
                            max_idx = idx
                    except ValueError:
                        continue
            return max_idx + 1
        except Exception:
            return 1

    def _get_next_index_append_mode(self, file_path: Path) -> int:
        """追加模式：从文件内容中提取最大序号"""
        if not file_path.exists():
            return 1
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取标题开头序号 ⭐0001⭐ (在新格式中只匹配标题序号，不匹配末尾数字)
            # 匹配模式：⭐数字⭐标题⭐🕒 报告时间:
            pattern = r"⭐(\d+)⭐.*⭐🕒 报告时间:"
            matches = re.findall(pattern, content)
            
            if matches:
                # 找到最大序号并+1
                max_idx = max(int(match) for match in matches)
                return max_idx + 1
            else:
                return 1
        except Exception:
            # 读取失败时安全回退
            return 1

    def _parse_logs(self, logs: str) -> Dict[str, Any]:
        """解析输入的各种日志信息"""
        data = {
            "input": None,      # 📥 批量读取统计
            "assets": {         # 📊 批量加载完成
                "images": 0,
                "videos": 0,
                "audios": 0,
                "texts": 0,
                "excel": 0,
                "end_pos": "未知",
                "end_line": 0
            },
            "output": {         # 📊 批量保存完成
                "images": 0,
                "videos": 0,
                "audios": 0,
                "last_file": "未知"
            },
            "history": {        # 📊 历史统计
                "processed": 0,
                "total": 0
            },
            "system": {
                "root_dir": "",
                "time": "",
                "duration": "0",
                "load_time": "",
                "save_time": ""
            }
        }
        
        if not logs:
            return data

        # 分割日志块（按 📊 或 📥 分割）
        blocks = re.split(r"(?=📊|📥)", logs)
        
        for block in blocks:
            block = block.strip()
            if not block: continue
            
            # --- 1. 解析 📥 批量读取统计 (TXT) ---
            if "📥 批量读取统计" in block:
                inp = {}
                m_count = re.search(r"✅ 文件总数: (\d+)", block)
                if m_count: inp["file_count"] = m_count.group(1)
                
                m_dir = re.search(r"📂 根目录: (.*)", block)
                if m_dir: inp["root_dir"] = m_dir.group(1).strip()
                
                m_data = re.search(r"📉 数据量: 扫描 (\d+) 行 -> 筛选输出 (\d+) 行", block)
                if m_data:
                    inp["scanned_lines"] = m_data.group(1)
                    inp["output_lines"] = m_data.group(2)
                
                m_list = re.search(r"🏷️ 文件名清单 \(前 \d+ 个\):\n([\s\S]*?)-{10,}", block)
                if m_list:
                    file_list = m_list.group(1).strip()
                    inp["file_list"] = file_list
                    # 自动识别文件清单中的资产类型
                    for line in file_list.split("\n"):
                        line_lower = line.lower()
                        if ".txt" in line_lower:
                            data["assets"]["texts"] += 1
                        elif ".xlsx" in line_lower or ".xls" in line_lower:
                            data["assets"]["excel"] += 1
                        elif ".png" in line_lower or ".jpg" in line_lower or ".jpeg" in line_lower:
                            data["assets"]["images"] += 1
                        elif ".mp4" in line_lower or ".avi" in line_lower or ".mov" in line_lower:
                            data["assets"]["videos"] += 1
                        elif ".wav" in line_lower or ".mp3" in line_lower or ".flac" in line_lower:
                            data["assets"]["audios"] += 1
                
                m_end_pos = re.search(r"📍 结束位置: (.*)", block)
                if m_end_pos:
                    end_pos = m_end_pos.group(1).strip()
                    inp["end_pos"] = end_pos
                    data["assets"]["end_pos"] = end_pos  # 同步到assets
                
                m_end_line = re.search(r"📌 结束行号: 第 (\d+) 行", block)
                if m_end_line:
                    end_line = m_end_line.group(1)
                    inp["end_line"] = end_line
                    data["assets"]["end_line"] = int(end_line)  # 同步到assets
                
                data["input"] = inp

            # --- 2. 解析 📊 批量加载完成 (Assets) ---
            elif "📊 批量加载完成" in block:
                m_img = re.search(r"🖼️ 图像: (\d+)", block)
                if m_img: data["assets"]["images"] = int(m_img.group(1))
                
                m_vid = re.search(r"🎬 视频: (\d+)", block)
                if m_vid: data["assets"]["videos"] = int(m_vid.group(1))
                
                m_aud = re.search(r"🎵 音频: (\d+)", block)
                if m_aud: data["assets"]["audios"] = int(m_aud.group(1))
                
                m_txt = re.search(r"📄 文本: (\d+)", block)
                if m_txt: data["assets"]["texts"] = int(m_txt.group(1))
                
                m_xls = re.search(r"📊 Excel: (\d+)", block)
                if m_xls: data["assets"]["excel"] = int(m_xls.group(1))
                
                m_time = re.search(r"🕒 时间: (.*)", block)
                if m_time: 
                    data["system"]["time"] = m_time.group(1).strip()
                    data["system"]["load_time"] = m_time.group(1).strip()

            # --- 3. 解析 📊 批量保存完成 (ListReceiveInfo) ---
            elif "📊 批量保存完成 |" in block:
                m_dir = re.search(r"📂 根目录: (.*)", block)
                if m_dir: data["system"]["root_dir"] = m_dir.group(1).strip()

                m_time = re.search(r"🕒 时间: (.*)", block)
                if m_time:
                    ts = m_time.group(1).strip()
                    data["system"]["time"] = ts
                    data["system"]["save_time"] = ts
                
                # 自动提取结束文件名并识别类型
                m_end_file = re.search(r"🔚 结束于: (.*)", block)
                if m_end_file:
                    filename = m_end_file.group(1).strip()
                    data["output"]["last_file"] = filename
                    # 根据扩展名自动识别产出类型
                    filename_lower = filename.lower()
                    if ".png" in filename_lower or ".jpg" in filename_lower or ".jpeg" in filename_lower:
                        m_count = re.search(r"🔢 总计: (\d+)", block)
                        if m_count: data["output"]["images"] = int(m_count.group(1))
                    elif ".mp4" in filename_lower or ".avi" in filename_lower or ".mov" in filename_lower or ".webm" in filename_lower:
                        m_count = re.search(r"🔢 总计: (\d+)", block)
                        if m_count: data["output"]["videos"] = int(m_count.group(1))
                    elif ".wav" in filename_lower or ".mp3" in filename_lower or ".flac" in filename_lower:
                        m_count = re.search(r"🔢 总计: (\d+)", block)
                        if m_count: data["output"]["audios"] = int(m_count.group(1))

            # --- 4. 解析 📊 批量保存完成 (Output) ---
            elif "📊 批量保存完成" in block:
                m_img = re.search(r"🖼️ 图像: (\d+)", block)
                if m_img: data["output"]["images"] = int(m_img.group(1))
                
                m_vid = re.search(r"🎬 视频: (\d+)", block)
                if m_vid: data["output"]["videos"] = int(m_vid.group(1))
                
                m_aud = re.search(r"🎵 音频: (\d+)", block)
                if m_aud: data["output"]["audios"] = int(m_aud.group(1))
                
                m_dir = re.search(r"📂 根目录: (.*)", block)
                if m_dir: data["system"]["root_dir"] = m_dir.group(1).strip()
                
                m_time = re.search(r"🕒 时间: (.*)", block)
                if m_time: 
                    data["system"]["time"] = m_time.group(1).strip()
                    data["system"]["save_time"] = m_time.group(1).strip()

            # --- 4. 解析 📊 历史统计 ---
            elif "📊 历史统计" in block:
                m_hist = re.search(r"已处理文件: (\d+)/(\d+)", block)
                if m_hist:
                    data["history"]["processed"] = int(m_hist.group(1))
                    data["history"]["total"] = int(m_hist.group(2))

                # 优先解析本次任务开始时间
                m_task_start = re.search(r"本次任务开始时间: (.*)", block)
                if m_task_start:
                    data["system"]["task_start_time"] = m_task_start.group(1).strip()
                
                # 解析上次重置时间
                m_reset = re.search(r"上次重置时间: (.*)", block)
                if m_reset:
                    data["system"]["reset_time"] = m_reset.group(1).strip()
                
                # 向后兼容：如果没有本次任务开始时间，使用上次重置时间
                if not data["system"].get("task_start_time") and data["system"].get("reset_time"):
                    data["system"]["task_start_time"] = data["system"]["reset_time"]

            # --- 5. 解析耗时 ---
            durations = re.findall(r"总生成时间: (\d+\.?\d*)秒", block)
            if durations:
                current_dur = float(data["system"]["duration"])
                data["system"]["duration"] = f"{current_dur + sum(float(d) for d in durations):.2f}"

        # 计算两个不同的耗时
        if data["system"]["save_time"]:
            try:
                from datetime import datetime

                def _parse_time(value: str):
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                        try:
                            return datetime.strptime(value, fmt)
                        except ValueError:
                            continue
                    return None

                save_time = _parse_time(data["system"]["save_time"])
                if save_time:
                    # 计算本次任务耗时（秒）：结束时间 - 本次任务开始时间
                    if data["system"].get("task_start_time"):
                        task_start = _parse_time(data["system"]["task_start_time"])
                        if task_start:
                            task_duration_seconds = int((save_time - task_start).total_seconds())
                            data["system"]["task_duration"] = max(0, task_duration_seconds)
                    
                    # 计算本轮任务总耗时（分钟）：结束时间 - 上次重置时间
                    if data["system"].get("reset_time"):
                        reset_time = _parse_time(data["system"]["reset_time"])
                        if reset_time:
                            reset_duration_seconds = int((save_time - reset_time).total_seconds())
                            if reset_duration_seconds <= 0:
                                reset_duration_minutes = 0
                            else:
                                # 向上取整：119秒->2分钟，123秒->3分钟
                                reset_duration_minutes = (reset_duration_seconds + 59) // 60
                            data["system"]["reset_duration"] = reset_duration_minutes
            except Exception:
                pass

        return data

    def _build_report(self, index_str: str, report_title: str, header_text: str, data: Dict[str, Any], footer_text: str) -> str:
        """构建最终报告文本"""
        title = report_title if report_title and report_title.strip() else "📊 产出任务汇总报告"
        
        # 计算数值
        # 已完成任务数：优先取历史统计中的已处理数，无则取本次产出数
        completed_tasks = data["history"]["processed"]
        if completed_tasks == 0:
            completed_tasks = max(data["output"]["images"], data["output"]["videos"], data["output"]["audios"])
        
        if completed_tasks == 0:
            completed_tasks = max(data["assets"]["images"], data["assets"]["videos"], data["assets"]["audios"])
            
        # 建议重启任务的起始数：等于已完成任务数（索引逻辑，不+1）
        next_start = completed_tasks
        
        # 本轮设定任务数：等于已处理文件1/10，里的10
        total_tasks = data["history"]["total"]
        if total_tasks == 0:
            total_tasks = completed_tasks
            
        duration = data["system"]["duration"]
        
        # 获取两个不同的耗时
        task_duration = data["system"].get("task_duration", 0)  # 本次任务耗时（秒）
        reset_duration = data["system"].get("reset_duration", 0)  # 本轮任务总耗时（分钟）
        
        # 获取报告时间
        report_time = data["system"]["time"] if data["system"]["time"] else time.strftime('%Y-%m-%d %H:%M:%S')
        
        lines = []
        # ⭐0001⭐标题⭐🕒 报告时间: 2026-01-02 20:19:38🕒616🕒⭐
        lines.append(f"⭐{index_str}⭐{title}⭐🕒 报告时间: {report_time}⭐🕒{next_start}🕒⭐")
        # ❗❗本次任务耗时：520秒❗❗本轮任务总耗时：8分钟❗❗ 建议重启任务的起始数：18❗❗
        lines.append(f"❗❗本次任务耗时：{task_duration}秒❗❗本轮任务总耗时：{reset_duration}分钟❗❗ 建议重启任务的起始数：{next_start}❗❗")
        # ⚪⚪本轮设定任务数：170⚪⚪已完成任务数：17⚪⚪
        lines.append(f"⚪⚪本轮设定任务数：{total_tasks}⚪⚪已完成任务数：{completed_tasks}⚪⚪")
        
        if header_text.strip():
            lines.append(header_text.strip())
            
        lines.append("=" * 50)
        
        # 1. 产出统计 (Output)
        out_lines = []
        o = data["output"]
        if o["videos"] > 0: out_lines.append(f"   🎬 视频成品: {o['videos']} 个")
        if o["images"] > 0: out_lines.append(f"   🖼️ 图片成品: {o['images']} 张")
        if o["audios"] > 0: out_lines.append(f"   🎵 音频成品: {o['audios']} 个")
        
        if out_lines:
            lines.append("1. 产出统计 (Output)")
            lines.extend(out_lines)
            lines.append("")

        # 2. 产出信息 (System)
        lines.append("2. 产出信息 (System)")
        lines.append(f"   📂 根目录: {data['system']['root_dir'] or '未知'}")
        lines.append(f"   🔚 结束于: {data['output']['last_file']}")
        lines.append(f"   🕒 报告时间: {data['system']['time'] if data['system']['time'] else time.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # 3. 资产加载 (Assets)
        asset_lines = []
        a = data["assets"]
        if a["images"] > 0: asset_lines.append(f"   - 图像资源: {a['images']} 个已加载")
        if a["videos"] > 0: asset_lines.append(f"   - 视频资源: {a['videos']} 个已加载")
        if a["audios"] > 0: asset_lines.append(f"   - 角色参考音频: {a['audios']} 个已加载")
        if a["texts"] > 0: asset_lines.append(f"   - 提示词文本行: {a['texts']} 个已加载")
        if a["excel"] > 0: asset_lines.append(f"   - 表格数据: {a['excel']} 个已加载")
        
        if asset_lines:
            lines.append("3. 资产加载 (Assets)")
            lines.extend(asset_lines)
            lines.append(f"📍 结束位置: {data['assets']['end_pos']}")
            lines.append(f"📌 结束行号: 第 {data['assets']['end_line']} 行 (文件内行号)")
            lines.append("")

        # 4. 资产源头 (Input)
        if data["input"]:
            inp = data["input"]
            lines.append("4. 资产源头 (Input）")
            lines.append(f"    ✅ TXT文件总数: {inp.get('file_count', '0')}")
            lines.append(f"    📂 根目录: {inp.get('root_dir', '未知')}")
            lines.append(f"    📉 数据量: 扫描 {inp.get('scanned_lines', '0')} 行 -> 筛选输出 {inp.get('output_lines', '0')} 行")
            lines.append("-" * 40)
            if inp.get("file_list"):
                file_list = inp["file_list"].split("\n")
                for f in file_list:
                    if f.strip():
                        clean_f = re.sub(r"^\s*\d+\.\s*", "", f)
                        lines.append(f"     > {clean_f}")
                lines.append("-" * 40)
            lines.append(f"📍 结束位置: {inp.get('end_pos', '未知')}")
            lines.append(f"📌 结束行号: 第 {inp.get('end_line', '0')} 行 (文件内行号)")
            lines.append("")

        if footer_text.strip():
            lines.append("=" * 50)
            lines.append(footer_text.strip())
            lines.append("")

        return "\n".join(lines)

NODE_CLASS_MAPPINGS = {
    "buding_BatchStatisticsLog": buding_BatchStatisticsLog
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_BatchStatisticsLog": "📊 Batch Statistics Log (批量统计日志)"
}
