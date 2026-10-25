"""Pages Barça / Real Madrid / El Clásico : vidéos, directs, calendrier, résultats.
Sources 100 % gratuites : ScoreBat (flux libre), YouTube Data API (optionnel),
TheSportsDB (clé de test publique). Aucune donnée simulée."""
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

from .cache import cached

router = APIRouter(prefix="/api/clubs", tags=["Clubs"])

SCOREBAT_URL = os.getenv("SCOREBAT_URL", "https://www.scorebat.com/video-api/v3/")
SCOREBAT_TOKEN = os.getenv("SCOREBAT_TOKEN", "").strip()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
SPORTSDB = "https://www.thesportsdb.com/api/v1/json/3"

CLUBS = {
    "barcelona": {
        "name": "FC Barcelone", "short": "Barça", "keywords": ["barcelona"],
        "sportsdb_id": "133739", "color": "#a50044", "color2": "#004d98",
        "youtube_query": "FC Barcelona live match",
        "official": [
            {"label": "Barça One (vidéos officielles)", "url": "https://www.fcbarcelona.com/en/barca-one"},
            {"label": "Chaîne YouTube officielle", "url": "https://www.youtube.com/@fcbarcelona"},
        ],
    },
    "real-madrid": {
        "name": "Real Madrid", "short": "Real", "keywords": ["real madrid"],
        "sportsdb_id": "133738", "color": "#febe10", "color2": "#00529f",
        "youtube_query": "Real Madrid live match",
        "official": [
            {"label": "RM Play / Real Madrid TV", "url": "https://www.realmadrid.com/en-US/realmadrid-tv"},
            {"label": "Chaîne YouTube officielle", "url": "https://www.youtube.com/@realmadrid"},
        ],
    },
}
CLASICO_KEYS = ("barcelona", "real madrid")


def _club(slug: str) -> dict:
    if slug not in CLUBS:
        raise HTTPException(404, "Club inconnu (barcelona ou real-madrid).")
    return CLUBS[slug]


