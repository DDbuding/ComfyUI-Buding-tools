"""
Buding-time 文本文件加载器
支持 SRT、TXT、JSON 等格式的文本文件批量加载
"""

import os
import re
from pathlib import Path
from typing import Tuple, Optional, List

class buding_TextFileLoader:
    """文本文件加载器 - 支持 SRT、TXT、JSON 批量加载"""
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "目录路径\n• 批量加载目录中的 SRT/TXT/JSON 文件\n• 相对路径相对于 ComfyUI 根目录\n• 绝对路径直接访问"
                }),
            },
            "optional": {
                "file_limit": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "tooltip": "文件数量限制\n• 0: 加载所有文件\n• >0: 限制加载文件数量"
                }),
                "start_index": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "tooltip": "起始索引\n• 从第几个文件开始加载\n• 0: 从第一个文件开始"
                }),
                "select_index": ("INT", {
                    "default": 0, 
                    "min": 0, 
                    "step": 1,
                    "tooltip": "选择索引\n• 返回指定索引的文件内容\n• 0: 返回第一个文件"
                }),
                "encoding": (["auto", "utf-8", "gbk"], {
                    "default": "auto",
                    "tooltip": "文件编码\n• auto: 自动检测编码\n• utf-8: 强制 UTF-8 编码\n• gbk: 强制 GBK 编码"
                }),
            }
        }
    
    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("SELECTED_CONTENT", "SELECTED_PATH", "ALL_PATHS", "FILE_COUNT")
    OUTPUT_IS_LIST = (False, False, True, False)
    FUNCTION = "load_text_files_from_directory"
    CATEGORY = "Buding-time/Loaders"
    DESCRIPTION = "文本文件批量加载器 - 支持 SRT/TXT/JSON 格式"
    
    @classmethod
    def IS_CHANGED(cls, directory_path: str, file_limit: int = 0, start_index: int = 0, select_index: int = 0, encoding: str = "auto"):
        """检查目录是否修改"""
        if directory_path and directory_path.strip():
            directory_path = directory_path.strip().strip('"\'')
            if os.path.exists(directory_path):
                return os.path.getmtime(directory_path)
        return ""
    
    def load_text_files_from_directory(self, directory_path: str, file_limit: int = 0, 
                                     start_index: int = 0, select_index: int = 0, 
                                     encoding: str = "auto") -> Tuple[str, str, List[str], int]:
        """从目录批量加载文本文件"""
        try:
            # 清理路径
            directory_path = directory_path.strip().strip('"\'')
            
            if not directory_path:
                raise Exception("目录路径不能为空")
            
            print(f"=== 文本文件批量加载 ===")
            print(f"目录路径: '{directory_path}'")
            print(f"编码设置: '{encoding}'")
            print(f"文件限制: {file_limit}, 起始索引: {start_index}, 选择索引: {select_index}")
            
            # 检查目录是否存在
            if not os.path.exists(directory_path):
                raise FileNotFoundError(f"目录不存在: {directory_path}")
            
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
            
            # 过滤文本文件
            valid_extensions = ['.srt', '.txt', '.json']
            text_files = [f for f in dir_files if any(f.lower().endswith(ext) for ext in valid_extensions)]
            
            print(f"找到 {len(text_files)} 个文本文件")
            
            if len(text_files) == 0:
                raise Exception(f"目录中没有文本文件: {directory_path}")
            
            # 排序文件
            text_files.sort()
            
            # 应用起始索引
            if start_index > 0:
                text_files = text_files[start_index:]
                print(f"应用起始索引 {start_index}，剩余 {len(text_files)} 个文件")
            
            # 应用数量限制
            if file_limit > 0 and len(text_files) > file_limit:
                text_files = text_files[:file_limit]
                print(f"应用数量限制 {file_limit}，处理 {len(text_files)} 个文件")
            
            # 构建完整路径
            file_paths = [os.path.join(directory_path, f) for f in text_files]
            
            # 加载文件内容
            all_contents = []
            valid_paths = []
            
            for i, file_path in enumerate(file_paths):
                try:
                    print(f"加载文件 ({i+1}/{len(file_paths)}): {file_path}")
                    
                    content = self._read_file_with_encoding(file_path, encoding)
                    if content:
                        all_contents.append(content)
                        valid_paths.append(file_path)
                        print(f"  ✅ 成功读取 ({len(content)} 字符)")
                    else:
                        print(f"  ⚠️ 文件内容为空，跳过")
                        continue
                        
                except Exception as file_error:
                    print(f"  ⚠️ 加载文件失败，跳过: {file_path}, 错误: {file_error}")
                    continue
            
            if len(all_contents) == 0:
                raise Exception("没有成功加载任何文本文件")
            
            print(f"成功加载 {len(all_contents)} 个文本文件")
            
            # 选择特定文件
            selected_content = ""
            selected_path = ""
            
            if 0 <= select_index < len(all_contents):
                selected_content = all_contents[select_index]
                selected_path = valid_paths[select_index]
                print(f"选择文件索引 {select_index}")
            else:
                selected_content = all_contents[0] if all_contents else ""
                selected_path = valid_paths[0] if valid_paths else ""
                print(f"选择默认文件 (索引0)")
            
            file_count = len(all_contents)
            print(f"返回选中文件内容、路径和所有文件路径列表")
            
            return (selected_content, selected_path, valid_paths, file_count)
            
        except Exception as e:
            error_msg = f"❌ 文本文件批量加载失败: {str(e)}"
            print(error_msg)
            raise Exception(error_msg)
    
    def _read_file_with_encoding(self, file_path: str, encoding: str) -> str:
        """使用指定编码读取文件"""
        encodings_to_try = []
        
        if encoding == "auto":
            encodings_to_try = ['utf-8', 'gbk', 'utf-8-sig']
        else:
            encodings_to_try = [encoding]
        
        for enc in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                print(f"  ✅ 成功使用 {enc} 编码读取")
                return content
            except UnicodeDecodeError:
                print(f"  ⚠️ {enc} 编码读取失败，尝试下一个...")
                continue
            except Exception as e:
                print(f"  ❌ {enc} 编码读取错误: {str(e)}")
                continue
        
        raise Exception(f"无法使用任何编码读取文件: {', '.join(encodings_to_try)}")

# 节点映射
NODE_CLASS_MAPPINGS = {
    "buding_TextFileLoader": buding_TextFileLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_TextFileLoader": "Buding - 文本文件加载器",
}
