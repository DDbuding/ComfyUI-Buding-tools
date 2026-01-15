import os
import re
import json
import time
import difflib
import hashlib
import subprocess
import tempfile
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

try:
    import torch
    import numpy as np
    TORCH_AVAILABLE = True
    print("✅ torch/numpy 可用")
except ImportError as e:
    TORCH_AVAILABLE = False
    print(f"⚠️ torch/numpy 不可用: {e}")
    # 尝试只导入numpy
    try:
        import numpy as np
        NUMPY_AVAILABLE = True
        print("✅ numpy 可用")
    except ImportError:
        NUMPY_AVAILABLE = False
        print("❌ numpy 也不可用")

class AudioLibraryCache:
    """音频库缓存管理器"""
    
    def __init__(self, cache_duration=3600):  # 1小时缓存
        self.cache = {}
        self.cache_duration = cache_duration
        self.cache_timestamps = {}
        self._name_index = {}  # 文件名索引
        self._metadata_cache = {}  # 音频元数据缓存
    
    def get_cache_key(self, library_root: str, scan_max_depth: int) -> str:
        """生成缓存键"""
        return hashlib.md5(f"{library_root}_{scan_max_depth}".encode()).hexdigest()
    
    def get_audio_files(self, library_root: str, scan_max_depth: int, force_reload: bool = False) -> List[Dict]:
        """获取音频文件（带缓存，可强制重载）"""
        cache_key = self.get_cache_key(library_root, scan_max_depth)
        
        # 检查缓存
        if cache_key in self.cache and not force_reload:
            cache_time = self.cache_timestamps.get(cache_key, 0)
            if time.time() - cache_time < self.cache_duration:
                print(f"📦 使用缓存: {len(self.cache[cache_key])}个文件")
                return self.cache[cache_key]
        
        # 重新扫描
        print("🔄 重新扫描音频库...")
        files = self._scan_audio_files(library_root, scan_max_depth)
        
        # 更新缓存
        self.cache[cache_key] = files
        self.cache_timestamps[cache_key] = time.time()
        
        # 构建索引
        self._build_name_index(files)
        
        return files
    
    def _scan_audio_files(self, library_root: str, max_depth: int) -> List[Dict]:
        """扫描音频文件"""
        audio_files = []
        extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma']
        exclude_dirs = {'.git', '__pycache__', 'temp', 'backup'}
        
        try:
            library_path = Path(library_root)
            if not library_path.exists():
                print(f"❌ 音频库目录不存在: {library_root}")
                return []
            
            scanned_dirs = 0
            found_files = 0
            
            for root, dirs, files in os.walk(library_root):
                # 控制扫描深度
                current_depth = len(Path(root).relative_to(library_path).parts)
                if current_depth > max_depth:
                    continue
                
                # 排除特定目录
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                scanned_dirs += 1
                
                # 查找音频文件
                for file in files:
                    if any(file.lower().endswith(ext.lower()) for ext in extensions):
                        file_path = os.path.join(root, file)
                        file_info = self._analyze_file(file_path, file)
                        audio_files.append(file_info)
                        found_files += 1
            
            print(f"📁 扫描完成: {scanned_dirs}个目录, {found_files}个音频文件")
            
        except Exception as e:
            print(f"❌ 扫描音频库失败: {e}")
        
        return audio_files
    
    def _analyze_file(self, file_path: str, filename: str) -> Dict:
        """分析音频文件，提取特征"""
        return {
            "path": file_path,
            "filename": filename,
            "name_without_ext": os.path.splitext(filename)[0],
            "directory": os.path.basename(os.path.dirname(file_path)),
            "size": os.path.getsize(file_path),
            "modified": os.path.getmtime(file_path),
            "clean_name": self._clean_text(filename)
        }
    
    def _clean_text(self, text: str) -> str:
        """清理文件名，提取核心名称"""
        # 移除扩展名
        name = os.path.splitext(text)[0]
        
        # 移除常见前缀/后缀
        prefixes = ["voice_", "audio_", "sound_", "bgm_", "char_", "character_"]
        suffixes = ["_voice", "_audio", "_sound", "_final", "_v1", "_v2", "_master", "_mix"]
        
        for prefix in prefixes:
            if name.lower().startswith(prefix):
                name = name[len(prefix):]
        
        for suffix in suffixes:
            if name.lower().endswith(suffix):
                name = name[:-len(suffix)]
        
        # 移除特殊字符（只保留中文、英文、数字）
        clean_name = re.sub(r'[^\w\u4e00-\u9fff]', '', name)
        
        return clean_name.lower()
    
    def _build_name_index(self, audio_files: List[Dict]):
        """构建轻量级文件名索引"""
        self._name_index = {}
        for file_info in audio_files:
            clean_name = file_info["clean_name"]
            if clean_name:
                first_char = clean_name[0].lower() if clean_name[0].isalnum() else '#'
                if first_char not in self._name_index:
                    self._name_index[first_char] = []
                self._name_index[first_char].append(file_info)
    
    def get_files_by_initial(self, initial: str) -> List[Dict]:
        """根据首字母获取文件列表，加速搜索"""
        return self._name_index.get(initial.lower(), [])
    
    @lru_cache(maxsize=200)
    def get_cached_file_info(self, file_path: str) -> Dict:
        """缓存文件信息，避免重复读取"""
        filename = os.path.basename(file_path)
        return self._analyze_file(file_path, filename)
    
    def cache_audio_metadata(self, file_path: str, metadata: Dict):
        """缓存音频元数据"""
        self._metadata_cache[file_path] = metadata
    
    def get_cached_metadata(self, file_path: str) -> Optional[Dict]:
        """获取缓存的音频元数据"""
        return self._metadata_cache.get(file_path)
    
    def invalidate_cache(self, library_root: str = None):
        """清除缓存"""
        if library_root:
            # 清除特定路径缓存
            keys_to_remove = []
            for key in self.cache.keys():
                # 这里简化处理，实际应该解析缓存键
                if library_root.encode() in key.encode():
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.cache[key]
                if key in self.cache_timestamps:
                    del self.cache_timestamps[key]
        else:
            # 清除所有缓存
            self.cache.clear()
            self.cache_timestamps.clear()
            self._name_index.clear()
            self._metadata_cache.clear()
        
        # 清除lru_cache
        self.get_cached_file_info.cache_clear()


