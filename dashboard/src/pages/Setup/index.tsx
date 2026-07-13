import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Segmented, Steps, Typography } from "antd";
import { Lock, UserCog, Cpu, CheckCircle, Wand2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ensureLocaleBundle } from "../../i18n";
import { storeUiLocale, type UiLocale } from "../../utils/locale";

import { authApi } from "../../api/modules/auth";
import { preferencesApi } from "../../api/modules/preferences";
import { useTheme } from "../../context/ThemeContext";
import PasswordStep from "./steps/PasswordStep";
import AdminStep from "./steps/AdminStep";
import ModelStep from "./steps/ModelStep";
import FinishStep from "./steps/FinishStep";
import type { ProviderDraft } from "./wizardClient";
import {
  wizardApi,
  wizardSession,
  STEP_PASSWORD,
  STEP_ADMIN,
  STEP_MODEL,
  STEP_FINISH,
} from "./wizardClient";
import styles from "./setup.module.less";

const { Text } = Typography;

export default function SetupPage() {
  const { t, i18n } = useTranslation();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);
  const [passwordRequired, setPasswordRequired] = useState(true);
  const [current, setCurrentRaw] = useState<number>(STEP_PASSWORD);
  const [adminCreds, setAdminCreds] = useState<{
    username: string;
    password: string;
  } | null>(null);
  const [providerDraft, setProviderDraft] = useState<ProviderDraft | null>(
    null,
  );

  const goToStep = useCallback((step: number) => {
    setCurrentRaw(step);
    wizardSession.saveStep(step);
  }, []);

  useEffect(() => {
    let cancelled = false;
    authApi
      .getAuthStatus()
      .then(async (status) => {
        if (cancelled) return;
        if (!status.setup_required) {
          wizardSession.clearAll();
          navigate("/login", { replace: true });
          return;
        }

        setPasswordRequired(status.wizard_password_required);

        if (!status.wizard_password_required) {
          const token = wizardSession.loadToken();
          if (!token) {
            try {
              const r = await wizardApi.begin();
              if (cancelled) return;
              wizardSession.saveToken(r.wizard_token);
            } catch {
              if (!cancelled) setChecking(false);
              return;
            }
          }
          goToStep(STEP_ADMIN);
          setChecking(false);
          return;
        }

        const token = wizardSession.loadToken();
        if (!token) {
          wizardSession.clearAll();
          goToStep(STEP_PASSWORD);
          setChecking(false);
          return;
        }

        try {
          const { valid } = await wizardApi.validateToken(token);
          if (cancelled) return;
          if (!valid) {
            wizardSession.clearAll();
            goToStep(STEP_PASSWORD);
            return;
          }

          const savedStep = wizardSession.loadStep();
          const draft = wizardSession.loadDraft();
          if (draft.provider) {
            setProviderDraft(draft.provider);
          }

          if (
            savedStep !== null &&
            savedStep >= STEP_ADMIN &&
            savedStep <= STEP_MODEL
          ) {
            goToStep(savedStep);
          } else {
            goToStep(STEP_ADMIN);
          }
        } catch {
          if (!cancelled) {
            wizardSession.clearAll();
            goToStep(STEP_PASSWORD);
          }
        } finally {
          if (!cancelled) setChecking(false);
        }
      })
      .catch(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [navigate, goToStep]);

  const handleBackToPassword = () => {
    wizardSession.clearToken();
    wizardSession.saveDraft({});
    setAdminCreds(null);
    setProviderDraft(null);
    goToStep(STEP_PASSWORD);
  };

  if (checking) {
    return (
      <div
        style={{
          height: "100dvh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--fn-bg-layout)",
        }}
      >
        <Text type="secondary">Checking setup status…</Text>
      </div>
    );
  }

  const isModelStep = current === STEP_MODEL;
  const currentLang = i18n.language?.startsWith("zh") ? "zh" : "en";

  const handleLanguageChange = (lang: string) => {
    const locale: UiLocale = lang.startsWith("zh") ? "zh" : "en";
    storeUiLocale(locale);
    void ensureLocaleBundle(locale).then(() => i18n.changeLanguage(locale));
    // If admin already exists mid-wizard, persist the user's explicit choice.
    const setupJwt = wizardSession.loadSetupJwt();
    if (setupJwt) {
      void preferencesApi.setLocale(locale).catch(() => {
        /* best-effort; FinishStep login still applies stored UI locale via create */
      });
    }
  };

  const stepItems = passwordRequired
    ? [
        { title: t("wizard.steps.password"), icon: <Lock size={22} /> },
        { title: t("wizard.steps.admin"), icon: <UserCog size={22} /> },
        { title: t("wizard.steps.model"), icon: <Cpu size={22} /> },
        { title: t("common.done"), icon: <CheckCircle size={22} /> },
      ]
    : [
        { title: t("wizard.steps.admin"), icon: <UserCog size={22} /> },
        { title: t("wizard.steps.model"), icon: <Cpu size={22} /> },
        { title: t("common.done"), icon: <CheckCircle size={22} /> },
      ];

  const stepIndex = passwordRequired
    ? current
    : Math.max(0, current - STEP_ADMIN);

  return (
    <div className={styles.wizardShell}>
      <div
        className={`${styles.wizardCard} ${
          isModelStep ? styles.wizardCardWide : styles.wizardCardNarrow
        }`}
      >
        {/* Header bar */}
        <div className={styles.wizardHeader}>
          <div className={styles.wizardHeaderTop}>
            <div className={styles.wizardHeaderBrand}>
              <img
                src={isDark ? "/logo_name_dark.png" : "/logo_name.png"}
                alt="Octop"
                className={styles.wizardHeaderLogo}
              />
              <div className={styles.wizardHeaderBrandText}>
                <Text type="secondary" className={styles.wizardHeaderSubtitle}>
                  <Wand2 size={11} /> {t("wizard.title")}
                </Text>
              </div>
            </div>
            <Segmented
              className={styles.wizardHeaderLang}
              size="small"
              value={currentLang}
              options={[
                { label: t("account.langZh"), value: "zh" },
                { label: t("account.langEn"), value: "en" },
              ]}
              onChange={handleLanguageChange}
            />
          </div>
          <Steps
            className={styles.wizardHeaderSteps}
            current={stepIndex}
            labelPlacement="vertical"
            responsive={false}
            items={stepItems}
          />
        </div>

        {/* Step content */}
        <div
          className={`${styles.wizardBody} ${
            isModelStep ? styles.wizardBodyFlush : ""
          }`}
        >
          {current === STEP_PASSWORD && passwordRequired && (
            <PasswordStep onVerified={() => goToStep(STEP_ADMIN)} />
          )}
          {current === STEP_ADMIN && (
            <AdminStep
              createdCreds={adminCreds}
              onBack={passwordRequired ? handleBackToPassword : undefined}
              onCreated={(creds) => {
                setAdminCreds(creds);
                wizardSession.saveDraft({ adminUsername: creds.username });
                goToStep(STEP_MODEL);
              }}
            />
          )}
          {current === STEP_MODEL && (
            <ModelStep
              onBack={() => goToStep(STEP_ADMIN)}
              onSkip={() => {
                setProviderDraft(null);
                wizardSession.saveDraft({});
                goToStep(STEP_FINISH);
              }}
              onContinue={(draft) => {
                setProviderDraft(draft);
                goToStep(STEP_FINISH);
              }}
            />
          )}
          {current === STEP_FINISH && adminCreds && (
            <FinishStep adminCreds={adminCreds} providerDraft={providerDraft} />
          )}
        </div>
      </div>
    </div>
  );
}
