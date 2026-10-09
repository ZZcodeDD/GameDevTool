# 知识库

## 高性价比人生指南

路径：[`how-to-live-better/`](./how-to-live-better/)

本地镜像了 [eternity4719/HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter)（CC BY 4.0）：有据可查的生活建议，用于检索、辅助决策。

| 用途 | 位置 |
| --- | --- |
| 正文条目 | `how-to-live-better/book/` |
| 场景长文 | `how-to-live-better/docs/` |
| AI 决策 skill | `.cursor/skills/life-decision-guide/` |
| 同步 | `bash knowledge/how-to-live-better/sync.sh`（≥7 天） |

## 毛泽东选集

路径：[`mao-zedong-anthology/`](./mao-zedong-anthology/)

本地镜像了 [NpTIme/MaoZeDongAnthology](https://github.com/NpTIme/MaoZeDongAnthology)：官方五卷 + 静火非官方两卷，约 392 篇。

| 用途 | 位置 |
| --- | --- |
| 正文 | `mao-zedong-anthology/volumes/` |
| 可检索 HTML（章节 / 注释跳转） | `mao-zedong-anthology/index.html`（`python3 tools/build_reader.py`） |
| AI skill | `.cursor/skills/mao-anthology/` |

涉及毛选原文时，助手**直接**检索 `volumes/` 再答（不先同步），并注明卷次与篇名；第六、七卷标明非官方。毛选视为静态知识，与人生指南的周更策略不同。
