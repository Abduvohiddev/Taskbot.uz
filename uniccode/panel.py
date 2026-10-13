"""
Admin panel (veb): dashboard, foydalanuvchilar, xatolar jurnali, AI hisobotlari.

Kirish parolsiz: botda /panel -> bir martalik havola (10 daqiqa) -> imzolangan cookie (12 soat).
Superadmin hamma bo'limni ko'radi va boshqaradi; bo'lim admini faqat o'z bo'limini ko'radi va
o'z bo'limiga oddiy foydalanuvchi qo'sha oladi. Barcha POST so'rovlar CSRF token bilan himoyalangan.
"""
import hashlib
import hmac
import logging
import secrets
import time
from html import escape
from typing import Dict, Optional, Tuple

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from uniccode import stats
from uniccode.access import ADMIN, DEPT_NAMES, DEPTS, ROLE_NAMES, USER, Access, Who
from uniccode.ai import AI
from uniccode.config import UnicSettings
from uniccode.generator import to_local
from uniccode.models import UCEvent

log = logging.getLogger("uniccode.panel")
COOKIE = "ucs"
SESSION_TTL = 12 * 3600
LOGIN_TTL = 600


class Panel:
    def __init__(self, sm: async_sessionmaker, cfg: UnicSettings, access: Access, ai: AI, notifier=None):
        self.sm, self.cfg, self.access, self.ai, self.notifier = sm, cfg, access, ai, notifier
        self._logins: Dict[str, Tuple[int, float]] = {}

    # ------------------------------------------------------------------ kirish
    def issue_login(self, uid: int) -> str:
        now = time.time()
        self._logins = {t: v for t, v in self._logins.items() if v[1] > now}
        token = secrets.token_urlsafe(24)
        self._logins[token] = (uid, now + LOGIN_TTL)
        return f"{self.cfg.PANEL_URL.rstrip('/')}/login?t={token}"

    def _sign(self, payload: str) -> str:
        return hmac.new(self.cfg.panel_secret, payload.encode(), hashlib.sha256).hexdigest()

    def _session_value(self, uid: int) -> str:
        payload = f"{uid}:{int(time.time()) + SESSION_TTL}"
        return f"{payload}:{self._sign(payload)}"

    def _session_uid(self, value: Optional[str]) -> Optional[int]:
        try:
            uid, exp, sig = (value or "").split(":")
            if hmac.compare_digest(sig, self._sign(f"{uid}:{exp}")) and int(exp) > time.time():
                return int(uid)
        except ValueError:
            pass
        return None

    def _csrf(self, request: web.Request) -> str:
        return self._sign("csrf:" + (request.cookies.get(COOKIE) or ""))[:32]

    # ------------------------------------------------------------------ ilova
    def app(self) -> web.Application:
        app = web.Application(middlewares=[self._auth])
        app.add_routes([
            web.get("/login", self.login), web.get("/logout", self.logout), web.get("/health", self.health),
            web.get("/", self.dashboard), web.get("/users", self.users), web.post("/users", self.users_save),
            web.post("/users/{id}/toggle", self.users_toggle), web.post("/users/{id}/delete", self.users_delete),
            web.get("/errors", self.errors), web.post("/errors/{id}/ai", self.errors_ai),
            web.get("/reports", self.reports), web.post("/reports/run", self.reports_run),
        ])
        return app

    @web.middleware
    async def _auth(self, request: web.Request, handler):
        if request.path in ("/login", "/health"):
            return await handler(request)
        who = self.access.who(self._session_uid(request.cookies.get(COOKIE)))
        if not who or not who.can_panel:
            return self._page(None, "Kirish", "<div class='card'><h2>Kirish kerak</h2><p>Telegram botda "
                              "<b>/panel</b> buyrug'ini yuboring - bot sizga bir martalik kirish havolasini beradi.</p>"
                              "</div>", status=401)
        request["who"] = who
        if request.method == "POST":
            form = await request.post()
            if not hmac.compare_digest(str(form.get("csrf", "")), self._csrf(request)):
                return web.Response(status=403, text="CSRF token noto'g'ri - sahifani yangilang")
            request["form"] = form
        return await handler(request)

    async def health(self, request):
        return web.Response(text="ok")

    async def login(self, request):
        item = self._logins.pop(request.query.get("t", ""), None)
        if not item or item[1] < time.time():
            return self._page(None, "Kirish", "<div class='card'><h2>Havola eskirgan</h2><p>Botda <b>/panel</b> "
                              "ni qayta yuboring. Havola 10 daqiqa va faqat bir marta ishlaydi.</p></div>", status=401)
        resp = web.HTTPFound("/")
        resp.set_cookie(COOKIE, self._session_value(item[0]), max_age=SESSION_TTL, httponly=True, samesite="Lax",
                        secure=self.cfg.PANEL_URL.startswith("https"))
        log.info("Panelga kirdi: %s", item[0])
        raise resp

    async def logout(self, request):
        resp = web.HTTPFound("/login")
        resp.del_cookie(COOKIE)
        raise resp

    # ------------------------------------------------------------------ sahifalar
    def _local(self, d) -> str:
        return to_local(d, self.cfg.UNIC_TZ).strftime("%d.%m.%Y %H:%M") if d else ""

    def _uname(self, uid, username="") -> str:
        u = self.access.get(uid) if uid else None
        return (u.full_name if u and u.full_name else ("@" + username if username else str(uid or "—")))

    async def dashboard(self, request):
        who: Who = request["who"]
        dept = request.query.get("dept") if who.is_super else who.dept
        dept = dept if dept in DEPTS else None
        async with self.sm() as s:
            d = await stats.dashboard(s, self.cfg.UNIC_TZ, dept)
        t = d["jami"]
        tabs = ""
        if who.is_super:
            tabs = "<div class='tabs'>" + "".join(
                f"<a class='{'on' if dept == k else ''}' href='/?dept={k or ''}'>{DEPT_NAMES[k]}</a>"
                for k in (None, "chexol", "polik")) + "</div>"
        kpis = "".join(f"<div class='kpi'><span>{escape(lbl)}</span><b>{v:,}</b></div>".replace(",", " ")
                       for lbl, v in (("Bugun", t["bugun"]), ("7 kun", t["7_kun"]), ("30 kun", t["30_kun"]),
                                      ("Jami kodlar", t["jami"]), ("Artikullar", t["artikullar"])))
        warn = []
        if d["xatolar_24_soat"]:
            warn.append(f"<a href='/errors'>{d['xatolar_24_soat']} ta xato (24 soat)</a>")
        if d["sheets_kutilmoqda"]:
            warn.append(f"Google Sheets'ga yuklanishi kutilmoqda: {d['sheets_kutilmoqda']}")
        if d["vidsiz_artikullar_30_kun"]:
            warn.append(f"Vidi noma'lum artikullar (30 kun): {d['vidsiz_artikullar_30_kun']} — /katalog_1c")
        status = "".join(f"<li>{w}</li>" for w in warn) or "<li class='ok'>Muammo yo'q</li>"
        arts = "".join(f"<tr><td>{escape(a['artikul'])}</td><td>{escape(a['nomi'])}</td><td class='n'>{a['kodlar']}</td></tr>"
                       for a in d["top_artikullar"]) or "<tr><td colspan=3>Ma'lumot yo'q</td></tr>"
        users = "".join(f"<tr><td>{escape(self._uname(u['user_id'], u['username']))}</td><td class='n'>{u['sorovlar']}</td>"
                        f"<td class='n'>{u['kodlar']}</td></tr>" for u in d["top_foydalanuvchilar"]) \
            or "<tr><td colspan=3>Ma'lumot yo'q</td></tr>"
        recent = "".join(f"<tr><td>{self._local(r['vaqt'])}</td><td>{escape(self._uname(r['user_id'], r['username']))}</td>"
                         f"<td>{escape(r['manba'])}</td><td>{escape(r['fayl'])}</td><td class='n'>{r['kodlar']}</td></tr>"
                         for r in d["oxirgi_sorovlar"]) or "<tr><td colspan=5>Ma'lumot yo'q</td></tr>"
        body = f"""{tabs}
<div class='kpis'>{kpis}</div>
<div class='grid'>
  <div class='card wide'><h3>Kunlik kodlar (30 kun)</h3>{bar_chart(d["kunlik"])}</div>
  <div class='card'><h3>Holat</h3><ul class='status'>{status}</ul></div>
  <div class='card'><h3>Eng ko'p kod yasalgan artikullar (30 kun)</h3>
    <table><tr><th>Artikul</th><th>Nomi</th><th>Kodlar</th></tr>{arts}</table></div>
  <div class='card'><h3>Eng faol foydalanuvchilar (30 kun)</h3>
    <table><tr><th>Kim</th><th>So'rov</th><th>Kodlar</th></tr>{users}</table></div>
  <div class='card wide'><h3>Oxirgi so'rovlar</h3>
    <table><tr><th>Vaqt</th><th>Kim</th><th>Manba</th><th>Fayl</th><th>Kodlar</th></tr>{recent}</table></div>
</div>
"""
        return self._page(who, "Dashboard", body, active="/", request=request)

    async def users(self, request, msg: str = "", ok: bool = False):
        who: Who = request["who"]
        rows = []
        for u in self.access.users(who):
            can = self.access.can_manage(who, u.role, u.dept)
            acts = ""
            if can:
                acts = (f"<form method='post' action='/users/{u.tg_id}/toggle'>{self._hidden(request)}"
                        f"<button>{'O‘chirish' if u.active else 'Yoqish'}</button></form>"
                        f"<form method='post' action='/users/{u.tg_id}/delete' onsubmit=\"return confirm('O‘chirilsinmi?')\">"
                        f"{self._hidden(request)}<button class='danger'>Delete</button></form>")
            rows.append(f"<tr class='{'' if u.active else 'off'}'><td>{u.tg_id}</td><td>{escape(u.full_name)}</td>"
                        f"<td>{ROLE_NAMES.get(u.role, u.role)}</td><td>{DEPT_NAMES.get(u.dept, u.dept)}</td>"
                        f"<td>{'faol' if u.active else 'o‘chiq'}</td><td class='acts'>{acts}</td></tr>")
        supers = ", ".join(str(i) for i in sorted(self.cfg.admin_ids)) or "—"
        if who.is_super:
            role_opts = f"<option value='{USER}'>Foydalanuvchi</option><option value='{ADMIN}'>Bo'lim admini</option>"
            dept_opts = "<option value='chexol'>Chexol</option><option value='polik'>Polik</option>" \
                        "<option value=''>Hammasi (faqat foydalanuvchi)</option>"
        else:
            role_opts = f"<option value='{USER}'>Foydalanuvchi</option>"
            dept_opts = f"<option value='{who.dept}'>{DEPT_NAMES[who.dept]}</option>"
        note = f"<div class='msg {'good' if ok else 'bad'}'>{escape(msg)}</div>" if msg else ""
        body = f"""{note}
<div class='card'><h3>Foydalanuvchi qo'shish yoki o'zgartirish</h3>
<form method='post' action='/users' class='row'>{self._hidden(request)}
  <label>Telegram ID<input name='tg_id' required inputmode='numeric' pattern='[0-9]{{5,15}}' placeholder='1048307913'></label>
  <label>Ism<input name='full_name' required maxlength='128' placeholder='Ism Familiya'></label>
  <label>Rol<select name='role'>{role_opts}</select></label>
  <label>Bo'lim<select name='dept'>{dept_opts}</select></label>
  <button class='primary'>Saqlash</button>
</form>
<p class='muted'>ID ni bilish uchun xodim botga istalgan xabar yozadi - bot unga ID'sini ko'rsatadi.
{f"Superadminlar (.env): {supers}" if who.is_super else ""}</p></div>
<div class='card'><h3>Foydalanuvchilar</h3>
<table><tr><th>ID</th><th>Ism</th><th>Rol</th><th>Bo'lim</th><th>Holat</th><th></th></tr>
{''.join(rows) or "<tr><td colspan=6>Hali yo'q</td></tr>"}</table></div>"""
        return self._page(who, "Foydalanuvchilar", body, active="/users", request=request)

    async def users_save(self, request):
        who, f = request["who"], request["form"]
        try:
            tg_id = int(str(f.get("tg_id", "")).strip())
        except ValueError:
            return await self.users(request, "Telegram ID faqat raqam bo'lishi kerak.")
        role = f.get("role") if f.get("role") in (ADMIN, USER) else USER
        dept = f.get("dept") or None
        if dept not in (None, *DEPTS):
            dept = None
        err = await self.access.save_user(who, tg_id, str(f.get("full_name", "")), role, dept)
        if not err:
            log.info("Foydalanuvchi saqlandi: %s (%s, %s) - %s", tg_id, role, dept, who.tg_id)
        return await self.users(request, err or "Saqlandi.", ok=not err)

    async def users_toggle(self, request):
        who, uid = request["who"], int(request.match_info["id"])
        u = self.access.get(uid)
        err = await self.access.set_active(who, uid, not (u and u.active))
        return await self.users(request, err or "O'zgartirildi.", ok=not err)

    async def users_delete(self, request):
        who, uid = request["who"], int(request.match_info["id"])
        err = await self.access.remove(who, uid)
        return await self.users(request, err or "O'chirildi.", ok=not err)

    async def errors(self, request):
        who: Who = request["who"]
        level = request.query.get("level", "")
        async with self.sm() as s:
            q = select(UCEvent).where(UCEvent.source != "hisobot").order_by(UCEvent.last_at.desc()).limit(200)
            if level in ("error", "warning"):
                q = q.where(UCEvent.level == level)
            evs = (await s.execute(q)).scalars().all()
        rows = []
        for e in evs:
            ai_btn = ""
            if who.is_super and self.ai.enabled and not e.ai_text:
                ai_btn = (f"<form method='post' action='/errors/{e.id}/ai'>{self._hidden(request)}"
                          f"<button>🤖 AI tahlil</button></form>")
            extra = ""
            if e.ai_text:
                extra += f"<div class='ai'>🤖 {escape(e.ai_text)}</div>"
            if e.details:
                extra += f"<details><summary>Tafsilot</summary><pre>{escape(e.details)}</pre></details>"
            rows.append(f"<tr><td><span class='lvl {e.level}'>{e.level}</span></td><td>{escape(e.source)}</td>"
                        f"<td>{escape(e.message)}{extra}</td><td class='n'>{e.count}</td>"
                        f"<td>{self._local(e.last_at)}</td><td>{ai_btn}</td></tr>")
        filt = "<div class='tabs'>" + "".join(
            f"<a class='{'on' if level == k else ''}' href='/errors?level={k}'>{n}</a>"
            for k, n in (("", "Hammasi"), ("error", "Xatolar"), ("warning", "Ogohlantirishlar"))) + "</div>"
        ai_note = "" if self.ai.enabled else ("<p class='muted'>AI o'chiq: serverda ANTHROPIC_API_KEY qo'yilsa, "
                                              "xatolar avtomatik tushuntiriladi.</p>")
        body = f"""{filt}{ai_note}<div class='card'><table>
<tr><th>Daraja</th><th>Manba</th><th>Xabar</th><th>Soni</th><th>Oxirgi marta</th><th></th></tr>
{''.join(rows) or "<tr><td colspan=6>Xato yo'q 🎉</td></tr>"}</table></div>"""
        return self._page(who, "Xatolar", body, active="/errors", request=request)

    async def errors_ai(self, request):
        who: Who = request["who"]
        if not who.is_super:
            raise web.HTTPForbidden()
        async with self.sm() as s:
            e = await s.get(UCEvent, int(request.match_info["id"]))
            if e is not None and not e.ai_text:
                text = await self.ai.explain_errors([{"daraja": e.level, "manba": e.source, "xabar": e.message,
                                                       "soni": e.count, "tafsilot": (e.details or "")[-3000:]}])
                e.ai_text = text or "AI javob bermadi (kalit yoki tarmoqni tekshiring)."
                await s.commit()
        raise web.HTTPFound("/errors")

    async def reports(self, request):
        who: Who = request["who"]
        scope = DEPT_NAMES.get(who.scope, "")
        async with self.sm() as s:
            q = select(UCEvent).where(UCEvent.source == "hisobot").order_by(UCEvent.id.desc()).limit(30)
            if not who.is_super:
                q = q.where(UCEvent.message == f"Kunlik hisobot: {scope}")
            evs = (await s.execute(q)).scalars().all()
        items = "".join(f"<div class='card'><h3>{escape(e.message)} · {self._local(e.created_at)}</h3>"
                        f"<div class='ai'>{escape(e.ai_text or '')}</div></div>" for e in evs)
        run = ""
        if who.is_super and self.notifier:
            run = (f"<form method='post' action='/reports/run'>{self._hidden(request)}"
                   f"<button class='primary'>Hozir hisobot yuborish</button></form>")
        hour = self.cfg.UNIC_REPORT_HOUR
        body = (f"<div class='card'><p>Kunlik hisobot har kuni soat {hour}:00 da Telegram'ga yuboriladi"
                f"{' va AI tomonidan yoziladi' if self.ai.enabled else ' (AI o‘chiq - faqat raqamlar)'}.</p>{run}</div>"
                + (items or "<div class='card'><p>Hali hisobot yo'q.</p></div>"))
        return self._page(who, "AI hisobotlar", body, active="/reports", request=request)

    async def reports_run(self, request):
        if not request["who"].is_super or not self.notifier:
            raise web.HTTPForbidden()
        await self.notifier.daily_report()
        raise web.HTTPFound("/reports")

    # ------------------------------------------------------------------ dizayn
    def _hidden(self, request) -> str:
        return f"<input type='hidden' name='csrf' value='{self._csrf(request)}'>"

    def _page(self, who: Optional[Who], title: str, body: str, active: str = "", request=None, status=200):
        nav = ""
        if who:
            links = [("/", "Dashboard"), ("/users", "Foydalanuvchilar"), ("/errors", "Xatolar"), ("/reports", "AI hisobotlar")]
            nav = "<nav>" + "".join(f"<a class='{'on' if active == h else ''}' href='{h}'>{n}</a>" for h, n in links) + \
                  f"<span class='me'>{escape(ROLE_NAMES[who.role])}{' · ' + DEPT_NAMES[who.dept] if who.dept else ''}" \
                  f" · <a href='/logout'>Chiqish</a></span></nav>"
        html = f"""<!doctype html><html lang='uz'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)} · Unic kod panel</title>
<style>{CSS}</style></head><body><header><b>Unic kod</b> panel</header>{nav}<main><h1>{escape(title)}</h1>{body}</main></body></html>"""
        return web.Response(text=html, content_type="text/html", status=status)


