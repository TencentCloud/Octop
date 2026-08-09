import { useState, useCallback } from "react";
import {
  Avatar,
  Modal,
  Drawer,
  Form,
  Input,
  Button,
  Tag,
  Divider,
  Segmented,
  Tooltip,
  Popover,
} from "antd";
import { message } from "@/utils/antdMessage";

import {
  LogOut,
  ChevronDown,
  ChevronUp,
  Settings,
  Palette,
  CircleHelp,
  Github,
  RefreshCw,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { authApi } from "../api/modules/auth";
import { preferencesApi } from "../api/modules/preferences";
import { clearAuthToken } from "../api/request";
import { applyGuestLocale, applyUserLocale } from "../utils/locale";
import { useUserRole } from "../hooks/useUserRole";
import { useIsMobile } from "../hooks/useIsMobile";
import ThemeSwitcher from "./ThemeSwitcher";
import PaletteSwitcher from "./PaletteSwitcher";
import type { OctopUser } from "../api/modules/auth";
import styles from "./AvatarDropdown.module.less";

const GITHUB_URL = "https://github.com/TencentCloud/Octop";

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
  /** Called before opening personal settings (e.g. close mobile nav drawer). */
  onBeforeOpenSettings?: () => void;
}

export default function AvatarDropdown({
  user,
  onUserChange,
  placement = "default",
  compact = false,
  onBeforeOpenSettings,
}: AvatarDropdownProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const role = useUserRole();
  const isMobile = useIsMobile();
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [changingPw, setChangingPw] = useState(false);
  const [profileForm] = Form.useForm<{ display_name: string }>();
  const [pwForm] = Form.useForm<{
    old_password: string;
    new_password: string;
    confirm: string;
  }>();

  const handleLogout = useCallback(async () => {
    setMenuOpen(false);
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

  const handleLocaleChange = (val: string) => {
    void preferencesApi
      .setLocale(val)
      .then(async (prefs) => {
        await applyUserLocale(prefs.locale);
        if (user) onUserChange?.({ ...user, locale: prefs.locale });
      })
      .catch((e) => {
        message.error(e instanceof Error ? e.message : String(e));
      });
  };

  const currentLang = i18n.language?.startsWith("zh") ? "zh" : "en";
  const roleLabel =
    role === "admin" ? t("account.roleAdmin") : t("account.roleUser");

  const displayName = user?.display_name || user?.username || "—";
  const initials = (user?.display_name || user?.username || "?")
    .charAt(0)
    .toUpperCase();

  const openSettings = () => {
    setMenuOpen(false);
    onBeforeOpenSettings?.();
    profileForm.setFieldsValue({ display_name: user?.display_name || "" });
    pwForm.resetFields();
    // Defer open so the account Popover / mobile sidebar can unmount first
    // and avoid touch "ghost click" closing the settings panel immediately.
    window.setTimeout(() => setSettingsOpen(true), 0);
  };

  const closeSettings = () => setSettingsOpen(false);

  const avatar = (
    <Avatar
      size={32}
      style={{
        background: "var(--fn-color-brand)",
        fontSize: 14,
        userSelect: "none",
        flexShrink: 0,
      }}
    >
      {initials}
    </Avatar>
  );

  const menuContent = (
    <div className={styles.menu}>
      <div className={styles.menuHeader}>
        <div className={styles.menuHeaderTop}>
          <span className={styles.menuDisplayName}>{displayName}</span>
          <Tag
            color={role === "admin" ? "blue" : "default"}
            className={styles.roleTag}
          >
            {roleLabel}
          </Tag>
        </div>
        {user?.username && (
          <span className={styles.menuHandle}>@{user.username}</span>
        )}
      </div>

      <Divider className={styles.menuDivider} />

      <div className={styles.menuItemRow}>
        <div className={styles.menuItemLabel}>
          <Palette size={16} strokeWidth={1.8} />
          <span>{t("account.appearance")}</span>
        </div>
        <ThemeSwitcher compact />
      </div>

      <button
        type="button"
        className={styles.menuItem}
        onClick={() => {
          setMenuOpen(false);
          message.info(t("account.helpBuilding"));
        }}
      >
        <CircleHelp size={16} strokeWidth={1.8} />
        <span>{t("account.helpFeedback")}</span>
      </button>

      <a
        className={styles.menuItem}
        href={GITHUB_URL}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => setMenuOpen(false)}
      >
        <Github size={16} strokeWidth={1.8} />
        <span>{t("account.projectUrl")}</span>
      </a>

      <button type="button" className={styles.menuItem} onClick={openSettings}>
        <Settings size={16} strokeWidth={1.8} />
        <span>{t("account.settings")}</span>
      </button>

      <button
        type="button"
        className={styles.menuItem}
        onClick={() => {
          setMenuOpen(false);
          navigate("/admin/advanced?tab=updates");
        }}
      >
        <RefreshCw size={16} strokeWidth={1.8} />
        <span>{t("account.checkUpdates")}</span>
      </button>

      <Divider className={styles.menuDivider} />

      <button
        type="button"
        className={`${styles.menuItem} ${styles.menuItemDanger}`}
        onClick={() => void handleLogout()}
      >
        <LogOut size={16} strokeWidth={1.8} />
        <span>{t("auth.logout")}</span>
      </button>
    </div>
  );

  const triggerButton =
    placement === "sidebar" && !compact ? (
      <button
        type="button"
        className={styles.triggerExpanded}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "var(--fn-sidebar-item-hover)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "transparent";
        }}
      >
        {avatar}
        <span className={styles.triggerName}>{displayName}</span>
        {menuOpen ? (
          <ChevronUp
            size={14}
            strokeWidth={1.8}
            className={styles.triggerChevron}
          />
        ) : (
          <ChevronDown
            size={14}
            strokeWidth={1.8}
            className={styles.triggerChevron}
          />
        )}
      </button>
    ) : (
      <Tooltip
        title={placement === "sidebar" ? displayName : undefined}
        placement="right"
        mouseEnterDelay={0.3}
      >
        <span role="button" tabIndex={0} className={styles.triggerCompact}>
          {avatar}
        </span>
      </Tooltip>
    );

  const settingsBody = (
    <div className={styles.settingsBody}>
      <div className={styles.settingsIdentity}>
        <Avatar
          size={44}
          style={{
            background: "var(--fn-color-brand)",
            fontSize: 18,
            flexShrink: 0,
          }}
        >
          {initials}
        </Avatar>
        <div className={styles.settingsIdentityText}>
          <div className={styles.settingsIdentityName}>
            <span>{displayName}</span>
            <Tag
              color={role === "admin" ? "blue" : "default"}
              className={styles.roleTag}
            >
              {roleLabel}
            </Tag>
          </div>
          {user?.username && (
            <span className={styles.settingsIdentityHandle}>
              @{user.username}
            </span>
          )}
        </div>
      </div>

      <section className={styles.settingsSection}>
        <div className={styles.settingsSectionHead}>
          <h3 className={styles.settingsSectionTitle}>
            {t("account.displayName")}
          </h3>
          <p className={styles.settingsSectionDesc}>
            {t("account.displayNameHint")}
          </p>
        </div>
        <Form
          form={profileForm}
          onFinish={handleSaveProfile}
          layout="vertical"
          requiredMark={false}
          initialValues={{ display_name: user?.display_name || "" }}
          className={styles.settingsForm}
        >
          <Form.Item
            name="display_name"
            style={{ marginBottom: 12 }}
            rules={[
              {
                max: 64,
                message: t("account.displayNameTooLong"),
              },
            ]}
          >
            <Input
              placeholder={t("account.displayNamePlaceholder")}
              maxLength={64}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saving} block>
            {t("account.saveDisplayName")}
          </Button>
        </Form>
      </section>

      <Divider className={styles.settingsDivider} />

      <section className={styles.settingsSection}>
        <div className={styles.settingsSectionHead}>
          <h3 className={styles.settingsSectionTitle}>
            {t("account.language")}
          </h3>
          <p className={styles.settingsSectionDesc}>
            {t("account.languageHint")}
          </p>
        </div>
        <Segmented
          block
          value={currentLang}
          options={[
            { label: t("account.langZh"), value: "zh" },
            { label: t("account.langEn"), value: "en" },
          ]}
          onChange={(val) => handleLocaleChange(val as string)}
        />
      </section>

      <Divider className={styles.settingsDivider} />

      <section className={styles.settingsSection}>
        <div className={styles.settingsSectionHead}>
          <h3 className={styles.settingsSectionTitle}>
            {t("account.palette")}
          </h3>
          <p className={styles.settingsSectionDesc}>
            {t("account.paletteHint")}
          </p>
        </div>
        <PaletteSwitcher />
      </section>

      <Divider className={styles.settingsDivider} />

      <section className={styles.settingsSection}>
        <div className={styles.settingsSectionHead}>
          <h3 className={styles.settingsSectionTitle}>
            {t("account.changePassword")}
          </h3>
          <p className={styles.settingsSectionDesc}>
            {t("account.changePasswordHint")}
          </p>
        </div>
        <Form
          form={pwForm}
          onFinish={handleChangePw}
          layout="vertical"
          requiredMark={false}
          className={styles.settingsForm}
        >
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
              {
                required: true,
                message: t("account.newPasswordRequired"),
              },
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
            style={{ marginBottom: 12 }}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button htmlType="submit" loading={changingPw} block>
            {t("account.changePassword")}
          </Button>
        </Form>
      </section>
    </div>
  );

  return (
    <>
      <Popover
        content={menuContent}
        trigger="click"
        open={menuOpen}
        onOpenChange={setMenuOpen}
        placement="topLeft"
        arrow={false}
        overlayClassName={styles.menuPopover}
        destroyOnHidden
        getPopupContainer={() => document.body}
      >
        {triggerButton}
      </Popover>

      {isMobile ? (
        <Drawer
          title={t("account.settings")}
          open={settingsOpen}
          onClose={closeSettings}
          placement="bottom"
          height="min(92dvh, 100%)"
          destroyOnHidden
          className={styles.settingsDrawer}
          styles={{
            body: {
              paddingTop: 8,
              paddingBottom: "calc(16px + env(safe-area-inset-bottom, 0px))",
            },
          }}
        >
          {settingsBody}
        </Drawer>
      ) : (
        <Modal
          title={t("account.settings")}
          open={settingsOpen}
          onCancel={closeSettings}
          footer={null}
          destroyOnHidden
          centered
          width={420}
          className={styles.settingsModal}
        >
          {settingsBody}
        </Modal>
      )}
    </>
  );
}
