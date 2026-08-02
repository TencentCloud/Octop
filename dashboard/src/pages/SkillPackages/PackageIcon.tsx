import { iconForName } from "../Experts/components/iconForName";

export function PackageIcon({
  iconUrl,
  iconName,
  size = 22,
  className,
  imageClassName,
}: {
  iconUrl?: string;
  iconName?: string;
  size?: number;
  className?: string;
  imageClassName?: string;
}) {
  if (iconUrl) {
    return <img src={iconUrl} alt="" className={imageClassName ?? className} />;
  }
  return iconForName(iconName, size);
}
