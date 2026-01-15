import os

class buding_DirectoryVideoPathLoader:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "directory_path": ("STRING", {
                    "default": "", 
                    "multiline": False,
                    "description": "目录路径\n• 包含视频文件的文件夹路径\n• 支持绝对路径和相对路径"
                }),
            },
            "optional": {
                "file_limit": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "description": "文件数量限制\n• 0表示不限制，加载所有文件\n• 设置后只加载指定数量的文件"
                }),
                "start_index": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "description": "起始索引\n• 从第几个文件开始加载\n• 0表示从第一个文件开始"
                }),
                "select_index": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "description": "选择索引\n• 选择输出的单个视频文件索引\n• 从加载的文件列表中选择一个"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("video_paths_list", "selected_video_path", "video_count")
    OUTPUT_IS_LIST = (True, False, False)
    FUNCTION = "load_video_paths_from_directory"
    CATEGORY = "buding_Tools/Path/Loaders"

    @classmethod
    def IS_CHANGED(cls, directory_path, file_limit=0, start_index=0, select_index=0):
        if directory_path and os.path.exists(directory_path):
            return os.path.getmtime(directory_path)
        return ""

    def load_video_paths_from_directory(self, directory_path, file_limit=0, start_index=0, select_index=0):
        """从目录加载视频文件路径"""
        try:
            # 清理路径
            directory_path = directory_path.strip().strip('"\'')
            
            print(f"=== 目录视频路径加载 ===")
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
            
            # 过滤视频文件
            valid_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp', '.ogv']
            video_files = [f for f in dir_files if any(f.lower().endswith(ext) for ext in valid_extensions)]
            
            print(f"找到 {len(video_files)} 个视频文件")
            
            if len(video_files) == 0:
                raise Exception(f"目录中没有视频文件: {directory_path}")
            
            # 排序文件
            video_files.sort()
            
            # 应用起始索引
            if start_index > 0:
                video_files = video_files[start_index:]
                print(f"应用起始索引 {start_index}，剩余 {len(video_files)} 个文件")
            
            # 应用数量限制
            if file_limit > 0 and len(video_files) > file_limit:
                video_files = video_files[:file_limit]
                print(f"应用数量限制 {file_limit}，处理 {len(video_files)} 个文件")
            
            # 构建完整路径
            video_paths = [os.path.join(directory_path, f) for f in video_files]
            
            # 选择特定视频路径
            selected_video_path = None
            if 0 <= select_index < len(video_paths):
                selected_video_path = video_paths[select_index]
                print(f"选择视频路径索引 {select_index}")
            else:
                selected_video_path = video_paths[0] if video_paths else None
                print(f"选择默认视频路径 (索引0)")
            
            video_count = len(video_paths)
            print(f"返回 {video_count} 个视频路径列表和选中的视频路径")
            
            return (video_paths, selected_video_path, video_count)
            
        except Exception as e:
            raise Exception(f"目录视频路径加载失败: {str(e)}")

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_DirectoryVideoPathLoader": buding_DirectoryVideoPathLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_DirectoryVideoPathLoader": "🎬 buding_Directory 视频路径加载器",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
