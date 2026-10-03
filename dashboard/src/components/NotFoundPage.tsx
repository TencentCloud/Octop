import { Button } from "antd";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { chatHomePath } from "../utils/chatRoute";
import { OctopEmptyMascot } from "./EmptyState";
import styles from "./NotFoundPage.module.less";

/** Catch-all placeholder for dashboard paths that do not match any route. */
export default function NotFoundPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const home = chatHomePath(useLocation().pathname);
  return (
    <div className={styles.wrap}>
      <div className={styles.inner}>
        <OctopEmptyMascot size={140} className={styles.mascot} />
        <h1 className={styles.title}>{t("common.notFound")}</h1>
        <p className={styles.hint}>{t("common.notFoundHint")}</p>
        {home && (
          <Button type="primary" onClick={() => navigate(home)}>
            {t("common.backToChat")}
          </Button>
        )}
      </div>
    </div>
  );
}
