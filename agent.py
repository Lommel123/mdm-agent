import os, time, json, pathlib, httpx, ollama

BASE = "https://mdm.manageengine.eu/api/v1/mdm"
MODEL = os.environ["MODEL"]
LOG = pathlib.Path("state/log.md"); LOG.parent.mkdir(exist_ok=True); LOG.touch()
os.environ["TZ"] = os.environ.get("TZONE", "Europe/Berlin"); time.tzset()

TOK = httpx.post("https://accounts.zoho.eu/oauth/v2/token", data={
    "grant_type": "refresh_token",
    "client_id": os.environ["ZOHO_CLIENT_ID"],
    "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
    "refresh_token": os.environ["ZOHO_REFRESH_TOKEN"]}, timeout=30).json()["access_token"]

BLOCK = ("wipe", "erase", "unmanage", "deprovision")

def mdm_request(method: str, path: str, body: dict | None = None) -> str:
    """Aufruf der ManageEngine MDM REST-API. Argumente: method, path (relativ zu /api/v1/mdm), body (JSON-Objekt)."""
    s = (path + json.dumps(body or {})).lower()
    if any(b in s for b in BLOCK) or (method.upper() == "DELETE" and path.startswith("/devices")):
        return "403 blockiert: Wipe/Entfernen des Geräts ist nicht erlaubt."
    r = httpx.request(method.upper(), BASE + path, json=body, timeout=60,
                      headers={"Authorization": f"Zoho-oauthtoken {TOK}", "Accept": "application/json"})
    return f"{r.status_code}\n{r.text[:2000]}"

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
API-REZEPTE (Pfade relativ, method + path + body):
Apps sperren:
 1. GET /blacklist/apps -> Liste mit appgroupid, appname, identifier
 2. Fehlt eine App: POST /blacklist/apps  {"apps":[{"identifier":"com.burbn.instagram","platform":1,"appname":"Instagram"}]}
 3. Sperren:   POST   /blacklist/devices {"resource_ids":[57549000000106417],"app_group_ids":[APPGROUPID]}
 4. Freigeben: DELETE /blacklist/devices {"resource_ids":[57549000000106417],"app_group_ids":[APPGROUPID]}
 5. Status: GET /blacklist/status
Bundle-IDs: Instagram com.burbn.instagram, TikTok com.zhiliaoapp.musically, YouTube com.google.ios.youtube,
 Snapchat com.toyopagroup.picaboo, X com.atebits.Tweetie2, Reddit com.reddit.Reddit, Netflix com.netflix.Netflix
Systemsperren per Profil:
 1. POST /profiles {"profile_name":"NAME","platform_type":1}  -> profile_id
 2. POST /profiles/PROFILE_ID/payloads/restrictionspolicy {"allow_safari":false,"allow_app_installation":false,
    "allow_use_of_youtube":false,"allow_game_center":false,"allow_host_pairing":true}
 3. POST /profiles/PROFILE_ID/publish
 4. Zuweisen:  POST   /groups/57549000000106563/profiles {"profile_ids":[PROFILE_ID]}
 5. Entziehen: DELETE /groups/57549000000106563/profiles {"profile_ids":[PROFILE_ID]}
 Vorhandene Profile: GET /profiles  (nutze vorhandene Profile wieder, statt jedes Mal neue zu erstellen)
Nachricht an Emil (erscheint als Mitteilung auf dem iPhone):
 1. POST /announcements {"announcement_name":"KURZNAME","announcement_format":1,
    "announcement_detail":{"title":"TITEL","nbar_message":"KURZTEXT","detail_message":"<p>TEXT</p>",
    "title_color":"#000000","needs_acknowledgement":false}}
 2. GET /announcements -> announcement_id der eben erstellten Nachricht suchen (Name)
 3. POST /announcements/ANNOUNCEMENT_ID/devices {"device_ids":["57549000000106417"]}
 Kündige Sperren vorher an und erkläre kurz, warum.
Lass allow_host_pairing immer true (sonst kann Emil nicht mehr entwickeln)."""

msgs = [{"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Jetzt: {time.strftime('%A %d.%m. %H:%M')}.\n"
         f"Protokoll der tatsächlich ausgeführten Aktionen bisher:\n{LOG.read_text()[-3000:]}\n\n"
         "Prüfe den aktuellen Zustand mit GET /blacklist/status, entscheide und handle. "
         "Schließe mit einer kurzen Notiz: was du geändert hast und warum."}]

done = []
note = ""
for _ in range(20):
    r = ollama.chat(model=MODEL, messages=msgs, tools=[mdm_request], think=False,
                    options={"num_ctx": 8192})
    msgs.append(r.message)
    calls = r.message.tool_calls or []
    if not calls:
        note = r.message.content or ""
        print("Schritt: fertig", flush=True)
        break
    for c in calls:
        a = dict(c.function.arguments or {})
        body = next((a[k] for k in ("body", "jsonPayload", "payload", "data", "json") if k in a), None)
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except Exception:
                body = None
        method, path = a.get("method", "GET"), a.get("path", "/")
        try:
            out = mdm_request(method, path, body)
        except Exception as e:
            out = f"Fehler beim Aufruf: {e}. Nutze genau: method, path, body."
        line = f"{method} {path} {json.dumps(body) if body else ''} -> {out.splitlines()[0]}"
        if method.upper() != "GET":
            done.append(line)
        print("Schritt:", line, flush=True)
        msgs.append({"role": "tool", "tool_name": c.function.name, "content": out})

fakten = "\n".join(done) if done else "KEINE Änderung ausgeführt."
report = f"TATSÄCHLICH AUSGEFÜHRT:\n{fakten}\n\nKI-NOTIZ (unbestätigt):\n{note}"
print(report, flush=True)
LOG.write_text(LOG.read_text() + f"\n## {time.strftime('%F %H:%M')}\n{fakten}\n")

if os.environ.get("TG_TOKEN"):
    httpx.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage",
               data={"chat_id": os.environ["TG_CHAT"],
                     "text": f"MDM-KI {time.strftime('%H:%M')}:\n{report}"[:4000]})
