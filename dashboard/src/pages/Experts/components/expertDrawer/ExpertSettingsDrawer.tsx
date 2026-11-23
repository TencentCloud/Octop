import { useEffect, useRef, useState, type ReactNode } from "react";
import { Form } from "antd";
import ExpertConfigDrawer from "./ExpertConfigDrawer";

type FieldPath = string | string[];

export default function ExpertSettingsDrawer({
  title,
  summary,
  children,
  fields,
  open: controlledOpen,
  onOpenChange,
}: {
  title: string;
  summary: string;
  children: ReactNode;
  fields?: FieldPath[];
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const form = Form.useFormInstance();
  const [localOpen, setLocalOpen] = useState(false);
  const original = useRef<Parameters<typeof form.setFields>[0]>();
  const open = controlledOpen ?? localOpen;
  const setOpen = onOpenChange ?? setLocalOpen;

  useEffect(() => {
    if (open && fields && !original.current) {
      original.current = fields.map((name) => ({
        name,
        value: form.getFieldValue(name),
        touched: form.isFieldTouched(name),
        errors: form.getFieldError(name),
      }));
    }
    if (!open) original.current = undefined;
  }, [fields, form, open]);

  return (
    <ExpertConfigDrawer
      title={title}
      summary={summary}
      open={open}
      keepMounted
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      onCancel={
        fields
          ? () => {
              if (original.current) form.setFields(original.current);
              original.current = undefined;
              setOpen(false);
            }
          : undefined
      }
      onApply={
        fields
          ? async () => {
              try {
                await form.validateFields(fields);
                original.current = undefined;
                setOpen(false);
              } catch {
                // Ant Design displays errors beside the fields in this drawer.
              }
            }
          : undefined
      }
    >
      {children}
    </ExpertConfigDrawer>
  );
}
