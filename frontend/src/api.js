export async function request(path, params = {}, signal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== "" && value !== null && value !== undefined)
      query.set(key, String(value));
  }
  const response = await fetch(
    `/api/v1/${path}${query.size ? `?${query}` : ""}`,
    { signal },
  );
  let data;
  try {
    data = await response.json();
  } catch (error) {
    if (error.name === "AbortError") throw error;
    const unavailable = new Error("无法连接游戏资料库，请确认后端服务正在运行。");
    unavailable.status = response.status;
    throw unavailable;
  }
  if (!response.ok) {
    const message = data.detail?.message;
    const failure = new Error(
      message ||
        (response.status === 422
          ? "筛选参数无效，请检查评分或评分人数。"
          : "游戏资料加载失败，请稍后重试。"),
    );
    failure.status = response.status;
    throw failure;
  }
  return data;
}

export function score(value) {
  return typeof value === "number" ? value.toFixed(1) : "暂无评分";
}

export function displayCover(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "images.igdb.com")
      return url.replace("/t_thumb/", "/t_cover_big_2x/");
  } catch {
    return null;
  }
  return url;
}
