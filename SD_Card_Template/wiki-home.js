/* Khan-Nomad Wikipedia home ("topic shelves").
 * Turns the menu into a Wikipedia-only front page when the card has /home.json
 * containing {"home": "wiki"} (the card builder writes it with --wiki-only).
 * /menu?home=wiki forces it on, /menu?home=all shows the normal menu.
 *
 * Topic tiles open the overview article for each topic, "Surprise me" opens a random
 * article, and "Continue reading" lists the last articles opened on this phone
 * (archive.html records them in localStorage under kn_wiki_recent). */
(function () {
  'use strict';

  var TOPICS = [
    ['History', 'History', '<path d="M4 20h16M6 20V10M10 20V10M14 20V10M18 20V10M3 10l9-6 9 6z"/>'],
    ['Science', 'Science', '<circle cx="12" cy="12" r="1.6"/><ellipse cx="12" cy="12" rx="9" ry="3.6"/><ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(120 12 12)"/>'],
    ['Places', 'Geography', '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>'],
    ['People', 'Biography', '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"/>'],
    ['Arts', 'The arts', '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.8 1.8-1.7 0-1.3-1.1-1.6-1.1-2.7 0-1 .8-1.6 1.8-1.6H17a4 4 0 0 0 4-4C21 6.6 17 3 12 3z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/>'],
    ['Tech', 'Technology', '<rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>'],
    ['Nature', 'Nature', '<path d="M5 19c0-8 5-13 14-14-1 9-6 14-14 14z"/><path d="M5 19l7-7"/>'],
    ['Sports', 'Sport', '<circle cx="12" cy="12" r="9"/><path d="M12 7.5l4 2.9-1.5 4.7h-5L8 10.4z"/><path d="M12 3v4.5M21 10.4l-5 0M17.5 19.5l-3-4.4M6.5 19.5l3-4.4M3 10.4h5"/>'],
    ['Maths', 'Mathematics', '<path d="M5 7h6M8 4v6M14 7h6M5 17l5-5M10 17l-5-5M14 15h6M14 19h6"/>']
  ];
  var RECENT_KEY = 'kn_wiki_recent';
  var ZIM_JS = '/assets/nomad-zim.js?v=idx3';

  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
  function tr(s) { try { return (window.NomadI18n && NomadI18n.t) ? NomadI18n.t(s) : s; } catch (e) { return s; } }

  function wantWiki() {
    var m = new URLSearchParams(location.search).get('home');
    if (m) return Promise.resolve(m === 'wiki');
    return fetch('/home.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return !!(j && j.home === 'wiki'); })
      .catch(function () { return false; });
  }

  var indexPromise = null;
  function getIndex() {
    if (indexPromise) return indexPromise;
    indexPromise = new Promise(function (res, rej) {
      if (window.NomadZim) return res();
      var s = document.createElement('script');
      s.src = ZIM_JS; s.onload = res; s.onerror = function () { rej(new Error('reader missing')); };
      document.head.appendChild(s);
    }).then(function () {
      var idx = new NomadZim.NomadArchiveIndex('/Archive/.nomad-zim');
      return idx.load().then(function () { return idx; });
    });
    indexPromise.catch(function () { indexPromise = null; });
    return indexPromise;
  }

  function articleUrl(h) {
    return '/archive.html?a=' + h.archiveIdx + '&c=' + h.cluster + '&b=' + h.blob + '&t=' + encodeURIComponent(h.title || '');
  }

  function busy(msg) {
    var el = document.getElementById('knWikiStatus');
    if (el) { el.textContent = msg ? tr(msg) : ''; el.hidden = !msg; }
  }

  function openTopic(title) {
    busy('Finding the article…');
    getIndex().then(function (idx) {
      return idx.listRange(title, title, { limit: 3 }).then(function (rows) {
        if (rows && rows.length) return rows[0];
        return idx.search(title, 5).then(function (hits) { return hits && hits[0]; });
      });
    }).then(function (hit) {
      if (hit) { location.href = articleUrl(hit); return; }
      busy('No article found. Is the Wikipedia search index on the card?');
    }).catch(function () { busy('Wikipedia is not on the card yet.'); });
  }

  function okRandom(t) {
    return t && !/^list(s)? of /i.test(t) && !/disambiguation|^index of /i.test(t) && !/^\d+$/.test(t);
  }

  function surprise() {
    busy('Picking a random article…');
    var letters = 'abcdefghijklmnoprstw', any = 'abcdefghijklmnopqrstuvwxyz';
    function pick(s) { return s.charAt(Math.floor(Math.random() * s.length)); }
    getIndex().then(function (idx) {
      var tries = 0;
      function attempt() {
        tries++;
        var a = pick(letters), b = pick(any), c = pick(any);
        // start at a random point inside a two-letter band so long and short titles both win
        var lo = tries < 7 ? a + b + c : a, hi = tries < 7 ? a + b + 'zzzz' : a + 'zzzz';
        return idx.listRange(lo, hi, { limit: 25 }).then(function (rows) {
          rows = (rows || []).filter(function (r) { return okRandom(r.title); });
          if (rows.length) return rows[Math.floor(Math.random() * rows.length)];
          return tries < 10 ? attempt() : null;
        });
      }
      return attempt();
    }).then(function (hit) {
      if (hit) { location.href = articleUrl(hit); return; }
      busy('Could not pick an article. Try again.');
    }).catch(function () { busy('Wikipedia is not on the card yet.'); });
  }

  function recent() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').filter(function (x) { return x && x.t; }); }
    catch (e) { return []; }
  }

  function svg(paths) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' + paths + '</svg>';
  }

  function build() {
    document.body.classList.add('kn-wiki');
    var input = document.getElementById('searchInput');
    if (input) {
      // the menu sets its own "search everything" hint once it finds the archive; keep ours
      var ours = function (v) { return v === 'Search Wikipedia' || v === tr('Search Wikipedia'); };
      input.setAttribute('placeholder', tr('Search Wikipedia'));
      new MutationObserver(function () {
        if (!ours(input.getAttribute('placeholder'))) input.setAttribute('placeholder', tr('Search Wikipedia'));
      }).observe(input, { attributes: true, attributeFilter: ['placeholder'] });
    }

    var sec = document.createElement('section');
    sec.id = 'knWiki';
    sec.className = 'kn-wiki-home';
    var tiles = TOPICS.map(function (t) {
      return '<button type="button" class="tile kn-topic" data-title="' + esc(t[1]) + '"><span class="chip" aria-hidden="true">' +
        svg(t[2]) + '</span><div class="label">' + esc(t[0]) + '</div></button>';
    }).join('');
    var rec = recent().slice(0, 4);
    sec.innerHTML =
      '<p class="kn-wiki-count" id="knWikiCount" hidden></p>' +
      '<h2 class="kn-wiki-h">Explore by topic</h2>' +
      '<div class="kn-topics">' + tiles + '</div>' +
      '<button type="button" class="kn-surprise" id="knSurprise">' +
        svg('<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1.2" fill="currentColor"/><circle cx="15" cy="15" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/>') +
        '<span>Surprise me</span></button>' +
      '<p class="kn-wiki-status" id="knWikiStatus" role="status" hidden></p>' +
      (rec.length ? '<h2 class="kn-wiki-h">Continue reading</h2><div class="kn-recent">' +
        rec.map(function (r) {
          return '<a class="kn-recent-row" href="' + esc(articleUrl({ archiveIdx: r.a, cluster: r.c, blob: r.b, title: r.t })) + '" data-no-i18n>' + esc(r.t) + '</a>';
        }).join('') + '</div>' : '') +
      '<a class="kn-all-pages" href="/menu?home=all">All pages</a>';

    var anchor = document.getElementById('continueCard') || document.getElementById('resultsPanel');
    anchor.parentNode.insertBefore(sec, anchor.nextSibling);

    sec.querySelectorAll('.kn-topic').forEach(function (b) {
      b.addEventListener('click', function () { openTopic(b.getAttribute('data-title')); });
    });
    document.getElementById('knSurprise').addEventListener('click', surprise);
    if (window.NomadI18n && NomadI18n.apply) { try { NomadI18n.apply(sec); } catch (e) {} }

    fetch('/Archive/.nomad-zim/manifest.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (m) {
        var n = 0;
        ((m && m.archives) || []).forEach(function (a) { n += +a.articleCount || 0; });
        if (!n) return;
        var el = document.getElementById('knWikiCount');
        el.textContent = n.toLocaleString('en-US') + ' articles · offline';
        el.hidden = false;
        if (window.NomadI18n && NomadI18n.apply) { try { NomadI18n.apply(el); } catch (e) {} }
      }).catch(function () {});
  }

  wantWiki().then(function (on) {
    if (!on) return;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
    else build();
  });
})();
