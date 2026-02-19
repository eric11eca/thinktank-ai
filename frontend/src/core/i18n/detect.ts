import type { Locale } from "@/core/i18n";

/**
 * Detect locale on the client side
 * Priority: localStorage > cookie > browser preference > default
 */
export function detectLocaleClient(): Locale {
  // Check localStorage first
  const stored = localStorage.getItem("locale");
  if (stored === "en-US" || stored === "zh-CN") {
    return stored;
  }

  // Check cookie
  const cookieMatch = document.cookie.match(/locale=(en-US|zh-CN)/);
  if (cookieMatch?.[1]) {
    return cookieMatch[1] as Locale;
  }

  // Fall back to browser preference
  const browserLang = navigator.language;
  if (browserLang.startsWith("zh")) {
    return "zh-CN";
  }

  return "en-US";
}
