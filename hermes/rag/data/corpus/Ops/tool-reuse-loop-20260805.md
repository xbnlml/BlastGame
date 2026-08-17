# 工具/经验"有却不用"的根治：触发闭环（2026-08-05 用户反复纠正后定稿）

## 症状
用户反复暴怒："为什么又是现有能用的工具却不用！！！！""明明有工具/经验但后面就是不知道用"。
实测：`tools/gen_payload.py` 在 skill 里出现 9 次，我仍手写硬编码 `gen_payload_7lv_white.py`。
根因**不是内容缺失**（skill 都有记录），是**检索/触发失效**——动手时心智模型是"完成操作"，
不会主动扫 skill 查现成工具/经验。

## 高手（Agentic Engineering）的解法 = 一个闭环，不是建一个静态文件
Matt Van Horn 22 条至理核心：CLAUDE.md 是"**持续编译的知识**"——**每次踩坑就追加，越厚越准**。
关键在**循环机制**，不在文件本身：
```
踩坑 → 立刻追加进"每次自动加载的高频文件" → 下次动手时必然看到 → 不再犯
```
而错误做法是：
```
踩坑 → 记进 159KB 大 skill → skill 太大/太散，动手时没触发 → 再犯
```
大 skill 里的低频内容要"按需 skill_view 加载"，**只有"当前最易犯的几条"该进每次自动加载的文件**，
且随时清理过时项（过时信息比没有信息更危险——用户原话）。

## Hermes 原生触发机制（不是 Claude Code 的 AGENTS.md）
Hermes 支持项目上下文文件 `.hermes.md` / `HERMES.md`，**每次会话自动注入**（不依赖 agent 主动 skill_view）。
- 源码：`prompt_builder.py` `_HERMES_MD_NAMES = (".hermes.md", "HERMES.md")`，`_find_hermes_md(cwd)` 从 cwd 向上到 git root 找第一个。
- 上限 **20,000 字符**，超了 head+tail 截断。
- git root = `D:\download\BlastGame\`（含 hermes/ 与 README.md），所以 `D:\download\BlastGame\hermes\.hermes.md` 会被自动加载。
- 用户纠正：**不要拿 Claude Code 的名字生搬硬套**——Hermes 有自己的 `.hermes.md` 机制。

## 触发要"按操作类型"，不是"每次会话/每个动作都看同一堆"
用户纠正（"每次动手都看 Excel 小数这些，跟好多不相干的活没关系"）：
- 高频/通用守则（如"写操作前先查 tools/"）进 `.hermes.md` 自动加载。
- 细分规则（Excel 小数 0.8=80%、写 asset 用 write_ddc 等）属"写操作"类，做写操作时才看，不塞进每次加载。
- 组织方式：按操作类型分（写操作 / 查数据 / 排查 / 通用），不是一坨全堆前面。

## 落地铁则（动手前 3 秒，宁可多花 30 秒查工具不写一行手写脚本）
1. `ls tools/` + `ls project-state/` + `ls scripts/` —— 先看现成脚本，禁止一上来手写。
2. 读对应类别工具：DB payload `tools/gen_payload.py --levels/--source/--override/--out`；
   Excel `write_excel.write_tiers`；board 固定 7 列整行；全流程 `reimport.py`/`reimport_batch.py`；
   只读审计 `compare_imported.py`/`verify_pool_data.py`/`audit_imported.py`/`compare_level_db.py`。
3. 生成 payload **千万别手写硬编码关卡列表的脚本**（2026-08-05 教训：gen_payload_7lv_white.py 被用户质问"工具是通用的你为什么不直接用"）。
4. 判定/组合/探针分析先跑现成只读脚本（`level_status.py`/`param_knowledge.py`/`find_best_combo.py`），别从零算。
5. 改 asset 前先算 fingerprint（官方 `computeTierConfigFingerprint`），DB 已有同配置 entry 可省写库（坑 128）。

## memory/skill 存放位置（可移植性，2026-08-05 用户澄清）
- **实际用的** blastgame skill + 注入的 system-prompt memory 在全局 `~/AppData/Local/hermes/`（实时更新）。
- 项目根 `hermes/memories/` 是 **7-31 旧快照**（40 条 vs 全局 50 条，含已废弃规则）；`hermes/project-state/_archive/skills-old/` 是归档旧 skill。
- 用户问"项目文件夹里也有 memory/skill 你没读取吗？"→ 答案是**那些是旧副本，实际用的是全局那份**，别被旧文件误导。
- 用户要求："BlastGame 相关的一切（memory/skill/工具/数据）最终都在 `D:\download\BlastGame\hermes\` 一拷就走，
  通用型 Hermes skill/memory 可留默认位置"；当前是"平时用全局、拷贝时才临时复制"的过渡方案。
- 活跃 agent 记忆 = `hermes/agents/{warden,planner,judge,curator}/memory.md`（在项目内，随项目走）。
- 主 skill 是唯一活跃的 BlastGame skill（合并了 9 个模块 skill），`.archive/` 里 10 个旧模块 skill 是历史参考，拷贝时只带主 skill 即可。