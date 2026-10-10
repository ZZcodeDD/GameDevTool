# 知识库

## 如何在对话里调用

在本仓库的对话中，用关键词即可唤起对应知识库（规则见 `.cursor/rules/knowledge-keywords.mdc`）：

| 你说 | 助手做什么 |
| --- | --- |
| **人生指南** / 用人生指南分析… | 查 `how-to-live-better/`，按性价比与证据给思路和原因 |
| **毛选** / 用毛选思路分析… | 查 `mao-zedong-anthology/`，按矛盾与方针给思路和原因 |
| 两个都提 | 分节检索后再综合 |

示例：「用人生指南分析：要不要裸辞」「用毛选思路分析：团队里主要矛盾是什么」

说明：绑定**本仓库**；其他项目没有这份 `knowledge/` 镜像时，无法自动读到正文。

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
