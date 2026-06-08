# 🎬 我用开源工具自动生成短视频，发现它有个致命缺陷……然后我把它修好了

> 一个 AI 短视频生成工具的「外科手术式」改造记录

---

## 一句话省流

**MPTurboPlus**：基于 81k Star 开源项目 MoneyPrinterTurbo 的增强版，修复了"AI 生成视频画面和主题各说各话"的核心 bug，**让你的短视频旁白第几段、画面就是第几个场景**。

---

## 01 原始项目有多强？

[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) 是一个现象级开源项目——**你只需要输入一个主题，它自动完成从写稿、配音、找素材、加字幕到合成视频的全部工作**。

Github 81,000+ Star，15+ 种大模型接入（OpenAI / DeepSeek / Gemini / 通义千问……），Pexels 和 Pixabay 海量无版权素材直接调用，支持竖屏横屏、中英文、批量生成、Docker 一键部署。

随便举一个例子：输入"金钱的作用"，30 秒后得到一个带配音、字幕、背景音乐的完整短视频。

但用了几天之后，我发现了一个问题。

---

## 02 致命缺陷：画面和主题各说各话

生成了十几个视频后，我开始注意到一种奇怪的"分裂感"：

| 旁白在讲 | 画面在播 |
|----------|----------|
| 海浪拍打着礁石，激起白色浪花 | 一个程序员在打字 ⌨️ |
| 金黄的银杏叶铺满林间小道 | 城市车流夜景 🚗 |
| 热腾腾的咖啡散发着香气 | 蓝天白云空镜 ☁️ |

于是我翻源码，在 `app/services/` 下面找到了答案。

**原版的生成流水线是这样的：**

```
用户主题 → LLM生成N段脚本 → LLM生成5个全局搜索词
→ 用这5个词一次性搜素材 → 所有素材混在一起随机拼接 → 输出视频
```

问题出在哪？**搜索词是"全局"的，不是"逐段落"的**。

一条 3 段脚本（森林→海洋→城市），只产出了 `["nature landscape", "beautiful scenery", "outdoor adventure", "wildlife animals", "forest trees"]` 五个全篇通用词。然后用随机模式拼接——第 1 段"森林"的旁白可能配上第 3 段"海洋"对应的素材。

**这就是为什么画面和旁白永远对不上。**

---

## 03 外科手术式修复：逐段落场景对齐

搞清楚根因之后，改造思路就很清晰了——**把"全局搜索→随机拼接"改成"逐段落搜索→按顺序对齐"**。

改造涉及四个核心文件：

```
app/services/llm.py      ← 新增 generate_terms_per_paragraph()
app/services/material.py ← 新增 download_videos_scene_aligned()
app/services/video.py    ← 新增 combine_videos_scene_aligned()
app/services/task.py     ← 自动检测 & 分发新旧流水线
```

**新的流水线：**

```
用户主题 → LLM生成N段可视化脚本
              ↓
为每个段落独立生成1-3个具象英文搜索词
  段落1: ["sunlit forest path", "morning dew leaves"]
  段落2: ["ocean waves crashing", "beach sunset golden"]
  段落3: ["city skyline night", "busy street traffic"]
              ↓
逐段落去Pexels搜索并下载，记录段落归属
              ↓
按音频时长平分时间窗口，每段素材只在其窗口内播放
              ↓
画面与旁白精准对齐 ✓
```

每一个环节都做了细节打磨：

- **搜索词 prompt 优化**：要求 LLM 输出"金色寻回犬幼犬在草地上奔跑"而不是"狗"
- **素材段间隔离**：段落 A 下载的素材不会被段落 B 的视频用到
- **Fallback 保护**：某段落搜索无结果时，自动借用相邻段落的素材
- **向后兼容**：`paragraph_number=1` 时走原版路径，零破坏

---

## 04 效果对比

用同一个主题"秋天的诗意"，`paragraph_number=3` 实测：

### 改造前

```
段落1 "金黄的银杏叶铺满道路" → 素材：随机混剪（含城市夜景）
段落2 "收获的果实在枝头摇曳" → 素材：随机混剪（含海浪礁石）
段落3 "秋风吹过稻田掀起金色波浪" → 素材：随机混剪（含办公室键盘）
```

### 改造后

```
段落1 → [yellow ginkgo leaves pathway, autumn forest trail]
段落2 → [ripe fruit on tree branch, apple orchard harvest]
段落3 → [golden rice field wind, wheat field sunset]
```

**画面场景匹配度从"碰运气"变成了"逐段对齐"。**

---

## 05 一键启动 + 完整 README

除了核心修复，本分支还附带：

| 文件 | 用途 |
|------|------|
| `start.bat` | Windows 一键启动（自动检测 venv/uv/Python，后台 API + 前台 WebUI） |
| `start.sh` | Linux/macOS 一键启动（Ctrl+C 同时停两个服务）|
| `start_helper.py` | 纯标准库端口探测 |
| `README.md` | 完整的中文文档，架构图 + 对比表 |

---

## 06 快速体验

```bash
git clone https://github.com/sapsapshen/MPTurboPlus.git
cd MPTurboPlus
uv sync --frozen
# Windows 双击 start.bat
# Linux/macOS 执行 ./start.sh
```

在 WebUI 中将「段落数」设为 3 以上，感受一下画面和旁白终于能对上是什么体验。

---

> 💡 **戳上方「MPTurboPlus」关注 / Star，获取第一手更新。**
>
> 🔗 GitHub：https://github.com/sapsapshen/MPTurboPlus
>
> 🙏 上游项目：https://github.com/harry0703/MoneyPrinterTurbo

---
