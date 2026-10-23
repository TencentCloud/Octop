import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getRememberLoginPreference, setAuthToken } from "../../api";
import { safeRedirect } from "./OidcComplete";

/**
 * 读取外部免登交接参数。
 *
 * 安全约定：token 只从 hash 读取——hash 不会随请求发送到服务器，也不会进入访问日志；
 * query 仅作为旧链接的兼容回退（与 OidcComplete 的既有约定一致）。
 */
export function readExternalCompleteParams(
  hash: string,
  search: string,
): { accessToken: string | null; redirect: string | null } {
  const fromHash = new URLSearchParams(
    hash.startsWith("#") ? hash.slice(1) : hash,
  );
  const fromQuery = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );
  return {
    // 参数名沿用后端换票响应的 snake_case 字段名
    accessToken: fromHash.get("access_token") || fromQuery.get("access_token"),
    redirect: fromHash.get("redirect") || fromQuery.get("redirect"),
  };
}

/**
 * 外部系统免登交接页（不可见）。
 *
 * 把业务系统通过服务端换票得到的 access_token 写入本机登录态，然后跳转到目标路由。
 * 这是唯一能在 Octop 同源下写登录态的环节，因此不渲染任何 DOM：无论正常路径还是
 * 跳转前的加载态都返回 null。
 */
export default function ExternalComplete() {
  const navigate = useNavigate();
  // 防止 effect 重复执行（React 18 StrictMode 下开发期会执行两次）
  const did = useRef(false);

  useEffect(() => {
    if (did.current) return;
    did.current = true;

    const { accessToken, redirect } = readExternalCompleteParams(
      window.location.hash,
      window.location.search,
    );

    // 读取后立即清除地址栏的 hash/query：避免 token 通过浏览器历史、截图或
    // 复制链接泄露（清空后即使回退也拿不到 token）。
    if (window.location.hash || window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }

    if (!accessToken) {
      // 缺少 token 视为无效交接，回到登录页
      navigate("/login", { replace: true });
      return;
    }

    // 沿用登录页“记住登录”偏好，决定写入 localStorage 还是 sessionStorage
    setAuthToken(accessToken, getRememberLoginPreference());

    // 此处拿不到 user 对象，故不做 applyUserLocale / refreshServerLabels。
    // redirect 只允许站内路径，默认值由 safeRedirect 负责兜底（/chat）。
    navigate(safeRedirect(redirect), { replace: true });
  }, [navigate]);

  // 页面不可见：不渲染 Spin、文案或任何 DOM
  return null;
}
