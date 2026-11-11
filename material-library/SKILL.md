---
name: material-library
description: 扫描千川本地视频、图片、文件和音效素材，使用 Codex 视觉判断维护 SQLite 分类、动作时间码、范围检索和剪辑反馈。
---

# 千川智能素材库

数据库固定为 `~/.codex/qianchuan-data/materials.db`，素材根目录默认为 `~/Desktop/千川AI剪辑素材库`。素材只读，不移动、不改名。视频用 `python3 scripts/scan_library.py` 扫描；图片、PDF 和音频用 `python3 scripts/scan_support.py --root <目录>` 登记。使用 `python3 scripts/library_status.py` 查看视频分析状态。分类规则见 [classification-rules.md](references/classification-rules.md)。

## 首次学习和增量更新

扫描后用 `material_db.py next` 获取 `pending`、`stale` 队列；失败素材显式 `library_status.py --retry-failed`，中断状态用 `--recover` 恢复。为素材建立独立 ChatCut Desktop 分析项目，使用 `push_asset` 登记，`inspect_asset` 读取元数据并生成带源时间码的 contact sheet；用 `record-sheet` 记录图片路径和源时间码。30 秒以内通常抽 8–16 帧，30–60 秒至少约 16 帧，超过 60 秒每张可抽至 25 帧并用交错时间点或分段补抽；动作幅度大时围绕动作区间以约 0.15–0.5 秒间隔追加抽帧。单次 `inspect_asset` 不超过 25 帧，具体密度见 [visual-analysis.md](references/visual-analysis.md)。将真实元数据写入 assets；未知字段留 NULL。按视觉标准由 Codex 看图分析，先调用 `material_db.py run-start`，每条完成后用 `run-complete --segments-json` 原子保存多个候选片段；失败用 `run-fail` 记原因。不得把文件名或抽帧脚本自动输出当作视觉理解。不要把稀疏抽帧的范围称为精确切点。最终运行 `validate_library.py`。

## 检索与剪辑反馈

用户已确认 `120支绿色` 目录包含两个颜色，正式按“120支／雨林绿（深）”“120支／针叶绿（浅）”归档（用户2026-11-06确认）。同框两色的素材标为混合并关联两色，排除单色展示；单色镜头按视觉分类。数据库逻辑分类与原始路径的处理见 [classification-rules.md](references/classification-rules.md)。

`material_db.py search --series ... --product ... --color ... --text ...` 严格匹配。视觉学习后用 `mark-product` 标记画面与目录产品是否一致；混入其他产品、画面与目录不符或未经视觉确认的素材不进入严格检索。尤其是 `格纹系列/120支 米黄格纹/FX61283.mov` 同时出现米黄和红色格纹，作为双产品混合素材，不作米黄格纹或红色格纹的单品展示。允许跨产品或颜色时才传 `--allow-mixed`，但仍须视觉核对并说明混合内容。结果包含路径、源素材时间码、内容和评分。入选镜头在 ChatCut 中高密度复查后才能编辑。素材不足时明确告知。

用户修改镜头时，用 `material_db.py feedback --asset-id ... --segment-id ... --action prefer|avoid|replace|trim|rate|note --comment ...` 记录；图片、文件或音效的反馈改用 `--supplemental-id`，必要时附项目 ID 与适用范围。下次查询用反馈权重排序。仅经用户确认且可迁移的偏好，再同步到 qianchuan `references/learned-rules.md`；一次性修改只留在数据库。原始分析和用户反馈分别保留，不改写历史证据。

## 定向检索与新素材

剪辑前只读取用户指定的范围：`list-scopes` 仅在名称不明时列出分类摘要；精确型号用 `search --product '80支磨毛'`，型号族用 `--product-prefix '120支'`，整个系列用 `--series-prefix '条纹'`，指定颜色再加 `--color`，指定画面类型可加 `--role unboxing` 等。SQL 先按产品/系列过滤，只返回有限候选片段，不遍历所有 Contact Sheet。混合素材默认排除；用户明确要混合画面时才加 `--allow-mixed`，仅看混合素材可再加 `--mixed-only`。`asset_product_mentions` 记录画面中确实出现的其他产品，所以混合素材可由任一已确认产品范围找到，但不可作为单品卖点证据。

用户2026-11-10确认两条“多品纯色合集”仅用于全系列混合展示。只有本次剪辑允许不限型号的全系列混合画面，才调用 material_db.py search-collections --all-series（可加 --text、--limit）。这类 collection_montage 不进入普通 search（包括 --allow-mixed）或 search-generic；不得用来支持某一型号、颜色、单品或局部系列的口播。具体归档见 [分类规则](references/classification-rules.md)。

