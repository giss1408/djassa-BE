"""The investor brief, behind a password.

The brief, the NDA and the letters of interest used to be public files on the
website, a static site that cannot ask for a password. They now live in
`app/investor_brief/` and are served here, at `/brief/`, only to a browser
that has entered the investor password.

One shared password, set with `INVESTOR_BRIEF_PASSWORD` (at least 12
characters) and given to investors by the team. Unset or too short, the brief
is closed: fail closed, never open. Changing the password signs everyone out,
because the session cookie carries a fingerprint of the password it was
issued for.

The session is a signed cookie (itsdangerous, keyed with FIDELIA_SECRET_KEY),
HttpOnly, SameSite=Lax, Secure over HTTPS, valid 7 days. Login attempts are
rate-limited per address. The password is never logged.

Only the stylesheet, the font and the icon are served without a session: the
login page needs them, and they say nothing.
"""

import hashlib
import hmac
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from ..core.security import SECRET_KEY
from ..rate_limiter import limiter

log = logging.getLogger("fidelia.investor_brief")

router = APIRouter(include_in_schema=False)

BRIEF_DIR = Path(__file__).resolve().parent.parent / "investor_brief"
COOKIE = "fidelia_brief"
SESSION_SECONDS = 7 * 24 * 3600
MIN_PASSWORD_LENGTH = 12

# Readable without a session: what the login page itself needs.
PUBLIC_FILES = {"brief.css", "instrument-serif-latin.woff2", "favicon.svg"}
# File names only: no directories, no "..", one known extension.
_SAFE_NAME = re.compile(r"^[a-z0-9-]+\.(html|css|pdf|svg|woff2)$")

_NO_STORE = {
    "Cache-Control": "private, no-store",
    "X-Robots-Tag": "noindex, nofollow",
}


def _password() -> str | None:
    value = os.getenv("INVESTOR_BRIEF_PASSWORD", "")
    if len(value) < MIN_PASSWORD_LENGTH:
        return None
    return value


