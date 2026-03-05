import { ScrollViewStyleReset } from "expo-router/html";
import type { PropsWithChildren } from "react";

export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="it">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no"
        />

        {/* PWA meta tags */}
        <meta name="theme-color" content="#1B5E20" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="SpesaSmart" />
        <meta
          name="description"
          content="Confronto prezzi supermercati - Monza e Brianza"
        />

        {/* PWA manifest */}
        <link rel="manifest" href="/manifest.json" />

        {/* PWA icons */}
        <link rel="icon" type="image/png" sizes="192x192" href="/pwa-icons/icon-192.png" />
        <link rel="apple-touch-icon" sizes="192x192" href="/pwa-icons/icon-192.png" />

        <ScrollViewStyleReset />

        {/* Web-specific global styles */}
        <style dangerouslySetInnerHTML={{ __html: `
          html, body, #root {
            height: 100%;
            margin: 0;
            padding: 0;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
          }
          body {
            overflow: hidden;
          }
          #root {
            display: flex;
            flex-direction: column;
          }
        `}} />
      </head>
      <body>{children}</body>
    </html>
  );
}