class buding_SmartAudioLoader:
    """
    智能音频加载器：根据关键词从音频库中智能匹配并加载音频文件
    支持FFmpeg优先加载，提供高性能的音频检索和加载功能
    """
    
    # 类级别的缓存实例
    _cache = AudioLibraryCache()
    _ffmpeg_available = None
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "keyword_input": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "输入关键词进行智能匹配"
                }),
                "library_root": ("STRING", {
                    "default": "./audio_library",
                    "tooltip": "音频库根目录路径"
                }),
                "scan_max_depth": ("INT", {
                    "default": 3,
                    "min": 1,
                    "max": 10,
                    "tooltip": "扫描子目录的最大深度"
                }),
                "similarity_threshold": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1,
                    "tooltip": "相似度阈值，低于此值的匹配将被忽略"
                }),
            },
            "optional": {
                "use_ffmpeg": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "优先使用FFmpeg加载音频"
                }),
                "target_sample_rate": ("INT", {
                    "default": 16000,
                    "min": 8000,
                    "max": 48000,
                    "tooltip": "目标采样率"
                }),
                "random_selection": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "随机选择匹配的音频文件（多个匹配时）"
                }),
                "randomize": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "随机模式下自动生成种子"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFFFFFFFFFF,
                    "tooltip": "随机种子，0表示自动生成"
                }),
                "max_duration_seconds": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 300.0,
                    "step": 0.1,
                    "tooltip": "音频长度限制（秒），0.0表示不限制"
                }),
                "debug_mode": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "启用调试输出"
                }),
                "always_reload": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "开启后每次调用都重新扫描音频库，不使用缓存（大库会更慢）"
                }),
            }
        }
    
    RETURN_TYPES = ("AUDIO", "STRING", "INT")
    RETURN_NAMES = ("audio", "matched_path", "used_seed")
    FUNCTION = "load_smart_audio"
    CATEGORY = "buding_Tools/Audio/Loaders"
    
    def __init__(self):
        # 检查FFmpeg可用性（延迟初始化）
        if buding_SmartAudioLoader._ffmpeg_available is None:
            buding_SmartAudioLoader._ffmpeg_available = self._check_ffmpeg()
    
    @classmethod
    def _check_ffmpeg(cls) -> bool:
        """检测FFmpeg是否可用"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("✅ FFmpeg 可用")
                return True
            else:
                print("⚠️ FFmpeg 不可用")
                return False
        except FileNotFoundError:
            print("⚠️ FFmpeg 未安装")
            return False
        except Exception as e:
            print(f"⚠️ FFmpeg 检测失败: {e}")
            return False
    
    def load_smart_audio(self, keyword_input, library_root, scan_max_depth, 
                        similarity_threshold, use_ffmpeg=True, target_sample_rate=16000,
                        random_selection=False, randomize=True, seed=0, max_duration_seconds=0.0, 
                        debug_mode=False, always_reload=False):
        """智能音频加载主函数"""
        
        # 种子处理逻辑
        used_seed = 0
        rng = None
        if random_selection:
            if randomize or seed == 0:
                used_seed = random.randint(1, 2_147_483_647)
            else:
                used_seed = seed
            rng = random.Random(used_seed)
        
        if debug_mode:
            print("🎵 === 智能音频加载器调试 ===")
            print(f"🔍 关键词: '{keyword_input}'")
            print(f"📁 音频库: '{library_root}'")
            print(f"🔢 扫描深度: {scan_max_depth}")
            print(f"📊 相似度阈值: {similarity_threshold}")
            print(f"🎧 FFmpeg: {'启用' if use_ffmpeg else '禁用'}")
            print(f"🎲 随机选择: {'启用' if random_selection else '禁用'}")
            if random_selection:
                print(f"🎲 自动种子: {'启用' if randomize else '禁用'}")
                print(f"🎲 使用种子: {used_seed}")
            print(f"⏱️ 长度限制: {max_duration_seconds}秒")
            print(f"♻️ 强制重载: {'启用' if always_reload else '禁用'}")
        
        try:
            # 清理关键词
            clean_keyword = self._clean_filename(keyword_input)
            
            # 扫描音频库（可选择强制重载）
            if always_reload:
                self._cache.invalidate_cache(library_root)
            audio_files = self._cache.get_audio_files(library_root, scan_max_depth, force_reload=always_reload)
            
            if debug_mode:
                print(f"📦 使用缓存: {len(audio_files)}个文件")
            
            if not audio_files:
                if debug_mode:
                    print("❌ 音频库为空或扫描失败")
                return (self._create_silent_audio(target_sample_rate), "", used_seed)
            
            if not clean_keyword:
                if debug_mode:
                    print("⚠️ 关键词为空，返回静音音频")
                return (self._create_silent_audio(target_sample_rate), "", used_seed)
            
            best_match = self._find_best_match(clean_keyword, audio_files, similarity_threshold, 
                                             random_selection, rng, debug_mode)
            
            if not best_match:
                if debug_mode:
                    print(f"❌ 未找到匹配的音频文件（关键词: {clean_keyword}）")
                return (self._create_silent_audio(target_sample_rate), "", used_seed)
            
            if debug_mode:
                print(f"🎯 找到最佳匹配: {best_match['filename']}")
                print(f"📍 文件路径: {best_match['path']}")
                print(f"📊 匹配分数: {best_match.get('score', 0.0):.3f}")
            
            # 加载音频文件
            audio_data = self._load_audio_file(best_match['path'], use_ffmpeg, target_sample_rate, 
                                             max_duration_seconds, debug_mode)
            
            if audio_data:
                if debug_mode:
                    print("✅ 音频加载成功")
                return (audio_data, best_match['path'], used_seed)
            else:
                if debug_mode:
                    print("❌ 音频加载失败，返回静音音频")
                return (self._create_silent_audio(target_sample_rate), "", used_seed)
            
        except Exception as e:
            print(f"❌ 智能音频加载失败: {e}")
            return (self._create_silent_audio(target_sample_rate), "", used_seed)
        
        finally:
            if debug_mode:
                print("🎵 === 调试结束 ===")

    def _clean_filename(self, filename: str) -> str:
        """清理文件名，移除扩展名和特殊字符"""
        if not filename:
            return ""
        
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        
        # 移除常见的音频格式标识
        audio_formats = ['.wav', '.mp3', '.flac', '.aac', '.ogg', '.m4a', '.wma']
        for fmt in audio_formats:
            name = name.replace(fmt.upper(), '')
        
        # 移除数字和特殊字符，保留中文、英文、下划线
        import re
        name = re.sub(r'[^\w\u4e00-\u9fff_]', '', name)
        
        return name.lower().strip()

    def _find_best_match(self, clean_keyword: str, audio_files: List[Dict], 
                         threshold: float, random_selection: bool = False, 
                         rng: Optional[random.Random] = None, debug_mode: bool = False) -> Optional[Dict]:
        """查找最佳匹配"""
        
        if random_selection:
            # 随机选择模式：找到所有符合条件的文件，然后随机选择
            matches = []
            
            for file_info in audio_files:
                score = self._calculate_similarity(clean_keyword, file_info)
                
                if debug_mode and score > 0.3:  # 只显示有希望的匹配
                    print(f"  📊 {file_info['filename']}: {score:.3f}")
                
                if score >= threshold:
                    matches.append((file_info, score))
            
            if not matches:
                if debug_mode:
                    print("❌ 没有找到符合阈值的匹配")
                return None
            
            if len(matches) == 1:
                if debug_mode:
                    print(f"✅ 只有一个匹配: {matches[0][0]['filename']}")
                return matches[0][0]
            
            # 使用种子进行随机选择
            if rng is not None:
                selected_match = rng.choice(matches)
                if debug_mode:
                    print(f"🎲 随机选择了 {len(matches)} 个匹配中的: {selected_match[0]['filename']}")
                return selected_match[0]
            else:
                # 回退到普通随机（不应该发生）
                selected_match = random.choice(matches)
                if debug_mode:
                    print(f"🎲 随机选择了 {len(matches)} 个匹配中的: {selected_match[0]['filename']}")
                return selected_match[0]
        else:
            # 原有的最高分模式
            best_match = None
            best_score = 0.0
            
            for file_info in audio_files:
                score = self._calculate_similarity(clean_keyword, file_info)
                
                if debug_mode and score > 0.3:  # 只显示有希望的匹配
                    print(f"  📊 {file_info['filename']}: {score:.3f}")
                
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match = file_info
            
            if best_match:
                best_match['score'] = best_score
            
            return best_match
    
    def _calculate_similarity(self, clean_keyword: str, file_info: Dict) -> float:
        """计算相似度分数"""
        
        clean_filename = file_info["clean_name"]
        directory_name = file_info["directory"].lower()
        
        # 1. 核心模糊匹配
        fuzzy_score = difflib.SequenceMatcher(None, clean_keyword, clean_filename).ratio()
        
        # 2. 完全匹配奖励
        exact_bonus = 0.2 if clean_keyword == clean_filename else 0.0
        
        # 3. 包含匹配奖励
        contains_bonus = 0.1 if clean_keyword in clean_filename else 0.0
        
        # 4. 目录匹配奖励
        directory_bonus = 0.1 if clean_keyword in directory_name else 0.0
        
        # 5. 综合评分
        final_score = fuzzy_score + exact_bonus + contains_bonus + directory_bonus
        
        return min(final_score, 1.0)
    
    def _load_audio_file(self, file_path: str, use_ffmpeg: bool, 
                        target_sample_rate: int, max_duration: float = 0.0,
                        debug_mode: bool = False):
        """加载音频文件"""
        
        if use_ffmpeg and self._ffmpeg_available:
            return self._load_with_ffmpeg(file_path, target_sample_rate, max_duration, debug_mode)
        else:
            if debug_mode and use_ffmpeg:
                print("⚠️ FFmpeg不可用，使用备用加载方案")
            return self._load_fallback(file_path, max_duration, debug_mode)
    
    def _load_with_ffmpeg(self, file_path: str, target_sample_rate: int, 
                         max_duration: float = 0.0, debug_mode: bool = False):
        """使用FFmpeg加载音频"""
        
        if not TORCH_AVAILABLE:
            print("❌ torch/numpy 不可用，无法使用FFmpeg加载")
            return self._load_fallback(file_path, max_duration, debug_mode)
        
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # FFmpeg命令：标准化音频格式
                cmd = ['ffmpeg', '-i', file_path]
                
                # 添加长度限制（正确位置：在输入文件后，其他参数前）
                if max_duration > 0:
                    cmd.extend(['-t', str(max_duration)])
                    if debug_mode:
                        print(f"⏱️ 限制音频长度为: {max_duration}秒")
                
                # 添加音频处理参数
                cmd.extend([
                    '-ar', str(target_sample_rate),  # 采样率
                    '-ac', '1',                      # 单声道
                    '-acodec', 'pcm_s16le',         # 16位PCM编码
                    '-y',                            # 覆盖输出文件
                    '-loglevel', 'error',           # 减少日志输出
                    temp_path
                ])
                
                if debug_mode:
                    print(f"🔧 FFmpeg命令: {' '.join(cmd)}")
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode != 0:
                    raise Exception(f"FFmpeg转换失败: {result.stderr}")
                
                # 读取WAV文件
                import wave
                with wave.open(temp_path, 'rb') as wav_file:
                    sample_rate = wav_file.getframerate()
                    frames = wav_file.readframes(-1)
                
                # 转换为numpy数组
                audio_array = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                
                # 修正维度：ComfyUI期望 [channels, frames] 格式
                if len(audio_array.shape) == 1:
                    # 单声道音频：[frames] -> [1, frames]
                    audio_tensor = torch.from_numpy(audio_array).unsqueeze(0)
                else:
                    # 已经是多声道，保持 [channels, frames] 格式
                    audio_tensor = torch.from_numpy(audio_array)
                
                # 添加Batch维度以兼容下游节点：[1, channels, frames]
                audio_tensor = audio_tensor.unsqueeze(0)
                
                if debug_mode:
                    print(f"✅ FFmpeg加载成功，音频形状: {audio_tensor.shape}")
                
                return {
                    'waveform': audio_tensor,
                    'sample_rate': sample_rate
                }
                
            finally:
                # 清理临时文件
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    
        except subprocess.TimeoutExpired:
            print("❌ FFmpeg处理超时")
            return self._load_fallback(file_path, max_duration, debug_mode)
        except Exception as e:
            if debug_mode:
                print(f"❌ FFmpeg加载失败: {e}")
            return self._load_fallback(file_path, max_duration, debug_mode)
    
    def _load_fallback(self, file_path: str, max_duration: float = 0.0, debug_mode: bool = False):
        """备用音频加载方案"""
        
        # 方案1：尝试使用torchaudio
        try:
            import torchaudio
            waveform, sample_rate = torchaudio.load(file_path)
            
            # torchaudio默认输出 [channels, frames] 格式，这是ComfyUI期望的格式
            # 无需转置，直接使用
            
            # 添加Batch维度以兼容下游节点：[1, channels, frames]
            waveform = waveform.unsqueeze(0)
            
            # 应用长度限制
            if max_duration > 0 and TORCH_AVAILABLE:
                max_samples = int(max_duration * sample_rate)
                if waveform.shape[-1] > max_samples:
                    waveform = waveform[..., :max_samples]
                    if debug_mode:
                        print(f"⏱️ 截取音频到 {max_duration} 秒")
            
            if debug_mode:
                print("✅ 使用torchaudio加载成功")
            return {
                'waveform': waveform,
                'sample_rate': sample_rate
            }
        except Exception as e:
            if debug_mode:
                print(f"⚠️ torchaudio加载失败: {e}")
        
        # 方案2：尝试使用pydub
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(file_path)
            
            # 应用长度限制
            if max_duration > 0:
                max_ms = int(max_duration * 1000)  # 转换为毫秒
                if len(audio) > max_ms:
                    audio = audio[:max_ms]
                    if debug_mode:
                        print(f"⏱️ 截取音频到 {max_duration} 秒")
            
            # 转换为numpy数组
            samples = np.array(audio.get_array_of_samples()).astype(np.float32)
            samples = samples / (2**15)  # 16位音频归一化
            
            # 重塑为ComfyUI期望的 [channels, frames] 格式
            if audio.channels == 1:
                # 单声道：[frames] -> [1, frames]
                samples = samples.reshape(1, -1)
            else:
                # 多声道：[frames*channels] -> [channels, frames]
                samples = samples.reshape((audio.channels, -1))
            
            if TORCH_AVAILABLE:
                waveform = torch.from_numpy(samples).float()
                # 添加Batch维度以兼容下游节点：[1, channels, frames]
                waveform = waveform.unsqueeze(0)
            else:
                # 如果torch不可用，返回numpy数组，格式为[1, channels, frames]
                waveform = samples[np.newaxis, ...]  # 添加batch维度
            
            if debug_mode:
                print("✅ 使用pydub加载成功")
            
            return {
                'waveform': waveform,
                'sample_rate': audio.frame_rate
            }
        except Exception as e:
            if debug_mode:
                print(f"⚠️ pydub加载失败: {e}")
        
        # 方案3：返回路径信息（让用户手动处理）
        if debug_mode:
            print(f"⚠️ 所有加载方案都失败，返回文件路径: {file_path}")
        
        return None
    
    def _create_silent_audio(self, sample_rate: int = 16000, duration: float = 0.1):
        """创建静音音频"""
        try:
            # 创建指定时长的静音音频
            samples = int(duration * sample_rate)
            
            if TORCH_AVAILABLE:
                # 使用torch创建，格式为 [1, 1, samples] -> [Batch, channels, frames]
                silent_array = np.zeros((1, samples), dtype=np.float32)
                silent_tensor = torch.from_numpy(silent_array)
                # 添加Batch维度以兼容下游节点
                silent_tensor = silent_tensor.unsqueeze(0)
                
                return {
                    'waveform': silent_tensor,
                    'sample_rate': sample_rate
                }
            elif 'NUMPY_AVAILABLE' in globals() and NUMPY_AVAILABLE:
                # 使用numpy创建，格式为 [1, 1, samples] -> [Batch, channels, frames]
                silent_array = np.zeros((1, 1, samples), dtype=np.float32)
                
                return {
                    'waveform': silent_array,
                    'sample_rate': sample_rate
                }
            else:
                print("⚠️ torch和numpy都不可用，无法创建静音音频")
                return None
                
        except Exception as e:
            print(f"❌ 创建静音音频失败: {e}")
            return None
    
    @classmethod
    def IS_CHANGED(cls, keyword_input, library_root, scan_max_depth, 
                   similarity_threshold, use_ffmpeg=True, target_sample_rate=16000,
                   random_selection=False, randomize=True, seed=0, max_duration_seconds=0.0, 
                   debug_mode=False):
        """检查输入是否改变"""
        # 创建一个包含所有相关参数的字符串来检查变化
        param_string = f"{keyword_input}_{library_root}_{scan_max_depth}_{similarity_threshold}_{use_ffmpeg}_{target_sample_rate}_{random_selection}_{randomize}_{seed}_{max_duration_seconds}"
        return hash(param_string)

# 注册节点
NODE_CLASS_MAPPINGS = {
    "buding_SmartAudioLoader": buding_SmartAudioLoader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_SmartAudioLoader": "🎵 buding_SmartAudioLoader (智能音频加载器)",
}

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
