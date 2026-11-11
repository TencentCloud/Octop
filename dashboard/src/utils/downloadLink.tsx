import { Input, Typography } from "antd";

import { getApiUrl } from "../api/config";
import { requestUpload } from "../api/request";
import i18n from "../i18n";
import { message } from "./antdMessage";
import { modal } from "./antdModal";
import { copyText } from "./copyText";

type DownloadLinkResponse = {
  url: string;
  filename: string;
  expires_in: number;
};

/**
 * Upload an already-fetched blob for a short-lived, credential-free link and
 * show it so the user can copy it into the system browser.
 */
export async function shareDownloadLink(
  blob: Blob,
  filename: string,
): Promise<void> {
  const body = new FormData();
  body.append("file", blob, filename);
  const link = await requestUpload<DownloadLinkResponse>(
    "/downloads/link",
    body,
  );
  const url = new URL(
    getApiUrl(link.url.replace(/^\/api/, "")),
    window.location.href,
  ).href;
  const minutes = Math.max(1, Math.round(link.expires_in / 60));

  modal.confirm({
    centered: true,
    icon: null,
    title: i18n.t("common.downloadLinkTitle", "下载链接已生成"),
    content: (
      <>
        <Typography.Paragraph type="secondary">
          {i18n.t("common.downloadLinkHint", { minutes })}
        </Typography.Paragraph>
        <Input.TextArea
          value={url}
          readOnly
          autoSize
          onFocus={(event) => event.target.select()}
        />
        <Typography.Link
          href={url}
          target="_blank"
          rel="noreferrer"
          style={{ display: "inline-block", marginTop: 8 }}
        >
          {link.filename}
        </Typography.Link>
      </>
    ),
    okText: i18n.t("common.copyLink", "复制链接"),
    cancelText: i18n.t("common.close", "关闭"),
    async onOk() {
      if (await copyText(url)) {
        message.success(i18n.t("common.copied", "已复制到剪贴板"));
      } else {
        message.error(i18n.t("common.copyFailed", "复制到剪贴板失败"));
      }
    },
  });
}
