import { Button, Popconfirm, Switch, Tag } from "antd";
import { ArrowUpCircle, Check, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  InstalledPlugin,
  MarketPlugin,
} from "../../../api/modules/plugins";
import SkillTile from "../../../workbuddy/SkillTile";
import { PluginIconView } from "./PluginIconView";
import { PluginCardMeta } from "./PluginCardMeta";

/** Original MyPluginCard/CardFrame structure; Octop owns runtime status/actions. */
export function InstalledPluginTile({
  plugin,
  toggling,
  onOpen,
  onToggle,
  onUninstall,
}: {
  plugin: InstalledPlugin;
  toggling: boolean;
  onOpen: () => void;
  onToggle: (enabled: boolean) => void;
  onUninstall: () => void;
}) {
  const { t } = useTranslation();
  const enabled = plugin.enabled !== false;
  const status = plugin.error
    ? t("plugins.statusError")
    : !enabled
    ? t("plugins.statusDisabled")
    : plugin.loaded
    ? t("plugins.statusLoaded")
    : t("plugins.statusIdle");
  return (
    <SkillTile
      title={plugin.name || plugin.id}
      description={
        plugin.error || plugin.description || t("plugins.noDescription")
      }
      icon={<PluginIconView icon={plugin.icon} size={28} />}
      enabled={enabled}
      onOpen={onOpen}
      metadata={
        <PluginCardMeta
          kind={plugin.kind}
          group={plugin.group}
          version={plugin.version}
          trailing={
            <Tag
              bordered={false}
              color={
                plugin.error
                  ? "error"
                  : enabled && plugin.loaded
                  ? "success"
                  : "default"
              }
            >
              {status}
            </Tag>
          }
        />
      }
      actions={
        <>
          <Popconfirm
            title={t("plugins.uninstallConfirm", { id: plugin.id })}
            onConfirm={onUninstall}
          >
            <Button
              type="text"
              danger
              size="small"
              icon={<Trash2 size={15} />}
              aria-label={t("plugins.uninstall")}
            />
          </Popconfirm>
          <Switch
            size="small"
            checked={enabled}
            loading={toggling}
            disabled={!!plugin.error}
            aria-label={t("plugins.colEnabled")}
            onChange={onToggle}
          />
        </>
      }
    />
  );
}

/** Original MarketPluginCard geometry, with Octop's actual install/update semantics. */
export function MarketPluginTile({
  plugin,
  installing,
  onInstall,
}: {
  plugin: MarketPlugin;
  installing: boolean;
  onInstall: (force: boolean) => void;
}) {
  const { t } = useTranslation();
  const installed = !!plugin.installed;
  const canUpdate = !!plugin.update_available;
  const label = canUpdate
    ? t("plugins.marketUpdate")
    : installed
    ? t("plugins.marketInstalled")
    : t("plugins.marketInstall");
  return (
    <SkillTile
      title={plugin.name || plugin.id}
      description={
        plugin.error || plugin.description || t("plugins.noDescription")
      }
      icon={<PluginIconView icon={plugin.icon} size={28} />}
      installed={installed}
      installedListMode={false}
      sourceLabel={plugin.id}
      metadata={
        <PluginCardMeta
          kind={plugin.kind}
          group={plugin.group}
          version={plugin.version}
        />
      }
      actions={
        <Button
          className="sm-add-btn"
          type="text"
          size="small"
          title={label}
          aria-label={label}
          loading={installing}
          disabled={installed && !canUpdate}
          icon={
            canUpdate ? (
              <ArrowUpCircle size={16} />
            ) : installed ? (
              <Check size={16} />
            ) : (
              <Plus size={16} />
            )
          }
          onClick={() => onInstall(canUpdate)}
        />
      }
    />
  );
}