def bar_chart(k: dict) -> str:
    """Kunlik kodlar: bo'limlar bo'yicha ustma-ust ustunlar (SVG, tashqi kutubxonasiz)."""
    series = [("chexol", "Chexol", "--c1"), ("polik", "Polik", "--c2"), ("aniqlanmagan", "Aniqlanmagan", "--c3")]
    n = len(k["labels"])
    totals = [sum(k[s][i] for s, _, _ in series) for i in range(n)]
    top = max(totals + [1])
    step = 10 ** max(len(str(top)) - 1, 0)
    top = ((top + step - 1) // step) * step
    W, H, L, B, T = 900, 260, 44, 22, 8
    bw = (W - L) / n
    parts = []
    for g in range(5):
        v = top * g / 4
        y = H - B - (H - B - T) * g / 4
        parts.append(f"<line x1='{L}' x2='{W}' y1='{y:.1f}' y2='{y:.1f}' class='gl'/>"
                     f"<text x='{L - 6}' y='{y + 4:.1f}' class='ax' text-anchor='end'>{int(v)}</text>")
    for i, lbl in enumerate(k["labels"]):
        x = L + i * bw + bw * 0.15
        y = H - B
        tip = f"{lbl[8:10]}.{lbl[5:7]}: " + ", ".join(f"{name} {k[s][i]}" for s, name, _ in series if k[s][i])
        for s, _, var in series:
            v = k[s][i]
            if v:
                h = (H - B - T) * v / top
                y -= h
                parts.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw * 0.7:.1f}' height='{h:.1f}' "
                             f"style='fill:var({var})'><title>{escape(tip)}</title></rect>")
        if i % 5 == 0 or i == n - 1:
            anchor = "end" if i == n - 1 else "middle"
            parts.append(f"<text x='{min(L + i * bw + bw / 2, W):.1f}' y='{H - 6}' class='ax' text-anchor='{anchor}'>"
                         f"{lbl[8:10]}.{lbl[5:7]}</text>")
    legend = "".join(f"<span><i style='background:var({var})'></i>{name} {sum(k[s]):,}</span>".replace(",", " ")
                     for s, name, var in series if sum(k[s]))
    return (f"<div class='legend'>{legend}</div><svg class='chart' viewBox='0 0 {W} {H}' role='img' "
            f"aria-label='Kunlik kodlar'>{''.join(parts)}</svg>")


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--muted:#6b7385;--line:#e3e6ec;--acc:#2f6fed;--c1:#2f6fed;--c2:#14a37f;
--c3:#b8bfcc;--bad:#c93a3a;--warn:#c98a1a;--good:#14a37f}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--card:#1b2029;--fg:#e6e9ef;--muted:#9aa3b5;--line:#2b313d;
--acc:#6b9bff;--c1:#6b9bff;--c2:#3cc9a0;--c3:#555d6e;--bad:#ff7373;--warn:#f0b54a;--good:#3cc9a0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:12px 16px;border-bottom:1px solid var(--line);background:var(--card)}
nav{display:flex;flex-wrap:wrap;gap:4px;align-items:center;padding:8px 16px;border-bottom:1px solid var(--line);background:var(--card)}
nav a{color:var(--fg);text-decoration:none;padding:6px 10px;border-radius:8px}nav a.on{background:var(--acc);color:#fff}
.me{margin-left:auto;color:var(--muted);font-size:13px}.me a{padding:0;color:var(--acc)}
main{max-width:1200px;margin:0 auto;padding:16px}h1{font-size:22px;margin:4px 0 14px}h3{margin:0 0 10px;font-size:15px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px;overflow-x:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}.grid .card{margin:0}.wide{grid-column:1/-1}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}.kpi span{color:var(--muted);font-size:13px;display:block}
.kpi b{font-size:24px}.chart{width:100%;height:auto;display:block}
.chart .gl{stroke:var(--line)}.chart .ax{fill:var(--muted);font-size:11px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin-bottom:6px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}tr.off td{opacity:.5}
.tabs{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}.tabs a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;
color:var(--fg);text-decoration:none;background:var(--card)}.tabs a.on{background:var(--acc);border-color:var(--acc);color:#fff}
.status{margin:0;padding-left:18px}.status .ok{color:var(--good)}a{color:var(--acc)}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}label{display:flex;flex-direction:column;font-size:13px;color:var(--muted);gap:4px}
input,select{font:inherit;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);min-width:150px}
button{font:inherit;padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);cursor:pointer}
button.primary{background:var(--acc);border-color:var(--acc);color:#fff}button.danger{color:var(--bad)}
td.acts{display:flex;gap:6px}td form{display:inline}
.msg{padding:10px 14px;border-radius:10px;margin-bottom:14px;border:1px solid var(--line)}.msg.good{color:var(--good)}.msg.bad{color:var(--bad)}
.muted{color:var(--muted);font-size:13px}.lvl{font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid currentColor}
.lvl.error{color:var(--bad)}.lvl.warning{color:var(--warn)}.lvl.info{color:var(--muted)}
.ai{white-space:pre-wrap;margin-top:6px;padding:8px 10px;border-left:3px solid var(--acc);background:var(--bg);border-radius:6px}
pre{white-space:pre-wrap;font-size:12px;max-height:300px;overflow:auto}
@media (max-width:600px){main{padding:12px}input,select{min-width:0;width:100%}label{width:100%}}
"""
