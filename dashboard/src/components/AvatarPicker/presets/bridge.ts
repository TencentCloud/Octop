import {
  Cloud,
  CloudCog,
  Cloudy,
  Globe,
  Home,
  Laptop,
  MapPin,
  Monitor,
  RadioTower,
  Satellite,
  Server,
  Wifi,
} from "lucide-react";

import type { AvatarPreset } from "../types";

/** Prefabricated Lucide icons for Bridge connections (``icon_name``). */
export const BRIDGE_AVATAR_PRESETS: AvatarPreset[] = [
  {
    id: "cloudy",
    labelKey: "advancedSettings.bridge.iconLabels.cloudy",
    Icon: Cloudy,
    tone: "plain",
  },
  {
    id: "cloud",
    labelKey: "advancedSettings.bridge.iconLabels.cloud",
    Icon: Cloud,
    tone: "plain",
  },
  {
    id: "cloud-cog",
    labelKey: "advancedSettings.bridge.iconLabels.cloud-cog",
    Icon: CloudCog,
    tone: "plain",
  },
  {
    id: "globe",
    labelKey: "advancedSettings.bridge.iconLabels.globe",
    Icon: Globe,
    tone: "plain",
  },
  {
    id: "home",
    labelKey: "advancedSettings.bridge.iconLabels.home",
    Icon: Home,
    tone: "plain",
  },
  {
    id: "laptop",
    labelKey: "advancedSettings.bridge.iconLabels.laptop",
    Icon: Laptop,
    tone: "plain",
  },
  {
    id: "monitor",
    labelKey: "advancedSettings.bridge.iconLabels.monitor",
    Icon: Monitor,
    tone: "plain",
  },
  {
    id: "server",
    labelKey: "advancedSettings.bridge.iconLabels.server",
    Icon: Server,
    tone: "plain",
  },
  {
    id: "radio-tower",
    labelKey: "advancedSettings.bridge.iconLabels.radio-tower",
    Icon: RadioTower,
    tone: "plain",
  },
  {
    id: "wifi",
    labelKey: "advancedSettings.bridge.iconLabels.wifi",
    Icon: Wifi,
    tone: "plain",
  },
  {
    id: "satellite",
    labelKey: "advancedSettings.bridge.iconLabels.satellite",
    Icon: Satellite,
    tone: "plain",
  },
  {
    id: "map-pin",
    labelKey: "advancedSettings.bridge.iconLabels.map-pin",
    Icon: MapPin,
    tone: "plain",
  },
];

export const DEFAULT_BRIDGE_AVATAR_ICON = "cloudy";
