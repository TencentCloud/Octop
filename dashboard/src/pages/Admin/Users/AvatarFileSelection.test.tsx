import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileAvatarPicker } from "./ProfileAvatar";
import ExpertAvatarPicker from "../../Experts/components/ExpertAvatarPicker";

vi.mock("../../../hooks/useAuthImageSrc", () => ({
  useAuthImageSrc: (url: string) => ({ src: url, loadState: "ready" }),
}));

vi.mock("../../Chat/components/ExpertAgentAvatar", () => ({
  default: ({ iconUrl }: { iconUrl?: string | null }) =>
    iconUrl ? <img src={iconUrl} alt="avatar" /> : null,
}));

beforeEach(() => {
  vi.stubGlobal("URL", {
    createObjectURL: vi.fn(() => "blob:avatar-preview"),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe.each([
  { name: "user", Picker: ProfileAvatarPicker, kind: "user" },
  { name: "role", Picker: ProfileAvatarPicker, kind: "role" },
  { name: "expert", Picker: ExpertAvatarPicker, kind: undefined },
] as const)("$name avatar file selection", ({ Picker, kind }) => {
  it("opens a mounted input synchronously and keeps it through upload", async () => {
    let finishUpload!: () => void;
    const onPick = vi.fn(
      () => new Promise<void>((resolve) => (finishUpload = resolve)),
    );
    const { container, unmount } = render(
      <Picker kind={kind} onPick={onPick} />,
    );
    let connectedDuringClick = false;
    const click = vi
      .spyOn(HTMLInputElement.prototype, "click")
      .mockImplementation(function (this: HTMLInputElement) {
        connectedDuringClick = this.isConnected;
      });
    fireEvent.click(
      screen.getByRole("button", { name: "experts.avatarUpload" }),
    );
    expect(click).toHaveBeenCalledOnce();
    expect(connectedDuringClick).toBe(true);
    const input =
      container.querySelector<HTMLInputElement>('input[type="file"]')!;
    expect(click.mock.instances[0]).toBe(input);

    const file = new File(["png"], "avatar.png", { type: "image/png" });
    await userEvent.upload(input, file);
    expect(onPick).toHaveBeenCalledWith(file);
    expect(input.isConnected).toBe(true);
    expect(
      screen.getByRole("button", { name: "experts.avatarChange" }),
    ).toBeInTheDocument();
    finishUpload();
    unmount();
    expect(input.isConnected).toBe(false);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:avatar-preview");
  });

  it("allows choosing again after cancelling the dialog", async () => {
    const onPick = vi.fn();
    const { container } = render(<Picker kind={kind} onPick={onPick} />);
    const input =
      container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const button = screen.getByRole("button", { name: "experts.avatarUpload" });
    await userEvent.click(button);
    fireEvent(input, new Event("cancel"));
    expect(onPick).not.toHaveBeenCalled();

    await userEvent.click(button);
    const file = new File(["jpeg"], "avatar.jpg", { type: "image/jpeg" });
    await userEvent.upload(input, file);
    expect(onPick).toHaveBeenCalledExactlyOnceWith(file);
  });

  it("clears the failed preview and permits retrying the same file", async () => {
    const onPick = vi
      .fn()
      .mockRejectedValueOnce(new Error("upload failed"))
      .mockResolvedValue(undefined);
    const { container } = render(<Picker kind={kind} onPick={onPick} />);
    const input =
      container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const file = new File(["png"], "avatar.png", { type: "image/png" });
    await userEvent.click(
      screen.getByRole("button", { name: "experts.avatarUpload" }),
    );
    await userEvent.upload(input, file);
    await waitFor(() => expect(onPick).toHaveBeenCalledOnce());
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:avatar-preview");
    await userEvent.click(
      await screen.findByRole("button", { name: "experts.avatarUpload" }),
    );
    expect(input.value).toBe("");
    // userEvent skips a change for an identical selection unless the input resets.
    await userEvent.upload(input, file);
    expect(onPick).toHaveBeenCalledTimes(2);
    expect(onPick).toHaveBeenLastCalledWith(file);
    expect(
      screen.getByRole("button", { name: "experts.avatarChange" }),
    ).toBeInTheDocument();
  });
});
