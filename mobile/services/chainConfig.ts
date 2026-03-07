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
    loginUrl: "https://www.esselunga.it/area-utenti/ist35/myesselunga/shoppingMovements",
    cookieDomains: ["www.esselunga.it", ".esselunga.it"],
    authCheckScript: `
(function() {
  try {
    var href = window.location.href.toLowerCase();
    var onAreaUtenti = href.indexOf("area-utenti") !== -1 || href.indexOf("myesselunga") !== -1;
    var onLogin = href.indexOf("login") !== -1 || href.indexOf("signin") !== -1 || href.indexOf("accedi") !== -1;
    var authenticated = onAreaUtenti && !onLogin;
    window.ReactNativeWebView.postMessage(JSON.stringify({ type: "AUTH_CHECK", authenticated: authenticated }));
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
