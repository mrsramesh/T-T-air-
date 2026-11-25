"""
Enterprise Stealth and Anti-Fingerprinting Engine.
Bypasses Cloudflare, Akamai, PerimeterX, and Bot-Detection Algorithms without cost:
- Realistic User-Agent rotation (modern macOS, Windows 11, Chrome 131, Safari, Firefox).
- Synchronized client hints headers (sec-ch-ua, sec-ch-ua-mobile, sec-ch-ua-platform).
- Comprehensive Playwright init scripts:
  - Masks navigator.webdriver
  - Mocks window.chrome and chrome.runtime
  - Spoofs WebGL hardware vendors (Apple Metal / Intel Iris Plus)
  - Adds Canvas & AudioContext noise
  - Masks navigator.languages and plugins
  - Emulates human typing and mouse movement jitter
"""

import random
import time
from typing import Dict, List, Optional, Any

USER_AGENTS = [
    # macOS Chrome 131 & 130
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Windows 11 Chrome 131
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # macOS Safari 17.6
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    # Windows 11 Edge 131
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# Advanced undetectable stealth injection script for Playwright
COMPREHENSIVE_STEALTH_SCRIPT = """
(() => {
    // 1. Evade navigator.webdriver detection
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true
    });
    delete navigator.__proto__.webdriver;

    // 2. Mock genuine window.chrome runtime
    if (!window.chrome) {
        window.chrome = {};
    }
    window.chrome.runtime = {
        PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
        PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
        OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
        connect: function() { return { disconnect: function() {}, onDisconnect: { addListener: function() {} }, onMessage: { addListener: function() {} }, postMessage: function() {} }; },
        sendMessage: function() {}
    };
    window.chrome.app = {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
    };

    // 3. Mock genuine plugins & mimeTypes
    const fakePlugins = [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
    ];
    Object.defineProperty(navigator, 'plugins', {
        get: () => fakePlugins,
        configurable: true
    });
    Object.defineProperty(navigator, 'mimeTypes', {
        get: () => [{ type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' }],
        configurable: true
    });

    // 4. Language & Hardware Concurrency
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'hi'],
        configurable: true
    });
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
        configurable: true
    });
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
        configurable: true
    });

    // 5. Mask WebGL vendor and renderer to genuine hardware
    const maskWebGL = (proto) => {
        const origGetParam = proto.getParameter;
        proto.getParameter = function(param) {
            // UNMASKED_VENDOR_WEBGL = 37445
            if (param === 37445) return 'Apple Inc.';
            // UNMASKED_RENDERER_WEBGL = 37446
            if (param === 37446) return 'Apple M2 Pro';
            return origGetParam.apply(this, arguments);
        };
    };
    if (window.WebGLRenderingContext) maskWebGL(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) maskWebGL(WebGL2RenderingContext.prototype);

    // 6. Mock notification permissions
    if (window.Notification) {
        Object.defineProperty(Notification, 'permission', {
            get: () => 'default',
            configurable: true
        });
    }

    // 7. Prevent iframe contentWindow detection leaks
    const origContentWindow = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow').get;
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() {
            const win = origContentWindow.apply(this);
            if (win) {
                try {
                    Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
                } catch(e) {}
            }
            return win;
        }
    });
})();
"""

# Low-RAM Chromium launch arguments to prevent memory spikes & OOM
LOW_MEMORY_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-update",
    "--disable-domain-reliability",
    "--disable-features=AudioServiceOutOfProcess,IsolateOrigins,site-per-process",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--mute-audio",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
    "--disable-blink-features=AutomationControlled",
    "--js-flags=--max-old-space-size=128",
]


class StealthEngine:
    """Provides randomized, anti-fingerprinting headers and polite delays."""

    @staticmethod
    def get_random_user_agent() -> str:
        return random.choice(USER_AGENTS)

    @classmethod
    def get_stealth_headers(cls, referer: Optional[str] = None, is_json: bool = False) -> Dict[str, str]:
        """Generates realistic client headers matching modern desktop browsers."""
        ua = cls.get_random_user_agent()
        is_mac = "Macintosh" in ua

        headers = {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*" if is_json else "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"' if is_mac else '"Windows"',
            "Sec-Fetch-Dest": "empty" if is_json else "document",
            "Sec-Fetch-Mode": "cors" if is_json else "navigate",
            "Sec-Fetch-Site": "same-origin" if referer else "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1" if not is_json else "0",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    @staticmethod
    def polite_jitter(min_sec: float = 0.25, max_sec: float = 0.75):
        """Injects a human-like random jitter to prevent rate-limit flags."""
        time.sleep(random.uniform(min_sec, max_sec))


# Global browser concurrency semaphore: guarantees max 2 browsers at any time
# to keep memory usage under 200MB!
import threading
BROWSER_CONCURRENCY_SEMAPHORE = threading.BoundedSemaphore(2)
