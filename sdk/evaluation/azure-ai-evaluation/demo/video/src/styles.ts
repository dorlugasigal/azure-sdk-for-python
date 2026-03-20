export const COLORS = {
  bg: "#0d1117",
  bgLight: "#161b22",
  bgCode: "#1a1e26",
  text: "#e6edf3",
  textMuted: "#8b949e",
  accent: "#58a6ff",
  accentGreen: "#3fb950",
  accentOrange: "#d29922",
  accentRed: "#f85149",
  accentPurple: "#bc8cff",
  border: "#30363d",
  terminal: "#0d1117",
  terminalGreen: "#3fb950",
  terminalYellow: "#d29922",
  terminalCyan: "#79c0ff",
  terminalRed: "#f85149",
  terminalWhite: "#e6edf3",
};

export const FONTS = {
  mono: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
  sans: "'Inter', 'Segoe UI', system-ui, sans-serif",
};

export const FPS = 30;

export const SCENE_DURATIONS = {
  title: 143,         // 4.8s — matches title audio clip
  yamlConfig: 900,    // 30s — config (20.3s) + metric (8.7s) + gap
  localAndView: 565,  // 18.8s — real screen recording
  remoteAndDashboard: 1177, // 39.2s — real screen recording
  outro: 60,          // 2s — black fade + thanks
} as const;

export const TOTAL_FRAMES = Object.values(SCENE_DURATIONS).reduce((a, b) => a + b, 0); // 1830
