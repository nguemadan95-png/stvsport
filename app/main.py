from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import os, secrets
import httpx
from dotenv import load_dotenv
from .database import Base, engine, get_db, SessionLocal
from . import models
from .security import hash_password, verify_password, create_token, decode_token
from . import clubs

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
SPORTSAPI_BASE_URL = os.getenv("SPORTSAPI_BASE_URL", "https://api.sportsapi.app").rstrip("/")
SPORTSAPI_KEY = os.getenv("SPORTSAPI_KEY", "").strip()

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.scalar(select(models.User).where(models.User.username == "admin")):
            pwd = os.getenv("ADMIN_PASSWORD", "").strip()
            generated = not pwd
            if generated:
                pwd = secrets.token_urlsafe(9)
            db.add(models.User(username="admin", email="admin@stv-sport.local",
                               password_hash=hash_password(pwd), is_admin=True))
            db.commit()
            if generated:
                (ROOT / "ADMIN_MOT_DE_PASSE.txt").write_text(
                    f"Identifiant : admin\nMot de passe : {pwd}\n\nChangez-le dans STV SPORT (menu Compte).\n",
                    encoding="utf-8")
                print(f"[STV SPORT] Compte admin cree. Mot de passe dans ADMIN_MOT_DE_PASSE.txt")
    finally:
        db.close()
    yield


app = FastAPI(title="STV SPORT API", version="3.0.0",
              description="STV SPORT : Barça, Real Madrid, El Clásico, directs et replays autorisés.",
              lifespan=lifespan)
# Application servie par le même serveur : CORS limité à l'origine locale.
app.add_middleware(CORSMiddleware,
                   allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(clubs.router)


@app.middleware("http")
async def no_cache_front(request, call_next):
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp
STATIC = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str
    password: str = Field(min_length=8)
class LoginIn(BaseModel):
    username: str
    password: str
ALLOWED_STREAM_TYPES = {"hls", "mp4", "embed"}
class ChannelIn(BaseModel):
    name: str
    sport: str = "Multi-sports"
    description: str = ""
    stream_url: str
    stream_type: str = "hls"
    logo_url: str = ""
    is_live: bool = True
    is_active: bool = True
    source_note: str = "Flux fourni par l’administrateur"
class MatchIn(BaseModel):
    home_team: str
    away_team: str
    competition: str = ""
    sport: str = "Football"
    starts_at: str = ""
    status: str = "upcoming"
    home_score: int = 0
    away_score: int = 0
    stream_url: str = ""
    replay_url: str = ""
    thumbnail_url: str = ""
    description: str = ""
class VideoIn(BaseModel):
    title: str
    sport: str = "Football"
    category: str = "Highlights"
    video_url: str
    thumbnail_url: str = ""
    description: str = ""

def user_from_header(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_token(authorization[7:])
    if not payload:
        return None
    return db.get(models.User, int(payload["sub"]))

def require_user(user=Depends(user_from_header)):
    if not user: raise HTTPException(401, "Connectez-vous pour effectuer cette action.")
    return user

def require_admin(user=Depends(require_user)):
    if not user.is_admin: raise HTTPException(403, "Accès administrateur requis.")
    return user

def as_dict(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

@app.get("/")
def home(): return FileResponse(STATIC / "index.html")
@app.get("/api/health")
def health(): return {"status": "ok", "app": "STV SPORT", "version": "3.0.0", "database": "sqlite"}

@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(models.User).where((models.User.username == data.username) | (models.User.email == data.email))):
        raise HTTPException(409, "Nom d’utilisateur ou e-mail déjà utilisé.")
    u = models.User(username=data.username, email=data.email, password_hash=hash_password(data.password))
    db.add(u); db.commit(); db.refresh(u)
    return {"token": create_token(u.id, False), "user": {"id": u.id, "username": u.username, "is_admin": False}}
@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(models.User).where(models.User.username == data.username))
    if not u or not verify_password(data.password, u.password_hash): raise HTTPException(401, "Identifiants incorrects.")
    return {"token": create_token(u.id, u.is_admin), "user": {"id": u.id, "username": u.username, "is_admin": u.is_admin}}
@app.get("/api/me")
def me(user=Depends(require_user)): return {"id": user.id, "username": user.username, "is_admin": user.is_admin}

class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)
@app.post("/api/me/password")
def change_password(data: PasswordIn, db: Session = Depends(get_db), user=Depends(require_user)):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(401, "Ancien mot de passe incorrect.")
    user.password_hash = hash_password(data.new_password); db.commit()
    return {"ok": True}

@app.get("/api/sportsapi/status")
def sportsapi_status():
    return {"configured": bool(SPORTSAPI_KEY), "provider": "SportsAPI", "base_url": SPORTSAPI_BASE_URL}

