import { useCallback, useState } from "react";

import {
  getLocalSettings,
  saveLocalSettings,
  type LocalSettings,
} from "./local";

export function useLocalSettings(): [
  LocalSettings,
  (
    key: keyof LocalSettings,
    value: Partial<LocalSettings[keyof LocalSettings]>,
  ) => void,
] {
  const [state, setState] = useState<LocalSettings>(() => getLocalSettings());
  const setter = useCallback(
    (
      key: keyof LocalSettings,
      value: Partial<LocalSettings[keyof LocalSettings]>,
    ) => {
      setState((prev) => {
        const newState = {
          ...prev,
          [key]: {
            ...prev[key],
            ...value,
          },
        };
        saveLocalSettings(newState);
        return newState;
      });
    },
    [],
  );
  return [state, setter];
}
