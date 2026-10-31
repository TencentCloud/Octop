import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getRememberLoginPreference, setAuthToken } from "../../api";
import { authApi } from "../../api/modules/auth";
import { refreshServerLabels } from "../../i18n";
import { applyUserLocale } from "../../utils/locale";
import { safeRedirect } from "./OidcComplete";

/**
 * 读取外部免登交接参数。
 *
 * 安全约定：一次性登录码只从 hash 的 `code` 读取——hash 不会随请求发送到服务器，
 * 也不会进入访问日志。query 中的 `code` 一律忽略（不接受把凭证放进查询串）。
 * `redirect` 可先读 hash，再回退 query，最终仍由 `safeRedirect` 限制为站内路径。
 * URL 中不得出现 JWT（`access_token`）。
 */
export function readExternalCompleteParams(
  hash: string,
  search: string,
): { code: string | null; redirect: string | null } {
  const fromHash = new URLSearchParams(
    hash.startsWith("#") ? hash.slice(1) : hash,
  );
  const fromQuery = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );
  return {
    code: fromHash.get("code"),
    redirect: fromHash.get("redirect") || fromQuery.get("redirect"),
  };
}

/**
 * 外部系统免登交接页（不可见）。
 *
 * 业务系统只拿到短时一次性登录码，并跳转到本页 hash。本页用该码向
 * `POST /api/auth/oidc/exchange` 换取会话后写入登录态。JWT 不出现在 URL。
 * 这是唯一能在 Octop 同源下写登录态的环节，因此不渲染任何 DOM。
 */
export default function ExternalComplete() {
  const navigate = useNavigate();
  // 防止 effect 重复执行（React 18 StrictMode 下开发期会执行两次）
  const did = useRef(false);

  useEffect(() => {
    if (did.current) return;
    did.current = true;

    const { code, redirect } = readExternalCompleteParams(
      window.location.hash,
      window.location.search,
    );

    // 读取后立即清除地址栏的 hash/query：避免一次性码通过浏览器历史、截图或
    // 复制链接泄露（清空后即使回退也拿不到码）。
    if (window.location.hash || window.location.search) {
      window.history.replaceState(null, "", window.location.pathname);
    }

    if (!code) {
      // 缺少一次性码视为无效交接，回到登录页
      navigate("/login", { replace: true });
      return;
    }

    const dest = safeRedirect(redirect);
    void authApi
      .exchangeOidcCode(code)
      .then(async (res) => {
        // 沿用登录页“记住登录”偏好，决定写入 localStorage 还是 sessionStorage
        setAuthToken(res.access_token, getRememberLoginPreference());
        await applyUserLocale(res.user.locale);
        void refreshServerLabels(res.user.locale);
        navigate(dest, { replace: true });
      })
      .catch(() => {
        // 页面不可见：换码失败静默回到登录页，与缺少码的行为一致
        navigate("/login", { replace: true });
      });
  }, [navigate]);

  // 页面不可见：不渲染 Spin、文案或任何 DOM
  return null;
}
