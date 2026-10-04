import SourceSceneIcon from "./SourceSceneIcon";
import { useTranslation } from "react-i18next";

export type WelcomeScene = "work" | "code" | "creative";
const SCENES = [{ id: "work" }, { id: "code" }, { id: "creative" }] as const;

export default function SceneTabs({
  value,
  onChange,
}: {
  value: WelcomeScene;
  onChange: (scene: WelcomeScene) => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="wb-scene-tabs"
      role="group"
      aria-label={t("workbuddy.sceneLabel")}
    >
      {SCENES.map(({ id }) => (
        <button
          key={id}
          type="button"
          className={`wb-scene-tabs__pill${
            value === id ? " wb-scene-tabs__pill--active" : ""
          }`}
          aria-pressed={value === id}
          onClick={() => onChange(id)}
        >
          <span className="wb-scene-tabs__icon" aria-hidden="true">
            <SourceSceneIcon scene={id} />
          </span>
          <span>{t(`workbuddy.scenes.${id}`)}</span>
        </button>
      ))}
    </div>
  );
}
