import { Tooltip } from "antd";

/** Expert title that ellipsizes, with a hover tip for the full name. */
export default function ExpertNameLabel({
  name,
  className,
}: {
  name: string;
  className: string;
}) {
  return (
    <Tooltip title={name} mouseEnterDelay={0.4} placement="topLeft">
      <span className={className}>{name}</span>
    </Tooltip>
  );
}
