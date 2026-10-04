export function workBuddyBrandTokens(isDark: boolean) {
  return {
    colorPrimary: isDark ? "#e6e6e6" : "#1f1f1f",
    colorPrimaryHover: isDark ? "#ffffff" : "#333333",
    colorPrimaryActive: isDark ? "#cccccc" : "#000000",
    colorPrimaryBg: isDark ? "#303030" : "#f2f2f2",
    colorPrimaryBorder: isDark ? "#606060" : "#d9d9d9",
    colorLink: isDark ? "#40d1b3" : "#009273",
  };
}
export function workBuddySurfaceTokens(
  isDark: boolean,
  isMobile: boolean,
  customAppearance = false,
) {
  return {
    borderRadius: 8,
    colorBgBase: isDark ? "#1f1f1f" : "#ffffff",
    colorBgContainer: isDark ? "#1f1f1f" : "#ffffff",
    colorBgElevated: isDark ? "#242424" : "#ffffff",
    colorBgLayout: isDark ? "#1f1f1f" : "#ffffff",
    colorTextBase: isDark ? "#ffffff" : "#000000",
    colorText: isDark ? "#ffffff" : "#1f1f1f",
    colorTextSecondary: isDark ? "#b3b3b3" : "#666666",
    colorTextTertiary: isDark ? "#808080" : "#999999",
    colorBorder: isDark ? "#363636" : "#e6e6e6",
    colorBorderSecondary: isDark ? "#2b2b2b" : "#eeeeee",
    colorBgMask: "rgba(0,0,0,0.35)",
    fontFamily:
      '"PingFang SC", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    colorTextLightSolid: !customAppearance && isDark ? "#1f1f1f" : "#ffffff",
    controlHeight: isMobile ? 40 : 32,
    fontSize: 14,
    boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
    boxShadowSecondary: "0 8px 32px rgba(0,0,0,0.12)",
  };
}
export function workBuddyDarkComponents() {
  return {
    Modal: { headerBg: "#242424", contentBg: "#242424" },
    Input: { colorBgBase: "#1f1f1f" },
    InputNumber: { colorBgBase: "#1f1f1f" },
    Select: { colorBgBase: "#1f1f1f", selectorBg: "#1f1f1f" },
    DatePicker: { colorBgBase: "#1f1f1f" },
    Segmented: { itemSelectedBg: "#303030" },
    Card: { colorBgContainer: "#242424" },
  };
}
