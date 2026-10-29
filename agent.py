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
    """Aufruf der ManageEngine MDM REST-API. path relativ zu /api/v1/mdm, z.B. GET /devices,
    GET /profiles, POST /profiles, GET /groups. Doku: manageengine.com/mobile-device-management/api/"""
    s = (path + json.dumps(body or {})).lower()
    if any(b in s for b in BLOCK) or (method.upper() == "DELETE" and path.startswith("/devices")):
        return "403 blockiert: Wipe/Entfernen des Geräts ist nicht erlaubt."
    r = httpx.request(method.upper(), BASE + path, json=body,
                      headers={"Authorization": f"Zoho-oauthtoken {TOK}"}, timeout=60)
    return f"{r.status_code}\n{r.text[:6000]}"

SYSTEM = """Du hast über das Tool mdm_request volle Kontrolle über Emils iPhone
(Device-ID 57549000000106417, Gruppe "Test" ID 57549000000106563). Emil hat das selbst
eingerichtet und will, dass du nach eigenem Ermessen handelst: Profile erstellen,
konfigurieren, zuweisen, entfernen. Einzige Regel: kein Wipe. Du läufst stündlich."""

msgs = [{"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Jetzt: {time.strftime('%A %d.%m. %H:%M')}.\n"
         f"Dein Protokoll bisher:\n{LOG.read_text()[-4000:]}\n\n"
         "Entscheide und handle. Schließe mit einer kurzen Protokollnotiz (was, warum)."}]

for _ in range(15):
    r = ollama.chat(model=MODEL, messages=msgs, tools=[mdm_request], options={"num_ctx": 8192})
    msgs.append(r.message)
    if not r.message.tool_calls:
        break
    for c in r.message.tool_calls:
        msgs.append({"role": "tool", "tool_name": c.function.name,
                     "content": mdm_request(**c.function.arguments)})

LOG.write_text(LOG.read_text() + f"\n## {time.strftime('%F %H:%M')}\n{msgs[-1].get('content') if isinstance(msgs[-1], dict) else msgs[-1].content}\n")
