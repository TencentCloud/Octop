import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";
import { describe, expect, it, vi } from "vitest";
import { ModelListEditor } from "./ModelListEditor";
import type { ProviderModel, ProviderRow } from "../../useProviders";

function renderEditor(models: ProviderModel[]) {
  const provider: ProviderRow = {
    id: 1,
    name: "mindie",
    kind: "openai",
    base_url: "http://10.0.0.8/v1",
    api_key: "sk-test",
    models,
    note: null,
    enabled: true,
  };
  return render(
    <App>
      <ModelListEditor
        provider={provider}
        models={models}
        onModelsChange={vi.fn()}
        canTest={false}
      />
    </App>,
  );
}

describe("ModelListEditor", () => {
  it("scrolls to the edit form after clicking edit", async () => {
    const user = userEvent.setup();
    const scrollIntoView = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollIntoView;
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    renderEditor([
      { id: "qwen", name: "Qwen", enabled: true, input: ["text"] },
    ]);

    await user.click(screen.getByRole("button", { name: "models.editModel" }));
    expect(await screen.findByDisplayValue("qwen")).toBeInTheDocument();
    expect(scrollIntoView).toHaveBeenCalled();
    expect(screen.getByText("models.purposeChat")).toBeInTheDocument();
    expect(screen.queryByText("models.reasoning")).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "models.showAdvanced" }),
    );
    expect(screen.getByText("models.reasoning")).toBeInTheDocument();
  });
});