async def _http_json(url: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def _scorebat_feed():
    params = {"token": SCOREBAT_TOKEN} if SCOREBAT_TOKEN else None
    return await cached("scorebat", 600, lambda: _http_json(SCOREBAT_URL, params))


def _iframe_src(embed: str) -> str | None:
    m = re.search(r'<iframe[^>]+src=["\']([^"\']+)', embed or "", re.I)
    if not m:
        return None
    src = m.group(1)
    if src.startswith("//"):
        src = "https:" + src
    # Les lecteurs doivent venir de https uniquement.
    return src if src.startswith("https://") else None


def _title_has(title: str, keys) -> bool:
    t = (title or "").lower()
    return all(k in t for k in keys) if isinstance(keys, tuple) else any(k in t for k in keys)


def _extract_videos(feed: dict, predicate) -> list[dict]:
    out = []
    for match in feed.get("response", []) or []:
        title = match.get("title", "")
        if not predicate(title):
            continue
        comp = match.get("competition")
        comp = comp.get("name") if isinstance(comp, dict) else comp
        for v in match.get("videos", []) or []:
            url = _iframe_src(v.get("embed", ""))
            if url:
                out.append({
                    "match": title, "date": match.get("date"), "competition": comp,
                    "title": v.get("title") or title, "embed_url": url,
                    "thumbnail": match.get("thumbnail"), "source": "ScoreBat",
                })
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out


@router.get("/status")
def status():
    return {
        "scorebat": "ok (flux libre)" if not SCOREBAT_TOKEN else "ok (jeton)",
        "youtube": "configuré" if YOUTUBE_API_KEY else "clé absente (directs YouTube désactivés)",
        "thesportsdb": "clé de test publique",
    }


@router.get("/clasico/videos")
async def clasico_videos():
    try:
        feed = await _scorebat_feed()
    except httpx.HTTPError:
        return {"club": "clasico", "videos": [], "error": "ScoreBat injoignable pour le moment."}
    videos = _extract_videos(feed, lambda t: _title_has(t, CLASICO_KEYS))
    return {"club": "clasico", "count": len(videos), "videos": videos}


@router.get("/{slug}/videos")
async def club_videos(slug: str):
    club = _club(slug)
    try:
        feed = await _scorebat_feed()
    except httpx.HTTPError:
        return {"club": slug, "videos": [], "error": "ScoreBat injoignable pour le moment."}
    videos = _extract_videos(feed, lambda t: _title_has(t, club["keywords"]))
    return {"club": slug, "count": len(videos), "videos": videos}


@router.get("/{slug}/live")
async def club_live(slug: str):
    club = _club(slug)
    if not YOUTUBE_API_KEY:
        return {"club": slug, "configured": False, "videos": [],
                "note": "Ajoutez YOUTUBE_API_KEY dans .env pour chercher les directs officiels."}

    async def load():
        return await _http_json("https://www.googleapis.com/youtube/v3/search", {
            "part": "snippet", "type": "video", "eventType": "live",
            "videoEmbeddable": "true", "q": club["youtube_query"],
            "maxResults": 6, "key": YOUTUBE_API_KEY,
        })

    try:
        # Cache 15 min : une recherche coûte 100 unités sur 10 000 par jour.
        payload = await cached(f"yt-live-{slug}", 900, load)
    except httpx.HTTPError:
        return {"club": slug, "configured": True, "videos": [], "error": "YouTube indisponible ou quota atteint."}
    videos = []
    for item in payload.get("items", []):
        vid = item.get("id", {}).get("videoId")
        if vid:
            sn = item.get("snippet", {})
            videos.append({
                "title": sn.get("title"), "channel": sn.get("channelTitle"),
                "embed_url": "https://www.youtube-nocookie.com/embed/" + vid,
                "thumbnail": (sn.get("thumbnails", {}).get("medium") or {}).get("url"),
                "source": "YouTube",
            })
    return {"club": slug, "configured": True, "count": len(videos), "videos": videos}


def _event(e: dict) -> dict:
    ts = e.get("strTimestamp") or ""
    return {
        "id": e.get("idEvent"), "home": e.get("strHomeTeam"), "away": e.get("strAwayTeam"),
        "home_score": e.get("intHomeScore"), "away_score": e.get("intAwayScore"),
        "competition": e.get("strLeague"), "date": e.get("dateEvent"),
        "time": (e.get("strTime") or "")[:5], "timestamp": ts,
        "venue": e.get("strVenue"),
    }


@router.get("/{slug}/matches")
async def club_matches(slug: str):
    club = _club(slug)
    tid = club["sportsdb_id"]
    try:
        nxt = await cached(f"next-{tid}", 1800, lambda: _http_json(f"{SPORTSDB}/eventsnext.php", {"id": tid}))
        last = await cached(f"last-{tid}", 1800, lambda: _http_json(f"{SPORTSDB}/eventslast.php", {"id": tid}))
    except httpx.HTTPError:
        return {"club": slug, "next": [], "last": [], "error": "Calendrier indisponible pour le moment."}
    nxt_l = [_event(e) for e in (nxt.get("events") or [])]
    last_l = [_event(e) for e in (last.get("results") or [])]
    last_l.sort(key=lambda x: x.get("date") or "", reverse=True)
    return {"club": slug, "next": nxt_l, "last": last_l}


@router.get("/{slug}/info")
def club_info(slug: str):
    c = _club(slug)
    return {"slug": slug, **{k: c[k] for k in ("name", "short", "color", "color2", "official")}}


@router.get("/{slug}/badge")
async def club_badge(slug: str):
    c = _club(slug)
    try:
        d = await cached(f"badge-{slug}", 86400,
                         lambda: _http_json(f"{SPORTSDB}/lookupteam.php", {"id": c["sportsdb_id"]}))
        team = (d.get("teams") or [{}])[0]
        return {"slug": slug, "badge": team.get("strBadge") or team.get("strLogo"),
                "banner": team.get("strBanner") or team.get("strFanart1")}
    except httpx.HTTPError:
        return {"slug": slug, "badge": None, "banner": None}
