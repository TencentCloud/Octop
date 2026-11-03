import { useTranslation } from "react-i18next";
import cx from "classnames";
import { useAuthImageSrc } from "../hooks/useAuthImageSrc";
import styles from "./AuthImage.module.less";

interface AuthImageProps {
  url: string;
  alt?: string;
  className?: string;
}

/** Image that loads JWT-protected API URLs via authenticated blob fetch. */
export default function AuthImage({
  url,
  alt = "",
  className,
}: AuthImageProps) {
  const { t } = useTranslation();
  const { src, loadState } = useAuthImageSrc(url, alt);

  if (loadState === "loading") {
    return <div className={cx(styles.placeholder, className)} aria-hidden />;
  }

  if (loadState === "error" || !src) {
    return (
      <div
        className={cx(styles.placeholder, styles.error, className)}
        role="img"
        aria-label={alt || t("chat.imageLoadFailed")}
      />
    );
  }

  return <img src={src} alt={alt} className={className} />;
}
