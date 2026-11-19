import type { ReactElement } from "react";
import { Form } from "antd";

import {
  TextAssistBar,
  type TextAssistBarProps,
} from "../../../../components/TextAssistBar";
import styles from "./expertDrawer.module.less";

export default function ExpertTextAssistField({
  name,
  label,
  tooltip,
  kind,
  children,
}: {
  name: "description" | "welcome_message";
  label: string;
  tooltip?: string;
  kind: TextAssistBarProps["kind"];
  children: ReactElement;
}) {
  const form = Form.useFormInstance();

  return (
    <div className={styles.assistField}>
      <Form.Item name={name} label={label} tooltip={tooltip}>
        {children}
      </Form.Item>
      <div className={styles.assistFieldAction}>
        <TextAssistBar
          compact
          kind={kind}
          getName={() => String(form.getFieldValue("name") ?? "")}
          getText={() => String(form.getFieldValue(name) ?? "")}
          onApply={(text) => form.setFieldValue(name, text)}
        />
      </div>
    </div>
  );
}
