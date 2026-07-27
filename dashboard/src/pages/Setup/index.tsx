import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Segmented, Steps, Typography } from "antd";
import { Lock, UserCog, Cpu, CheckCircle, Wand2, Database } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ensureLocaleBundle } from "../../i18n";
import { storeUiLocale, type UiLocale } from "../../utils/locale";

import { authApi } from "../../api/modules/auth";
import { preferencesApi } from "../../api/modules/preferences";
import { useTheme } from "../../context/ThemeContext";
import DatabaseStep from "./steps/DatabaseStep";
import PasswordStep from "./steps/PasswordStep";
import AdminStep from "./steps/AdminStep";
import ModelStep from "./steps/ModelStep";
import FinishStep from "./steps/FinishStep";
import type { ProviderDraft } from "./wizardClient";
import {
  wizardApi,
  wizardSession,
  STEP_DATABASE,
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

  const ensureWizardToken = useCallback(async () => {
    const token = wizardSession.loadToken();
    if (token) {
      try {
        const { valid } = await wizardApi.validateToken(token);
        if (valid) return token;
      } catch {
        /* fall through */
      }
    }
    const r = await wizardApi.begin();
    wizardSession.saveToken(r.wizard_token);
    return r.wizard_token;
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

        const savedStep = wizardSession.loadStep();
        const draft = wizardSession.loadDraft();
        if (draft.provider) {
          setProviderDraft(draft.provider);
        }

        const token = wizardSession.loadToken();
        if (token) {
          try {
            const { valid } = await wizardApi.validateToken(token);
            if (cancelled) return;
            if (valid) {
              if (
                savedStep !== null &&
                savedStep >= STEP_DATABASE &&
                savedStep <= STEP_MODEL
              ) {
                if (savedStep === STEP_DATABASE && status.database_bound) {
                  goToStep(STEP_ADMIN);
                } else {
                  goToStep(savedStep);
                }
              } else if (
                savedStep === STEP_PASSWORD &&
                status.wizard_password_required
              ) {
                goToStep(STEP_PASSWORD);
              } else {
                goToStep(status.database_bound ? STEP_ADMIN : STEP_DATABASE);
              }
              setChecking(false);
              return;
            }
          } catch {
            /* fall through */
          }
        }

        // No valid wizard token yet.
        if (status.wizard_password_required) {
          goToStep(STEP_PASSWORD);
        } else {
          try {
            await ensureWizardToken();
          } catch {
            /* continue into database step; begin can be retried */
          }
          if (!cancelled) goToStep(STEP_DATABASE);
        }
        if (!cancelled) setChecking(false);
      })
      .catch(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [navigate, goToStep, ensureWizardToken]);

  const handlePasswordVerified = () => {
    goToStep(STEP_DATABASE);
  };

  const handleDatabaseContinue = async () => {
    try {
      await ensureWizardToken();
    } catch {
      /* token may already exist after password step */
    }
    goToStep(STEP_ADMIN);
  };

  const handleBackFromAdmin = () => {
    setAdminCreds(null);
    setProviderDraft(null);
    wizardSession.saveDraft({});
    goToStep(STEP_DATABASE);
  };

  const handleBackFromDatabase = () => {
    if (!passwordRequired) return;
    wizardSession.clearToken();
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
    const setupJwt = wizardSession.loadSetupJwt();
    if (setupJwt) {
      void preferencesApi.setLocale(locale).catch(() => {
        /* best-effort */
      });
    }
  };

  const stepItems = passwordRequired
    ? [
        { title: t("wizard.steps.password"), icon: <Lock size={22} /> },
        { title: t("wizard.steps.database"), icon: <Database size={22} /> },
        { title: t("wizard.steps.admin"), icon: <UserCog size={22} /> },
        { title: t("wizard.steps.model"), icon: <Cpu size={22} /> },
        { title: t("common.done"), icon: <CheckCircle size={22} /> },
      ]
    : [
        { title: t("wizard.steps.database"), icon: <Database size={22} /> },
        { title: t("wizard.steps.admin"), icon: <UserCog size={22} /> },
        { title: t("wizard.steps.model"), icon: <Cpu size={22} /> },
        { title: t("common.done"), icon: <CheckCircle size={22} /> },
      ];

  const stepIndex = (() => {
    if (passwordRequired) return current;
    // Password step omitted visually: map DATABASE..FINISH → 0..3
    if (current <= STEP_DATABASE) return 0;
    if (current === STEP_ADMIN) return 1;
    if (current === STEP_MODEL) return 2;
    return 3;
  })();

  return (
    <div className={styles.wizardShell}>
      <div
        className={`${styles.wizardCard} ${
          isModelStep ? styles.wizardCardWide : styles.wizardCardNarrow
        }`}
      >
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

        <div
          className={`${styles.wizardBody} ${
            isModelStep ? styles.wizardBodyFlush : ""
          }`}
        >
          {current === STEP_PASSWORD && passwordRequired && (
            <PasswordStep onVerified={handlePasswordVerified} />
          )}
          {current === STEP_DATABASE && (
            <DatabaseStep
              onContinue={() => void handleDatabaseContinue()}
              onBack={passwordRequired ? handleBackFromDatabase : undefined}
            />
          )}
          {current === STEP_ADMIN && (
            <AdminStep
              createdCreds={adminCreds}
              onBack={handleBackFromAdmin}
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