@app.get("/api/sportsapi/sports")
async def sportsapi_sports():
    if not SPORTSAPI_KEY:
        raise HTTPException(503, "Clé SportsAPI absente. Configurez SPORTSAPI_KEY dans le fichier .env.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{SPORTSAPI_BASE_URL}/v2/sports", headers={"Authorization": f"Bearer {SPORTSAPI_KEY}"})
        if response.status_code == 401:
            raise HTTPException(401, "Clé SportsAPI invalide ou révoquée.")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Erreur renvoyée par SportsAPI.")
    except httpx.HTTPError:
        raise HTTPException(502, "Impossible de joindre SportsAPI.")

@app.get("/api/sportsapi/livescores")
async def sportsapi_livescores(sport: Optional[str] = None):
    if not SPORTSAPI_KEY:
        raise HTTPException(503, "Clé SportsAPI absente. Configurez SPORTSAPI_KEY dans le fichier .env.")
    params = {"sport": sport} if sport else {}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{SPORTSAPI_BASE_URL}/v2/livescores", headers={"Authorization": f"Bearer {SPORTSAPI_KEY}"}, params=params)
        if response.status_code == 401:
            raise HTTPException(401, "Clé SportsAPI invalide ou révoquée.")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Erreur renvoyée par SportsAPI.")
    except httpx.HTTPError:
        raise HTTPException(502, "Impossible de joindre SportsAPI.")

@app.get("/api/channels")
def channels(db: Session = Depends(get_db)):
    return [as_dict(x) for x in db.scalars(select(models.Channel).where(models.Channel.is_active == True)).all()]
