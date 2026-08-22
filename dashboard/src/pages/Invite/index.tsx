import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button, Form, Input, Steps, Typography } from "antd";
import { CheckCircle2, KeyRound, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { setAuthToken } from "../../api";
import { invitesApi } from "../../api/modules/invites";
import { message } from "@/utils/antdMessage";
import { apiErrorMessage } from "../../utils/apiError";
import { applyGuestLocale, applyUserLocale } from "../../utils/locale";
import { refreshServerLabels } from "../../i18n";
import { useTheme } from "../../context/ThemeContext";

const { Text, Title } = Typography;

type StepKey = 0 | 1 | 2;

export default function InvitePage() {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialCode = useMemo(() => {
    return (
      searchParams.get("code") ||
      searchParams.get("invite") ||
      ""
    ).trim();
  }, [searchParams]);

  const [step, setStep] = useState<StepKey>(0);
  const [code, setCode] = useState(initialCode);
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm<{
    username: string;
    password: string;
    display_name?: string;
  }>();

  useEffect(() => {
    void applyGuestLocale();
  }, []);

  useEffect(() => {
    if (initialCode) setCode(initialCode);
  }, [initialCode]);

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
  }) => {
    setSubmitting(true);
    try {
      const res = await invitesApi.redeem({
        code: code.trim(),
        username: values.username.trim(),
        password: values.password,
        display_name: values.display_name?.trim() || null,
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
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--fn-bg-layout)",
        transition: "background var(--fn-transition)",
        padding: 24,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 420,
          padding: "40px 32px 36px",
          borderRadius: 16,
          background: isDark ? "var(--fn-bg-container)" : "#fff",
          border: "1px solid var(--fn-border-primary)",
          boxShadow: isDark ? "none" : "0 8px 32px rgba(0,0,0,0.06)",
        }}
      >
        <Title level={3} style={{ marginTop: 0, marginBottom: 4 }}>
          {t("invite.title")}
        </Title>
        <Text type="secondary" style={{ display: "block", marginBottom: 24 }}>
          {t("invite.subtitle")}
        </Text>

        <Steps
          size="small"
          current={step}
          style={{ marginBottom: 28 }}
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
              <Input size="large" autoComplete="username" />
            </Form.Item>
            <Form.Item name="display_name" label={t("invite.displayName")}>
              <Input size="large" autoComplete="nickname" />
            </Form.Item>
            <Form.Item
              name="password"
              label={t("invite.password")}
              rules={[
                { required: true, message: t("invite.passwordRequired") },
                { min: 8, message: t("invite.passwordHint") },
              ]}
            >
              <Input.Password size="large" autoComplete="new-password" />
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
          <div style={{ textAlign: "center", padding: "12px 0" }}>
            <CheckCircle2
              size={40}
              style={{ color: "var(--fn-success, #52c41a)", marginBottom: 12 }}
            />
            <Title level={4} style={{ marginBottom: 8 }}>
              {t("invite.successTitle")}
            </Title>
            <Text type="secondary">{t("invite.successHint")}</Text>
          </div>
        ) : null}
      </div>
    </div>
  );
}
