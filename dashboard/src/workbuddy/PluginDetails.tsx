import { Button, Drawer, type DrawerProps } from "antd";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { WORKBUDDY_UI } from "./variant";
import { useEffect, useRef } from "react";

type Props = Pick<
  DrawerProps,
  | "children"
  | "title"
  | "open"
  | "onClose"
  | "width"
  | "destroyOnHidden"
  | "styles"
>;

/** Source plugin details are an inline view; the list controller stays mounted. */
export default function PluginDetails(props: Props) {
  const { t } = useTranslation();
  const back = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!WORKBUDDY_UI || !props.open) return;
    const previous = document.activeElement as HTMLElement | null;
    back.current?.focus();
    return () => {
      if (previous?.isConnected) previous.focus();
    };
  }, [props.open]);
  if (!WORKBUDDY_UI) return <Drawer {...props} />;
  if (!props.open) return null;
  return (
    <article className="cb-plugin-detail wb-plugin-detail">
      <Button
        ref={back}
        type="text"
        className="cb-plugin-detail-back"
        onClick={props.onClose}
        icon={<ArrowLeft size={16} />}
      >
        {t("common.back")}
      </Button>
      <header className="cb-plugin-detail-header">{props.title}</header>
      {props.children}
    </article>
  );
}
