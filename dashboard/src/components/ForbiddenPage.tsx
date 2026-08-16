import { Button, Result } from "antd";
import { ShieldOff } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

/** Full-area "no permission" placeholder used by route and tab guards. */
export default function ForbiddenPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
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
          <Button type="primary" onClick={() => navigate("/chat")}>
            {t("common.backToChat")}
          </Button>
        }
      />
    </div>
  );
}
