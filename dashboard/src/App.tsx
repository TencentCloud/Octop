import { createGlobalStyle } from "antd-style";
import { ConfigProvider, theme as antdTheme } from "antd";
import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useTranslation } from "react-i18next";
import MainLayout from "./layouts/MainLayout";
import LoginPage from "./pages/Login";
import OidcComplete from "./pages/Login/OidcComplete";
import SetupPage from "./pages/Setup";
import InvitePage from "./pages/Invite";
import AuthGuard from "./components/AuthGuard";
import { AntdAppProvider } from "./components/AntdAppProvider";
import GlobalErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider, useTheme } from "./context/ThemeContext";
import { AgentProvider } from "./context/AgentContext";
import { LayoutModeProvider } from "./context/LayoutModeContext";
import { VoiceOutputProvider } from "./context/VoiceOutputContext";
import { useIsMobile } from "./hooks/useIsMobile";
import { useUnauthorizedRedirect } from "./hooks/useUnauthorizedRedirect";
import { brandTokensFor } from "./styles/themePalettes";
import "./styles/theme-vars.css";
import "./styles/layout.css";
import "./styles/form-override.css";

const GlobalStyle = createGlobalStyle`
* {
  margin: 0;
  box-sizing: border-box;
}
`;

function ThemedApp() {
  const { isDark, palette, customColor } = useTheme();
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const brandTokens = brandTokensFor(palette, isDark, customColor);

  useUnauthorizedRedirect();

  // Set document title based on current language
  useEffect(() => {
    document.title = t("app.pageTitle");
  }, [t]);

  const themeConfig = {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      borderRadius: 10,
      ...(isMobile
        ? {
            fontSize: 15,
            fontSizeSM: 13,
            fontSizeLG: 17,
            fontSizeXL: 22,
            controlHeight: 36,
          }
        : {}),
      ...(isDark
        ? {
            colorBgBase: "#0f1117",
            colorTextBase: "#e7e7ed",
            colorBgContainer: "#0f1117",
            colorBgElevated: "#1a1c28",
            colorBgLayout: "#0b0d14",
            colorBgSpotlight: "rgba(255, 255, 255, 0.08)",
            colorBgMask: "rgba(5, 5, 8, 0.80)",
            colorBorder: "rgba(255,255,255,0.08)",
            colorBorderSecondary: "rgba(255,255,255,0.05)",
            colorText: "rgba(255, 255, 255, 0.92)",
            colorTextSecondary: "rgba(255, 255, 255, 0.64)",
            colorTextTertiary: "rgba(255, 255, 255, 0.38)",
            colorTextQuaternary: "rgba(255, 255, 255, 0.22)",
            colorFill: "rgba(255, 255, 255, 0.06)",
            colorFillSecondary: "rgba(255, 255, 255, 0.04)",
            colorFillTertiary: "rgba(255, 255, 255, 0.03)",
            colorFillQuaternary: "rgba(255, 255, 255, 0.02)",
            colorBgTextHover: "rgba(255, 255, 255, 0.06)",
            ...brandTokens,
            boxShadow: "0px 4px 6px 0px rgba(0, 0, 0, 0.3)",
            boxShadowSecondary:
              "0px 12px 24px -16px rgba(0, 0, 0, 0.2), 0px 8px 40px 0px rgba(0, 0, 0, 0.3)",
          }
        : {
            ...brandTokens,
          }),
    },
    components: isDark
      ? {
          Modal: { headerBg: "#1a1c28", contentBg: "#1a1c28" },
          Input: { colorBgBase: "#0f1117" },
          InputNumber: { colorBgBase: "#0f1117" },
          Select: { colorBgBase: "#0f1117", selectorBg: "#0f1117" },
          DatePicker: { colorBgBase: "#0f1117" },
          Segmented: { itemSelectedBg: "#1a1c28" },
          Card: { colorBgContainer: "#161822" },
        }
      : {},
  };

  return (
    <ConfigProvider theme={themeConfig} prefixCls="octop">
      <AntdAppProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/login/oidc/complete" element={<OidcComplete />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/invite" element={<InvitePage />} />
          <Route
            path="/*"
            element={
              <AuthGuard>
                <AgentProvider>
                  <LayoutModeProvider>
                    <VoiceOutputProvider>
                      <MainLayout />
                    </VoiceOutputProvider>
                  </LayoutModeProvider>
                </AgentProvider>
              </AuthGuard>
            }
          />
        </Routes>
      </AntdAppProvider>
    </ConfigProvider>
  );
}

function App() {
  return (
    <BrowserRouter>
      <GlobalErrorBoundary>
        <GlobalStyle />
        <ThemeProvider>
          <ThemedApp />
        </ThemeProvider>
      </GlobalErrorBoundary>
    </BrowserRouter>
  );
}

export default App;
