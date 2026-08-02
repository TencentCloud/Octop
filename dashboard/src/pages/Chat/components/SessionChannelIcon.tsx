import { Tooltip } from "antd";
import { MessageSquare } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  CHANNEL_ICONS,
  CHANNEL_LABEL_KEYS,
  CHANNEL_LABELS,
  type ChannelKey,
} from "../../Agent/Channels/components/constants";

function isChannelKey(value: string): value is ChannelKey {
  return Object.prototype.hasOwnProperty.call(CHANNEL_ICONS, value);
}

interface SessionChannelIconProps {
  channelType: string;
  size?: number;
  className?: string;
  /** Show channel name on hover (session list / title bar). */
  withTooltip?: boolean;
}

/** Channel glyph matching the chat history rail (dashboard → MessageSquare). */
export default function SessionChannelIcon({
  channelType,
  size = 12,
  className,
  withTooltip = true,
}: SessionChannelIconProps) {
  const { t } = useTranslation();

  if (channelType === "dashboard") {
    return (
      <MessageSquare
        size={size}
        className={className}
        strokeWidth={1.75}
        aria-hidden
      />
    );
  }

  const label = isChannelKey(channelType)
    ? t(CHANNEL_LABEL_KEYS[channelType], CHANNEL_LABELS[channelType])
    : channelType;
  const iconSrc = isChannelKey(channelType)
    ? CHANNEL_ICONS[channelType]
    : CHANNEL_ICONS.octopbot;

  const img = (
    <img
      src={iconSrc}
      alt=""
      className={className}
      style={{
        width: size,
        height: size,
        objectFit: "contain",
        display: "block",
      }}
      aria-label={label}
    />
  );

  if (!withTooltip) return img;
  return (
    <Tooltip title={label} mouseEnterDelay={0.35}>
      {img}
    </Tooltip>
  );
}
