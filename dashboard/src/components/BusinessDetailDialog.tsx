import { useContext } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { MarketDetailContext } from "../workbuddy/MarketDetailContext";
import { Drawer, Modal, type DrawerProps } from "antd";
import { WORKBUDDY_UI } from "../workbuddy/variant";

type Props = Pick<
  DrawerProps,
  | "children"
  | "open"
  | "title"
  | "onClose"
  | "footer"
  | "width"
  | "placement"
  | "destroyOnHidden"
  | "rootClassName"
  | "forceRender"
  | "styles"
  | "extra"
  | "className"
  | "zIndex"
> & { kind?: "business" | "connector" | "skill" | "editor" };

/** Keep the existing form lifecycle and callbacks in the selected display frame. */
export default function BusinessDetailDialog(props: Props) {
  const { kind = "business", ...drawerProps } = props;
  const inline = useContext(MarketDetailContext);
  const { t } = useTranslation();
  if (WORKBUDDY_UI && inline && kind === "skill") {
    if (!props.open) return null;
    return (
      <article className="wb-market-detail">
        <header>
          <button
            type="button"
            className="wb-detail-back"
            onClick={props.onClose}
            aria-label={t("common.back")}
          >
            <ArrowLeft size={16} />
            {t("common.back")}
          </button>
          {props.title}
          {props.extra}
        </header>
        <div className="wb-market-detail__body" style={props.styles?.body}>
          {props.children}
        </div>
        {props.footer && <footer>{props.footer}</footer>}
      </article>
    );
  }
  if (!WORKBUDDY_UI) return <Drawer {...drawerProps} />;
  return (
    <Modal
      open={props.open}
      title={
        props.extra ? (
          <div className="wb-detail-title-row">
            <span>{props.title}</span>
            {props.extra}
          </div>
        ) : (
          props.title
        )
      }
      onCancel={props.onClose}
      footer={props.footer ?? null}
      destroyOnHidden={props.destroyOnHidden}
      forceRender={props.forceRender}
      zIndex={props.zIndex}
      styles={{ body: props.styles?.body }}
      width={
        kind === "editor"
          ? 880
          : kind === "skill"
          ? 640
          : kind === "connector"
          ? 600
          : 520
      }
      centered
      className={`wb-business-modal wb-detail-${kind}${
        props.className ? ` ${props.className}` : ""
      }`}
      rootClassName={props.rootClassName}
    >
      {props.children}
    </Modal>
  );
}
