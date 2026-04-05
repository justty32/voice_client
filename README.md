# Voice Client (V-TUI Assistant)

一个整合语音与文字、具备本地小模型辅助、且由使用者完全掌控缓冲区的终端机 AI 客户端。

## 🌟 核心愿景

V-TUI Assistant 旨在提供一个高效、直观的语音优先交互环境。通过整合 STT (语音转文字)、TTS (文字转语音) 以及本地 SLM (小语言模型) 的摘要能力，让用户能够通过最自然的语音方式与强大的远端 LLM 进行深度交流。

## 🏗️ 系统架构

系统采用非同步事件驱动架构，确保各模块并发运行而不互相阻塞：

- **Main Router (`main.py`)**: 核心调度器，负责各模块间的消息转发。
- **Audio Pipeline**:
    - **Recorder (`record.py`)**: 具备智能切片逻辑的录音器，支持 VAD (静音检测)。
    - **VoiceToText (`voice_to_text.py`)**: 基于 `faster-whisper` 的本地 STT 引擎。
    - **AudioPriorityPlayer (`text_to_voice.py`)**: 具备优先级的 TTS 播放器，支持立即中断与排队。
- **Logic & Buffer**:
    - **TextAccumulator (`text_accumulator.py`)**: 消息缓冲区，允许在发送前累积多段输入。
    - **SummaryGenerator (`summary_generator.py`)**: 调用本地 SLM (如 gemma3:1b) 生成长回答摘要。
    - **SessionManager (`session_manager.py`)**: 管理对话历史与多会话切换。
- **Interface**:
    - **TuiRenderer (`tui_renderer.py`)**: 基于终端的交互界面。
    - **KeyboardListener (`keyboard_listener.py`)**: 全局快捷键监听。

## ⌨️ 控制指南

### 全局快捷键
- **F7**: **语音指令模式**。录音结束后将识别内容解析为斜线指令（如“清空”、“发送”）。
- **F8**: **录音开关**。点击开始录音，再次点击停止并识别（内容进入缓冲区）。
- **F9**: **快速发送**。立即将当前缓冲区内容发送给远端 LLM。
- **F10**: **强制停止语音**。立即中断正在播放的 TTS。

### 斜线指令 (Slash Commands)
在终端输入框输入或通过语音指令触发：
- `/new [title]`: 新建对话。
- `/switch [title]`: 切换到指定对话。
- `/list`: 列出所有对话。
- `/delete [title]`: 删除对话。
- `/save [file]`: 保存对话到文件。
- `/clear`: 清除 UI 内容。
- `/clear buffer`: 清除缓冲区内容。
- `/show`: 查看缓冲区当前积攒的内容。
- `/stop`: 停止当前语音播放。
- `/help`: 显示帮助信息。

## ⚙️ 配置说明 (`config.ini`)

项目核心行为可通过 `config.ini` 进行高度自定义：

- **[AUDIO]**: 采样率、静音检测阈值、最大录音时长等。
- **[STT]**: Whisper 模型大小、运行设备 (cpu/cuda) 等。
- **[SLM]**: 本地小模型配置，包括 `summary_threshold` (触发摘要的字数门槛)。
- **[LLM]**: 核心对话模型配置与 API 地址。
- **[TTS]**: 语音合成引擎设置、语速与音量。

## 🚀 快速开始

1. **环境准备**:
   - 安装 Python 3.10+。
   - 确保已安装 FFmpeg (Whisper 依赖)。
   - (推荐) 安装 Ollama 以运行本地 SLM 进行摘要生成。

2. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

3. **运行程序**:
   ```bash
   python main.py
   ```

## 🛠️ 技术栈
- **STT**: `faster-whisper`
- **TTS**: `pyttsx3` (离线) / `Kokoro` (HTTP)
- **SLM/LLM**: `Ollama API` / `OpenAI Compatible API`
- **UI**: `rich`
- **Input**: `pynput` (Global Hotkeys)
