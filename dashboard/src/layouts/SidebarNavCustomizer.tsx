import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { Button, Drawer, Input, Popconfirm } from "antd";
import { useTranslation } from "react-i18next";
import { Eye, EyeOff, GripVertical, Plus, Trash2 } from "lucide-react";
import { message } from "../utils/antdMessage";
import { apiErrorMessage } from "../utils/apiError";
import { preferencesApi } from "../api/modules/preferences";
import {
  builtinNavGroupLabelKey,
  type NavItem,
  type NavSection,
} from "./sidebarNav";
import {
  catalogItems,
  createGroup,
  deleteGroup,
  editorFromCatalog,
  groupNameMissing,
  layoutFromEditor,
  moveGroup,
  newNavGroupId,
  nextGroupName,
  placeItem,
  renameGroup,
  preservedPlacements,
  visibleEditorGroups,
  type SidebarNavEditorState,
  type SidebarNavItemPlacement,
  type SidebarNavItemZone,
  type SidebarNavLayout,
} from "./sidebarNavLayout";
import styles from "./SidebarNavCustomizer.module.less";

type DragPayload =
  | { type: "item"; key: string }
  | { type: "group"; id: string };

function allowDrop(event: DragEvent) {
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
}

export default function SidebarNavCustomizer({
  open,
  catalog,
  layout,
  onClose,
  onSaved,
}: {
  open: boolean;
  catalog: NavSection[];
  layout: SidebarNavLayout | null;
  onClose: () => void;
  onSaved: (layout: SidebarNavLayout | null) => void;
}) {
  const { t } = useTranslation();
  const items = useMemo(() => catalogItems(catalog), [catalog]);
  const [draft, setDraft] = useState<SidebarNavEditorState>(() =>
    editorFromCatalog(catalog, layout),
  );
  const [preserved, setPreserved] = useState<SidebarNavItemPlacement[]>([]);
  const [cleared, setCleared] = useState(false);
  const [saving, setSaving] = useState(false);
  const dragRef = useRef<DragPayload | null>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open && !wasOpen.current) {
      setDraft(editorFromCatalog(catalog, layout));
      setPreserved(preservedPlacements(layout, catalog));
      setCleared(false);
    }
    wasOpen.current = open;
  }, [open, catalog, layout]);

  const edit = (next: SidebarNavEditorState) => {
    setCleared(false);
    setDraft(next);
  };

  const onDragStart = (event: DragEvent, payload: DragPayload) => {
    dragRef.current = payload;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", payload.type);
  };

  const dropItem = (zone: SidebarNavItemZone, beforeKey: string | null) => {
    const payload = dragRef.current;
    dragRef.current = null;
    if (!payload || payload.type !== "item") return;
    edit(placeItem(draft, payload.key, zone, beforeKey));
  };

  const dropGroup = (beforeId: string | null) => {
    const payload = dragRef.current;
    dragRef.current = null;
    if (!payload || payload.type !== "group") return;
    edit(moveGroup(draft, payload.id, beforeId));
  };

  const addGroup = () => {
    const name = nextGroupName(draft, t("nav.newGroupDefault"));
    edit(createGroup(draft, newNavGroupId(), name));
  };

  const reset = () => {
    setDraft(editorFromCatalog(catalog, null));
    setPreserved([]);
    setCleared(true);
  };

  const save = async () => {
    if (!cleared && groupNameMissing(draft)) {
      message.error(t("nav.groupNameRequired"));
      return;
    }
    const baseline = layoutFromEditor(editorFromCatalog(catalog, null));
    const next = layoutFromEditor(draft, preserved);
    const isDefault =
      preserved.length === 0 &&
      JSON.stringify(next) === JSON.stringify(baseline);
    const payload = cleared || isDefault ? null : next;
    setSaving(true);
    try {
      await preferencesApi.patch({ sidebar_nav: payload });
      onSaved(payload);
      onClose();
    } catch (error) {
      message.error(apiErrorMessage(error, t("nav.saveFailed"), t));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      title={t("nav.customizeTitle")}
      open={open}
      onClose={onClose}
      width={420}
      destroyOnClose
      extra={
        <Button icon={<Plus size={14} />} onClick={addGroup}>
          {t("nav.newGroup")}
        </Button>
      }
      footer={
        <div className={styles.footer}>
          <Popconfirm
            title={t("nav.resetLayoutConfirm")}
            onConfirm={reset}
            okText={t("common.confirm")}
            cancelText={t("common.cancel")}
          >
            <Button type="text">{t("nav.resetLayout")}</Button>
          </Popconfirm>
          <div className={styles.footerActions}>
            <Button onClick={onClose}>{t("common.cancel")}</Button>
            <Button type="primary" loading={saving} onClick={() => void save()}>
              {t("common.save")}
            </Button>
          </div>
        </div>
      }
    >
      <section className={styles.section}>
        <div className={styles.sectionLabel}>{t("nav.ungrouped")}</div>
        <p className={styles.hint}>{t("nav.ungroupedHint")}</p>
        <ItemList
          zone={{ kind: "ungrouped" }}
          keys={draft.ungrouped}
          items={items}
          hidden={false}
          t={t}
          onDragStart={onDragStart}
          onDropItem={dropItem}
          onMove={(key, zone) => edit(placeItem(draft, key, zone, null))}
        />
      </section>

      <div
        onDragOver={allowDrop}
        onDrop={(event) => {
          event.preventDefault();
          if (dragRef.current?.type === "group") dropGroup(null);
        }}
      >
        {visibleEditorGroups(draft, catalog).map((group) => {
          const labelKey = builtinNavGroupLabelKey(group.id);
          const keys = draft.itemsByGroup[group.id] ?? [];
          return (
            <section
              key={group.id}
              className={styles.group}
              onDragOver={allowDrop}
              onDrop={(event) => {
                event.preventDefault();
                event.stopPropagation();
                const payload = dragRef.current;
                if (payload?.type === "group") {
                  dropGroup(group.id);
                } else if (payload?.type === "item") {
                  dropItem(
                    { kind: "group", groupId: group.id },
                    keys[0] ?? null,
                  );
                }
              }}
            >
              <div className={styles.groupHead}>
                <span
                  className={styles.handle}
                  draggable
                  title={t("nav.dragToReorder")}
                  onDragStart={(event) =>
                    onDragStart(event, { type: "group", id: group.id })
                  }
                >
                  <GripVertical size={14} />
                </span>
                <Input
                  className={styles.groupName}
                  size="small"
                  maxLength={40}
                  value={group.name ?? ""}
                  placeholder={
                    labelKey ? t(labelKey) : t("nav.groupNamePlaceholder")
                  }
                  aria-label={t("nav.groupNamePlaceholder")}
                  onChange={(event) =>
                    edit(
                      renameGroup(
                        draft,
                        group.id,
                        event.target.value ? event.target.value : null,
                      ),
                    )
                  }
                />
                <Popconfirm
                  title={t("nav.deleteGroupConfirm")}
                  onConfirm={() => edit(deleteGroup(draft, group.id))}
                  okText={t("common.confirm")}
                  cancelText={t("common.cancel")}
                >
                  <Button
                    type="text"
                    size="small"
                    aria-label={t("nav.deleteGroup")}
                    icon={<Trash2 size={14} />}
                  />
                </Popconfirm>
              </div>
              <ItemList
                zone={{ kind: "group", groupId: group.id }}
                keys={keys}
                items={items}
                hidden={false}
                t={t}
                onDragStart={onDragStart}
                onDropItem={dropItem}
                onMove={(key, zone) => edit(placeItem(draft, key, zone, null))}
              />
            </section>
          );
        })}
      </div>

      <section className={styles.section}>
        <div className={styles.sectionLabel}>{t("nav.hiddenItems")}</div>
        <ItemList
          zone={{ kind: "hidden" }}
          keys={draft.hidden}
          items={items}
          hidden
          t={t}
          onDragStart={onDragStart}
          onDropItem={dropItem}
          onMove={(key, zone) => edit(placeItem(draft, key, zone, null))}
        />
      </section>
    </Drawer>
  );
}

