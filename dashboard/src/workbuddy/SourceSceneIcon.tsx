import icons from "./generated/scene-icons.json";
import type { WelcomeScene } from "./SceneTabs";

/** Original 5.5.6 SVG geometry, extracted as data; no source app runtime. */
export default function SourceSceneIcon({ scene }: { scene: WelcomeScene }) {
  const icon = icons[scene];
  return (
    <svg
      width={16}
      height={16}
      viewBox={icon.viewBox}
      fill="none"
      aria-hidden="true"
    >
      <path
        d={icon.path.d}
        transform={icon.path.transform}
        fill={icon.path.fill}
        fillRule={
          "fillRule" in icon.path && icon.path.fillRule === "evenodd"
            ? "evenodd"
            : undefined
        }
      />
    </svg>
  );
}
