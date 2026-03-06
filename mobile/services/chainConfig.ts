/**
 * Per-chain configuration for WebView login.
 * Centralizes login URLs, cookie domains, and auth-check JS scripts.
 */

export interface ChainLoginConfig {
  slug: string;
  label: string;
  loginUrl: string;
  /** Domains whose cookies should be captured after login */
  cookieDomains: string[];
  /**
   * JavaScript to inject into the WebView to check if user is authenticated.
   * Must post a message via window.ReactNativeWebView.postMessage(JSON.stringify({ type, ...payload })).
   * type = "AUTH_CHECK", authenticated: boolean
   */
  authCheckScript: string;
  /**
   * JavaScript to inject to extract localStorage entries.
   * Posts { type: "LOCAL_STORAGE", entries: [{key, value}] }
   */
  localStorageScript: string;
}

const LOCAL_STORAGE_EXTRACT = `
(function() {
  try {
    var entries = [];
    for (var i = 0; i < localStorage.length; i++) {
      var key = localStorage.key(i);
      entries.push({ name: key, value: localStorage.getItem(key) });
    }
    window.ReactNativeWebView.postMessage(JSON.stringify({
      type: "LOCAL_STORAGE",
      entries: entries
    }));
  } catch (e) {
    window.ReactNativeWebView.postMessage(JSON.stringify({
      type: "LOCAL_STORAGE",
      entries: [],
      error: e.message
    }));
  }
})();
`;

export const CHAIN_LOGIN_CONFIGS: Record<string, ChainLoginConfig> = {
  esselunga: {
    slug: "esselunga",
    label: "Esselunga",
    loginUrl: "https://spesaonline.esselunga.it",
    cookieDomains: ["spesaonline.esselunga.it", ".esselunga.it"],
    authCheckScript: `
(async function() {
  try {
    var r = await fetch("https://spesaonline.esselunga.it/commerce/resources/nav/supermercato", {
      credentials: "include",
      headers: { "Accept": "application/json" }
    });
    if (!r.ok) {
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: "AUTH_CHECK", authenticated: false }));
      return;
    }
    var d = await r.json();
    window.ReactNativeWebView.postMessage(JSON.stringify({ type: "AUTH_CHECK", authenticated: true }));
  } catch (e) {
    window.ReactNativeWebView.postMessage(JSON.stringify({ type: "AUTH_CHECK", authenticated: false }));
  }
})();
`,
    localStorageScript: LOCAL_STORAGE_EXTRACT,
  },

  iperal: {
    slug: "iperal",
    label: "Iperal",
    loginUrl: "https://www.iperalspesaonline.it",
    cookieDomains: ["www.iperalspesaonline.it", ".iperalspesaonline.it"],
    authCheckScript: `
(async function() {
  try {
    var r = await fetch("https://www.iperalspesaonline.it/ebsn/api/auth/test", {
      credentials: "include",
      headers: { "Accept": "application/json" }
    });
    var d = await r.json();
    var userId = (d && d.data && d.data.user && d.data.user.userId) || (d && d.user && d.user.userId) || 0;
    window.ReactNativeWebView.postMessage(JSON.stringify({
      type: "AUTH_CHECK",
      authenticated: parseInt(userId, 10) > 0
    }));
  } catch (e) {
    window.ReactNativeWebView.postMessage(JSON.stringify({ type: "AUTH_CHECK", authenticated: false }));
  }
})();
`,
    localStorageScript: LOCAL_STORAGE_EXTRACT,
  },
};

export function getChainConfig(slug: string): ChainLoginConfig | undefined {
  return CHAIN_LOGIN_CONFIGS[slug];
}
