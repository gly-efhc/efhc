import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" data-theme="dark">
      <Head>
        <script src="/public-runtime-config.js" />
        <meta name="theme-color" content="#0a0a0f" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, viewport-fit=cover"
        />
        <meta name="color-scheme" content="dark light" />
        <meta name="format-detection" content="telephone=no" />
        <link
          rel="preload"
          as="image"
          href="/assets/efhc/responsive/efhc_coin_128.avif"
          type="image/avif"
          fetchPriority="high"
        />
        <style id="efhc-first-paint-css">
          {`
            html,body,#_next{
              min-height:100%;
              background:#0a0a0f;
              color:#fff;
            }
            body{
              margin:0;
              overflow-x:hidden;
            }
          `}
        </style>
        <script src="https://telegram.org/js/telegram-web-app.js" async />
      </Head>
      <body className="efhc-first-paint-body">
        <noscript>
          <div
            style={{
              background: "#0a0a0f",
              color: "#ffffff",
              minHeight: "100vh",
              padding: "24px",
              fontFamily: "Arial, Helvetica Neue, Helvetica, sans-serif",
            }}
          >
            EFHC needs JavaScript to run the WebApp.
          </div>
        </noscript>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
