import { Button, Result } from "antd";
import { ShieldOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { chatHomePath } from "../utils/chatRoute";

/** Full-area "no permission" placeholder used by route and tab guards. */
export default function ForbiddenPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const home = chatHomePath(useLocation().pathname);
  return (
    <div
      style={{
        flex: 1,
        minHeight: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <Result
        icon={<ShieldOff size={48} strokeWidth={1.5} />}
        title={t("common.noPermission")}
        subTitle={t("common.noPermissionHint")}
        extra={
          home && (
            <Button type="primary" onClick={() => navigate(home)}>
              {t("common.backToChat")}
            </Button>
          )
        }
      />
    </div>
  );
}
