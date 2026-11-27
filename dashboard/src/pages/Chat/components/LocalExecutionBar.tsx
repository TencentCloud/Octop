import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  ChevronDown,
  CloudCog,
  Folder,
  MonitorCog,
  Plus,
  X,
} from "lucide-react";
import { Popover } from "antd";
import cx from "classnames";
import RootDirSelect from "../../Experts/components/RootDirSelect";
import { fetchFilesystemDefaults } from "../../Experts/components/agentBackendForm";
import { HOST_FS_ROOT } from "../../Experts/components/rootDirTree";
import {
  isDraftExecutionThread,
  pathTail,
  readLocalExecution,
  writeLocalExecution,
  type LocalExecutionChoice,
} from "../localExecution";
import styles from "../index.module.less";

interface LocalExecutionBarProps {
  agentId: string;
  threadId?: string | null;
}

function samePath(left: string, right: string): boolean {
  const norm = (value: string) =>
    value.trim().replace(/\\/g, "/").replace(/\/+$/, "") || "/";
  return norm(left) === norm(right);
}

export default function LocalExecutionBar({
  agentId,
  threadId = null,
}: LocalExecutionBarProps) {
  const { t } = useTranslation();
  const locked = !isDraftExecutionThread(threadId);
  const [choice, setChoice] = useState<LocalExecutionChoice>(() =>
    readLocalExecution(agentId, threadId),
  );
  useEffect(() => {
    setChoice(readLocalExecution(agentId, threadId));
  }, [agentId, threadId]);
  const [modeOpen, setModeOpen] = useState(false);
  const [dirOpen, setDirOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  /** Tree dropdown is portaled to ``document.body``, so it sits outside the popover. */
  const directoryTreeOpen = useRef(false);
  const fetchedBrowseAgent = useRef<string | null>(null);
  const [browse, setBrowse] = useState<{
    agentId: string;
    roots: string[];
    home: string | null;
  } | null>(null);

  const update = (next: LocalExecutionChoice) => {
    setChoice(next);
    writeLocalExecution(agentId, null, next);
  };

  const local = choice.mode === "local";
  const home = browse?.home ?? null;

  useEffect(() => {
    if (locked || !local || fetchedBrowseAgent.current === agentId) return;
    let cancelled = false;
    fetchFilesystemDefaults(agentId)
      .then((defaults) => {
        if (cancelled) return;
        fetchedBrowseAgent.current = agentId;
        const next = defaults.browse_roots?.length
          ? defaults.browse_roots
          : [defaults.tree_root || HOST_FS_ROOT];
        setBrowse({
          agentId,
          roots: next,
          home: defaults.default_agent_workspace?.trim() || null,
        });
      })
      .catch(() => {
        if (cancelled) return;
        fetchedBrowseAgent.current = agentId;
        setBrowse({ agentId, roots: [HOST_FS_ROOT], home: null });
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, local, locked]);

  useEffect(() => {
    if (locked || !local || !home) return;
    setChoice((current) => {
      if (current.mode !== "local" || current.directory.trim()) return current;
      const next = { ...current, directory: home };
      writeLocalExecution(agentId, null, next);
      return next;
    });
  }, [agentId, local, home, locked]);

  const usingDefault =
    !choice.directory.trim() ||
    (home != null && samePath(choice.directory, home));
  const extraWorkspaces = choice.workspaces.filter(
    (path) => home == null || !samePath(path, home),
  );

  const selectDirectory = (path: string) => {
    update({ mode: "local", directory: path, workspaces: choice.workspaces });
    setAdding(false);
    setDirOpen(false);
  };

  const removeWorkspace = (path: string) => {
    const workspaces = choice.workspaces.filter(
      (item) => !samePath(item, path),
    );
    const directory = samePath(choice.directory, path)
      ? home ?? ""
      : choice.directory;
    update({ mode: "local", directory, workspaces });
  };

  const modeLabel = local
    ? t("chat.remoteExpert.executionLocal")
    : t("chat.remoteExpert.executionCloud");
  const fullDirectory = choice.directory.trim() || home || "";
  const dirLabel =
    pathTail(fullDirectory) || t("chat.remoteExpert.defaultWorkspace");

  if (locked) {
    const location = local
      ? choice.directory.trim()
      : t("chat.remoteExpert.executionPeerWorkspace");
    return (
      <div
        className={styles.executionChips}
        aria-label={`${t("chat.remoteExpert.executionLabel")}: ${modeLabel}`}
      >
        <span className={styles.executionStatus}>
          {local ? <MonitorCog size={15} /> : <CloudCog size={15} />}
          <span>{modeLabel}</span>
        </span>
        <span className={styles.executionStatus} title={location}>
          {local ? <Folder size={15} /> : <CloudCog size={15} />}
          <span>{location}</span>
        </span>
      </div>
    );
  }

  return (
    <div className={styles.executionChips}>
      <Popover
        trigger="click"
        placement="topLeft"
        open={modeOpen}
        onOpenChange={setModeOpen}
        overlayClassName={styles.modelPopover}
        content={
          <div className={styles.modeMenu}>
            <button
              type="button"
              className={cx(
                styles.modeMenuItem,
                !local && styles.modeMenuItemActive,
              )}
              onClick={() => {
                update({ ...choice, mode: "cloud" });
                setModeOpen(false);
              }}
            >
              <span className={styles.modeMenuTitle}>
                <CloudCog size={16} />
                {t("chat.remoteExpert.executionCloud")}
              </span>
              <span className={styles.modeMenuHint}>
                {t("chat.remoteExpert.executionCloudHint")}
              </span>
            </button>
            <button
              type="button"
              className={cx(
                styles.modeMenuItem,
                local && styles.modeMenuItemActive,
              )}
              onClick={() => {
                update({
                  ...choice,
                  mode: "local",
                  directory: choice.directory || home || "",
                });
                setModeOpen(false);
              }}
            >
              <span className={styles.modeMenuTitle}>
                <MonitorCog size={16} />
                {t("chat.remoteExpert.executionLocal")}
              </span>
              <span className={styles.modeMenuHint}>
                {t("chat.remoteExpert.executionLocalHint")}
              </span>
            </button>
          </div>
        }
      >
        <button
          type="button"
          className={styles.executionChip}
          aria-label={`${t("chat.remoteExpert.executionLabel")}: ${modeLabel}`}
        >
          {local ? <MonitorCog size={15} /> : <CloudCog size={15} />}
          <span>{modeLabel}</span>
          <ChevronDown size={14} />
        </button>
      </Popover>
      {local ? (
        <Popover
          trigger="click"
          placement="topLeft"
          open={dirOpen}
          onOpenChange={(next) => {
            // The tree popup lives on document.body. A click inside it is
            // outside this popover; closing here unmounts the tree mid-align
            // and the two popups chase each other until the tab freezes.
            if (!next && directoryTreeOpen.current) return;
            setDirOpen(next);
            if (!next) setAdding(false);
          }}
          overlayClassName={styles.modelPopover}
          content={
            adding && browse ? (
              <div className={styles.workspaceAdd}>
                <RootDirSelect
                  manage
                  treeRoots={browse.roots}
                  placeholder={t("chat.remoteExpert.executionDirectory")}
                  getPopupContainer={() => document.body}
                  onDropdownOpenChange={(next) => {
                    directoryTreeOpen.current = next;
                  }}
                  onChange={(path) => {
                    if (home && samePath(path, home)) {
                      selectDirectory(home);
                      return;
                    }
                    const workspaces = extraWorkspaces.some((item) =>
                      samePath(item, path),
                    )
                      ? choice.workspaces
                      : [...choice.workspaces, path];
                    update({ mode: "local", directory: path, workspaces });
                    setAdding(false);
                    setDirOpen(false);
                  }}
                />
              </div>
            ) : (
              <div className={styles.workspaceMenu}>
                <button
                  type="button"
                  className={cx(
                    styles.workspaceItem,
                    usingDefault && styles.workspaceItemActive,
                  )}
                  disabled={!home}
                  onClick={() => {
                    if (home) selectDirectory(home);
                  }}
                >
                  <Folder size={15} />
                  <span
                    className={styles.workspaceItemLabel}
                    title={home || undefined}
                  >
                    {home
                      ? pathTail(home)
                      : t("chat.remoteExpert.defaultWorkspace")}
                  </span>
                  {usingDefault ? <Check size={15} /> : null}
                </button>
                {extraWorkspaces.map((path) => {
                  const active = samePath(choice.directory, path);
                  return (
                    <button
                      key={path}
                      type="button"
                      className={cx(
                        styles.workspaceItem,
                        active && styles.workspaceItemActive,
                      )}
                      title={path}
                      onClick={() => selectDirectory(path)}
                    >
                      <Folder size={15} />
                      <span className={styles.workspaceItemLabel}>
                        {pathTail(path)}
                      </span>
                      {active ? <Check size={15} /> : null}
                      <span
                        role="button"
                        tabIndex={0}
                        className={styles.workspaceRemove}
                        aria-label={t("chat.remoteExpert.removeWorkspace")}
                        title={t("chat.remoteExpert.removeWorkspace")}
                        onClick={(event) => {
                          event.stopPropagation();
                          removeWorkspace(path);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            event.stopPropagation();
                            removeWorkspace(path);
                          }
                        }}
                      >
                        <X size={14} />
                      </span>
                    </button>
                  );
                })}
                <button
                  type="button"
                  className={styles.workspaceItem}
                  onClick={() => setAdding(true)}
                >
                  <Plus size={15} />
                  <span className={styles.workspaceItemLabel}>
                    {t("chat.remoteExpert.addWorkspace")}
                  </span>
                </button>
              </div>
            )
          }
        >
          <button
            type="button"
            className={styles.executionChip}
            aria-label={`${t("chat.remoteExpert.executionLabel")}: ${dirLabel}`}
            title={fullDirectory || undefined}
          >
            <Folder size={15} />
            <span>{dirLabel}</span>
            <ChevronDown size={14} />
          </button>
        </Popover>
      ) : null}
    </div>
  );
}
