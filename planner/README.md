# 日次 · 生活与工作清单

手机（苹果）和 Windows 都能用，**不要求工作电脑一直开机**。

## 怎么协作（最省事）

你在 Cursor 对话里用自然语言告诉我，例如：

> 下周三下午 3 点交方案，周末买菜，明天早上 9 点提醒我交社保

我会：

1. 分成「生活 / 工作」
2. 加密写入云端清单并推送
3. 需要提醒时，到点给你手机推送（ntfy），也可导出到系统日历

## 双端怎么用（电脑关机也行）

### 1. 打开清单网页

把本仓库的 `planner/` 用下面任一方式打开（任选其一）：

**方式 A（推荐，一次设置）**  
GitHub 仓库 → Settings → Pages → Build and deployment → Source 选 `Deploy from a branch` → Branch 选合并后的默认分支，Folder 选 `/planner`（若界面只能选 `/` 或 `/docs`，则把 Pages 指到 `/docs` 并把内容同步过去，或用方式 B）。

**方式 B（立刻可用）**  
用 jsDelivr 打开当前分支上的页面（分支合并后把分支名改成 `master`）：

`https://cdn.jsdelivr.net/gh/ZZcodeDD/GameDevTool@cursor/personal-planner-2d68/planner/index.html`

Windows 浏览器收藏；iPhone Safari 打开后可「分享 → 添加到主屏幕」。

### 2. 解锁口令

口令由我私下发给你（不会写进公开仓库明文事项）。  
手机和 Windows **各输入一次**，会记在该设备浏览器里。

云端文件 `data/tasks.cloud.json` 只有密文；公开仓库里看不到你的事项原文。

### 3. 苹果手机推送提醒

1. App Store 安装免费应用 **ntfy**
2. 订阅我发给你的主题（形如 `rici-xxxxxxxx`）
3. 保持通知权限开启

到点后由云端助手推送，**不依赖你的 Windows 开机**。

若你更习惯系统日历：在网页点「导出日历」，把 `.ics` 导入 iPhone「日历」或 Google 日历。

## 本地开发

```bash
cd planner
python3 -m http.server 5173
```

浏览器打开 `http://localhost:5173`，用口令解锁。

维护者加密同步：

```bash
# 先编辑 data/tasks.json（此文件已 gitignore）
node sync.mjs
```

## 数据说明

| 文件 | 是否提交 | 说明 |
| --- | --- | --- |
| `data/tasks.json` | 否 | 明文工作副本，仅本地/助手环境 |
| `data/tasks.cloud.json` | 是 | 加密后的云端数据，双端读取 |
| `data/holidays.json` | 是 | 中国法定节假日与调休（2025–2026） |
| `data/tasks.example.json` | 是 | 字段示例 |

字段：`category`=`life`/`work`，`date`，`time`，`remindAt`，`done`。
