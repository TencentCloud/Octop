import type { ReactNode } from "react";

interface SkillTileProps {
  title: string;
  description: string;
  icon: ReactNode;
  badge?: ReactNode;
  sourceLabel?: string;
  enabled?: boolean;
  installed?: boolean;
  installedListMode?: boolean;
  metadata?: ReactNode;
  actions?: ReactNode;
  onOpen?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

/** 5.5.6 skill-market/cards/card-frame.tsx, with Octop data and action slots. */
export default function SkillTile({
  title,
  description,
  icon,
  badge,
  sourceLabel,
  enabled = true,
  installed = true,
  installedListMode = true,
  metadata,
  actions,
  onOpen,
  onMouseEnter,
  onMouseLeave,
}: SkillTileProps) {
  return (
    <div
      className={`skill-card${installed ? " skill-card--installed" : ""}${
        installed && installedListMode ? " skill-card--installed-list-mode" : ""
      }${enabled ? "" : " skill-card--disabled"}`}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      aria-label={onOpen ? title : undefined}
      onClick={onOpen}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onKeyDown={(event) => {
        if (
          onOpen &&
          event.target === event.currentTarget &&
          (event.key === "Enter" || event.key === " ")
        ) {
          event.preventDefault();
          onOpen();
        }
      }}
    >
      <div className="skill-card-content">
        <div className="skill-card-icon">{icon}</div>
        <div className="skill-card-top">
          <div className="skill-card-body">
            <div className="skill-card-name-row">
              <span className="skill-card-name" title={title}>
                {title}
              </span>
              {sourceLabel && (
                <span className="skill-card-source">{sourceLabel}</span>
              )}
              {badge}
            </div>
          </div>
        </div>
        <div
          className="skill-status"
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {actions}
        </div>
      </div>
      <div
        className="skill-card-desc skill-card-desc--two-lines"
        title={description}
      >
        {description}
      </div>
      {metadata && <div className="wb-plugin-meta">{metadata}</div>}
    </div>
  );
}
