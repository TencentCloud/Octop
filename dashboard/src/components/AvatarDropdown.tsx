import { useState, useCallback } from "react";
import {
  Avatar,
  Drawer,
  Form,
  Input,
  Button,
  Tag,
  Space,
  message,
  Typography,
  Divider,
  Segmented,
  Tooltip,
} from "antd";
import { LogOut, ChevronDown } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { authApi } from "../api/modules/auth";
import { preferencesApi } from "../api/modules/preferences";
import { clearAuthToken } from "../api/request";
import { applyGuestLocale } from "../utils/locale";
import { useUserRole } from "../hooks/useUserRole";
import { applyUserLocale } from "../utils/locale";
import type { OctopUser } from "../api/modules/auth";

const { Text } = Typography;

interface AvatarDropdownProps {
  user: OctopUser | null;
  onUserChange?: (u: OctopUser) => void;
  /**
   * ``sidebar`` — brand-rail footer trigger (avatar [+ name when expanded]).
   * Default keeps a plain avatar button (legacy header style).
   */
  placement?: "default" | "sidebar";
  /** When placement is sidebar and true, show avatar only (collapsed rail). */
  compact?: boolean;
}

export default function AvatarDropdown({
  user,
  onUserChange,
  placement = "default",
  compact = false,
}: AvatarDropdownProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const role = useUserRole();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [changingPw, setChangingPw] = useState(false);
  const [profileForm] = Form.useForm<{ display_name: string }>();
  const [pwForm] = Form.useForm<{
    old_password: string;
    new_password: string;
    confirm: string;
  }>();

  const handleLogout = useCallback(async () => {
    await authApi.logout();
    clearAuthToken();
    await applyGuestLocale();
    navigate("/login", { replace: true });
  }, [navigate]);

  const handleSaveProfile = async (values: { display_name: string }) => {
    setSaving(true);
    try {
      const updated = await authApi.updateProfile(
        values.display_name?.trim() || null,
      );
      onUserChange?.(updated);
      message.success(t("account.savedSuccess"));
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleChangePw = async (values: {
    old_password: string;
    new_password: string;
    confirm: string;
  }) => {
    if (values.new_password !== values.confirm) {
      message.error(t("account.passwordMismatch"));
      return;
    }
    setChangingPw(true);
    try {
      await authApi.changePassword(values.old_password, values.new_password);
      message.success(t("account.passwordChanged"));
      pwForm.resetFields();
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setChangingPw(false);
    }
  };

  const currentLang = i18n.language?.startsWith("zh") ? "zh" : "en";
  const roleLabel =
    role === "admin" ? t("account.roleAdmin") : t("account.roleUser");

  const displayName = user?.display_name || user?.username || "—";
  const initials = (user?.display_name || user?.username || "?")
    .charAt(0)
    .toUpperCase();

  const avatar = (
    <Avatar
      size={32}
      style={{
        background: "var(--fn-color-brand, #4f6ef7)",
        fontSize: 14,
        userSelect: "none",
        flexShrink: 0,
      }}
    >
      {initials}
    </Avatar>
  );

  const trigger =
    placement === "sidebar" && !compact ? (
      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          width: "100%",
          border: "none",
          background: "transparent",
          padding: "8px 10px",
          borderRadius: "var(--fn-radius-md)",
          cursor: "pointer",
          textAlign: "left",
          color: "var(--fn-text-primary)",
          transition: "background var(--fn-transition-fast)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "var(--fn-sidebar-item-hover)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "transparent";
        }}
      >
        {avatar}
        <span
          style={{
            flex: 1,
            minWidth: 0,
            fontSize: 13,
            fontWeight: 600,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {displayName}
        </span>
        <ChevronDown
          size={14}
          strokeWidth={1.8}
          style={{ flexShrink: 0, color: "var(--fn-text-tertiary)" }}
        />
      </button>
    ) : (
      <Tooltip
        title={placement === "sidebar" ? displayName : undefined}
        placement="right"
        mouseEnterDelay={0.3}
      >
        <span
          role="button"
          tabIndex={0}
          onClick={() => setDrawerOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setDrawerOpen(true);
            }
          }}
          style={{ cursor: "pointer", display: "inline-flex" }}
        >
          {avatar}
        </span>
      </Tooltip>
    );

  return (
    <>
      {trigger}

      <Drawer
        title={t("account.myAccount")}
        placement="left"
        width={400}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        footer={
          <Button
            danger
            block
            icon={<LogOut size={14} />}
            onClick={() => void handleLogout()}
          >
            {t("auth.logout")}
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: "100%" }} size="large">
          {/* Identity summary */}
          <div>
            <div style={{ fontWeight: 600, fontSize: 15 }}>{displayName}</div>
            {user?.username && (
              <Text type="secondary" style={{ fontSize: 13 }}>
                @{user.username}
              </Text>
            )}
          </div>

          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("account.username")}
            </Text>
            <Input
              value={user?.username || ""}
              disabled
              style={{ marginTop: 4 }}
            />
          </div>

          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("account.role")}
            </Text>
            <div style={{ marginTop: 4 }}>
              <Tag color={role === "admin" ? "blue" : "default"}>
                {roleLabel}
              </Tag>
            </div>
          </div>

          <Form
            form={profileForm}
            onFinish={handleSaveProfile}
            layout="vertical"
            initialValues={{ display_name: user?.display_name || "" }}
          >
            <Form.Item name="display_name" label={t("account.displayName")}>
              <Input placeholder={t("account.displayNamePlaceholder")} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={saving}>
              {t("common.save")}
            </Button>
          </Form>

          <Divider style={{ margin: 0 }} />

          <div>
            <Text strong style={{ display: "block", marginBottom: 8 }}>
              {t("language.title")}
            </Text>
            <Text
              type="secondary"
              style={{ fontSize: 12, display: "block", marginBottom: 10 }}
            >
              {t("language.description")}
            </Text>
            <Segmented
              block
              value={currentLang}
              options={[
                { label: t("account.langZh"), value: "zh" },
                { label: t("account.langEn"), value: "en" },
              ]}
              onChange={(val) => {
                void preferencesApi
                  .setLocale(val as string)
                  .then(async (prefs) => {
                    await applyUserLocale(prefs.locale);
                    onUserChange?.({ ...user!, locale: prefs.locale });
                  })
                  .catch((e) => {
                    message.error(e instanceof Error ? e.message : String(e));
                  });
              }}
            />
          </div>

          <Divider style={{ margin: 0 }} />

          <Form form={pwForm} onFinish={handleChangePw} layout="vertical">
            <Text strong style={{ display: "block", marginBottom: 12 }}>
              {t("account.changePassword")}
            </Text>
            <Form.Item
              name="old_password"
              label={t("account.currentPassword")}
              rules={[
                {
                  required: true,
                  message: t("account.currentPasswordRequired"),
                },
              ]}
            >
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Form.Item
              name="new_password"
              label={t("account.newPassword")}
              rules={[
                { required: true, message: t("account.newPasswordRequired") },
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Form.Item
              name="confirm"
              label={t("account.confirmPassword")}
              rules={[
                {
                  required: true,
                  message: t("account.confirmPasswordRequired"),
                },
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Button htmlType="submit" loading={changingPw}>
              {t("account.changePassword")}
            </Button>
          </Form>
        </Space>
      </Drawer>
    </>
  );
}
