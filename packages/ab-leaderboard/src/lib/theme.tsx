/**
 * Theme + density + view-variant context.
 *
 * Applies side-effects to <html>:
 *   - class `.theme-dark` / `.theme-light`
 *   - attribute `data-density="compact|regular|comfortable"`
 *
 * Persists to localStorage. Read once on mount.
 */

import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type ThemeMode = "dark" | "light";
export type Density = "compact" | "regular" | "comfortable";
export type LeaderboardView = "matrix" | "cards";
export type TrajectoryLayout = "three-pane" | "stacked";

export interface ThemeState {
  theme: ThemeMode;
  density: Density;
  leaderboardView: LeaderboardView;
  trajectoryLayout: TrajectoryLayout;
}

export interface ThemeContextValue extends ThemeState {
  setTheme: (v: ThemeMode) => void;
  toggleTheme: () => void;
  setDensity: (v: Density) => void;
  setLeaderboardView: (v: LeaderboardView) => void;
  setTrajectoryLayout: (v: TrajectoryLayout) => void;
}

const DEFAULT_STATE: ThemeState = {
  theme: "dark",
  density: "regular",
  leaderboardView: "matrix",
  trajectoryLayout: "three-pane",
};

const STORAGE_KEY = "ab-leaderboard.theme";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(): ThemeState {
  if (typeof window === "undefined") return DEFAULT_STATE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_STATE;
    const parsed = JSON.parse(raw) as Partial<ThemeState>;
    return { ...DEFAULT_STATE, ...parsed };
  } catch {
    return DEFAULT_STATE;
  }
}

function writeStored(state: ThemeState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* localStorage full or disabled — silently drop. */
  }
}

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [state, setState] = useState<ThemeState>(() => readStored());

  useEffect(() => {
    const html = document.documentElement;
    html.classList.toggle("theme-dark", state.theme === "dark");
    html.classList.toggle("theme-light", state.theme === "light");
    html.classList.toggle("dark", state.theme === "dark");
    html.setAttribute("data-density", state.density);
    writeStored(state);
  }, [state]);

  const setTheme = useCallback((theme: ThemeMode) => setState((s) => ({ ...s, theme })), []);
  const toggleTheme = useCallback(
    () => setState((s) => ({ ...s, theme: s.theme === "dark" ? "light" : "dark" })),
    [],
  );
  const setDensity = useCallback((density: Density) => setState((s) => ({ ...s, density })), []);
  const setLeaderboardView = useCallback(
    (leaderboardView: LeaderboardView) => setState((s) => ({ ...s, leaderboardView })),
    [],
  );
  const setTrajectoryLayout = useCallback(
    (trajectoryLayout: TrajectoryLayout) => setState((s) => ({ ...s, trajectoryLayout })),
    [],
  );

  const value = useMemo<ThemeContextValue>(
    () => ({ ...state, setTheme, toggleTheme, setDensity, setLeaderboardView, setTrajectoryLayout }),
    [state, setTheme, toggleTheme, setDensity, setLeaderboardView, setTrajectoryLayout],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
