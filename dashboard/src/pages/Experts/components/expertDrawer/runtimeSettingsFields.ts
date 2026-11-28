import type { FormInstance } from "antd";
import { AGENT_RUNTIME_CONFIG_KEYS } from "@/utils/agentRuntimeConfig";

export const runtimeSettingsFields = [
  ...AGENT_RUNTIME_CONFIG_KEYS,
  ...[
    "model",
    "enabled",
    "trigger_fraction",
    "keep_fraction",
    "trim_tokens",
  ].map((field) => ["compaction", field]),
];

export function hasRuntimeSettingsErrors(
  form: Pick<FormInstance, "getFieldsError">,
) {
  return form
    .getFieldsError()
    .some(
      ({ name, errors }) =>
        errors.length > 0 &&
        (name[0] === "compaction" ||
          AGENT_RUNTIME_CONFIG_KEYS.some((field) => field === name[0])),
    );
}