@app.post("/api/channels")
def add_channel(data: ChannelIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    if data.stream_type not in ALLOWED_STREAM_TYPES: raise HTTPException(422,"Type de flux : hls, mp4 ou embed.")
    if not data.stream_url.lower().startswith("https://"): raise HTTPException(422,"L'URL du flux doit commencer par https://")
    x=models.Channel(**data.model_dump()); db.add(x); db.commit(); db.refresh(x); return as_dict(x)
@app.delete("/api/channels/{item_id}")
def delete_channel(item_id: int, db: Session = Depends(get_db), user=Depends(require_admin)):
    x=db.get(models.Channel,item_id)
    if not x: raise HTTPException(404,"Chaîne introuvable")
    db.delete(x); db.commit(); return {"ok":True}

@app.get("/api/matches")
def matches(sport: Optional[str]=None, status: Optional[str]=None, q_text: Optional[str]=None, db: Session=Depends(get_db)):
    q=select(models.Match)
    if q_text:
        like=f"%{q_text}%"
        q=q.where(models.Match.home_team.ilike(like)|models.Match.away_team.ilike(like)|models.Match.competition.ilike(like))
    if sport and sport.lower() != "tous": q=q.where(models.Match.sport == sport)
    if status: q=q.where(models.Match.status == status)
    return [as_dict(x) for x in db.scalars(q.order_by(models.Match.id.desc())).all()]
@app.post("/api/matches")
def add_match(data: MatchIn, db: Session=Depends(get_db), user=Depends(require_admin)):
    x=models.Match(**data.model_dump()); db.add(x); db.commit(); db.refresh(x); return as_dict(x)
@app.delete("/api/matches/{item_id}")
def delete_match(item_id:int, db:Session=Depends(get_db), user=Depends(require_admin)):
    x=db.get(models.Match,item_id)
    if not x: raise HTTPException(404,"Match introuvable")
    db.delete(x); db.commit(); return {"ok":True}

@app.get("/api/videos")
def videos(sport: Optional[str]=None, db:Session=Depends(get_db)):
    q=select(models.Video)
    if sport and sport.lower()!="tous": q=q.where(models.Video.sport==sport)
    return [as_dict(x) for x in db.scalars(q.order_by(models.Video.id.desc())).all()]
@app.post("/api/videos")
def add_video(data:VideoIn, db:Session=Depends(get_db), user=Depends(require_admin)):
    x=models.Video(**data.model_dump()); db.add(x); db.commit(); db.refresh(x); return as_dict(x)
@app.delete("/api/videos/{item_id}")
def delete_video(item_id:int, db:Session=Depends(get_db), user=Depends(require_admin)):
    x=db.get(models.Video,item_id)
    if not x: raise HTTPException(404,"Vidéo introuvable")
    db.delete(x); db.commit(); return {"ok":True}

@app.post("/api/history")
def history(data: dict, db:Session=Depends(get_db), user=Depends(require_user)):
    db.add(models.WatchHistory(user_id=user.id,title=str(data.get("title","Vidéo")),video_url=str(data.get("video_url",""))))
    db.commit(); return {"ok":True}
@app.get("/api/history")
def get_history(db:Session=Depends(get_db), user=Depends(require_user)):
    return [as_dict(x) for x in db.scalars(select(models.WatchHistory).where(models.WatchHistory.user_id==user.id).order_by(models.WatchHistory.id.desc()).limit(30)).all()]

@app.get("/api/favorites")
def favorites(db:Session=Depends(get_db), user=Depends(require_user)):
    ids=[x.match_id for x in db.scalars(select(models.Favorite).where(models.Favorite.user_id==user.id)).all()]
    return [as_dict(x) for x in db.scalars(select(models.Match).where(models.Match.id.in_(ids))).all()] if ids else []
@app.post("/api/favorites/{match_id}")
def favorite(match_id:int, db:Session=Depends(get_db), user=Depends(require_user)):
    if not db.get(models.Match,match_id): raise HTTPException(404,"Match introuvable")
    existing=db.scalar(select(models.Favorite).where(models.Favorite.user_id==user.id,models.Favorite.match_id==match_id))
    if existing: db.delete(existing); state=False
    else: db.add(models.Favorite(user_id=user.id,match_id=match_id)); state=True
    db.commit(); return {"favorite":state}

@app.get("/api/admin/summary")
def summary(db:Session=Depends(get_db), user=Depends(require_admin)):
    return {"users":len(db.scalars(select(models.User)).all()),"channels":len(db.scalars(select(models.Channel)).all()),"matches":len(db.scalars(select(models.Match)).all()),"videos":len(db.scalars(select(models.Video)).all())}


# Logos automatiques des clubs et drapeaux des sélections nationales.
_TEAM_LOGO_CACHE = {}
_COUNTRY_CODES = {
    "gabon": "ga", "france": "fr", "espagne": "es", "spain": "es",
    "angleterre": "gb-eng", "england": "gb-eng", "portugal": "pt",
    "bresil": "br", "brazil": "br", "argentine": "ar", "argentina": "ar",
    "allemagne": "de", "germany": "de", "italie": "it", "italy": "it",
    "maroc": "ma", "morocco": "ma", "senegal": "sn", "cote d'ivoire": "ci",
    "côte d'ivoire": "ci", "cameroun": "cm", "cameroon": "cm",
    "nigeria": "ng", "ghana": "gh", "belgique": "be", "belgium": "be",
    "pays-bas": "nl", "netherlands": "nl", "uruguay": "uy",
    "etats-unis": "us", "états-unis": "us", "usa": "us",
    "japon": "jp", "japan": "jp", "coree du sud": "kr",
    "corée du sud": "kr", "mexique": "mx", "mexico": "mx",
}

@app.get("/api/team-logo/{team_name:path}")
async def team_logo(team_name: str):
    import unicodedata
    name = team_name.strip()
    normalized = unicodedata.normalize("NFKD", name.lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = " ".join(normalized.split())
    if not normalized:
        return {"name": name, "logo_url": None, "kind": "unknown"}

    # National-team names use official country flag images.
    code = _COUNTRY_CODES.get(normalized)
    if code:
        return {
            "name": name,
            "logo_url": f"https://flagcdn.com/w160/{code}.png",
            "kind": "country"
        }

    # TheSportsDB free demo endpoint supplies club badges when available.
    cache_key = normalized
    if cache_key in _TEAM_LOGO_CACHE:
        return _TEAM_LOGO_CACHE[cache_key]

    known = {"barcelona": "133739", "fc barcelona": "133739", "barca": "133739",
             "real madrid": "133738", "real madrid cf": "133738"}
    if normalized in known:
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                r = await client.get("https://www.thesportsdb.com/api/v1/json/3/lookupteam.php",
                                     params={"id": known[normalized]})
                r.raise_for_status()
            t = (r.json().get("teams") or [{}])[0]
            result = {"name": name, "logo_url": t.get("strBadge"), "kind": "club"}
            if result["logo_url"]:
                _TEAM_LOGO_CACHE[cache_key] = result
            return result
        except (httpx.HTTPError, ValueError):
            return {"name": name, "logo_url": None, "kind": "unknown"}

    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            response = await client.get(
                "https://www.thesportsdb.com/api/v1/json/3/searchteams.php",
                params={"t": name}
            )
            response.raise_for_status()
            payload = response.json()
        teams = payload.get("teams") or []
        soccer = [t for t in teams if t.get("strSport") == "Soccer"] or teams
        badge = next((item.get("strBadge") for item in soccer if item.get("strBadge")), None)
        result = {"name": name, "logo_url": badge, "kind": "club"}
    except (httpx.HTTPError, ValueError):
        result = {"name": name, "logo_url": None, "kind": "unknown"}

    if result.get("logo_url"):
        _TEAM_LOGO_CACHE[cache_key] = result
    return result
