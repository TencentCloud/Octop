import type { ReactNode } from "react";

interface ConnectorTileProps {
  name: string;
  description: string;
  icon: ReactNode;
  installed?: boolean;
  disabled?: boolean;
  status?: ReactNode;
  detail?: ReactNode;
  actions: ReactNode;
  onOpen?: () => void;
}

/** 5.5.6 connector-panel.tsx card structure; status comes only from Octop. */
export default function ConnectorTile({
  name,
  description,
  icon,
  installed = false,
  disabled = false,
  status,
  detail,
  actions,
  onOpen,
}: ConnectorTileProps) {
  const interactive = Boolean(onOpen) && !disabled;
  return (
    <div
      className={`connector-card connector-card--${
        installed ? "installed" : "available"
      }${disabled ? " connector-card--incompatible" : ""}`}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-label={interactive ? name : undefined}
      aria-disabled={disabled || undefined}
      onClick={interactive ? onOpen : undefined}
      onKeyDown={(event) => {
        if (
          interactive &&
          event.target === event.currentTarget &&
          (event.key === "Enter" || event.key === " ")
        ) {
          event.preventDefault();
          onOpen?.();
        }
      }}
    >
      <div className="connector-card-icon">{icon}</div>
      <div className="connector-card-main">
        <div className="connector-card-name-row">
          <div className="connector-card-name" title={name}>
            {name}
          </div>
          {status}
        </div>
        <div className="connector-card-desc">
          {description}
          {detail && <div className="wb-connector-detail">{detail}</div>}
        </div>
      </div>
      <div
        className="connector-card-action"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => event.stopPropagation()}
      >
        {actions}
      </div>
    </div>
  );
}
