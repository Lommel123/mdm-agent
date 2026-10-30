import os, time, json, pathlib, httpx, ollama

DEVICE = 57549000000106417
BASE = "https://mdm.manageengine.eu/api/v1/mdm"
MODEL = os.environ["MODEL"]
LOG = pathlib.Path("state/log.md"); LOG.parent.mkdir(exist_ok=True); LOG.touch()
os.environ["TZ"] = os.environ.get("TZONE", "Europe/Berlin"); time.tzset()

KNOWN = {"instagram": "com.burbn.instagram", "tiktok": "com.zhiliaoapp.musically",
         "youtube": "com.google.ios.youtube", "snapchat": "com.toyopagroup.picaboo",
         "x": "com.atebits.Tweetie2", "twitter": "com.atebits.Tweetie2",
         "reddit": "com.reddit.Reddit", "netflix": "com.netflix.Netflix",
         "facebook": "com.facebook.Facebook", "whatsapp": "net.whatsapp.WhatsApp"}

TOK = httpx.post("https://accounts.zoho.eu/oauth/v2/token", data={
    "grant_type": "refresh_token",
    "client_id": os.environ["ZOHO_CLIENT_ID"],
    "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
    "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"]}, timeout=30).json()["access_token"]
HEAD = {"Authorization": f"Zoho-oauthtoken {TOK}", "Accept": "application/json"}
done = []