function ItemList({
  zone,
  keys,
  items,
  hidden,
  t,
  onDragStart,
  onDropItem,
  onMove,
}: {
  zone: SidebarNavItemZone;
  keys: string[];
  items: Map<string, NavItem>;
  hidden: boolean;
  t: (key: string) => string;
  onDragStart: (event: DragEvent, payload: DragPayload) => void;
  onDropItem: (zone: SidebarNavItemZone, beforeKey: string | null) => void;
  onMove: (key: string, zone: SidebarNavItemZone) => void;
}) {
  return (
    <div
      className={styles.list}
      onDragOver={allowDrop}
      onDrop={(event) => {
        event.preventDefault();
        onDropItem(zone, null);
      }}
    >
      {keys.length === 0 ? (
        <div className={styles.empty}>
          {hidden ? t("nav.hiddenEmpty") : t("nav.dropHere")}
        </div>
      ) : null}
      {keys.map((key) => {
        const item = items.get(key);
        if (!item) return null;
        return (
          <div
            key={key}
            className={styles.row}
            onDragOver={allowDrop}
            onDrop={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onDropItem(zone, key);
            }}
          >
            <span
              className={styles.handle}
              draggable
              title={t("nav.dragToReorder")}
              onDragStart={(event) => {
                event.stopPropagation();
                onDragStart(event, { type: "item", key });
              }}
            >
              <GripVertical size={14} />
            </span>
            <span className={styles.itemIcon}>{item.icon}</span>
            <span className={styles.itemLabel}>{t(item.labelKey)}</span>
            <Button
              type="text"
              size="small"
              aria-label={hidden ? t("nav.showInNav") : t("nav.hideFromNav")}
              icon={hidden ? <Eye size={14} /> : <EyeOff size={14} />}
              onClick={() =>
                onMove(key, hidden ? { kind: "ungrouped" } : { kind: "hidden" })
              }
            />
          </div>
        );
      })}
    </div>
  );
}
