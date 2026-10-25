/* Khan-Nomad interface language (English / Türkçe).
 *
 * Pages stay written in English. When the language is set to Turkish this
 * script swaps known interface strings (text, placeholder, title, aria-label)
 * for their Turkish versions, including text added later by page scripts.
 * Anything not in the dictionary (movie titles, file names...) is left alone.
 *
 * The choice lives in localStorage under "nomad_lang" ("en" or "tr"), so it is
 * per phone/browser. Switch with NomadI18n.setLang('tr') or the menu button.
 */
(function () {
  const KEY = 'nomad_lang';

  const TR = {
    // menu
    'Your personal Media Library': 'Kişisel medya kütüphaneniz',
    'Movies': 'Filmler', 'Shows': 'Diziler', 'Music': 'Müzik', 'Books': 'Kitaplar',
    'Gallery': 'Galeri', 'Files': 'Dosyalar', 'Games': 'Oyunlar', 'Maps': 'Haritalar',
    'Archive': 'Arşiv', 'Translate': 'Çeviri', 'Cookbook': 'Tarifler', 'Workshop': 'Atölye',
    'Resume': 'Devam et', 'Chat': 'Sohbet', 'Admin': 'Yönetim', 'Admin panel': 'Yönetim paneli',
    'Toggle theme': 'Temayı değiştir', 'Application title': 'Uygulama adı',
    'Search everything on this card...': 'Bu karttaki her şeyde ara...',
    'Search everything on this card, wiki articles...': 'Bu karttaki her şeyde, wiki makalelerinde ara...',
    'Search': 'Ara', 'Search results': 'Arama sonuçları', 'Categories': 'Kategoriler',
    'Language': 'Dil',
    'Welcome': 'Hoş geldin', 'Good morning': 'Günaydın', 'Good afternoon': 'İyi günler',
    'Good evening': 'İyi akşamlar', 'Good night': 'İyi geceler',
    '1 person around the yurt': 'Yurtta 1 kişi',
    'Continue watching': 'İzlemeye devam et', 'Continue listening': 'Dinlemeye devam et',
    'Continue reading': 'Okumaya devam et',

    // shared
    '← Back to Menu': '← Menüye dön', '← Back': '← Geri',
    'Close': 'Kapat', '✕ Close': '✕ Kapat', 'Cancel': 'İptal', 'Download': 'İndir',
    'Upload': 'Yükle', 'Upload files': 'Dosya yükle', 'Next': 'Sonraki', 'Prev': 'Önceki',
    'Previous': 'Önceki', '← Previous': '← Önceki', '← Prev': '← Önceki', 'Next →': 'Sonraki →',
    'Play': 'Oynat', 'Pause': 'Duraklat', 'Loading…': 'Yükleniyor…', 'Loading...': 'Yükleniyor...',
    'toolbar': 'araç çubuğu', 'Video player': 'Video oynatıcı',
    'Compact view': 'Kompakt görünüm', 'Comfort view': 'Rahat görünüm', 'Gallery view': 'Galeri görünümü',
    'Small view': 'Küçük görünüm', 'Medium view': 'Orta görünüm', 'Large view': 'Büyük görünüm',
    'Sort:': 'Sırala:', 'Per page:': 'Sayfa başına:', 'Items per page': 'Sayfa başına öğe',
    'Name A→Z': 'Ad A→Z', 'Name Z→A': 'Ad Z→A', 'Type ↑': 'Tür ↑', 'Type ↓': 'Tür ↓',
    'Size ↑': 'Boyut ↑', 'Size ↓': 'Boyut ↓', 'All': 'Tümü', 'Built-in': 'Dahili',
    'Khan-Nomad · based on': 'Khan-Nomad · kaynak:',

    // movies and shows
    'What would you like to do?': 'Ne yapmak istersiniz?',
    'What do you want to do?': 'Ne yapmak istiyorsunuz?',
    'Play from Start': 'Baştan oynat', 'Play (from start)': 'Oynat (baştan)',
    'Play / Download': 'Oynat / İndir', 'Select an episode': 'Bir bölüm seçin',
    'Search movies…': 'Filmlerde ara…', 'Search movies': 'Filmlerde ara',
    'Sort movies': 'Filmleri sırala', 'Movie list': 'Film listesi', 'Close video': 'Videoyu kapat',
    'Search shows…': 'Dizilerde ara…', 'Search shows': 'Dizilerde ara',
    'Sort shows': 'Dizileri sırala', 'Show list': 'Dizi listesi',

    // music
    'Songs': 'Şarkılar', 'Playlists': 'Çalma listeleri', 'Queue': 'Sıradakiler',
    'Not playing': 'Çalmıyor', 'Shuffle': 'Karıştır', 'Loop': 'Tekrar',
    'Loop: off': 'Tekrar: kapalı', 'Loop: all': 'Tekrar: tümü', 'Loop: one': 'Tekrar: tek',
    'Sort A → Z': 'A → Z sırala', 'Sort Z → A': 'Z → A sırala',
    'All Songs': 'Tüm şarkılar', 'Search songs…': 'Şarkılarda ara…', 'Add to queue': 'Sıraya ekle',
    'Search playlists…': 'Çalma listelerinde ara…', 'Clear Queue': 'Sırayı temizle',
    'Queue is empty. Add songs from other tabs!': 'Sıra boş. Diğer sekmelerden şarkı ekleyin!',

    // books and readers
    'Contents': 'İçindekiler', 'Table of Contents': 'İçindekiler', '📑 TOC': '📑 İçindekiler',
    'Book Title': 'Kitap adı', 'Pages': 'Sayfalar', 'Audiobook': 'Sesli kitap', 'Speed': 'Hız',
    'Search books…': 'Kitaplarda ara…', 'Search books': 'Kitaplarda ara', 'Sort books': 'Kitapları sırala',
    'Primary action': 'Ana işlem', 'Download file': 'Dosyayı indir',
    'Toggle view mode': 'Görünüm modunu değiştir', 'Decrease font size': 'Yazıyı küçült',
    'Increase font size': 'Yazıyı büyüt', 'Close reader': 'Okuyucuyu kapat', 'Close TOC': 'İçindekileri kapat',
    'Back 15 seconds': '15 saniye geri', 'Forward 15 seconds': '15 saniye ileri',
    'Play/Pause': 'Oynat/Duraklat', 'Play or pause': 'Oynat veya duraklat',
    'Single Page': 'Tek sayfa', 'Two Page': 'Çift sayfa',
    'Left to Right': 'Soldan sağa', 'Right to Left': 'Sağdan sola',
    '❌ No comic path specified.': '❌ Çizgi roman yolu belirtilmedi.',

    // games
    'All Consoles': 'Tüm konsollar', 'Exit Game': 'Oyundan çık',
    'Search games…': 'Oyunlarda ara…', 'Search games': 'Oyunlarda ara',
    'Filter by console': 'Konsola göre filtrele', 'Sort games': 'Oyunları sırala',

    // gallery and files
    'Gallery toolbar': 'Galeri araç çubuğu', 'Sort gallery': 'Galeriyi sırala',
    'Search files…': 'Dosyalarda ara…', 'Search files': 'Dosyalarda ara',
    'Filter by type': 'Türe göre filtrele', 'Sort files': 'Dosyaları sırala',

    // maps
    'No offline maps installed yet.': 'Henüz çevrimdışı harita yüklü değil.',
    'Location on this map': 'Bu haritadaki konum', 'Map region': 'Harita bölgesi',
    'Zoom in': 'Yakınlaştır', 'Zoom out': 'Uzaklaştır', 'Show my location': 'Konumumu göster',

    // translate
    'Copy': 'Kopyala', 'Getting things ready': 'Hazırlanıyor',
    'Checking which languages are on this Nomad.': "Bu Nomad'da hangi dillerin olduğu kontrol ediliyor.",
    'Clear both': 'İkisini de temizle', 'Clear both boxes': 'İki kutuyu da temizle',
    'Translate from': 'Kaynak dil', 'Translate into': 'Hedef dil', 'Swap languages': 'Dilleri değiştir',
    'Type here': 'Buraya yazın', 'Copy this text': 'Bu metni kopyala',
  };

  // text with numbers in it
  const TR_PATTERNS = [
    [/^(\d+) tracks?$/, '$1 parça'],
    [/^(\d+) playlists?$/, '$1 çalma listesi'],
    [/^(\d+) in queue$/, 'Sırada $1'],
    [/^Page (\d+) of (\d+)$/, 'Sayfa $1 / $2'],
    [/^(\d+) items?$/, '$1 öğe'],
    [/^(\d+) results?$/, '$1 sonuç'],
    [/^(\d+) people around the yurt$/, 'Yurtta $1 kişi'],
    [/^Left off at (.+)$/, 'Kaldığın yer: $1'],
    [/^Continue watching: (.+)$/, 'İzlemeye devam et: $1'],
    [/^Continue listening: (.+)$/, 'Dinlemeye devam et: $1'],
    [/^Continue reading: (.+)$/, 'Okumaya devam et: $1'],
  ];

  const ATTRS = ['placeholder', 'title', 'aria-label'];
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE']);

  function getLang() {
    try { return localStorage.getItem(KEY) === 'tr' ? 'tr' : 'en'; } catch (e) { return 'en'; }
  }

  function tr(s) {
    if (TR[s]) return TR[s];
    for (const [rx, rep] of TR_PATTERNS) if (rx.test(s)) return s.replace(rx, rep);
    return null;
  }

  function fixText(node) {
    const raw = node.nodeValue;
    const t = raw.trim();
    if (!t || t.length > 120) return;
    const out = tr(t);
    if (out && out !== t) node.nodeValue = raw.replace(t, out);
  }

  function fixEl(el) {
    for (const a of ATTRS) {
      const v = el.getAttribute && el.getAttribute(a);
      if (v) { const out = tr(v.trim()); if (out) el.setAttribute(a, out); }
    }
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { if (!SKIP.has(root.parentNode && root.parentNode.nodeName)) fixText(root); return; }
    if (root.nodeType !== 1 || SKIP.has(root.nodeName) || root.closest('[data-no-i18n]')) return;
    fixEl(root);
    root.querySelectorAll('[placeholder],[title],[aria-label]').forEach(fixEl);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: n => (SKIP.has(n.parentNode.nodeName) || n.parentNode.closest('[data-no-i18n]'))
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    let n; while ((n = w.nextNode())) fixText(n);
  }

  function start() {
    document.documentElement.lang = 'tr';
    walk(document.body);
    new MutationObserver(muts => {
      for (const m of muts) {
        if (m.type === 'characterData') fixText(m.target);
        else if (m.type === 'attributes') fixEl(m.target);
        else m.addedNodes.forEach(walk);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true,
                                attributes: true, attributeFilter: ATTRS });
  }

  window.NomadI18n = {
    lang: getLang,
    setLang(l) {
      try { localStorage.setItem(KEY, l === 'tr' ? 'tr' : 'en'); } catch (e) {}
      location.reload();  // simplest way back to the English originals
    },
    t: s => (getLang() === 'tr' && tr(s)) || s,
  };

  // the menu's EN/TR button shows the current language
  function labelButton() {
    const b = document.getElementById('langBtn');
    if (b) b.textContent = getLang().toUpperCase();
  }

  function boot() {
    labelButton();
    if (getLang() === 'tr') start();
  }

  if (document.body) boot();
  else document.addEventListener('DOMContentLoaded', boot);
})();
