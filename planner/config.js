// 公开配置（不含口令）。口令只保存在各设备浏览器里，由你本地输入。
export const PLANNER_CONFIG = {
  // cloud：从加密云端文件读取（双端共享，不依赖电脑开机）
  mode: "cloud",
  cloudUrl: "./data/tasks.cloud.json",
  // 推送提醒主题只作展示；真实主题在解锁后由本地配置或对话同步
  appName: "日次",
};
