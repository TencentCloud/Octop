/** Shared model ref formatting — matches agent create/edit drawers. */

export interface ModelPickerOption {
  provider_name: string;
  model: string;
  name?: string;
}

/** Form / Select sentinel: empty string means auto (stored as null). */
export const MODEL_AUTO_VALUE = "";

export function modelRef(providerName: string, model: string): string {
  return `${providerName}/${model}`;
}

export function modelOptionValue(m: ModelPickerOption): string {
  return modelRef(m.provider_name, m.model);
}

export function modelOptionLabel(m: ModelPickerOption): string {
  return `${m.provider_name} / ${m.name || m.model}`;
}

export function buildModelSelectOptions(
  models: ModelPickerOption[],
  autoLabel: string,
): { label: string; value: string }[] {
  return [
    { label: autoLabel, value: MODEL_AUTO_VALUE },
    ...models.map((m) => ({
      label: modelOptionLabel(m),
      value: modelOptionValue(m),
    })),
  ];
}

/** Map form value to API payload (null = auto). */
export function defaultModelFromForm(
  value: string | null | undefined,
): string | null {
  if (!value || !value.trim()) return null;
  return value;
}

/** Map API value to form field (null/undefined = auto). */
export function defaultModelToForm(value: string | null | undefined): string {
  return value?.trim() ? value : MODEL_AUTO_VALUE;
}

export function modelShortLabel(modelRefValue: string): string {
  const slash = modelRefValue.lastIndexOf("/");
  if (slash < 0) return modelRefValue;
  return modelRefValue.slice(slash + 1);
}

/** Same text as the model picker, so the chat chip can tell two vendors apart. */
export function modelRefLabel(
  modelRefValue: string,
  models?: readonly ModelPickerOption[] | null,
): string {
  const ref = modelRefValue.trim();
  if (!ref) return "";
  const match = models?.find((item) => modelOptionValue(item) === ref);
  if (match) return modelOptionLabel(match);
  const slash = ref.indexOf("/");
  if (slash <= 0 || slash === ref.length - 1) return ref;
  return `${ref.slice(0, slash)} / ${ref.slice(slash + 1)}`;
}
