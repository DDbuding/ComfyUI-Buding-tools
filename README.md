# ComfyUI-Buding-tools

![Version](https://img.shields.io/badge/version-3.1.3-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![ComfyUI](https://img.shields.io/badge/ComfyUI-compatible-brightgreen.svg)
![Date](https://img.shields.io/badge/release-2026.01.12-orange.svg)

## 📖 概述

**ComfyUI-Buding-tools** 是一个功能强大的 ComfyUI 插件工具集，为AI内容创作提供全面的解决方案。插件集成了文本处理、音频管理、视频控制、批量操作和数据处理等核心功能，支持从创意构思到最终输出的完整工作流。

**🎯 核心优势**：
- **71个专业节点**：涵盖内容创作、媒体处理、数据管理等全方位功能
- **优雅依赖处理**：即使缺少可选依赖，所有节点仍能正常加载和显示
- **智能备用机制**：多重解析策略，确保最大兼容性和稳定性
- **统一插件架构**：整合三个原始插件，简化管理和维护

## ✨ 核心特性

### 🎭 智能内容创作
- **剧情生成**: 支持多种故事类型和叙事结构
- **角色管理**: 自定义角色、情节、冲突设计
- **批量创作**: 支持自定义随机种子的大规模内容生成
- **脚本生成**: 短视频脚本和爆款元素智能组合

### 📝 高级文本处理
- **文本净化**: 去除前缀、符号容器、特殊字符
- **智能过滤**: 多种匹配模式（包含、前缀、精确、正则）、AND/OR逻辑
- **内容提取**: 从各种符号容器中提取正文
- **究极行筛选**: 多维度文本行筛选（语言特征、关键词、行号、黑名单）
- **随机输出**: 支持行级别的随机选择和去重
- **灵活合并**: 自定义分隔符的行合并操作

### 🎵 专业音频处理
- **智能音频加载**: 关键词匹配，FFmpeg优先处理
- **音频分段**: 基于Whisper的智能音频切割
- **格式转换**: 支持WAV、MP3、FLAC等多种音频格式
- **角色音频匹配**: 文本识别，布尔值控制输出
- **批量音频管理**: 时长筛选、格式标准化、元数据快速扫描

### 🎬 视频控制系统
- **字幕驱动**: SRT时间轴转换为帧数精确控制
- **一键集成**: SRT帧数转换器整合4个独立节点功能
- **批量视频加载**: 分辨率筛选、时域切片、帧采样控制
- **智能分块**: 自动计算物理最少批次，智能压缩策略
- **视频保存**: 支持多种格式的批量保存和合并

### 🔧 批量操作工具
- **智能文件加载**: 支持图像、音频、视频、文本、Excel批量处理
- **路径管理**: 目录扫描、文件过滤、多格式支持
- **批量控制器**: 自动种子生成、参数统一管理
- **统计日志**: 详细的处理记录和科学推演

### 📊 数据处理引擎
- **表格操作**: CSV/XLSX完整读写能力，WPS兼容
- **JSON处理**: 数据解码、批量迭代、类型转换
- **编码处理**: UTF-8统一支持，智能编码检测
- **元数据管理**: PNG参数筛选、EXIF校正、智能防洪

### ⚡ 高级功能特性
- **智能音频批量加载**: 时长筛选、格式标准化、元数据快速扫描
- **批量运行控制**: 统一种子管理、参数分发、自动批量推断
- **Windows属性映射**: 种子、提示词写入图片元数据，支持资源管理器查看
- **高分辨率支持**: 最大支持32K分辨率图像处理
- **优雅依赖处理**: 即使缺少可选依赖，所有节点仍能正常加载和显示
- **备用解析机制**: 智能的节点注册系统，确保最大兼容性

## 📝 更新日志

### v3.1.3 (2026-01-12)
- ✨ **新增节点**: Ultra Text Line Filter (究极行筛选器)
- 🔧 **文本处理增强**: 多维度文本行筛选功能
- 🎯 **智能筛选**: 支持语言特征、关键词、行号等多重筛选条件

### v3.1.2 (2026-01-12)
- 🔧 **Path Name Extractor优化**:
  - 父目录输出现在独立于前缀开关，始终输出父目录名
  - 提升用户体验和功能灵活性

### v3.1.1 (2026-01-12)
- ✨ **新增节点**: Path Name Extractor (路径名提取器)
- 📝 **文本处理增强**: 新增路径提取和处理功能

### v3.1.0 (2026-01-XX)
- 🔄 **插件架构重组**: 统一插件架构，简化管理
- 📦 **依赖优化**: 改进依赖处理机制
- 🛠️ **兼容性提升**: 增强多版本ComfyUI兼容性

## 📦 完整节点列表 (71个节点)

### 🎭 内容创作 (Content Creation)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_SmartPromptComposer | 智能提示词组合逻辑 | v2.0 |
| buding_InfiniteTextConcatenate | 无限文本连接器 | v1.0 |
| buding_FullTextController | 完整文本控制器 | v1.0 |

### 📝 文本处理 (Text Processing)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_PathNameExtractor | ✂️ 路径名提取器 (Path Name Extractor) | v1.1.1 |
| buding_UltraTextLineFilter | ✂️ 究极行筛选器 (Ultra Line Filter) | v1.0 |
| buding_TextCleaner | 文本净化器 | v2.0 |
| buding_TextCleanerAdvanced | 高级文本净化器 | v2.0 |
| buding_TextFilter | 多模式关键词过滤 | v2.0 |
| buding_TextExtractor | 文本容器提取 | v2.0 |
| buding_ReadTxtAdvanced | TXT文件增强读取 | v2.0 |
| buding_TextFileLoader | 基础TXT文件加载 | v1.0 |
| buding_TextFilter | 文本过滤器 | v1.0 |

### 🎵 音频处理 (Audio Processing)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_SmartAudioLoader | 智能音频加载器 | v2.0 |
| buding_SmartAudioBatchLoader | 智能音频批量加载器（时长筛选、格式标准化） | v2.0 |
| buding_SimpleAudioBatchLoader | 简化音频批量加载器 | v1.0 |
| buding_AudioBatchSave | 音频批量保存器 | v1.0 |
| buding_AudioStitcherABC | 音频拼接器ABC | v1.0 |
| buding_BasicAudioSegmenter | 基础音频分段器 | v1.0 |
| buding_SmartAudioSegmenter | 智能音频分段器 | v2.0 |
| buding_ConditionalAudio | 条件音频开关 | v1.0 |

### 🎬 视频处理 (Video Processing)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_SmartVideoBatchLoader | 智能视频批量加载器 | v2.0 |
| buding_SimpleVideoBatchLoader | 简化视频批量加载器 | v1.0 |
| buding_VideoBatchSave | 视频批量保存器 | v1.0 |
| buding_VideoPathLoader | 目录视频路径加载器 | v1.0 |
| buding_VideoBatchCalculatorV3 | 视频分块计算器V3 | v3.0 |
| buding_VideoSaveAndMergeV5 | 视频保存合并器V5 | v5.0 |

### 🖼️ 图像处理 (Image Processing)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_BatchImageLoader | 智能图像批量加载器（支持32K高分辨率） | v2.0 |
| buding_SimpleImageBatchLoader | 简化图像批量加载器 | v1.0 |
| buding_ImageBatchSave | 智能图像批量保存器（Windows属性映射、元数据嵌入） | v2.0 |
| buding_ImagePathLoader | 目录图像路径加载器 | v1.0 |

### 📊 数据处理 (Data Processing)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_JSONBatchIterator | JSON批量迭代器 | v1.0 |
| buding_JSONDataExtractor | JSON数据提取器 | v1.0 |
| buding_SimpleExcelBatchLoader | 简化Excel批量加载器 | v1.0 |
| buding_FrameDurationLimiter | 帧数限制器 | v2.0 |
| buding_ScriptToSrtNode | 脚本转SRT节点 | v1.0 |
| buding_SRTParser | SRT字幕解析器 | v2.0 |
| buding_SRTFrameConverter | SRT帧数转换器（集成SRT解析、帧数限制和循环输出） | v1.0 |

### 🔧 工具节点 (Utility Nodes)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_BatchRunController | 批处理运行控制器（统一种子管理、自动批量推断） | v2.0 |
| buding_BatchIndexStepper | 批量索引步进器 | v1.0 |
| buding_BatchLineOutput | 批量行输出 | v1.0 |
| buding_BatchRoleAudio | 批量角色音频 | v1.0 |
| buding_BatchRoleAudioV2 | 批量角色音频V2 | v2.0 |
| buding_BatchStatisticsLog | 批量统计日志 | v1.0 |
| buding_PathLoader | 路径加载器 | v1.0 |
| buding_RoleMatcher | 角色匹配器 | v1.0 |
| buding_ScriptProductionPrecheck | 脚本生产预检 | v1.0 |
| buding_IndexTTSDynamicEmotion | IndexTTS动态情绪生成器 | v2.0 |

### 🎛️ 控制节点 (Control Nodes)
| 节点名称 | 功能描述 | 版本 |
|---------|---------|------|
| buding_ClampNode | 数值限制器 | v1.0 |
| buding_EnsureIntNode | 整数类型确保器 | v1.0 |
| buding_ListClampNode | 列表数值限制器 | v1.0 |
| buding_ListConditionalMaxNode | 列表条件最大值 | v1.0 |
| buding_ListNodes | 列表节点集合 | v1.0 |

## 🚀 快速开始

### 安装要求
- **ComfyUI** (必需)
- **Python 3.8+** (必需)
- **推荐依赖**: 见 `requirements.txt`

### 安装步骤
1. 将 `ComfyUI-Buding-tools` 文件夹放入 ComfyUI 的 `custom_nodes` 目录
2. 安装依赖包：
   ```bash
   pip install -r requirements.txt
   ```
3. 重启 ComfyUI
4. 在节点菜单中搜索 "buding" 即可找到所有相关节点

### 基础使用
1. **文本处理**: 使用 `buding_TextCleaner` 进行文本预处理
2. **究极筛选**: 使用 `buding_UltraTextLineFilter` 进行多维度文本行筛选
3. **批量加载**: 使用 `buding_BatchImageLoader` 进行智能图像批量加载
4. **音频处理**: 使用 `buding_SmartAudioLoader` 进行音频文件处理
5. **视频控制**: 使用 `buding_FrameDurationLimiter` 进行字幕驱动的视频生成

## ⚙️ 依赖要求

插件采用**极简宽松的依赖策略**，所有依赖均为**可选**，具备优雅的降级处理机制：

**核心依赖**（ComfyUI环境通常已包含）：
- torch>=1.9.0, torchvision>=0.10.0, torchaudio>=0.9.0, numpy>=1.21.0

**音频处理相关**：
- mutagen>=1.45.0, soundfile>=0.10.0, ffmpeg-python>=0.2.0, scipy>=1.7.0, faster_whisper>=0.10.0

**图像/视频处理相关**：
- opencv-python>=4.5.0, Pillow>=8.0.0, decord>=0.6.0

**数据处理相关**：
- openpyxl

**🎯 重要特性**: 插件设计为**即使缺少任何依赖包也能正常加载和使用**。通过智能的备用解析机制，所有节点都会在ComfyUI界面中正确显示。节点运行时会自动检测可用库并适配功能，缺失依赖仅影响特定高级功能，不会影响整体使用体验。

## 🏗️ 项目结构

```
ComfyUI-Buding-tools/
├── __init__.py              # 插件主入口，动态加载所有节点
├── nodes/                   # 节点文件目录 (68个节点文件)
├── utils/                   # 工具函数
├── web/                     # 前端脚本（预留）
├── requirements.txt         # 依赖列表
├── node_list.json          # 节点信息索引
├── test_registration.py    # 注册验证脚本
├── test_plugin_loading.py  # 加载测试脚本
└── README.md               # 说明文档
```

## 🎯 核心工作流示例

### 字幕驱动视频生成工作流
1. **buding_ScriptToSrtNode** → 将文本转换为SRT格式
2. **buding_SRTFrameConverter** → 一键集成SRT解析、帧数限制和循环输出
3. **buding_SmartPromptComposer** → 组合最终提示词
4. **视频生成节点** → 生成视频片段

*或者使用传统流程:*
1. **buding_ScriptToSrtNode** → 将文本转换为SRT格式
2. **buding_FrameDurationLimiter** → 转换时间轴为帧数
3. **buding_JSONBatchIterator** → 准备循环数据
4. **buding_JSONDataExtractor** → 解包数据类型
5. **buding_SmartPromptComposer** → 组合最终提示词
6. **视频生成节点** → 生成视频片段

### 智能批量内容处理工作流
1. **buding_BatchRunController** → 统一种子管理和参数分发
2. **buding_BatchImageLoader** → 智能加载图像资产（支持32K分辨率）
3. **buding_SmartAudioBatchLoader** → 批量加载音频文件（时长筛选、格式标准化）
4. **buding_ImageBatchSave** → 批量保存结果（Windows属性映射）
5. **buding_BatchStatisticsLog** → 生成处理报告

## 🔧 开发与扩展

- **动态加载**: 插件使用动态扫描机制自动发现和注册节点
- **模块化设计**: 所有节点文件位于 `nodes/` 目录，便于维护
- **错误处理**: 完善的异常处理和降级机制
- **兼容性**: 完全兼容ComfyUI生态系统，支持与其他插件协同工作

## 📈 版本历史

### v3.1.0 (2026-01-12)
- 🚀 **备用解析机制**: 实现智能节点注册，即使缺少依赖也能正常加载
- 🎬 **新增SRT帧数转换器**: 集成SRT解析、帧数限制和循环输出为一体的综合节点
- 📈 **节点数量增加**: 从59个节点扩展到69个节点
- 🔧 **依赖处理优化**: 优雅的降级机制，确保所有节点在ComfyUI中可见
- 🛠️ **加载机制改进**: 多重备用策略，最大化兼容性

### v3.0.0 (2026-01-12)
- 🎉 **全新统一插件**: 整合所有Buding工具系列
- ✅ **59个节点**: 完整的工具集合
- 🔄 **智能适配**: 依赖缺失时的自动降级处理
- 📊 **批量优化**: 增强的批量处理能力和性能
- 🎯 **工作流集成**: 完整的创作到输出的工作流支持

## 📝 更新日志

### v3.1.2 (2026-01-12)
- 🔧 **Path Name Extractor优化**: 
  - 父目录输出现在独立于前缀开关，始终输出父目录名
  - 提升用户体验和功能灵活性

### v3.1.1 (2026-01-12)
- ✨ **新增节点**: Path Name Extractor (路径名提取器)
- 📝 **文本处理增强**: 新增路径提取和处理功能

### v3.1.0 (2026-01-XX)
- 🔄 **插件架构重组**: 统一插件架构，简化管理
- 📦 **依赖优化**: 改进依赖处理机制
- 🛠️ **兼容性提升**: 增强多版本ComfyUI兼容性

## 📞 支持与反馈

- **问题反馈**: 在GitHub Issues中提交问题
- **功能建议**: 欢迎提出新功能需求
- **贡献代码**: 接受Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 LICENSE 文件

---

**ComfyUI-Buding-tools** - 让AI内容创作更简单、更强大！

## 许可证

遵循原始各插件的许可证协议。
