"""
图片批量保存节点 (Windows 属性精准映射版)
映射关系：
- 标题 -> 角色/主体
- 标记 -> 种子
- 备注 -> 提示词
需安装: pip install piexif
"""

import os
import re
import torch
import numpy as np
from PIL import Image, PngImagePlugin
import folder_paths
from datetime import datetime

# 尝试导入 piexif
try:
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False

def create_xmp_metadata(title, keywords, description, creator="ComfyUI"):
    """
    创建XMP元数据XML，用于PNG文件的元数据嵌入
    """
    # XMP的基本结构
    xmp_template = '''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.3-c011 66.145661, 2012/02/06-14:56:27">
   <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
      <rdf:Description rdf:about=""
            xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:xmp="http://ns.adobe.com/xap/1.0/"
            xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/"
            xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/">
         <dc:title>
            <rdf:Alt>
               <rdf:li xml:lang="x-default">{title}</rdf:li>
            </rdf:Alt>
         </dc:title>
         <dc:creator>
            <rdf:Seq>
               <rdf:li>{creator}</rdf:li>
            </rdf:Seq>
         </dc:creator>
         <dc:description>
            <rdf:Alt>
               <rdf:li xml:lang="x-default">{description}</rdf:li>
            </rdf:Alt>
         </dc:description>
         <dc:subject>
            <rdf:Bag>
               <rdf:li>{keywords}</rdf:li>
            </rdf:Bag>
         </dc:subject>
         <xmp:CreateDate>{create_date}</xmp:CreateDate>
         <xmp:CreatorTool>{creator}</xmp:CreatorTool>
         <photoshop:Headline>{title}</photoshop:Headline>
         <photoshop:Credit>{creator}</photoshop:Credit>
         <photoshop:CaptionWriter>{creator}</photoshop:CaptionWriter>
      </rdf:Description>
   </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
'''

    # 格式化XMP
    create_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    xmp_content = xmp_template.format(
        title=title,
        keywords=keywords,
        description=description,
        creator=creator,
        create_date=create_date
    )

    return xmp_content

