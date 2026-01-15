import os
import numpy as np
import torch
from PIL import Image, ImageOps


class DirectoryImageLoader:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "directory_path": ("STRING", {
                    "default": "", 
                    "multiline": False,
                    "description": "目录路径\n• 包含图像文件的文件夹路径\n• 支持绝对路径和相对路径"
                }),
            },
            "optional": {
                "image_limit": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "description": "图像数量限制\n• 0表示不限制，加载所有图像\n• 设置后只加载指定数量的图像文件"
                }),
                "start_index": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "description": "起始索引\n• 从第几个图像文件开始加载\n• 0表示从第一个文件开始"
                }),
                "select_index": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "description": "选择索引\n• 选择输出的单个图像索引\n• 从加载的图像列表中选择一个输出为selected_image"
                }),
            }
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "INT")
    RETURN_NAMES = ("image_list", "selected_image", "file_paths", "image_count")
    OUTPUT_IS_LIST = (True, False, True, False)
    FUNCTION = "load_images_from_directory"
    CATEGORY = "buding_Tools/Path/Loaders"

    @classmethod
    def IS_CHANGED(cls, directory_path, image_limit=0, start_index=0, select_index=0):
        if directory_path and os.path.exists(directory_path):
            return os.path.getmtime(directory_path)
        return ""

    def load_images_from_directory(self, directory_path, image_limit=0, start_index=0, select_index=0):
        """基于Inspire-Pack方式的目录图像加载"""
        try:
            # 清理路径
            directory_path = directory_path.strip().strip('"\'')
            
            print(f"=== 目录图像加载 ===")
            print(f"目录路径: '{directory_path}'")
            
            if not directory_path:
                raise Exception("目录路径不能为空")
            
            # 检查目录是否存在
            if not os.path.exists(directory_path):
                raise Exception(f"目录不存在: {directory_path}")
            
            if not os.path.isdir(directory_path):
                raise Exception(f"路径不是目录: {directory_path}")
            
            # 列出目录文件
            try:
                dir_files = os.listdir(directory_path)
                print(f"目录中找到 {len(dir_files)} 个文件/目录")
            except Exception as list_error:
                raise Exception(f"无法列出目录内容: {str(list_error)}")
            
            if len(dir_files) == 0:
                raise Exception(f"目录为空: {directory_path}")
            
            # 过滤图像文件
            valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff']
            image_files = [f for f in dir_files if any(f.lower().endswith(ext) for ext in valid_extensions)]
            
            print(f"找到 {len(image_files)} 个图像文件")
            
            if len(image_files) == 0:
                raise Exception(f"目录中没有图像文件: {directory_path}")
            
            # 排序文件
            image_files.sort()
            
            # 应用起始索引
            if start_index > 0:
                image_files = image_files[start_index:]
                print(f"应用起始索引 {start_index}，剩余 {len(image_files)} 个文件")
            
            # 应用数量限制
            if image_limit > 0 and len(image_files) > image_limit:
                image_files = image_files[:image_limit]
                print(f"应用数量限制 {image_limit}，处理 {len(image_files)} 个文件")
            
            # 构建完整路径
            image_paths = [os.path.join(directory_path, f) for f in image_files]
            
            # 加载图像
            images = []
            file_paths = []
            
            for i, image_path in enumerate(image_paths):
                try:
                    print(f"加载图像 ({i+1}/{len(image_paths)}): {image_path}")
                    
                    # 使用Inspire-Pack的方式加载图像
                    img = Image.open(image_path)
                    img = ImageOps.exif_transpose(img)
                    img = img.convert("RGB")
                    
                    # 转换为tensor
                    img_array = np.array(img).astype(np.float32) / 255.0
                    img_tensor = torch.from_numpy(img_array)[None,]
                    
                    images.append(img_tensor)
                    file_paths.append(image_path)
                    
                except Exception as img_error:
                    print(f"警告: 加载图像失败，跳过: {image_path}, 错误: {img_error}")
                    continue
            
            if len(images) == 0:
                raise Exception("没有成功加载任何图像")
            
            print(f"成功加载 {len(images)} 个图像")
            
            # 选择特定图像
            selected_image = None
            if 0 <= select_index < len(images):
                selected_image = images[select_index]
                print(f"选择图像索引 {select_index}")
            else:
                selected_image = images[0] if images else None
                print(f"选择默认图像 (索引0)")
            
            image_count = len(images)
            print(f"返回 {image_count} 个图像列表、选中的图像和文件路径列表")
            
            return (images, selected_image, file_paths, image_count)
            
        except Exception as e:
            raise Exception(f"目录图像加载失败: {str(e)}")


NODE_CLASS_MAPPINGS = {
    "buding_Directory Image Loader": DirectoryImageLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_Directory Image Loader": "📁 buding_Directory Image Loader",
}
