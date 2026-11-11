import { useState } from "react";
import { Button, Form, Switch } from "antd";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Provider compatibility: live token counts via stream_options.include_usage. */
export function StreamUsageAdvanced() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: open ? 8 : 12,
        }}
      >
        <Button
          type="link"
          size="small"
          style={{ padding: 0 }}
          icon={open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          onClick={() => setOpen(!open)}
        >
          {open ? t("models.hideCompatibility") : t("models.compatibility")}
        </Button>
      </div>
      <div style={{ display: open ? undefined : "none" }}>
        <Form.Item
          name="stream_usage"
          label={t("models.streamUsage")}
          extra={t("models.streamUsageHint")}
          valuePropName="checked"
        >
          <Switch size="small" />
        </Form.Item>
      </div>
    </div>
  );
}