class ImageBatchSave:
    def __init__(self):
        self.output_dir = folder_paths.get_output_directory()
        self.type = "output"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "要保存的图像张量，支持批量图像输入"}),
                "filename_prefix": ("STRING", {"default": "001", "multiline": False, "tooltip": "文件名前缀，用于生成基础文件名，如 'batch_001'"}),
                "output_subdir": ("STRING", {"default": "Image_Batch", "multiline": False, "tooltip": "输出子目录名称，将在ComfyUI输出目录下创建此子目录"}),
                "auto_name_detail": ("BOOLEAN", {"default": False, "tooltip": "自动命名：启用后将种子和提示词信息自动添加到文件名中，便于文件管理"}),
                "save_format": ("BOOLEAN", {"default": False, "label_on": "PNG (无损)", "label_off": "JPEG (EXIF属性显示)", "tooltip": "选择保存格式：JPEG(默认)在Windows属性窗口完整显示元数据，PNG保持无损但属性显示不完整"}),

                # --- 映射输入区 ---
                "seeds": ("STRING", {"default": "", "multiline": True, "tooltip": "种子列表，支持字符串（每行一个种子）或列表格式，对应图片属性的【标记】字段"}),
                "subject_descriptions": ("STRING", {"default": "", "multiline": True, "tooltip": "主体描述列表，支持字符串（每行一个描述）或列表格式，对应图片属性的【标题】字段"}),
                "positive_prompts": ("STRING", {"default": "", "multiline": True, "tooltip": "正面提示词列表，支持字符串（每行一个提示词）或列表格式，对应图片属性的【备注】字段"}),
                "line_indices": ("STRING", {"default": "", "multiline": True, "tooltip": "行号列表，支持字符串（每行一个数字）或列表格式，对应文本的行号（从BatchRunController自动获取）"}),

                # --- 自动命名前缀 ---
                "auto_name_prefix": ("STRING", {"default": "", "multiline": False, "tooltip": "自动命名前缀：在启用自动命名的前提下，在文件名最前面追加此文本。不填写则不生效"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("ABSOLUTE_PATHS", "SAVE_LOG")
    FUNCTION = "save_batch"
    OUTPUT_NODE = True
    CATEGORY = "buding_Tools/图像处理"

    def save_batch(self, images, filename_prefix, output_subdir, auto_name_detail, save_format,
                   seeds, subject_descriptions, positive_prompts, line_indices, auto_name_prefix):

        # 1. 检查依赖
        if not PIEXIF_AVAILABLE:
            print("⚠️ 警告: 未检测到 piexif。属性面板将为空。请运行: pip install piexif")

        # 2. 辅助函数
        def clean_filename(text, max_chars=30):
            if not text: return ""
            text = str(text).strip().replace("\n", "").replace("\r", "").replace("_", "-")
            text = re.sub(r'[\\/:*?"<>|]', '', text)
            return text[:max_chars].strip()

        def get_windows_exif_bytes(title_str, tags_str, comment_str):
            """
            精准映射 Windows 属性
            Windows属性窗口字段映射:
            - 标题 -> XPTitle (40091)
            - 标记 -> XPKeywords (40094) ← 支持在资源管理器按"标记"分组！
            - 备注 -> XPComment (40092)
            """
            if not PIEXIF_AVAILABLE:
                return None

            def to_ucs2(s):
                # Windows XP Tags 必须用 utf-16le 编码
                return s.encode('utf-16le') + b'\x00\x00'

            zeroth_ifd = {
                # [标题] -> XPTitle
                40091: to_ucs2(title_str),

                # [备注] -> XPComment (提示词显示在这里)
                40092: to_ucs2(comment_str),

                # [标记] -> XPKeywords (种子放这里，资源管理器可按此分组!)
                40094: to_ucs2(tags_str),

                # [作者] -> XPAuthor (固定署名)
                40093: to_ucs2("ComfyUI"),

                # ImageDescription (270) - 也设置为提示词，提高兼容性
                270: comment_str.encode('utf-8') if comment_str else b''
            }

            exif_dict = {"0th": zeroth_ifd, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            return piexif.dump(exif_dict)

        try:
            saved_files = []
            absolute_paths = []  # 保存所有文件的绝对路径

            # 3. 准备路径
            output_subdir = output_subdir.strip().strip('"').strip("'")
            if os.path.isabs(output_subdir) or ":\\" in output_subdir:
                 full_output_dir = output_subdir
            else:
                 full_output_dir = os.path.join(self.output_dir, output_subdir)
            os.makedirs(full_output_dir, exist_ok=True)

            print(f"\n🖼️ 开始保存 ({len(images)}张)...")

            # 辅助函数：统一处理字符串输入（支持多行和单行）
            def normalize_input(input_data):
                if isinstance(input_data, str):
                    # 如果是字符串，分割成行
                    return [x.strip() for x in input_data.splitlines() if x.strip()]
                elif isinstance(input_data, list):
                    # 如果是列表（兼容旧格式），转换为字符串列表
                    return [str(x).strip() for x in input_data if str(x).strip()]
                else:
                    # 其他类型，转换为字符串列表
                    return [str(input_data).strip()] if str(input_data).strip() else []

            subjects = normalize_input(subject_descriptions)
            prompts = normalize_input(positive_prompts)
            seed_list = normalize_input(seeds)
            line_indices_list = [int(x) for x in normalize_input(line_indices) if x.isdigit()]

            saved_files = []
            # 扫描现有文件，建立已存在的文件名集合
            existing_filenames = set()
            if os.path.exists(full_output_dir):
                for filename in os.listdir(full_output_dir):
                    if filename.endswith('.png'):
                        existing_filenames.add(filename)

            for idx, image_tensor in enumerate(images):
                img = image_tensor
                if img.dim() == 4: img = img.squeeze(0)
                # ComfyUI格式: (C, H, W) -> 转换为PIL格式: (H, W, C)
                if img.dim() == 3 and img.shape[0] in [1, 3, 4]:  # 通道在第一维
                    img = img.permute(1, 2, 0)
                img_np = (img * 255).clamp(0, 255).byte().cpu().numpy()
                pil_img = Image.fromarray(img_np, 'RGBA' if img_np.shape[-1] == 4 else 'RGB')

                # 获取当前图的数据
                curr_subject = subjects[idx] if idx < len(subjects) else "" # 标题
                curr_prompt = prompts[idx] if idx < len(prompts) else ""    # 备注
                curr_seed = seed_list[idx] if idx < len(seed_list) else ""  # 标记
                curr_line_index = line_indices_list[idx] if idx < len(line_indices_list) else (idx + 1)  # 行号，默认递增

                # 文件名逻辑 - 主编号以行为基础递增，内容编号使用行号
                content_index_str = f"{curr_line_index:04d}"  # 内容编号（行号，用于末尾）
                main_index = 1  # 默认从1开始编号

                while True:
                    main_index_str = f"{main_index:04d}"    # 主编号（递增直到不冲突）

                    # 确定文件扩展名
                    file_extension = "png" if save_format else "jpg"
                    
                    if auto_name_detail:
                        s_clean = clean_filename(curr_subject, 15)
                        p_clean = clean_filename(curr_prompt, 20)
                        detail = f"({s_clean}){p_clean}" if (s_clean or p_clean) else ""
                        # 添加自动命名前缀
                        prefix_part = f"{auto_name_prefix}_" if auto_name_prefix.strip() else ""
                        filename = f"{prefix_part}{content_index_str}{detail}-{main_index_str}.{file_extension}"
                    else:
                        # 修复：当不启用auto_name_detail时，也要包含main_index来避免文件名冲突
                        filename = f"{filename_prefix}_{content_index_str}_{main_index_str}.{file_extension}"

                    if filename not in existing_filenames:
                        break
                    # 若文件名已存在，主编号递增
                    main_index += 1

                # 最终文件路径（filename已包含正确的扩展名）
                filepath = os.path.join(full_output_dir, filename)

                # --- 🔥 生成元数据 🔥 ---
                exif_bytes = None
                png_info = None
                exif_bytes = None
                exif_bytes_for_png = None
                
                if save_format:  # PNG格式
                    # 生成 PngInfo (PNG文本块 + XMP元数据)
                    png_info = PngImagePlugin.PngInfo()

                    # 构建显示标题：(种子)主体
                    title_display = f"({curr_seed}){curr_subject}" if curr_seed else curr_subject

                    # ✅ 修正 XMP 元数据映射 (Windows 优先读取这个)
                    if curr_subject or curr_seed or curr_prompt:
                        xmp_data = create_xmp_metadata(
                            title=title_display,      # 标题: (种子)苏尘
                            keywords=curr_prompt,     # 标记: 提示词
                            description=str(curr_seed) # 备注/描述: 种子
                        )
                        png_info.add_text("XML:com.adobe.xmp", xmp_data)

                    # ✅ 修正 PNG 文本块映射
                    if title_display:
                        png_info.add_text("Title", title_display)
                        png_info.add_text("Subject", title_display)
                    if curr_prompt:
                        png_info.add_text("Keywords", curr_prompt)
                        png_info.add_text("Tags", curr_prompt)
                    if curr_seed:
                        png_info.add_text("Comment", str(curr_seed))
                    
                    # AI 软件兼容字段
                    png_info.add_text("Author", "ComfyUI")
                    png_info.add_text("Software", "ComfyUI")
                    if curr_seed: png_info.add_text("Seed", str(curr_seed))
                    if curr_prompt: png_info.add_text("parameters", f"{curr_prompt}\nSeed: {curr_seed}")
                    
                    # 为 PNG 生成 EXIF 字节 (作为三重保障)
                    if PIEXIF_AVAILABLE:
                        exif_bytes_for_png = get_windows_exif_bytes(
                            title_str=title_display,      # 标题: (种子)苏尘
                            tags_str=curr_prompt,         # 标记: 提示词
                            comment_str=str(curr_seed)    # 备注: 种子
                        )
                    else:
                        exif_bytes_for_png = None

                else:  # JPEG格式 - 使用EXIF元数据
                    # ✅ 修正 JPEG 属性映射
                    # 标题(Title) = 苏尘
                    # 标记(Keywords) = 种子数
                    # 备注(Comment) = 提示词
                    
                    if PIEXIF_AVAILABLE:
                        exif_bytes = get_windows_exif_bytes(
                            title_str=curr_subject,       # 标题: 苏尘
                            tags_str=str(curr_seed),      # 标记: 种子数
                            comment_str=curr_prompt       # 备注: 提示词
                        )
                    else:
                        exif_bytes = None

                    # JPEG 也保留 PNG 文本块用于 AI 兼容
                    png_info = PngImagePlugin.PngInfo()
                    if curr_seed: png_info.add_text("Seed", str(curr_seed))
                    if curr_prompt: png_info.add_text("parameters", f"{curr_prompt}\nSeed: {curr_seed}")

                # 保存
                if save_format:  # PNG格式
                    # 使用 Pillow 原生支持的 exif 参数保存 (更稳定)
                    if exif_bytes_for_png:
                        pil_img.save(filepath, pnginfo=png_info, compress_level=4, exif=exif_bytes_for_png)
                    else:
                        pil_img.save(filepath, pnginfo=png_info, compress_level=4)
                        
                else:  # JPEG格式
                    if exif_bytes:
                        pil_img.save(filepath, exif=exif_bytes, quality=95)
                    else:
                        pil_img.save(filepath, quality=95)

                print(f"    ✓ {filename}")
                saved_files.append(filename)
                absolute_paths.append(filepath)  # 保存绝对路径
                # 更新已存在文件名集合（为后续图片避免冲突）
                existing_filenames.add(filename)

            # 返回所有保存文件的绝对路径（多行文本格式，便于下游节点处理）
            paths_text = "\n".join(absolute_paths)

            # 生成日志（数量按实际保存的文件算，时间精确到秒，仿照 List Receive Info 的格式）
            saved_count = len(saved_files)
            last_filename = saved_files[-1] if saved_files else "无"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_log = (
                f"📊 批量保存完成 | 🔢 总计: {saved_count} 个文件\n"
                f"📂 根目录: {full_output_dir}\n"
                f"🔚 结束于: {last_filename}\n"
                f"🕒 时间: {timestamp}"
            )
            print(save_log)
            
            return (paths_text, save_log)

        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            return (f"Error: {e}", f"Error: {e}")

NODE_CLASS_MAPPINGS = {
    "buding_ImageBatchSave": ImageBatchSave
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_ImageBatchSave": "🖼️ Image Batch Save (批量保存图片)"
}