"""
Measure the squadron roster's natural width in every language.

    python tools/measure_roster.py [--width 2072] [--career "<id>"]

Drives headless Chrome over the DevTools protocol and reads the table's
scrollWidth against its container's clientWidth — the only honest answer to
"does the roster overflow", since it is what the browser itself decides. A
screenshot cannot tell a table that fits from one that is clipped.

Needs the tracker running on :5002 and Chrome installed. Flips the global
language for each measurement and restores it afterwards.
"""

import argparse
import json
import subprocess
import time
import urllib.parse
import urllib.request

import websocket   # websocket-client

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9222
BASE = "http://127.0.0.1:5002"
LANGS = ("en", "de", "es", "fr", "ru", "zh")

JS = r"""
(() => {
  const t = document.querySelector('table#d-roster');
  if (!t) return {error: 'no roster'};
  const box = t.closest('.table-scroll') || t.parentElement;
  const heads = [...t.querySelectorAll('thead th')].map(th => ({
    text: th.textContent.trim().replace(/\s+/g, ' '),
    w: Math.round(th.getBoundingClientRect().width)
  }));
  const r = t.querySelector('thead').getBoundingClientRect();
  const first = t.querySelector('tbody tr');
  const fr = first ? first.getBoundingClientRect() : r;
  return {table: t.scrollWidth, box: box.clientWidth, heads,
          clip: {x: Math.max(0, r.left - 8), y: r.top + window.scrollY - 8,
                 width: r.width + 16, height: (fr.bottom - r.top) + 16}};
})()
"""


def api(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


class Tab:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self.n = 0

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                return msg.get("result", {})

    def evaluate(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True)
        return r.get("result", {}).get("value")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--width", type=int, default=2072)
    ap.add_argument("--career", default="Alexander Zink, 39th FIS USAF")
    ap.add_argument("--shot", metavar="DIR",
                    help="also save roster_<lang>.png of the header and first row")
    args = ap.parse_args()

    original = api("/api/settings")["language"]
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}",
         "--remote-allow-origins=*", f"--window-size={args.width},2000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        tab = Tab(page["webSocketDebuggerUrl"])
        tab.call("Page.enable")
        tab.call("Emulation.setDeviceMetricsOverride", width=args.width, height=2000,
                 deviceScaleFactor=1, mobile=False)

        url = f"{BASE}/#career/{urllib.parse.quote(args.career)}"
        available = None
        print(f"  viewport {args.width}px\n")
        print(f"  {'lang':<5} {'table':>6} {'box':>6}   result")
        for lang in LANGS:
            api("/api/settings", {"language": lang})
            tab.call("Page.navigate", url="about:blank")
            time.sleep(0.3)
            tab.call("Page.navigate", url=url)
            for _ in range(60):
                time.sleep(0.25)
                r = tab.evaluate(JS)
                if r and not r.get("error") and r.get("table", 0) > 0:
                    break
            if not r or r.get("error"):
                print(f"  {lang:<5} roster did not render")
                continue
            over = r["table"] - r["box"]
            verdict = "fits" if over <= 0 else f"OVERFLOWS by {over}px"
            print(f"  {lang:<5} {r['table']:>6} {r['box']:>6}   {verdict}")
            available = r["box"]
            widest = sorted(r["heads"], key=lambda h: -h["w"])[:4]
            print("         widest columns: " +
                  ", ".join(f"{h['text']!r} {h['w']}px" for h in widest))
            if args.shot:
                import base64
                from pathlib import Path
                # Clip in page coordinates with captureBeyondViewport, so no
                # scrolling is needed and the clip cannot drift against it.
                shot = tab.call("Page.captureScreenshot", format="png",
                                captureBeyondViewport=True,
                                clip={**r["clip"], "scale": 1})
                out = Path(args.shot) / f"roster_{lang}.png"
                out.write_bytes(base64.b64decode(shot["data"]))
                print(f"         -> {out}")
    finally:
        api("/api/settings", {"language": original})
        chrome.terminate()
        print(f"\n  language restored to {original}")


if __name__ == "__main__":
    main()
