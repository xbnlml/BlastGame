# Wrongbook 边界规则

`Doc/wrongbook.md` 和 Hermes skill 的内容如何划分：

## Wrongbook 放什么（流程级别错误）

- 工具 bug 和修复（如 `pool.py` 的去重键未归一化、`find_best_combo` 的 O(n⁵) 超时）
- 目录/路径混淆（如 WB-010：reasonix vs Hermes 目录混淆）
- 数据流/缓存问题（如 bot 数据批次聚合而非累加）

## Skill 放什么（知识级内容）

- 参数理解（sd 非单调、of 非线性、sc 含义、ratios 等价）
- 探针设计原则（缺口评估、槽位分配、微调法）
- 判级规则（合格判定、硬性违规、审美）
- 操作流程（三批流程、提交方式、排错）
- 工具用法（preflight、asset_patcher 等）

## 重复的后果

WB-011~013 曾放在 wrongbook 但完全与 skill 重复：
- WB-011（参数经验）→ 已在 `probe-design.md` 和 `multi-tier-designer` 规则库
- WB-012（asset 缩进）→ 已在 `bot-orchestrator` 排错章节
- WB-013（submit 用法）→ 已在 `bot-orchestrator` 核心规则

一旦发现 wrongbook 条目与 skill 重复，删除 wrongbook 条目，保留 skill 版本。
