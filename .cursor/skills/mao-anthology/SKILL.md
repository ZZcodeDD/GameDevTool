---
name: mao-anthology
description: 用本地《毛泽东选集》知识库（NpTIme/MaoZeDongAnthology 镜像）回答与毛选原文、历史背景注释相关的问题。先检索篇目再答，注明卷次与篇名；第六、七卷为非官方静火整理须标明。触发词：毛选、毛泽东选集、毛主席、矛盾论、实践论、论持久战、为人民服务、引用毛选、这篇文章怎么说。
---

# 毛泽东选集：查原文再答

## 知识库位置

`knowledge/mao-zedong-anthology/`

| 路径 | 用途 |
| --- | --- |
| `volumes/` | 七卷 Markdown 正文 |
| `catalog.json` | 卷 / 篇目录 |
| `index.html` | 可读 HTML（章节、检索、注释跳转） |
| `SYNC.json` | 上次同步时间 |

## 回答前是否同步

若 `SYNC.json` 不存在，或 `synced_at` 距现在 ≥ 7 天：先执行

```bash
bash knowledge/mao-zedong-anthology/sync.sh
```

强制刷新：`bash knowledge/mao-zedong-anthology/sync.sh --force`。答完后简要说明是否同步及变更。

## 怎么查

1. 先读 `catalog.json` 或 `grep` 篇名定位卷次。
2. 在 `volumes/` 里按关键词检索，**整篇或相关段落读完**再答（含文首说明与文末「注释」）。
3. 引用格式：`第 X 卷《篇名》`；有注释则写 `注〔n〕`。
4. 第六、七卷必须标明「非官方·静火整理」。

示例：

```bash
KB=knowledge/mao-zedong-anthology
grep -RIn '矛盾' "$KB/volumes" --include='*.md' | head
grep -RIn '^# ' "$KB/catalog.json"  # 或直接读 catalog.json
```

## 怎么写答复

1. 一句话点明相关篇目与核心论断。
2. 引文尽量短，忠实原文，不改写关键表述。
3. 需要背景时可用文首按语 / 文末注释，并标明是注释。
4. 书中没有的内容明确说「选集未收 / 未检索到」，不要编造语录。
5. 这是历史文献库，不作现实政治动员；分析问题时把原文与当下应用分开写清。

## 边界

- 不替代严肃史学或原著版本考证；版本争议以上叙述明。
- 非官方卷（六、七）结论更谨慎，必要时建议核对官方出版物。
