/**
 * KORA Settings Store — persistent user preferences (V2).
 *
 * Establishes the persistence pattern for KORA: settings are mirrored to
 * localStorage (instant local read) AND synced to the backend (settings.json)
 * so auto-start / wake-word preferences survive across browsers and the
 * Python desktop agent can read them too.
 *
 * Pattern follows the existing codebase conventions: plain state + ref mirrors.
 * No Context/Zustand — this is deliberately lightweight to match audio.ts/memoryTypes.ts.
 */

export interface KoraSettings {
  /** Launch KORA (backends + browser tab) silently on Windows login. */
  autoStart: boolean;
  /** Enable the always-listening wake-word detector. */
  wakeWordEnabled: boolean;
  /** Phrase that activates KORA (case-insensitive substring match). */
  wakePhrase: string;
  /** Preferred microphone device id ("" = system default). */
  micDeviceId: string;
  /** Wake-word sensitivity: 0 (strict) .. 100 (loose). Affects debounce window. */
  sensitivity: number;
  /** Master toggle for UI animations. */
  animations: boolean;
  /** Selected Gemini Live voice name. */
  voice: string;
  /** Selected background video filename. */
  backgroundVideo: string;
  /** Avatar style ("character" or "orb"). */
  avatarStyle: "character" | "orb";
}

export const GEMINI_VOICES = [
  { id: "Aoede", label: "Aoede (Default)", desc: "Warm and natural" },
  { id: "Charon", label: "Charon", desc: "Deep and authoritative" },
  { id: "Fenrir", label: "Fenrir", desc: "Bold and confident" },
  { id: "Kore", label: "Kore", desc: "Soft and gentle" },
  { id: "Leda", label: "Leda", desc: "Calm and composed" },
  { id: "Puck", label: "Puck", desc: "Energetic and playful" },
  { id: "Zephyr", label: "Zephyr", desc: "Light and breezy" },
] as const;

export const DEFAULT_SETTINGS: KoraSettings = {
  autoStart: false,
  wakeWordEnabled: false,
  wakePhrase: "hey kora",
  micDeviceId: "",
  sensitivity: 60,
  animations: true,
  // "Kore" is Gemini's soft/female prebuilt voice (Charon is deep/male).
  voice: "Kore",
  backgroundVideo: "solid",
  // "character" renders the 3D golden holographic particle core; "orb" is the plasma orb.
  avatarStyle: "character",
};

const STORAGE_KEY = "kora.settings.v2";

/** Settings keys that the browser should never persist (security). */
const NEVER_PERSIST: ReadonlySet<keyof KoraSettings> = new Set([]);

/**
 * Load settings from localStorage, merged over defaults so new keys always
 * have a sane value even when an older payload is present.
 */
export function loadSettings(): KoraSettings {
  if (typeof window === "undefined") return { ...DEFAULT_SETTINGS };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const parsed = JSON.parse(raw) as Partial<KoraSettings>;
    const merged: KoraSettings = { ...DEFAULT_SETTINGS, ...parsed };
    // Rename migration: the assistant used to be called ELYSIA, now KORA.
    // Any stored wake phrase that still mentions the old name is upgraded.
    // (The old check looked for "kora" and would wrongly reset a custom
    // phrase like "hey kora wake up" back to the default.)
    if (typeof merged.wakePhrase === "string" && merged.wakePhrase.toLowerCase().includes("elysia")) {
      merged.wakePhrase = DEFAULT_SETTINGS.wakePhrase;
    }
    // Voice migration: the old default "Charon" is a deep MALE voice — the
    // assistant is a girl now, so move anyone still on it to the female "Kore".
    if (merged.voice === "Charon") {
      merged.voice = DEFAULT_SETTINGS.voice;
    }
    // Avatar migration: old default was the orb; show the anime character.
    if (merged.avatarStyle === "orb") {
      merged.avatarStyle = DEFAULT_SETTINGS.avatarStyle;
    }
    return merged;
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

/**
 * Persist a full or partial settings update to localStorage.
 * Returns the fully merged settings object.
 */
export function saveSettings(patch: Partial<KoraSettings>): KoraSettings {
  const current = loadSettings();
  const next: KoraSettings = { ...current, ...patch };
  if (typeof window !== "undefined") {
    try {
      // Strip any sensitive keys before writing to localStorage.
      const safe: Record<string, unknown> = {};
      (Object.keys(next) as (keyof KoraSettings)[]).forEach((k) => {
        if (!NEVER_PERSIST.has(k)) safe[k] = next[k];
      });
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(safe));
    } catch {
      /* localStorage may be unavailable (private mode) — fail silently. */
    }
  }
  // Best-effort sync to backend so the Python agent can read auto-start state.
  void syncSettingsToBackend(next).catch(() => {});
  return next;
}

/** Push settings to the backend (src/server/index.ts persists to settings.json). */
async function syncSettingsToBackend(settings: KoraSettings): Promise<void> {
  try {
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
  } catch {
    /* Backend may be briefly unavailable during boot — non-fatal. */
  }
}
