"""
✂️ Path Name Extractor (路径名提取器)
功能：从路径字符串中提取文件名（Stem），支持添加父目录前缀，支持长度截断。
更新：
1. 增加严格的空值检查，防止报错。
2. 新增"父目录名"独立输出，始终输出父目录名（不受前缀开关影响）。
"""

import os

class PathNameExtractor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 支持手动粘贴多行路径，也支持接收上游的 List 字符串
                "path_string": ("STRING", {"default": "", "multiline": True, "forceInput": False}),
                
                # 开关 1：是否添加父目录名前缀
                # 开启后：主输出 "📄提取结果" 会变成 "父目录-文件名" 格式
                # 副输出 "📂父目录名" 始终输出父目录名（不受此开关影响）
                "add_parent_prefix": ("BOOLEAN", {"default": False, "label": "📁 添加父目录前缀 (Parent-File)"}),
                
                # 开关 2：是否提取完整文件名 (关闭则截取前20字)
                "full_name_mode": ("BOOLEAN", {"default": True, "label": "📝 提取完整文件名 (关闭则限长20字)"}),
            }
        }    # 增加了一个输出：父目录名
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("📄提取结果", "📂父目录名")

    # 两个输出都是 List，保持同步循环
    OUTPUT_IS_LIST = (True, True)

    FUNCTION = "extract_name"
    CATEGORY = "buding_Tools/文本处理"

    def extract_name(self, path_string, add_parent_prefix, full_name_mode):
        # 1. 统一处理输入格式
        if isinstance(path_string, list):
            paths = path_string
        elif isinstance(path_string, str):
            paths = [p.strip() for p in path_string.splitlines() if p.strip()]
        else:
            paths = []

        # 🚀 严格验证：如果列表为空，直接返回空结果，防止报错
        if not paths:
            print("⚠️ [PathNameExtractor] 输入路径为空，跳过处理")
            return ([], [])

        results = []
        parent_names_list = []

        for p in paths:
            # 2. 清理路径 & 兼容性
            clean_path = p.strip('"').strip("'").replace("\\", "/")
            if not clean_path: continue

            # 3. 基础信息提取
            # 移除末尾斜杠，确保文件夹路径也能取到 basename
            clean_path = clean_path.rstrip("/")

            base_name = os.path.basename(clean_path)
            stem, _ = os.path.splitext(base_name)

            # 获取父目录信息
            parent_dir = os.path.dirname(clean_path)
            parent_name = os.path.basename(parent_dir)

            # 4. 构建主输出结果 (文件名)
            final_name = stem

            if add_parent_prefix:
                if parent_name:
                    final_name = f"{parent_name}-{stem}"

            if not full_name_mode:
                final_name = final_name[:20]

            results.append(final_name)

            # 5. 构建副输出结果 (父目录名)
            # 逻辑：始终输出父目录名（如果存在），不受开关影响
            if parent_name:
                parent_names_list.append(parent_name)
            else:
                parent_names_list.append("")

        print(f"✂️ [PathNameExtractor] 处理完成: {len(results)} 条")

        # 返回两个列表
        return (results, parent_names_list)

# 节点映射配置
NODE_CLASS_MAPPINGS = {
    "buding_PathNameExtractor": PathNameExtractor
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_PathNameExtractor": "✂️ Path Name Extractor (路径名提取器)"
}