/** React binding for the mock engine via useSyncExternalStore. */
import { useSyncExternalStore } from "react";
import { subscribe, getVersion, startEngine } from "./engine";

startEngine();

/** Re-renders the caller on every engine tick (2s). Cheap: version number. */
export function useLiveTick(): number {
  return useSyncExternalStore(subscribe, getVersion, getVersion);
}
