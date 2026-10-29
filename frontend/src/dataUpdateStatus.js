export const busyUpdateStates = new Set(["checking", "downloading", "installing"]);

export function updateStatusLabel(state = {}) {
  return {
    loading: "准备中", disabled: "未启用", idle: "待检查",
    checking: "检查中", downloading: "下载中", installing: "更新中",
    updated: "已同步", up_to_date: "已同步", no_release: "暂无更新",
    configuration_error: "待配置", failed: "暂未同步",
  }[state.status] || "状态未知";
}

export function updateStatusTone(state = {}) {
  if (["failed", "configuration_error"].includes(state.status)) return "warning";
  if (busyUpdateStates.has(state.status) || state.status === "loading") return "busy";
  if (["updated", "up_to_date"].includes(state.status)) return "synced";
  return "muted";
}

export function updateStatusText(state = {}) {
  const messages = {
    loading: "正在读取更新状态",
    disabled: "自动更新未启用",
    idle: "启动后自动检查更新",
    checking: "正在检查数据更新",
    downloading: "正在下载更新包",
    installing: "正在备份并更新资料",
    updated: "游戏资料已更新",
    up_to_date: "游戏资料已是最新",
    no_release: "暂时没有可用更新",
    configuration_error: "更新配置需要检查",
    failed: "更新暂未完成",
  };
  return messages[state.status] || "更新状态暂不可用";
}

export function shouldRefreshCatalog(previous, next) {
  return previous !== undefined && next != null && previous !== next;
}
