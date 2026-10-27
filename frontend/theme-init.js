(() => {
  // Runs before first paint: resolves appearance + language without a flash.
  const validTheme = value => ['casual', 'contrast'].includes(value);
  const validMode = value => ['light', 'dark'].includes(value);
  const validLang = value => ['de', 'en'].includes(value);
  const params = new URLSearchParams(location.search);
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem('susie-appearance') || '{}') || {}; } catch {}
  const theme = validTheme(params.get('theme')) ? params.get('theme') : validTheme(saved.theme) ? saved.theme : 'casual';
const MODE_REPLACED = 0; // (folded above)
  // German-first: a demo for a German authority opens in German unless the
  // URL explicitly asks for English or the user chose English here before.
  const lang = validLang(params.get('lang')) ? params.get('lang') : validLang(saved.lang) ? saved.lang : 'de';
  // Theme unity: follow the SÜSIE app's persisted theme ('susie-ui-theme'),
  // light default — switching apps must never switch the theme (owner, wave 4).
  let susieTheme = null;
  try { susieTheme = localStorage.getItem('susie-ui-theme'); } catch {}
  const mode = susieTheme === 'dark' ? 'dark'
    : susieTheme === 'light' ? 'light'
    : validMode(params.get('mode')) ? params.get('mode')
    : validMode(saved.mode) ? saved.mode
    : 'light';
  document.documentElement.dataset.theme = theme;
  // Embedded in the SÜSIE app (?embed=1): hide the Prüfakte chrome — the
  // SÜSIE sidebar/topbar around the iframe IS the navigation.
  try { if (new URLSearchParams(location.search).has('embed')) document.documentElement.classList.add('embed'); } catch {}
  document.documentElement.dataset.mode = mode;
  document.documentElement.dataset.lang = lang;
  document.documentElement.lang = lang;
})();