`包装、开箱` 下的通用动作视频按用户要求不识别具体产品；视觉复核后用 `asset-role ... unboxing`、`mark-generic`，并用 `search-generic --role unboxing --text ...` 单独查找拆封、放盒、掀盖、移盒等动作。动作搜索只匹配正向动作标签与已观察到的主体运动；“没有掀盖”一类否定说明不能算作掀盖镜头。普通产品搜索不自动混入通用开箱镜头；只有脚本或用户画面要求需要开箱时才追加这一小组检索。镜头里若出现明确的其他产品标识或不宜混用的内容，只登记安全区间或保留待确认。不能把品牌盒入画、摆放、盖盒称作已经打开盒子。

新视频须经视觉检查后用 `asset-role` 标记产品画面、开箱、认证或其他内容；新图片、PDF、音效先进入 `supplemental_assets` 的 `pending/unclassified` 队列。用 `support-pending` 查看待确认项；能辨认内容但归属未明时，用 `support-note` 保存可见证据并保持 pending，向用户提问。核对实际内容和所属产品后才用 `support-set` 写描述、角色、口播位置关键词和确认依据；用户明确确认适用于所有产品时使用 `support-set --all-products`，不要复制成多个产品记录。已确认辅助素材才通过 `support-search` 进入剪辑候选。图片区分检测报告、报告首页与宣传图；数据库分别记录文件可见证据和用户确认的适用范围，不把用户确认表述成已独立核验证书。不能判断的内容向用户提问，绝不凭文件名决定。音效库可用独立根目录扫描；音效需试听后标记用途，不能只按名字套用。细则见 [classification-rules.md](references/classification-rules.md)。

未来遇到大幅或重复运动，先密集定位每次动作的第一帧和最后一帧，再用 `motion-event` 保存源时间坐标、动作模式和证据；重复动作逐次记录 `cycle_index`。`frame_verified` 只给已经检查相邻源帧的边界，稀疏候选仍标 `coarse`。精确选帧方法见 [visual-analysis.md](references/visual-analysis.md)。

## 音效学习

`scripts/inspect_audio.py --root <素材总目录> --report <JSON路径>` 使用本机已有的 ffprobe/ffmpeg 扫描辅助素材，保存 `audio_metadata` 的时长、采样率、声道、解码后指纹、RMS/样本峰值及100毫秒能量包络。它只做技术检测，不识别声音内容，不安装依赖，也不把待确认素材升级为已听审。完整听过声音后才用 `support-set --role sound_effect` 写入实际声音描述、可用源区间、与画面动作或氛围的对应关系、突兀声/人声/音乐干扰、尾音与循环接缝等证据。用途明确的通用音效可不绑定产品。

音频输入未实际到达模型时，说明限制并保持 `pending`；文件名、转写、频谱与能量包络都不能代替试听，不能确认其高级感、具体声源或精确动作切点。已确认音效用 `support-search --role sound_effect --text <当前动作或氛围>` 定向查询；不要每次读取全部音效。实剪按 qianchuan 的 `references/audio-use.md` 克制使用，并在成片中复听。

本机已安装本地 Qwen 音频理解，调用方法、实测结果与不确定性处理见 [local-qwen-audio.md](references/local-qwen-audio.md)。仅在需要音效内容分析时读取；保留模型来源，不把推断当作已人工听审。

## 已学素材的视觉复核

视频默认只学习画面，不分析音轨；独立音效或口播文件另走音频流程。用户要求重新比较旧分析时，先备份数据库、核对源文件指纹，再由当前 Codex 重新查看全片代表帧，覆盖尾段；长片和大幅或重复动作追加密集抽帧。以实际证据、用途、动作完整性和时间码可靠性比较版本，不能仅因换模型或提高评分就覆盖旧版。保留准确的旧分析和用户确认，只有明确纠错或补充才修改。

旧片段复核不要用 `run-complete --segments-json` 整体重建；它会删除旧片段并断开反馈关联。使用 `scripts/review_analysis.py --db <数据库> --records <JSON> --version <唯一复核版本>`，每条记录提供 `id`、`decision`（keep/revise）、`observation`、实际看过的 `evidence`（含 `image_path`、`source_times_us`），以及可选 `patches`（片段 ID 到字段修正）。脚本原子保留片段 ID、用户反馈和动作证据，把前后快照与选择理由写入 `visual_reviews`。未逐帧核实的切点仍标 coarse；确实截断的动作明确记为不完整。

用户已确认 `天冷了脚收回被子里.MP4`、`机洗.mp4`、`卧室环境（不带床）/11月3日-2.mov` 和 `11月3日-12.mov` 是通用生活场景，不绑定型号。目录中的无产品环境画面也只进入通用场景检索。`音效/翻书.mp3` 按用户确认仅称纸张摩擦声，不确定为翻页，按实际纸张动作克制使用。
