import type { ComponentProps } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CurrentUserProvider } from "../../../../../hooks/useCurrentUser";
import type { OctopUser } from "../../../../../api/modules/auth";
import { ModelDefaults } from "./ModelDefaults";
import { ActiveModelPool } from "./ActiveModelPool";

const { request, errorMessage } = vi.hoisted(() => ({
  request: vi.fn(),
  errorMessage: vi.fn(),
}));

vi.mock("../../../../../api/request", () => ({
  request,
  bridgeAgentHeaders: () => ({}),
}));

vi.mock("../../../../../utils/antdMessage", () => ({
  message: { success: vi.fn(), error: errorMessage },
}));

const admin: OctopUser = {
  id: 1,
  username: "admin",
  display_name: null,
  role: "admin",
  locale: "en",
};
const globalModel = { provider_name: "OpenRouter", model: "global/model" };
const models = [
  { ...globalModel, provider_id: 1, provider_kind: "openai", name: "Global" },
  {
    provider_id: 1,
    provider_name: "OpenRouter",
    provider_kind: "openai",
    model: "org/next/model",
    name: "Next",
  },
  {
    provider_id: 2,
    provider_name: "Other",
    provider_kind: "openai",
    model: "chat/model",
    name: "Chat",
  },
];
const onSaved = vi.fn();

function renderDefaults(
  props: Partial<ComponentProps<typeof ModelDefaults>> = {},
  user = admin,
) {
  return render(
    <CurrentUserProvider user={user} setUser={vi.fn()}>
      <ModelDefaults
        globalActiveModel={globalModel}
        preferredModel="Other/chat/model"
        resolvedModels={models}
        onSaved={onSaved}
        {...props}
      />
    </CurrentUserProvider>,
  );
}

beforeEach(() => {
  request.mockReset().mockResolvedValue({});
  onSaved.mockReset();
  errorMessage.mockReset();
});

describe("ModelDefaults", () => {
  it("shows both defaults and explains when the chat preference overrides the global one", () => {
    renderDefaults();
    expect(screen.getByText("OpenRouter / Global")).toBeVisible();
    expect(screen.getByText("Other / Chat")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "models.chatModelOverrideWarning",
    );
  });

  it.each(["", "OpenRouter/global/model"])(
    "does not warn when the chat preference is %j",
    (preferredModel) => {
      renderDefaults({ preferredModel });
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      if (!preferredModel) {
        expect(screen.getByText("models.followsGlobalModel")).toBeVisible();
      }
    },
  );

  it("saves only the global default, preserves model IDs containing slashes, and refreshes", async () => {
    const user = userEvent.setup();
    renderDefaults();
    await user.click(
      screen.getByRole("button", { name: "models.changeGlobalModel" }),
    );
    const save = screen.getByRole("button", { name: "common.save" });
    expect(save).toBeDisabled();
    await user.click(
      screen.getByRole("combobox", { name: "models.globalActiveModel" }),
    );
    await user.click(screen.getByText("OpenRouter / Next"));
    await user.click(save);

    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(request).toHaveBeenCalledExactlyOnceWith("/providers/active-model", {
      method: "PUT",
      body: JSON.stringify({
        provider_name: "OpenRouter",
        model: "org/next/model",
      }),
    });
    expect(screen.getByText("Other / Chat")).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });

  it("does not save a cancelled selection", async () => {
    const user = userEvent.setup();
    renderDefaults();
    await user.click(
      screen.getByRole("button", { name: "models.changeGlobalModel" }),
    );
    await user.click(
      screen.getByRole("combobox", { name: "models.globalActiveModel" }),
    );
    await user.click(screen.getByText("OpenRouter / Next"));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(request).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("keeps the current defaults and the dialog when saving fails", async () => {
    request.mockRejectedValue(new Error("Permission denied"));
    const user = userEvent.setup();
    renderDefaults();
    await user.click(
      screen.getByRole("button", { name: "models.changeGlobalModel" }),
    );
    await user.click(
      screen.getByRole("combobox", { name: "models.globalActiveModel" }),
    );
    await user.click(screen.getByText("OpenRouter / Next"));
    await user.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() =>
      expect(errorMessage).toHaveBeenCalledWith("Permission denied"),
    );
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(
      screen.getByText("models.personalChatModel:").parentElement,
    ).toHaveTextContent("Other / Chat");
  });

  it("shows the default without allowing users lacking providers permission to edit it", () => {
    renderDefaults(
      {},
      { ...admin, role: "user", permissions: ["ollama_models"] },
    );
    expect(screen.getByText("OpenRouter / Global")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "models.changeGlobalModel" }),
    ).not.toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
  });

  it("allows a non-admin with providers permission to edit the global default", () => {
    renderDefaults({}, { ...admin, role: "user", permissions: ["providers"] });
    expect(
      screen.getByRole("button", { name: "models.changeGlobalModel" }),
    ).toBeEnabled();
  });

  it("handles an unset default and disables editing when no models are available", () => {
    renderDefaults({
      globalActiveModel: { provider_name: "", model: "" },
      preferredModel: "",
      resolvedModels: [],
    });
    expect(screen.getByText("models.globalModelNotSet")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "models.changeGlobalModel" }),
    ).toBeDisabled();
  });
});

describe("ActiveModelPool chat preference", () => {
  it.each(["", "Other/chat/model"])(
    "writes only the personal preference when starring the global model (previous preference %j)",
    async (preferredModel) => {
      const user = userEvent.setup();
      render(
        <ActiveModelPool
          resolvedModels={models}
          preferredModel={preferredModel}
          providers={[]}
          modelReasoning={{}}
          onSaved={onSaved}
        />,
      );
      await user.click(
        screen.getByRole("button", {
          name: "models.setAsPreferred: OpenRouter / Global",
        }),
      );

      await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
      expect(request).toHaveBeenCalledExactlyOnceWith("/preferences", {
        method: "PATCH",
        body: JSON.stringify({ preferred_model: "OpenRouter/global/model" }),
      });
    },
  );
});
