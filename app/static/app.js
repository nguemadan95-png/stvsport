/* STV SPORT v3 — frontend */
let token = localStorage.getItem('stv_token'), currentUser = null, registering = false, currentClub = 'barcelona';
const $ = id => document.getElementById(id);
const esc = (s = '') => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function headers() { return token ? { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }; }
async function api(path, opts = {}) {
  const r = await fetch('/api' + path, { ...opts, headers: { ...headers(), ...(opts.headers || {}) } });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(typeof d.detail === 'string' ? d.detail : 'Erreur serveur');
  return d;
}
let toastTimer;
function toast(t) { const el = $('toast'); el.textContent = t; el.style.display = 'block'; clearTimeout(toastTimer); toastTimer = setTimeout(() => el.style.display = 'none', 3000); }

/* ---------- Logos (clubs) et drapeaux (pays), mis en cache dans le navigateur ---------- */
const logoCache = JSON.parse(localStorage.getItem('stv_logos_v2') || '{}');
const logoPending = {};
async function teamLogoUrl(name) {
  const key = String(name || '').trim();
  if (!key) return null;
  if (key in logoCache) return logoCache[key];
  if (!logoPending[key]) {
    logoPending[key] = fetch('/api/team-logo/' + encodeURIComponent(key)).then(r => r.json())
      .then(d => { if (d.logo_url) { logoCache[key] = d.logo_url; try { localStorage.setItem('stv_logos_v2', JSON.stringify(logoCache)); } catch (e) { } } return d.logo_url || null; })
      .catch(() => null);
  }
  return logoPending[key];
}
function logoMarkup(name, url, big = false) {
  const n = esc(name), cls = big ? ' big' : '';
  const img = url ? `<img class="team-logo${cls}" src="${esc(url)}" alt="Logo ${n}" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'team-logo-fallback${cls}',textContent:this.alt.slice(5,7).toUpperCase()}))">`
    : `<span class="team-logo-fallback${cls}">${n.slice(0, 2).toUpperCase()}</span>`;
  return `<span class="team-chip">${img}<b>${n}</b></span>`;
}

/* ---------- Cartes ---------- */
async function matchCard(home, away, meta, desc, actions, hs = '', as = '') {
  const [hu, au] = await Promise.all([teamLogoUrl(home), teamLogoUrl(away)]);
  return `<article class="item match-item"><div class="match-scoreline">${logoMarkup(home, hu)}<strong class="score">${esc(hs)} – ${esc(as)}</strong>${logoMarkup(away, au)}</div>
  <div class="item-body"><div class="muted">${esc(meta || '')}</div><p class="muted">${esc(desc || '')}</p><div class="item-actions">${actions}</div></div></article>`;
}
function card(title, meta, desc, actions, thumb = '') {
  return `<article class="item"><div class="thumb">${thumb ? `<img src="${esc(thumb)}" alt="" loading="lazy" onerror="this.remove()">` : 'STV SPORT'}</div>
  <div class="item-body"><h3>${esc(title)}</h3><div class="muted">${esc(meta || '')}</div><p class="muted">${esc(desc || '')}</p><div class="item-actions">${actions}</div></div></article>`;
}
const playBtn = (label, title, url, type = 'auto', note = '', cls = 'primary') =>
  `<button class="${cls}" data-action="play" data-title="${esc(title)}" data-url="${esc(url)}" data-type="${esc(type)}" data-note="${esc(note)}">${label}</button>`;
