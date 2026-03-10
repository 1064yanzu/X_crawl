export const THEME_STORAGE_KEY = "xcrawl-theme";

export type ThemeMode = "light" | "dark";

export function applyTheme(mode: ThemeMode) {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
}

export const THEME_INIT_SCRIPT = `(() => {
  try {
    const storageKey = ${JSON.stringify(THEME_STORAGE_KEY)};
    const stored = window.localStorage.getItem(storageKey);
    const systemDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const mode = stored === 'dark' || stored === 'light' ? stored : (systemDark ? 'dark' : 'light');
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.colorScheme = mode;
  } catch {
    document.documentElement.dataset.theme = 'light';
    document.documentElement.style.colorScheme = 'light';
  }
})();`;
