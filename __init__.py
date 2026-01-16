# ComfyUI-Buding-tools
# 核心总入口：负责自动扫描并汇总所有节点

import os
import importlib.util
import sys

print("""************************************************************

🚀ComfyUI-Buding-tools插件加载成功🚀
🤝 确认过眼神，你是最懂【枪】的人🤝

************************************************************

📢 作者声明-DD布丁AIGC（B站）：

插件是免费的，本工具旨在解放双手，护肝保发。

😘 答应我，多出去走走，不要再一坐就是一整天，出去浪！😘 

************************************************************""")

# 手动注册所有节点映射（作为动态加载的备份）
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# 动态扫描并汇总节点（作为补充）
def load_nodes_from_module(module_name, module_path):
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, 'NODE_CLASS_MAPPINGS'):
            NODE_CLASS_MAPPINGS.update(module.NODE_CLASS_MAPPINGS)
        if hasattr(module, 'NODE_DISPLAY_NAME_MAPPINGS'):
            NODE_DISPLAY_NAME_MAPPINGS.update(module.NODE_DISPLAY_NAME_MAPPINGS)
    except Exception as e:
        print(f"[ComfyUI-Buding-tools] 跳过模块 {module_name}: {e}")
        # 即使导入失败，也尝试直接解析注册信息
        try:
            with open(module_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 使用正则表达式提取映射
            import re
            
            # 提取 NODE_CLASS_MAPPINGS
            class_match = re.search(r'NODE_CLASS_MAPPINGS\s*=\s*\{(.*?)\}', content, re.DOTALL)
            if class_match:
                class_content = class_match.group(1)
                # 简单解析键值对
                class_mappings = {}
                for line in class_content.split('\n'):
                    line = line.strip().strip(',')
                    if ':' in line and not line.startswith('#'):
                        try:
                            key, value = line.split(':', 1)
                            key = key.strip().strip('"\'')
                            value = value.strip().strip('"\'').strip(',')
                            if key and value:
                                # 对于类映射，我们不需要实际的类对象，只需要映射关系
                                class_mappings[key] = f"<class {value}>"  # 占位符
                        except:
                            pass
                
                # 提取 NODE_DISPLAY_NAME_MAPPINGS
                display_match = re.search(r'NODE_DISPLAY_NAME_MAPPINGS\s*=\s*\{(.*?)\}', content, re.DOTALL)
                if display_match:
                    display_content = display_match.group(1)
                    display_mappings = {}
                    for line in display_content.split('\n'):
                        line = line.strip().strip(',')
                        if ':' in line and not line.startswith('#'):
                            try:
                                key, value = line.split(':', 1)
                                key = key.strip().strip('"\'')
                                value = value.strip().strip('"\'').strip(',')
                                if key and value:
                                    # 移除外层的引号
                                    value = value.strip('"\'')
                                    display_mappings[key] = value
                            except:
                                pass
                    
                    # 如果两个映射都成功提取且键匹配
                    if class_mappings and display_mappings and set(class_mappings.keys()) == set(display_mappings.keys()):
                        NODE_CLASS_MAPPINGS.update(class_mappings)
                        NODE_DISPLAY_NAME_MAPPINGS.update(display_mappings)
                        print(f"[ComfyUI-Buding-tools] 成功通过备用解析加载 {module_name}: {len(class_mappings)} 个节点")
                        return
        except Exception as parse_e:
            print(f"[ComfyUI-Buding-tools] 备用解析失败 {module_name}: {parse_e}")

# 扫描 nodes 目录下的所有 .py 文件
nodes_dir = os.path.join(os.path.dirname(__file__), 'nodes')
for file in os.listdir(nodes_dir):
    if file.endswith('.py') and file != '__init__.py':
        module_name = file[:-3]  # 去掉 .py
        module_path = os.path.join(nodes_dir, file)
        load_nodes_from_module(module_name, module_path)

# 导出节点映射
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

