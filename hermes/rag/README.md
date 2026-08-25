# 本地 RAG

该目录提供 BlastGame 文档的本地检索：Markdown 切块 → BGE 向量 → FAISS IndexFlatIP → 来源可追溯检索 → Golden QA 评估。

## 环境

使用 Python 3.11：

```bash
python -m pip install -r requirements.txt
```

固定依赖见 `requirements.txt`。Embedding 模型为 `BAAI/bge-small-zh-v1.5`，默认 revision：

```text
7999e1d3359715c523056ef9478215996d62a620
```

可通过 `RAG_EMBED_REVISION` 显式覆盖。首次加载模型可能访问 Hugging Face；模型进入本地缓存后可离线运行。

## 构建

```bash
python -m rag.build_index
```

默认路径均由 `rag/config.py` 相对当前仓库推导，也可通过以下环境变量覆盖：

- `RAG_CORPUS_ROOT`
- `RAG_INDEX_DIR`
- `RAG_GOLDEN_QA`
- `RAG_CORPUS_SUBDIRS`

构建会：

1. 排除 `archive/` 和 `*_Archive.md`；
2. 拒绝含机器绝对路径或凭据模式的语料；
3. 先写 `.tmp`，成功后原子替换索引；
4. 生成 `index/build_manifest.json`，记录模型 revision、依赖版本、切块参数、语料文件哈希和产物哈希。

## 查询

```bash
python rag_query.py "同一个配置的 optimizer 和 bot 胜率差很多先查什么" --hybrid
```

## 评估

```bash
python -m rag.eval --qa rag/data/golden_qa.json
```

评估口径：

- 44 条正例只有命中规范化的当前来源文件才算命中；错误来源中的泛化关键词不计分；
- 5 条 `__NONE__` 负例单独按默认相似度阈值报告拒答率，不混入 Recall/MRR 分母；
- archive 来源不参与构建或评估。

2026-08-25 当前实测（MainGame + Ops，1205 chunks）：

| 指标 | 结果 |
|---|---:|
| Recall@1 | 52.27%（23/44） |
| Recall@3 | 75.00%（33/44） |
| Recall@5 | 77.27%（34/44） |
| MRR | 0.630 |
| 负例拒答率 | 0.00%（0/5） |

负例拒答率为 0% 表明当前阈值不能可靠识别知识库外问题；在完成阈值标定或拒答分类器前，不把该检索器描述为具备可靠拒答能力。