const delBtn = (path, id) => currentUser?.is_admin ? `<button class="secondary danger" data-action="delete" data-path="${path}" data-id="${id}">Supprimer</button>` : '';
const fmtDate = (ts, d, t) => {
  try {
    const dt = ts ? new Date(ts.endsWith('Z') ? ts : ts + 'Z') : new Date(`${d}T${t || '00:00'}:00Z`);
    if (isNaN(dt)) return d || '';
    return dt.toLocaleString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch (e) { return d || ''; }
};

/* ---------- Lecteur ---------- */
let hlsLoader = null;
function loadHls() {
  if (window.Hls) return Promise.resolve();
  if (!hlsLoader) hlsLoader = new Promise((res, rej) => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js';
    s.onload = res; s.onerror = rej; document.head.append(s);
  });
  return hlsLoader;
}
function ytId(u) {
  const m = u.match(/youtube(?:-nocookie)?\.com\/(?:embed\/|watch\?v=)([\w-]{6,})/) || u.match(/youtu\.be\/([\w-]{6,})/);
  return m ? m[1] : null;
}
function toEmbed(u) {
  const id = ytId(u);
  // youtube.com est moins souvent bloqué que youtube-nocookie.com par les réseaux/FAI
  return id ? 'https://www.youtube.com/embed/' + id + '?rel=0' : u;
}
async function play(title, url, type = 'auto', note = '') {
  if (!url) { toast('Aucun flux vidéo n’a été configuré pour ce programme.'); return; }
  const u = url.trim();
  if (!/^https:\/\//i.test(u)) { toast('Lien refusé : seules les URL https sont lues.'); return; }
  $('player-title').textContent = title; $('player-note').textContent = note;
  const area = $('player-area'); area.innerHTML = '';
  const isEmbed = type === 'embed' || /youtube\.com\/(embed|watch)|youtu\.be|youtube-nocookie\.com|vimeo\.com|scorebat\.com/i.test(u);
  if (isEmbed) {
    const f = document.createElement('iframe');
    f.src = toEmbed(u); f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen'; f.allowFullscreen = true;
    f.referrerPolicy = 'strict-origin-when-cross-origin'; area.append(f);
    const id = ytId(u);
    if (id) {
      const a = document.createElement('a'); a.href = 'https://www.youtube.com/watch?v=' + id; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.className = 'secondary yt-fallback'; a.textContent = 'La vidéo ne s’affiche pas ? Ouvrir sur YouTube ↗'; area.append(a);
    } else {
      const a = document.createElement('a'); a.href = u; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.className = 'secondary yt-fallback'; a.textContent = 'Ouvrir dans un nouvel onglet ↗'; area.append(a);
    }
  } else {
    const v = document.createElement('video'); v.controls = true; v.autoplay = true; v.playsInline = true; area.append(v);
    if (/\.m3u8(\?|$)/i.test(u)) {
      try { await loadHls(); } catch (e) { }
      if (window.Hls && Hls.isSupported()) { const h = new Hls(); h.loadSource(u); h.attachMedia(v); v._hls = h; }
      else v.src = u;
    } else v.src = u;
  }
  $('player-modal').classList.remove('hidden');
  if (token) api('/history', { method: 'POST', body: JSON.stringify({ title, video_url: u }) }).catch(() => { });
}
function closePlayer() { const v = $('player-area').querySelector('video'); if (v?._hls) v._hls.destroy(); $('player-modal').classList.add('hidden'); $('player-area').innerHTML = ''; }

/* ---------- Pages clubs ---------- */
const CLUB_LABEL = { barcelona: 'FC Barcelona', 'real-madrid': 'Real Madrid' };
const CLUB_COLORS = { barcelona: ['#a50044', '#004d98'], 'real-madrid': ['#febe10', '#00529f'] };
const CLUB_KEY = { barcelona: 'barcelona', 'real-madrid': 'real madrid' };

function videoCards(videos, emptyMsg) {
  if (!videos.length) return `<div class="empty">${esc(emptyMsg)}</div>`;
  return videos.map(v => `<article class="item"><div class="thumb">${v.thumbnail ? `<img src="${esc(v.thumbnail)}" alt="" loading="lazy" onerror="this.remove()">` : '▶'}</div>
  <div class="item-body"><h3>${esc(v.match || v.title)}</h3><div class="muted">${esc([v.competition, v.channel, v.source].filter(Boolean).join(' • '))}</div>
  <div class="item-actions">${playBtn('▶ Regarder', v.match || v.title, v.embed_url, 'embed', 'Source : ' + v.source)}</div></div></article>`).join('');
}
function findSummary(videos, opp) {
  const o = String(opp || '').toLowerCase();
  return o ? videos.find(v => (v.match || '').toLowerCase().includes(o)) : null;
}
async function loadClub(slug) {
  currentClub = slug;
  document.querySelectorAll('#club-tabs .tab').forEach(b => b.classList.toggle('active', b.dataset.club === slug));
  const view = $('club-view');
  view.innerHTML = '<div class="empty">Chargement…</div>';

  if (slug === 'clasico') {
    const [b1, b2, cv] = await Promise.all([teamLogoUrl('Barcelona'), teamLogoUrl('Real Madrid'), api('/clubs/clasico/videos').catch(e => ({ videos: [], error: e.message }))]);
    if (currentClub !== slug) return;
    view.innerHTML = `<div class="club-banner" style="--c1:#a50044;--c2:#febe10"><div class="vs-row">${logoMarkup('FC Barcelona', b1, true)}<span class="vs">VS</span>${logoMarkup('Real Madrid', b2, true)}</div><p>Tous les résumés d’El Clásico disponibles gratuitement.</p></div>
    <h3 class="sub">Résumés et buts</h3><div class="cards">${videoCards(cv.videos || [], cv.error || 'Aucun résumé d’El Clásico dans le flux gratuit pour le moment. Revenez après le prochain match.')}</div>`;
    return;
  }

  const [info, badge, videos, live, matches] = await Promise.all([
    api(`/clubs/${slug}/info`).catch(() => null), api(`/clubs/${slug}/badge`).catch(() => ({})),
    api(`/clubs/${slug}/videos`).catch(e => ({ videos: [], error: e.message })),
    api(`/clubs/${slug}/live`).catch(e => ({ videos: [], error: e.message })),
    api(`/clubs/${slug}/matches`).catch(e => ({ next: [], last: [], error: e.message })),
  ]);
  const [c1, c2] = CLUB_COLORS[slug];
  const vids = videos.videos || [];

  const nextHtml = (await Promise.all((matches.next || []).slice(0, 5).map(m =>
    matchCard(m.home, m.away, `${m.competition || ''} • ${fmtDate(m.timestamp, m.date, m.time)}`, m.venue ? 'Stade : ' + m.venue : '', '', '', '')))).join('');
  const lastHtml = (await Promise.all((matches.last || []).slice(0, 5).map(m => {
    const opp = (m.home || '').toLowerCase().includes(CLUB_KEY[slug]) ? m.away : m.home;
    const sum = findSummary(vids, opp);
    return matchCard(m.home, m.away, `${m.competition || ''} • ${m.date || ''}`, '',
      sum ? playBtn('▶ Résumé', sum.match, sum.embed_url, 'embed', 'Source : ScoreBat') : '<span class="muted">Résumé pas encore disponible</span>',
      m.home_score ?? '-', m.away_score ?? '-');
  }))).join('');
  if (currentClub !== slug) return;

  const liveMsg = live.configured === false ? (live.note || '') : (live.error || 'Aucun direct officiel trouvé en ce moment. STV SPORT n’affiche que de vrais flux autorisés.');
  const links = (info?.official || []).map(o => `<a class="secondary" href="${esc(o.url)}" target="_blank" rel="noopener noreferrer">${esc(o.label)} ↗</a>`).join('');

  view.innerHTML = `<div class="club-banner" style="--c1:${c1};--c2:${c2}"><div class="vs-row">${logoMarkup(CLUB_LABEL[slug], badge.badge, true)}</div><p>Directs officiels, résumés, calendrier et résultats.</p><div class="actions">${links}</div></div>
  <h3 class="sub">● Directs officiels</h3><div class="cards">${videoCards(live.videos || [], liveMsg)}</div>
  <h3 class="sub">Prochains matchs</h3><div class="cards">${nextHtml || '<div class="empty">' + esc(matches.error || 'Calendrier indisponible.') + '</div>'}</div>
  <h3 class="sub">Derniers résultats</h3><div class="cards">${lastHtml || '<div class="empty">Aucun résultat récent.</div>'}</div>
  <h3 class="sub">Résumés et buts</h3><div class="cards">${videoCards(vids.slice(0, 9), videos.error || 'Aucun résumé disponible dans le flux gratuit pour l’instant.')}</div>`;
}

async function loadHeroLogos() {
  const [b, r] = await Promise.all([teamLogoUrl('Barcelona'), teamLogoUrl('Real Madrid')]);
  $('hero-barca').innerHTML = logoMarkup('Barça', b, true);
  $('hero-real').innerHTML = logoMarkup('Real', r, true);
}

/* ---------- Sections générales ---------- */
async function loadApiLive() {
  const t = $('api-live-list');
  try {
    const result = await api('/sportsapi/livescores');
    const xs = result.data || [];
    t.innerHTML = xs.length ? (await Promise.all(xs.map(x => matchCard(x.home?.name || 'Équipe 1', x.away?.name || 'Équipe 2',
      '● LIVE • ' + (x.league?.name || x.sport || 'Sport') + ' • ' + (x.status?.description || x.status?.type || 'En cours'),
      'Score automatique SportsAPI. Le flux vidéo doit venir d’un diffuseur autorisé.', '', x.homeScore?.current ?? '-', x.awayScore?.current ?? '-')))).join('')
      : '<div class="empty">Aucun match en cours selon SportsAPI.</div>';
  } catch (e) { t.innerHTML = '<div class="empty">' + esc(e.message) + ' (optionnel : ajoutez SPORTSAPI_KEY dans .env)</div>'; }
}
async function loadChannels() {
  const xs = await api('/channels');
  const mk = (x, live) => card((live ? '● ' : '') + x.name, (live ? 'EN DIRECT • ' : '') + x.sport, x.description,
    playBtn(live ? '▶ Voir le direct' : '▶ Regarder', x.name, x.stream_url, x.stream_type, x.source_note) + delBtn('channels', x.id), x.logo_url);
  $('channel-list').innerHTML = xs.length ? xs.map(x => mk(x, false)).join('') : '<div class="empty">Aucune chaîne ajoutée. Connectez-vous en administrateur pour ajouter vos flux autorisés.</div>';
  const lives = xs.filter(x => x.is_live);
  $('live-list').innerHTML = lives.length ? lives.map(x => mk(x, true)).join('') : '<div class="empty">Aucun direct configuré. Ajoutez un flux autorisé dans l’administration, ou consultez les directs officiels de chaque club ci-dessus.</div>';
}
async function loadMatches() {
  const sport = $('sport-filter').value, q = $('search').value.trim();
  const qs = new URLSearchParams(); if (sport !== 'Tous') qs.set('sport', sport); if (q) qs.set('q_text', q);
  const xs = await api('/matches' + (qs.toString() ? '?' + qs : ''));
  $('match-list').innerHTML = xs.length ? (await Promise.all(xs.map(x => matchCard(x.home_team, x.away_team,
    `${x.competition} • ${x.sport} • ${x.status === 'live' ? 'EN DIRECT' : x.status === 'finished' ? 'TERMINÉ' : x.starts_at}`, x.description,
    (x.stream_url ? playBtn('▶ Direct', x.home_team + ' - ' + x.away_team, x.stream_url) : '') + (x.replay_url ? playBtn('Replay', 'Rediffusion', x.replay_url, 'auto', '', 'secondary') : '') +
    `<button class="secondary" data-action="fav" data-id="${x.id}">☆ Favori</button>` + delBtn('matches', x.id), x.home_score ?? '', x.away_score ?? '')))).join('')
    : '<div class="empty">Aucun événement publié. L’administrateur peut ajouter le calendrier des matchs.</div>';
}
async function loadVideos() {
  const xs = await api('/videos');
  $('video-list').innerHTML = xs.length ? xs.map(x => card(x.title, x.sport + ' • ' + x.category, x.description, playBtn('▶ Regarder', x.title, x.video_url) + delBtn('videos', x.id), x.thumbnail_url)).join('')
    : '<div class="empty">Les rediffusions apparaîtront ici après leur ajout.</div>';
}
async function loadAccountData() {
  if (!currentUser) { $('favs').classList.add('hidden'); return; }
  const [favs, hist] = await Promise.all([api('/favorites').catch(() => []), api('/history').catch(() => [])]);
  $('favs').classList.remove('hidden');
  $('fav-list').innerHTML = favs.length ? (await Promise.all(favs.map(x => matchCard(x.home_team, x.away_team, x.competition + ' • ' + x.sport, '', `<button class="secondary" data-action="fav" data-id="${x.id}">★ Retirer</button>`, x.home_score ?? '', x.away_score ?? '')))).join('') : '<div class="empty">Aucun favori pour l’instant.</div>';
  $('history-list').innerHTML = hist.length ? hist.slice(0, 10).map(h => `<div class="hist-row">${playBtn('▶', h.title, h.video_url, 'auto', '', 'secondary')}<span>${esc(h.title)}</span></div>`).join('') : '<div class="muted">Rien regardé pour l’instant.</div>';
}
async function refresh() {
  try {
    if (token) {
      try { currentUser = await api('/me'); } catch (e) { token = null; localStorage.removeItem('stv_token'); currentUser = null; }
    } else currentUser = null;
    const isUser = !!currentUser;
    $('who').textContent = isUser ? currentUser.username : 'Invité';
    $('btn-login').classList.toggle('hidden', isUser); $('logout').classList.toggle('hidden', !isUser); $('btn-pass').classList.toggle('hidden', !isUser);
    $('admin').classList.toggle('hidden', !currentUser?.is_admin);
    if (currentUser?.is_admin) { const s = await api('/admin/summary'); $('stats').innerHTML = Object.entries(s).map(([k, v]) => `<div class="stat"><b>${v}</b>${k}</div>`).join(''); }
    await Promise.all([loadChannels(), loadMatches(), loadVideos(), loadAccountData()]);
  } catch (e) { console.error(e); }
}

/* ---------- Compte ---------- */
function toggleAuth() {
  registering = !registering;
  $('auth-title').textContent = registering ? 'Créer un compte' : 'Connexion';
  $('auth-email').classList.toggle('hidden', !registering); $('auth-email').required = registering;
  $('auth-submit').textContent = registering ? 'Créer mon compte' : 'Se connecter';
  $('auth-switch').innerHTML = registering ? 'Déjà inscrit ? <a data-action="toggle-auth">Se connecter</a>' : 'Pas encore de compte ? <a data-action="toggle-auth">Créer un compte</a>';
}
async function authSubmit(e) {
  e.preventDefault();
  try {
    const body = { username: $('auth-user').value.trim(), password: $('auth-pass').value };
    if (registering) body.email = $('auth-email').value.trim();
    const d = await api('/auth/' + (registering ? 'register' : 'login'), { method: 'POST', body: JSON.stringify(body) });
    token = d.token; localStorage.setItem('stv_token', token); $('auth-modal').classList.add('hidden'); $('auth-pass').value = '';
    toast('Connexion réussie'); await refresh();
  } catch (err) { toast(err.message); }
}
function logout() { token = null; currentUser = null; localStorage.removeItem('stv_token'); toast('Déconnexion'); refresh(); }

/* ---------- Événements (délégation) ---------- */
document.addEventListener('click', async e => {
  const el = e.target.closest('[data-action]'); if (!el) return;
  const d = el.dataset;
  switch (d.action) {
    case 'play': play(d.title, d.url, d.type, d.note); break;
    case 'close-player': closePlayer(); break;
    case 'club': loadClub(d.club); break;
    case 'refresh-live': loadApiLive(); break;
    case 'open-auth': $('auth-modal').classList.remove('hidden'); break;
    case 'close-auth': $('auth-modal').classList.add('hidden'); break;
    case 'toggle-auth': toggleAuth(); break;
    case 'open-pass': $('pass-modal').classList.remove('hidden'); break;
    case 'close-pass': $('pass-modal').classList.add('hidden'); break;
    case 'logout': logout(); break;
    case 'fav':
      if (!token) { $('auth-modal').classList.remove('hidden'); return; }
      try { const r = await api('/favorites/' + d.id, { method: 'POST' }); toast(r.favorite ? 'Ajouté aux favoris' : 'Retiré des favoris'); loadAccountData(); } catch (err) { toast(err.message); }
      break;
    case 'delete':
      if (!confirm('Supprimer cet élément ?')) return;
      try { await api(`/${d.path}/${d.id}`, { method: 'DELETE' }); toast('Supprimé'); refresh(); } catch (err) { toast(err.message); }
      break;
  }
});
document.addEventListener('submit', async e => {
  const f = e.target;
  if (f.id === 'auth-form') return authSubmit(e);
  if (f.id === 'pass-form') {
    e.preventDefault();
    try { await api('/me/password', { method: 'POST', body: JSON.stringify({ old_password: $('pass-old').value, new_password: $('pass-new').value }) }); toast('Mot de passe modifié'); f.reset(); $('pass-modal').classList.add('hidden'); } catch (err) { toast(err.message); }
    return;
  }
  if (f.dataset.form) {
    e.preventDefault();
    const obj = Object.fromEntries(new FormData(f).entries());
    try { await api(f.dataset.form, { method: 'POST', body: JSON.stringify(obj) }); f.reset(); toast('Contenu ajouté'); refresh(); } catch (err) { toast(err.message); }
  }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closePlayer(); $('auth-modal').classList.add('hidden'); $('pass-modal').classList.add('hidden'); } });
$('sport-filter').addEventListener('change', loadMatches);
let searchTimer; $('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadMatches, 300); });

/* ---------- Démarrage ---------- */
refresh(); loadApiLive(); loadHeroLogos(); loadClub('barcelona');
setInterval(() => { if (!document.hidden) loadApiLive(); }, 60000);
