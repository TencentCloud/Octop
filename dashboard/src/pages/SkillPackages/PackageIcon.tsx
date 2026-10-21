import { ExpertIcon } from "../Experts/components/iconForName";

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
  return (
    <ExpertIcon
      iconUrl={iconUrl}
      iconName={iconName}
      size={size}
      className={imageClassName ?? className}
    />
  );
}
