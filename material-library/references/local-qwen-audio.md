# 本地 Qwen 音频理解

已安装位置：`/path/to/home/Documents/ChatGPT/千川剪辑/qianchuan-data/qwen-audio/`。具体模型、版本、环境及验证记录见该目录的 `installation.json`。模型为 `giangndm/qwen2.5-omni-7b-mlx-4bit`，用独立 Python 环境运行，音频推理不调用外部 API。

## 调用

```sh
"/path/to/home/Documents/ChatGPT/千川剪辑/qianchuan-data/qwen-audio/.venv/bin/python" \
  "/path/to/home/Documents/ChatGPT/千川剪辑/qianchuan-data/qwen-audio/analyze_audio.py" \
  "/绝对路径/音效.mp3" \
  --output "/绝对路径/分析结果.json"
```

支持传入多个音频路径；按需只处理新增或变化的音效。默认每段最多12秒，长音频逐段分析；`source_in_us/source_out_us` 是分析窗口，不能当作声音事件精确起止。原音频只读。不要给模型传文件名或预设内容，先判断真实声音再与用户分类核对。

工具受限进程可能不能访问 Metal；当前安装验证已在宿主进程使用 M4 GPU 成功运行。宿主终端可直接调用；Codex 工具需使用获授权的宿主执行方式，不因受限进程读不到 GPU 误判电脑不兼容。模型按需加载，完成后进程退出，无常驻服务。

## 证据和限制

2026-11-03测试3条真实音效，模型未收到文件名，输出布料般窸窣声、鸟鸣、短促点击声；约2.1秒加载，测试峰值 GPU 内存约5.02GB。这些是该组短音频的实测，不是所有素材的性能保证。依赖已锁定在 `requirements.lock.txt`；权重和分词器有下载清单和SHA256验证。

纯提示音对照中出现过误报人声；原始模型也曾给全零静音编造声音，入口已对全零输入单独检测。输出英文便于保持当前实现稳定，可由主Agent翻译，但不得添加原分析没有的声源事实。结果属于**本地Qwen音频推断**，不称作Codex原生直接听审或人工确认。

入库时保存模型名称、版本、源文件指纹、分析窗口、原始描述和不确定性。只采纳有足够依据的声学内容；人声/音乐是否存在、具体声源、材质、动作同步、循环接缝和高级感仍需结合证据判断。信息不明或结论冲突时保持待确认并向用户提问。不能仅凭模型一句描述自动确认全部音效，不能把窗口边界写成精确动作切点。使用原则继续按 qianchuan `references/audio-use.md`。