def _fingerprint(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()[:16]


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(SECRET_KEY, salt="investor-brief")


def _signed_in(request: Request) -> bool:
    password = _password()
    token = request.cookies.get(COOKIE)
    if password is None or not token:
        return False
    try:
        data = _serializer().loads(token, max_age=SESSION_SECONDS)
    except BadSignature:
        return False
    return hmac.compare_digest(str(data.get("p", "")), _fingerprint(password))


def _site_url() -> str | None:
    value = os.getenv("FIDELIA_SITE_URL", "").strip().rstrip("/")
    return value if value.startswith("https://") or value.startswith("http://") else None


def _page(name: str) -> HTMLResponse:
    """A brief page, with the website link pointed at the public site (or
    removed when the site address is not configured)."""
    html = (BRIEF_DIR / name).read_text(encoding="utf-8")
    site = _site_url()
    if site:
        html = html.replace('href="__SITE_URL__"', f'href="{site}/"')
    else:
        html = re.sub(r'<a href="__SITE_URL__">[^<]*</a>', "", html)
    return HTMLResponse(html, headers=_NO_STORE)


def _safe_next(value: str | None) -> str:
    """Only a page of the brief itself, never another site (open redirect)."""
    if value and value.startswith("/brief/") and _SAFE_NAME.match(value[len("/brief/"):] or "x"):
        return value
    return "/brief/"


def _login_page(english: bool, next_path: str, error: str | None = None, closed: bool = False, status: int = 200):
    if english:
        title, lead = "Investor brief", "This brief is shared with investors and partners. Enter the password the Fidelia team gave you."
        label, button, other = "Password", "Open the brief", '<a href="/brief/?lang=fr" hreflang="fr" lang="fr">Français</a>'
        closed_text = "The investor brief is not open at the moment. Write to contact.fidelia@regisse.com."
        lang = "en"
    else:
        title, lead = "Dossier investisseur", "Ce dossier est réservé aux investisseurs et partenaires. Saisissez le mot de passe transmis par l’équipe Fidelia."
        label, button, other = "Mot de passe", "Ouvrir le dossier", '<a href="/brief/?lang=en" hreflang="en" lang="en">English</a>'
        closed_text = "Le dossier investisseur n’est pas ouvert pour le moment. Écrivez à contact.fidelia@regisse.com."
        lang = "fr"
    body = (
        f'<p class="notice">{closed_text}</p>'
        if closed
        else f"""<p class="lead">{lead}</p>
      {f'<p class="notice" role="alert">{error}</p>' if error else ''}
      <form method="post" action="/brief/login" class="login">
        <input type="hidden" name="next" value="{next_path}" />
        <input type="hidden" name="lang" value="{lang}" />
        <label for="password">{label}</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required autofocus />
        <button type="submit">{button}</button>
      </form>"""
    )
    html = f"""<!doctype html>
<html lang="{lang}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Fidelia — {title}</title>
    <meta name="robots" content="noindex, nofollow" />
    <link rel="icon" type="image/svg+xml" href="/brief/favicon.svg" />
    <link rel="stylesheet" href="/brief/brief.css" />
  </head>
  <body>
    <main class="brief">
      <header class="top">
        <div>
          <p class="eyebrow">Fidelia</p>
          <h1>{title}</h1>
          <p class="where">Abidjan, Côte d’Ivoire</p>
        </div>
        <nav class="tools">{other}</nav>
      </header>
      {body}
    </main>
  </body>
</html>"""
    return HTMLResponse(html, status_code=status, headers=_NO_STORE)


def _wants_english(request: Request, next_path: str = "") -> bool:
    if request.query_params.get("lang") == "en":
        return True
    return next_path.endswith(("/en.html", "/nda.html")) or next_path.startswith("/brief/letter-of-interest")


@router.get("/brief")
async def brief_root() -> RedirectResponse:
    return RedirectResponse("/brief/", status_code=308)


@router.get("/brief/")
async def brief_home(request: Request) -> Response:
    # Where to go after signing in: a page or PDF that was asked for, else the
    # brief in the reader's language.
    asked = request.query_params.get("next")
    next_path = _safe_next(asked) if asked else None
    english = _wants_english(request, next_path or "")
    if _password() is None:
        return _login_page(english, next_path or "/brief/", closed=True, status=503)
    if not _signed_in(request):
        return _login_page(english, next_path or ("/brief/en.html" if english else "/brief/"))
    if next_path and next_path != "/brief/":
        return RedirectResponse(next_path, status_code=303)
    return _page("en.html" if english else "index.html")


@router.get("/brief/{name}")
async def brief_file(name: str, request: Request) -> Response:
    if not _SAFE_NAME.match(name) or not (BRIEF_DIR / name).is_file():
        return Response(status_code=404, headers=_NO_STORE)
    if name in PUBLIC_FILES:
        return FileResponse(BRIEF_DIR / name, headers={"Cache-Control": "public, max-age=86400"})
    next_path = f"/brief/{name}"
    if _password() is None:
        return _login_page(_wants_english(request, next_path), next_path, closed=True, status=503)
    if not _signed_in(request):
        if name.endswith(".html"):
            return _login_page(_wants_english(request, next_path), next_path)
        # A PDF link opened without a session goes through the login first.
        return RedirectResponse(f"/brief/?next={next_path}", status_code=303)
    if name.endswith(".html"):
        return _page(name)
    return FileResponse(BRIEF_DIR / name, headers=_NO_STORE)


def login_limit() -> str:
    """Per-address limit on password attempts. Read at request time so tests
    and operators can change it."""
    return os.getenv("INVESTOR_BRIEF_LOGIN_LIMIT", "5/minute")


@router.post("/brief/login")
@limiter.limit(login_limit)
async def brief_login(
    request: Request,
    password: str = Form(..., max_length=200),
    next: str = Form("/brief/"),
    lang: str = Form("fr"),
) -> Response:
    english = lang == "en"
    target = _safe_next(next)
    expected = _password()
    if expected is None:
        return _login_page(english, target, closed=True, status=503)
    # Compare digests, so the comparison takes the same time whatever the length.
    if not hmac.compare_digest(hashlib.sha256(password.encode()).digest(), hashlib.sha256(expected.encode()).digest()):
        log.warning("investor brief: wrong password from %s", request.client.host if request.client else "?")
        error = "Wrong password." if english else "Mot de passe incorrect."
        return _login_page(english, target, error=error, status=401)

    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        COOKIE,
        _serializer().dumps({"p": _fingerprint(expected)}),
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/brief",
    )
    log.info("investor brief: signed in")
    return response


@router.post("/brief/logout")
async def brief_logout() -> Response:
    response = RedirectResponse("/brief/", status_code=303)
    response.delete_cookie(COOKIE, path="/brief")
    return response
