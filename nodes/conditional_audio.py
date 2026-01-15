import numpy as np
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

class buding_ConditionalAudio:
    """
    条件音频开关：根据布尔值控制音频数据的输出
    """
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_input": ("AUDIO", {
                    "tooltip": "来自上游加载节点的原始音频数据"
                }),
                "enable": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "来自 buding_RoleMatcher 的控制信号，True=输出音频，False=阻断音频"
                }),
                "debug_mode": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "开启后会在控制台显示音频开关状态"
                }),
                "volume_normalization": ("FLOAT", {
                    "default": -20.0,
                    "min": -60.0,
                    "max": 0.0,
                    "step": 1.0,
                    "tooltip": "音量标准化水平(dB)，-20dB适合大多数场景，负值减小音量，正值增大音量，设为-60可禁用音量标准化"
                }),
            }
        }
    
    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio_output",)
    FUNCTION = "conditional_output"
    CATEGORY = "buding_Tools/Audio/Control"
    
    def conditional_output(self, audio_input, enable, debug_mode, volume_normalization=-20.0):
        """
        根据控制信号条件输出音频
        
        参数:
            audio_input: 输入的音频数据
            enable: 控制信号
            debug_mode: 是否开启调试模式
            
        返回:
            tuple: 包含音频数据或None的元组
        """
        try:
            if debug_mode:
                self._debug_output(enable, audio_input is not None)
            
            if enable:
                # 启用状态：处理音频数据
                processed_audio = audio_input
                
                # 音量标准化（-60dB表示禁用）
                if audio_input and volume_normalization > -60:
                    processed_audio = self._normalize_volume(audio_input, volume_normalization)
                
                # 内置淡入效果（使用固定2200样本数，约50ms@44.1kHz）
                if audio_input:
                    processed_audio = self._apply_gentle_fade_in(processed_audio, 2200)
                
                return (processed_audio,)
            else:
                # 禁用状态：返回None来阻断数据流
                # ComfyUI会跳过接收None的下游节点
                return (None,)
                
        except Exception as e:
            print(f"❌ 条件音频开关错误: {e}")
            # 出错时返回None以确保安全
            return (None,)
    
    def _debug_output(self, enable, has_audio):
        """
        调试信息输出
        
        参数:
            enable: 控制信号状态
            has_audio: 是否有音频输入
        """
        print("\n🎵 === 条件音频调试信息 ===")
        print(f"🔛 控制信号: {'启用' if enable else '禁用'}")
        print(f"🎧 音频输入: {'有效' if has_audio else '无效/None'}")
        
        if enable:
            if has_audio:
                print("✅ 音频将通过开关传递到下游节点")
            else:
                print("⚠️ 开关已启用，但音频输入为无效数据")
        else:
            print("🚫 音频被阻断，下游节点将不会执行")
        
        print("🎵 === 调试信息结束 ===\n")
    
    def _normalize_volume(self, audio_input, target_db=-20.0):
        """
        标准化音频音量到目标dB水平
        
        参数:
            audio_input: 输入音频数据
            target_db: 目标音量水平(dB)
            
        返回:
            处理后的音频数据
        """
        if not audio_input:
            return audio_input
            
        try:
            waveform = audio_input['waveform']
            
            # 计算当前RMS值
            if TORCH_AVAILABLE and isinstance(waveform, torch.Tensor):
                rms = torch.sqrt(torch.mean(waveform ** 2))
                
                # 避免除零错误
                if rms < 1e-8:
                    return audio_input
                
                # 计算需要的增益以达到目标dB水平
                current_db = 20 * torch.log10(rms)
                gain_db = target_db - current_db.item()
                gain_linear = 10 ** (gain_db / 20)
                
                # 应用增益，扩大可调节范围
                max_gain = 100.0  # 最大100倍增益，支持更大的音量调节范围
                gain_linear = min(gain_linear, max_gain)
                
                # 应用增益
                normalized_waveform = waveform * gain_linear
                
                # 简单的限幅器防止削波
                max_val = torch.max(torch.abs(normalized_waveform))
                if max_val > 0.95:
                    normalized_waveform = normalized_waveform * (0.95 / max_val)
                
                # 返回处理后的音频
                return {
                    'waveform': normalized_waveform, 
                    'sample_rate': audio_input['sample_rate']
                }
            else:
                # 使用numpy处理
                waveform_np = np.array(waveform)
                rms = np.sqrt(np.mean(waveform_np ** 2))
                
                if rms < 1e-8:
                    return audio_input
                    
                current_db = 20 * np.log10(rms)
                gain_db = target_db - current_db
                gain_linear = 10 ** (gain_db / 20)
                gain_linear = min(gain_linear, 100.0)  # 扩大可调节范围，最大100倍增益
                
                normalized_waveform = waveform_np * gain_linear
                
                # 限幅器
                max_val = np.max(np.abs(normalized_waveform))
                if max_val > 0.95:
                    normalized_waveform = normalized_waveform * (0.95 / max_val)
                    
                return {
                    'waveform': normalized_waveform, 
                    'sample_rate': audio_input['sample_rate']
                }
                
        except Exception as e:
            print(f"❌ 音量标准化失败: {e}")
            return audio_input
    
    def _apply_gentle_fade_in(self, audio_input, transition_samples=2200):
        """
        应用极短的淡入效果，避免影响音色
        
        参数:
            audio_input: 输入音频数据
            transition_samples: 过渡样本数
            
        返回:
            处理后的音频数据
        """
        if not audio_input:
            return audio_input
            
        try:
            waveform = audio_input['waveform']
            
            # 检查音频长度
            if waveform.shape[-1] <= transition_samples:
                return audio_input  # 音频太短，不需要淡入
                
            # 创建淡入曲线
            if TORCH_AVAILABLE and isinstance(waveform, torch.Tensor):
                # 使用cosine曲线，更平滑
                fade_curve = 0.5 * (1 - torch.cos(torch.linspace(0, torch.pi, transition_samples)))
                
                # 克隆波形避免修改原始数据
                faded_waveform = waveform.clone()
                
                # 应用淡入效果
                faded_waveform[..., :transition_samples] *= fade_curve
                
                return {
                    'waveform': faded_waveform, 
                    'sample_rate': audio_input['sample_rate']
                }
            else:
                # 使用numpy处理
                fade_curve = 0.5 * (1 - np.cos(np.linspace(0, np.pi, transition_samples)))
                
                # 复制波形避免修改原始数据
                faded_waveform = np.array(waveform, copy=True)
                
                # 应用淡入效果
                faded_waveform[..., :transition_samples] *= fade_curve
                
                return {
                    'waveform': faded_waveform, 
                    'sample_rate': audio_input['sample_rate']
                }
                
        except Exception as e:
            print(f"❌ 淡入效果应用失败: {e}")
            return audio_input


NODE_CLASS_MAPPINGS = {
    "buding_ConditionalAudio": buding_ConditionalAudio,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "buding_ConditionalAudio": "🎵 buding_ConditionalAudio (音频开关)",
}
