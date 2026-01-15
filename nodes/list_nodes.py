from datetime import datetime

class GetListLength:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input_list": ("*",),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("length",)
    FUNCTION = "get_length"
    CATEGORY = "buding_Tools/List/Utility"

    def get_length(self, input_list):
        """获取列表长度"""
        try:
            # 检查输入是否为列表
            if isinstance(input_list, list):
                length = len(input_list)
                print(f"列表长度: {length}")
                return (length,)
            else:
                # 如果不是列表，尝试获取长度
                try:
                    length = len(input_list)
                    print(f"对象长度: {length}")
                    return (length,)
                except:
                    # 如果无法获取长度，返回1（单个对象）
                    print(f"单个对象")
                    return (1,)
        except Exception as e:
            print(f"获取长度失败: {e}")
            return (0,)


class ListReceiveInfo:
    """统计接收到的日志字符串数量，并以最后一条构造完整保存摘要。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "list_input": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "连接多个 SAVE_LOG 输出时会按 list 形式传入，节点会统计数量并以最后一条填充目录/文件/时间"
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("receive_message",)
    FUNCTION = "doit"
    CATEGORY = "buding_Tools/List/Utility"

    INPUT_IS_LIST = True

    def doit(self, list_input):
        entries = [entry for entry in list_input if entry] if list_input else []

        total = len(entries)
        final_entry = entries[-1] if entries else ""

        root_dir = "未知"
        last_file = "未知"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(final_entry, str):
            for line in final_entry.splitlines():
                line = line.strip()
                if line.startswith("📂 根目录:"):
                    root_dir = line.split("📂 根目录:", 1)[1].strip()
                elif line.startswith("🔚 结束于:"):
                    last_file = line.split("🔚 结束于:", 1)[1].strip()
                elif line.startswith("🕒 时间:"):
                    timestamp = line.split("🕒 时间:", 1)[1].strip()

        message = (
            f"📊 批量保存完成 | 🔢 总计: {total} 个文件\n"
            f"📂 根目录: {root_dir}\n"
            f"🔚 结束于: {last_file}\n"
            f"🕒 时间: {timestamp}"
        )
        print(message)
        return (message,)


NODE_CLASS_MAPPINGS = {
    "buding_Get List Length": GetListLength,
    "buding_ListReceiveInfo": ListReceiveInfo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_Get List Length": "📏 buding_Get List Length",
    "buding_ListReceiveInfo": "📋 buding_List Receive Info (统计列表数量+接收时间)",
}
