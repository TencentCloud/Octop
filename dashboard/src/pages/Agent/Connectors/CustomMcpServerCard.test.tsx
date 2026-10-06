import { useState } from "react";
import { App } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CustomMcpServerCard } from "./CustomMcpServerCard";
import { newCard, type ServerCardState } from "./customMcpUtils";

const PEM =
  "-----BEGIN CERTIFICATE-----\ntest-public-certificate\n-----END CERTIFICATE-----";

function renderEditor() {
  const onUpdate = vi.fn();
  function Editor() {
    const [card, setCard] = useState({
      ...newCard("streamable_http", 0),
      url: "https://mcp.example.com/mcp",
    });
    return (
      <App>
        <CustomMcpServerCard
          card={card}
          probing={false}
          transportOptions={[]}
          onUpdate={(key: string, patch: Partial<ServerCardState>) => {
            onUpdate(key, patch);
            setCard((previous) => ({ ...previous, ...patch }));
          }}
          onToggleEnabled={() => undefined}
          onRemove={() => undefined}
          onProbe={() => undefined}
        />
      </App>
    );
  }
  const rendered = render(<Editor />);
  return { ...rendered, onUpdate };
}

describe("custom MCP certificate upload", () => {
  it("only shows upload after opting in, and clears certificate trust when disabled", async () => {
    const { container, onUpdate } = renderEditor();
    expect(
      screen.queryByRole("button", { name: "上传证书" }),
    ).not.toBeInTheDocument();
    const checkbox = screen.getByRole("checkbox", {
      name: "使用自签名／私有 CA 证书",
    });
    fireEvent.click(checkbox);
    expect(
      screen.getByRole("button", { name: "上传证书" }),
    ).toBeInTheDocument();

    const file = new File([PEM], "private.crt", {
      type: "application/x-pem-file",
    });
    Object.defineProperty(file, "text", { value: () => Promise.resolve(PEM) });
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(screen.getByText("private.crt")).toBeInTheDocument(),
    );
    expect(onUpdate).toHaveBeenLastCalledWith(expect.any(String), {
      caCert: PEM,
      caCertName: "private.crt",
    });

    fireEvent.click(checkbox);
    expect(onUpdate).toHaveBeenLastCalledWith(expect.any(String), {
      useCustomCertificate: false,
      caCert: "",
      caCertName: "",
    });
    expect(
      screen.queryByRole("button", { name: "上传证书" }),
    ).not.toBeInTheDocument();
  });

  it("rejects private-key files before sending certificate data", async () => {
    const { container, onUpdate } = renderEditor();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "使用自签名／私有 CA 证书" }),
    );
    const file = new File(["private key"], "private.pem");
    Object.defineProperty(file, "text", {
      value: () => Promise.resolve("-----BEGIN PRIVATE KEY-----\nsecret"),
    });
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(
        screen.getByText("请上传 PEM 格式的证书文件，不要包含私钥"),
      ).toBeInTheDocument(),
    );
    expect(onUpdate).toHaveBeenCalledTimes(1);
  });
});
