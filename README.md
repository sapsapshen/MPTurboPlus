<div align="center">
<h1 align="center">MPTurboPlus 🎬</h1>

<p align="center">
  <b>场景级对齐 · 一键启动 · 零幻觉视频生成</b>
</p>

<p align="center">
  <a href="https://github.com/sapsapshen/MPTurboPlus/blob/main/LICENSE"><img src="https://img.shields.io/github/license/sapsapshen/MPTurboPlus.svg?style=for-the-badge" alt="License"></a>
  <a href="https://github.com/harry0703/MoneyPrinterTurbo"><img src="https://img.shields.io/badge/upstream-MoneyPrinterTurbo-blue?style=for-the-badge" alt="Upstream"></a>
</p>

<br>
<h3>简体中文 | <a href="README-en.md">English</a></h3>

<br>
基于 <a href="https://github.com/harry0703/MoneyPrinterTurbo">MoneyPrinterTurbo</a> 的增强分支，<b>修复了"生成视频场景与主题相差甚远"的核心问题</b>，并增加一键启动脚本。
<br>

</div>

---

## 为什么选择 MPTurboPlus？

**MoneyPrinterTurbo** 是一个非常优秀的全自动短视频生成工具。但在实际使用中，很多用户发现：

> ❌ 主题是"森林徒步"，画面却出现了城市车流
> ❌ 旁白在讲"海浪拍岸"，视频却在播"办公室键盘"
> ❌ 5 个全局搜索词无法覆盖多段落脚本的丰富内容

**MPTurboPlus** 通过**逐段落场景对齐**彻底解决了这个问题：

| | 原版 MoneyPrinterTurbo | MPTurboPlus |
|---|---|---|
| 搜索词生成 | 整条脚本 → 5 个全局词 | **每个段落** → 1-3 个可视化搜索词 |
| 素材下载 | 所有词混在一起搜索 | **逐段落**搜索，追踪归属 |
| 视频拼接 | 随机 shuffle 填充 | **按段落时间窗口**顺序拼接 |
| 场景匹配度 | 随机 | **旁白第 N 段 ↔ 画面第 N 段** |

---

## 核心改进 🔧

### 1. 逐段落场景对齐流水线

```
用户主题 → LLM 生成可视化脚本(N段)
              ↓
         逐段落生成搜索词 ← 新增 `generate_terms_per_paragraph()`
              ↓
         逐段落下载素材   ← 新增 `download_videos_scene_aligned()`
              ↓
         按时间窗口拼接   ← 新增 `combine_videos_scene_aligned()`
              ↓
         画面与旁白精准对齐的短视频
```

- **`app/services/llm.py`** — 新增 `generate_terms_per_paragraph()`，每个段落独立生成 1-3 个具象英文搜索词
- **`app/services/material.py`** — 新增 `download_videos_scene_aligned()`，素材按段落归属，段间不混用
- **`app/services/video.py`** — 新增 `combine_videos_scene_aligned()`，按音频时长平分时间窗口，每段素材只在其窗口内出现
- **`app/services/task.py`** — 自动检测多段落场景，无缝切换到对齐流水线

### 2. 增强 Prompt（视觉引导）

- 脚本生成 prompt 增加约束：每个段落必须描述一个**可拍摄的具体视觉场景**
- 搜索词 prompt 优先**具象名词短语**（`golden retriever puppy playing` 而非 `dog`）
- 避免抽象概念，确保每个搜索词在 Pexels/Pixabay 上可命中

### 3. 一键启动脚本

| 平台 | 脚本 | 说明 |
|------|------|------|
| Windows | `start.bat` | 自动检测 `.venv` / `uv` / 系统 Python，后台启动 API，前台启动 WebUI |
| Linux / macOS | `start.sh` | 同上，带 trap 清理，Ctrl+C 同时停止两个服务 |
| 通用 | `start_helper.py` | 纯 stdlib 端口探测，为 bat 脚本提供可靠端口检测 |

启动后终端输出：

```
======================================
  API:    http://127.0.0.1:8080
  Docs:   http://127.0.0.1:8080/docs
  WebUI:  http://127.0.0.1:8501
======================================
```

### 4. 向后兼容

- `paragraph_number=1` 时走原版路径，行为完全不变
- 所有新增函数与旧函数并存，旧 API 调用不受影响
- 配置文件和 WebUI 参数无变化

---

## 快速开始 🚀

### 前提条件

- Python 3.11（推荐通过 `uv` 管理）
- 网络通畅（需访问 Pexels/Pixabay API 和 LLM API）

### 安装

```shell
git clone https://github.com/sapsapshen/MPTurboPlus.git
cd MPTurboPlus
uv python install 3.11
uv sync --frozen
```

将 `config.example.toml` 复制为 `config.toml`，填入你的 API Key：

- `pexels_api_keys` / `pixabay_api_keys`（素材搜索）
- `llm_provider` + 对应 API Key（脚本和搜索词生成）

### 启动

**Windows（推荐）**：
双击 `start.bat`

**Linux / macOS**：
```shell
chmod +x start.sh && ./start.sh
```

**手动启动**：
```shell
# 终端 1：启动 API
uv run python main.py

# 终端 2：启动 WebUI
uv run streamlit run webui/Main.py --server.address=127.0.0.1 --server.enableCORS=True
```

### 使用建议

- 将 `paragraph_number` 设为 **3 以上**，体验场景对齐效果最佳
- 主题尽量具体（如"黄山云海日出"而非"风景"）
- `video_clip_duration` 建议 3-5 秒，避免单段过长失去节奏

---

## 配置要求 📦

| 项目 | 最低配置 | 推荐配置 |
| ---- | -------- | -------- |
| CPU  | 4 核     | 8 核     |
| RAM  | 4 GB     | 8 GB     |
| GPU  | 非必须   | 4 GB+    |

- 依赖云端 LLM + 在线素材时，CPU 和网络比 GPU 更重要
- 启用 `faster-whisper` 本地转录时建议 GPU

---

## 功能特性 🎯

保留 MoneyPrinterTurbo 全部功能：

- 完整 MVC 架构，支持 API + WebUI
- AI 自动生成文案或自定义文案
- 竖屏 9:16 / 横屏 16:9 高清视频
- 批量生成 + 多语言 + 多种 TTS 语音
- 字幕生成（字体/位置/颜色/大小/描边）
- 背景音乐（随机或指定）
- 无版权素材 + 本地素材
- 支持 OpenAI / DeepSeek / Gemini / Qwen / Ollama / Azure 等 15+ LLM 提供商
- Docker 部署

**MPTurboPlus 新增**：

- 逐段落场景对齐视频生成
- 增强视觉 Prompt 系统
- 一键启动脚本（Windows + Linux/macOS）

---

## 上游致谢 🙏

本项目基于 [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) 构建，感谢原作者 [@harry0703](https://github.com/harry0703) 和所有贡献者的出色工作。

---

## 许可证 📝

MIT — 详见 [`LICENSE`](LICENSE) 文件
