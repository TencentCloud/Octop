import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Form, Input, Segmented, Steps, Typography } from "antd";
import {
  CheckCircle2,
  IdCard,
  KeyRound,
  Lock,
  Mail,
  User,
  UserPlus,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { setAuthToken } from "../../api";
import { invitesApi } from "../../api/modules/invites";
import { message } from "@/utils/antdMessage";
import { apiErrorMessage } from "../../utils/apiError";
import {
  applyGuestLocale,
  applyUserLocale,
  storeUiLocale,
  type UiLocale,
} from "../../utils/locale";
import {
  MIN_PASSWORD_LENGTH,
  passwordPolicyIssue,
} from "../../utils/passwordPolicy";
import { ensureLocaleBundle, refreshServerLabels } from "../../i18n";
import { useTheme } from "../../context/ThemeContext";
import styles from "./invite.module.less";

const { Text, Title } = Typography;

type StepKey = 0 | 1 | 2;

export default function InvitePage() {
  const { t, i18n } = useTranslation();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialCode = useMemo(() => {
    return (searchParams.get("code") || "").trim();
  }, [searchParams]);

  const [step, setStep] = useState<StepKey>(0);
  const [code, setCode] = useState(initialCode);
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<{
    username: string;
    password: string;
    confirm: string;
    display_name?: string;
    email?: string;
  }>();

  const passwordPolicyMessage = (
    issue: ReturnType<typeof passwordPolicyIssue>,
  ) => {
    switch (issue) {
      case "too_short":
        return t("account.passwordTooShort", { min: MIN_PASSWORD_LENGTH });
      case "need_letter_and_digit":
        return t("account.passwordNeedLetterAndDigit");
      case "too_common":
        return t("account.passwordTooCommon");
      default:
        return t("account.passwordTooWeak");
    }
  };

  useEffect(() => {
    void applyGuestLocale();
  }, []);

  useEffect(() => {
    if (initialCode) setCode(initialCode);
  }, [initialCode]);

  const currentLang = i18n.language?.startsWith("zh") ? "zh" : "en";

  const handleLanguageChange = (lang: string) => {
    const locale: UiLocale = lang.startsWith("zh") ? "zh" : "en";
    storeUiLocale(locale);
    void ensureLocaleBundle(locale).then(() => i18n.changeLanguage(locale));
  };

  const onValidate = async () => {
    const trimmed = code.trim();
    if (!trimmed) {
      message.error(t("invite.codeRequired"));
      return;
    }
    setValidating(true);
    try {
      await invitesApi.validate(trimmed);
      setCode(trimmed);
      setStep(1);
    } catch (err) {
      message.error(apiErrorMessage(err, t("invite.validateFailed"), t));
    } finally {
      setValidating(false);
    }
  };

  const onCreate = async (values: {
    username: string;
    password: string;
    display_name?: string;
    email?: string;
  }) => {
    setSubmitting(true);
    try {
      const res = await invitesApi.redeem({
        code: code.trim(),
        username: values.username.trim(),
        password: values.password,
        display_name: values.display_name?.trim() || null,
        email: values.email?.trim() || null,
      });
      setAuthToken(res.access_token);
      await applyUserLocale(res.user.locale);
      void refreshServerLabels(res.user.locale);
      setStep(2);
      window.setTimeout(() => {
        navigate("/chat", { replace: true });
      }, 800);
    } catch (err) {
      message.error(apiErrorMessage(err, t("invite.createFailed"), t));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.inviteShell}>
      <div className={styles.inviteShellInner}>
        <div
          className={[styles.inviteCard, isDark ? styles.inviteCardDark : ""]
            .filter(Boolean)
            .join(" ")}
        >
          <div className={styles.inviteHeader}>
            <Title level={3} className={styles.inviteTitle}>
              {t("invite.title")}
            </Title>
            <Segmented
              className={styles.inviteLang}
              size="small"
              value={currentLang}
              options={[
                { label: t("account.langZh"), value: "zh" },
                { label: t("account.langEn"), value: "en" },
              ]}
              onChange={handleLanguageChange}
            />
          </div>
          <Text type="secondary" className={styles.inviteSubtitle}>
            {t("invite.subtitle")}
          </Text>

          <Steps
            size="small"
            current={step}
            className={styles.inviteSteps}
            items={[
              { title: t("invite.stepCode"), icon: <KeyRound size={14} /> },
              { title: t("invite.stepAccount"), icon: <UserPlus size={14} /> },
              { title: t("invite.stepDone"), icon: <CheckCircle2 size={14} /> },
            ]}
          />

          {step === 0 ? (
            <div>
              <Text style={{ display: "block", marginBottom: 8 }}>
                {t("invite.codeLabel")}
              </Text>
              <Input
                size="large"
                prefix={<KeyRound size={16} />}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onPressEnter={() => void onValidate()}
                placeholder={t("invite.codePlaceholder")}
                style={{ marginBottom: 16 }}
              />
              <Button
                type="primary"
                size="large"
                block
                loading={validating}
                onClick={() => void onValidate()}
              >
                {t("invite.continue")}
              </Button>
              <Button
                type="link"
                block
                style={{ marginTop: 8 }}
                onClick={() => navigate("/login", { replace: true })}
              >
                {t("invite.backToLogin")}
              </Button>
            </div>
          ) : null}

          {step === 1 ? (
            <Form
              form={form}
              layout="vertical"
              requiredMark={false}
              onFinish={(v) => void onCreate(v)}
            >
              <Form.Item
                name="username"
                label={t("invite.username")}
                rules={[
                  { required: true, message: t("invite.usernameRequired") },
                ]}
              >
                <Input
                  size="large"
                  prefix={<User size={16} />}
                  autoComplete="username"
                />
              </Form.Item>
              <Form.Item
                name="email"
                label={t("invite.email")}
                rules={[{ type: "email", message: t("invite.emailInvalid") }]}
              >
                <Input
                  size="large"
                  prefix={<Mail size={16} />}
                  type="email"
                  autoComplete="email"
                />
              </Form.Item>
              <Form.Item name="display_name" label={t("invite.displayName")}>
                <Input
                  size="large"
                  prefix={<IdCard size={16} />}
                  autoComplete="nickname"
                />
              </Form.Item>
              <Form.Item
                name="password"
                label={t("invite.password")}
                extra={t("invite.passwordHint")}
                rules={[
                  { required: true, message: t("invite.passwordRequired") },
                  {
                    validator(_, value: string) {
                      if (!value) return Promise.resolve();
                      const issue = passwordPolicyIssue(value);
                      if (issue) {
                        return Promise.reject(
                          new Error(passwordPolicyMessage(issue)),
                        );
                      }
                      return Promise.resolve();
                    },
                  },
                ]}
              >
                <Input.Password
                  size="large"
                  prefix={<Lock size={16} />}
                  autoComplete="new-password"
                />
              </Form.Item>
              <Form.Item
                name="confirm"
                label={t("invite.passwordConfirm")}
                dependencies={["password"]}
                rules={[
                  {
                    required: true,
                    message: t("invite.passwordConfirmRequired"),
                  },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue("password") === value) {
                        return Promise.resolve();
                      }
                      return Promise.reject(
                        new Error(t("invite.passwordMismatch")),
                      );
                    },
                  }),
                ]}
              >
                <Input.Password
                  size="large"
                  prefix={<Lock size={16} />}
                  autoComplete="new-password"
                />
              </Form.Item>
              <Button
                type="primary"
                size="large"
                htmlType="submit"
                block
                loading={submitting}
              >
                {t("invite.createAccount")}
              </Button>
              <Button
                type="link"
                block
                style={{ marginTop: 8 }}
                onClick={() => setStep(0)}
              >
                {t("invite.back")}
              </Button>
            </Form>
          ) : null}

          {step === 2 ? (
            <div className={styles.inviteSuccess}>
              <CheckCircle2
                size={40}
                style={{
                  color: "var(--fn-success, #52c41a)",
                  marginBottom: 12,
                }}
              />
              <Title level={4} style={{ marginBottom: 8 }}>
                {t("invite.successTitle")}
              </Title>
              <Text type="secondary">{t("invite.successHint")}</Text>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