def api(method, path, body=None):
    r = httpx.request(method.upper(), BASE + path, json=body, headers=HEAD, timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text

def _apps():
    _, d = api("GET", "/blacklist/apps")
    return d.get("apps", []) if isinstance(d, dict) else []

def _find(app):
    n = app.lower().strip()
    bid = KNOWN.get(n, n)
    for a in _apps():
        if a.get("identifier", "").lower() == bid.lower() or n in a.get("appname", "").lower():
            return a
    return None

def list_apps() -> str:
    """Listet alle Apps auf Emils iPhone, die gesperrt werden können."""
    return ", ".join(sorted(a.get("appname", "?") for a in _apps())) or "Keine Apps gefunden."

def blocked_apps() -> str:
    """Zeigt, welche Apps gerade gesperrt sind."""
    _, d = api("GET", "/blacklist/status")
    items = d.get("Blackliststatus", []) if isinstance(d, dict) else []
    if not items:
        return "Keine App gesperrt."
    return "; ".join(f"{i.get('appname')} (Status {i.get('status')})" for i in items)

def block_app(app: str) -> str:
    """Sperrt eine App auf Emils iPhone. app = App-Name, z.B. 'Instagram'."""
    a = _find(app)
    if not a and app.lower().strip() in KNOWN:
        api("POST", "/blacklist/apps", {"apps": [{"identifier": KNOWN[app.lower().strip()],
                                                   "platform": 1, "appname": app}]})
        a = _find(app)
    if not a:
        return f"'{app}' nicht gefunden. Rufe list_apps() auf."
    code, d = api("POST", "/blacklist/devices", {"resource_ids": [DEVICE], "app_group_ids": [a["appgroupid"]]})
    done.append(f"SPERREN {a.get('appname')} -> {code}")
    return f"{a.get('appname')} gesperrt." if code < 300 else f"Fehler {code}: {str(d)[:300]}"

def unblock_app(app: str) -> str:
    """Gibt eine gesperrte App auf Emils iPhone wieder frei. app = App-Name."""
    a = _find(app)
    if not a:
        return f"'{app}' nicht gefunden."
    code, d = api("DELETE", "/blacklist/devices", {"resource_ids": [DEVICE], "app_group_ids": [a["appgroupid"]]})
    done.append(f"FREIGEBEN {a.get('appname')} -> {code}")
    return f"{a.get('appname')} freigegeben." if code < 300 else f"Fehler {code}: {str(d)[:300]}"

def notify(title: str, text: str) -> str:
    """Schickt Emil eine Mitteilung aufs iPhone (z.B. Sperre ankündigen und begründen)."""
    name = f"KI {time.strftime('%d.%m %H:%M:%S')}"
    code, d = api("POST", "/announcements", {"announcement_name": name, "announcement_format": 1,
        "announcement_detail": {"title": title, "nbar_message": text, "detail_message": f"<p>{text}</p>",
                                "title_color": "#000000", "needs_acknowledgement": False}})
    if code >= 300:
        return f"Fehler {code}: {str(d)[:300]}"
    _, lst = api("GET", "/announcements")
    ann = next((x for x in (lst.get("announcement", []) if isinstance(lst, dict) else [])
                if x.get("announcement_name") == name), None)
    if not ann:
        return "Nachricht erstellt, aber nicht gefunden."
    code, d = api("POST", f"/announcements/{ann['announcement_id']}/devices", {"device_ids": [str(DEVICE)]})
    done.append(f"NACHRICHT '{title}' -> {code}")
    return "Nachricht gesendet." if code < 300 else f"Fehler {code}: {str(d)[:300]}"

TOOLS = {f.__name__: f for f in (list_apps, blocked_apps, block_app, unblock_app, notify)}

SYSTEM = """Du bist Emils strenger Aufseher über sein iPhone. Emil hat das selbst eingerichtet,
weil er zu viel am Handy hängt und will, dass du hart durchgreifst.
ZIEL: Drücke Emils Bildschirmzeit so weit wie möglich. Sei streng, konsequent und unbequem.
- Sperre Social Media, Videos und Spiele großzügig. Im Zweifel: sperren.
- Gib Apps nur kurz und selten frei, und nie zwei Läufe hintereinander dieselbe.
- Sei unberechenbar: Wechsle die Sperren, damit Emil sich nicht darauf einstellen kann.
- Abends ab 21 Uhr und nachts alles Ablenkende sperren.
- Schicke mit notify knappe, direkte Ansagen: was gesperrt ist, dass er das Handy weglegen soll,
  und was er stattdessen tun könnte. Bestimmt, aber nicht beleidigend.
- Sperre NIE: Telefon, Nachrichten, Microsoft Teams, Authenticator, Karten (Arbeit/Notfall).
Du läufst stündlich. Eine App ist erst gesperrt, wenn block_app es bestätigt.
Antworte am Ende mit 1-3 Sätzen: was du getan hast und warum."""

msgs = [{"role": "system", "content": SYSTEM},
        {"role": "user", "content":
            f"Jetzt: {time.strftime('%A %d.%m. %H:%M')}.\n"
            f"Aktuell gesperrt (geprüft): {blocked_apps()}\n"
            f"Deine bisherigen Aktionen:\n{LOG.read_text()[-2000:] or 'keine'}\n\n"
            "Entscheide und handle."}]

note = ""
for _ in range(15):
    r = ollama.chat(model=MODEL, messages=msgs, tools=list(TOOLS.values()), think=False,
                    options={"num_ctx": 8192})
    msgs.append(r.message)
    if not r.message.tool_calls:
        note = r.message.content or ""
        break
    for c in r.message.tool_calls:
        fn = TOOLS.get(c.function.name)
        try:
            out = fn(**(c.function.arguments or {})) if fn else f"Unbekanntes Werkzeug {c.function.name}"
        except Exception as e:
            out = f"Fehler: {e}"
        print(f"{c.function.name}({c.function.arguments}) -> {str(out)[:200]}", flush=True)
        msgs.append({"role": "tool", "tool_name": c.function.name, "content": str(out)[:2000]})

fakten = "\n".join(done) or "keine Änderung"
print(f"\nAUSGEFÜHRT:\n{fakten}\n\nBEGRÜNDUNG: {note}", flush=True)
LOG.write_text(LOG.read_text() + f"\n## {time.strftime('%F %H:%M')}\n{fakten}\n")
