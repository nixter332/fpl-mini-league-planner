// Which app's built-in browser the page is open in, if any (LinkedIn, Facebook, Instagram, ...).
// Google refuses sign-in inside these ("disallowed_useragent"), so the optional sign-in is hidden
// there, and analytics records it so we can see where visitors come from.

const APPS: [RegExp, string][] = [
  [/LinkedInApp/i, "linkedin"],
  [/FBAN|FBAV|FB_IAB/i, "facebook"],
  [/Instagram/i, "instagram"],
  [/\bLine\//i, "line"],
  [/Snapchat/i, "snapchat"],
  [/Twitter|TwitterAndroid/i, "x"],
  [/\bWhatsApp/i, "whatsapp"],
  [/; wv\)/i, "android-webview"], // any other Android app's embedded browser
];

/** "linkedin", "facebook", … for an app's built-in browser; null for a normal browser. */
export function inAppBrowser(userAgent: string): string | null {
  for (const [pattern, name] of APPS) if (pattern.test(userAgent)) return name;
  return null;
}
