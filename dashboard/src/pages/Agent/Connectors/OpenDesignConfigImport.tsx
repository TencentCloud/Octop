import { useState } from "react";
import { Button, Input, Select, Space, Alert } from "antd";
import { useTranslation } from "react-i18next";
import {
  parseOpenDesignConfigs,
  type OpenDesignLaunchConfig,
} from "./openDesignConfig";
import styles from "./index.module.less";

export function OpenDesignConfigImport({
  onImport,
}: {
  onImport: (value: OpenDesignLaunchConfig) => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [configs, setConfigs] = useState<Record<
    string,
    OpenDesignLaunchConfig
  > | null>(null);
  const [selected, setSelected] = useState<string>();
  const [invalid, setInvalid] = useState(false);
  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Input.TextArea
        className={styles.openDesignImportInput}
        value={text}
        rows={4}
        placeholder={t("connectors.openDesignImportHint")}
        onChange={(event) => {
          setText(event.target.value);
          setConfigs(null);
          setSelected(undefined);
          setInvalid(false);
        }}
      />
      {invalid && (
        <Alert type="error" message={t("connectors.openDesignImportInvalid")} />
      )}
      {configs && (
        <Select
          style={{ width: "100%" }}
          value={selected}
          placeholder={t("connectors.openDesignSelectServer")}
          options={Object.keys(configs).map((name) => ({
            value: name,
            label: name,
          }))}
          onChange={setSelected}
        />
      )}
      <div className={styles.openDesignImportActions}>
        <Button
          type="primary"
          disabled={!text.trim() || (configs !== null && !selected)}
          onClick={() => {
            try {
              const values = configs ?? parseOpenDesignConfigs(text);
              const names = Object.keys(values);
              if (names.length > 1 && !selected) {
                setConfigs(values);
                return;
              }
              onImport(values[selected ?? names[0]]);
              setText("");
              setConfigs(null);
              setSelected(undefined);
            } catch {
              setInvalid(true);
            }
          }}
        >
          {t("connectors.openDesignImport")}
        </Button>
      </div>
    </Space>
  );
}
