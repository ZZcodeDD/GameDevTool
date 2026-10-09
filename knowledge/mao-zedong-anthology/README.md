# 毛泽东选集 · 本地知识库

镜像自 [NpTIme/MaoZeDongAnthology](https://github.com/NpTIme/MaoZeDongAnthology)：官方五卷 + 静火非官方两卷，共约 392 篇。

## 阅读

| 文件 | 说明 |
| --- | --- |
| `index.html` | 可检索阅读器：左侧分卷目录、全文搜索、正文脚注 ⇄ 注释跳转 |
| 构建 | `python3 tools/build_reader.py` |
| PDF / EPUB | 见 agent artifacts 或上游 `合并版本/` |

重新生成阅读器：

```bash
python3 knowledge/mao-zedong-anthology/tools/build_reader.py
```

## 给助手用

- Skill：`.cursor/skills/mao-anthology/SKILL.md`
- 正文：`volumes/`
- 目录：`catalog.json`

毛选视为**静态知识库**：回答相关问题前**不自动同步**，直接查本地原文。若以后要手动刷新上游，可自行运行 `bash knowledge/mao-zedong-anthology/sync.sh --force`。

第六、七卷为非官方整理，引用时须标明。详见 [`ATTRIBUTION.md`](./ATTRIBUTION.md)。
