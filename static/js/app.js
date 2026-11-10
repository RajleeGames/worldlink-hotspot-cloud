/* WorldLink Hotspot Cloud v0.4 — one shared interaction script */
(() => {
  'use strict';
  const root = document.documentElement;
  const safeStore = (store, key, fallback) => { try { return store.getItem(key) ?? fallback; } catch (_) { return fallback; } };
  const safeSet = (store, key, value) => { try { store.setItem(key, value); } catch (_) {} };
  const themeIcon = (name) => `<svg class="icon" aria-hidden="true"><use href="#ico-${name}"></use></svg>`;

  function renderTheme() {
    const dark = root.dataset.theme === 'dark';
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.innerHTML = themeIcon(dark ? 'sun' : 'moon');
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('title', dark ? 'Light mode / Mandhari ya mwanga' : 'Dark mode / Mandhari ya giza');
    });
  }
  document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    safeSet(localStorage, 'whc-theme', root.dataset.theme);
    renderTheme();
  }));
  renderTheme();

  const sidebar = document.getElementById('sidebar');
  const scrollFrame = document.getElementById('sidebarScroll');
  const backdrop = document.querySelector('[data-close-sidebar]');
  const mobile = window.matchMedia('(max-width:780px)');
  const scrollKey = 'whc-sidebar-scroll';
  const menusKey = 'whc-sidebar-groups';
  function saveScroll() { if (scrollFrame) safeSet(sessionStorage, scrollKey, String(Math.round(scrollFrame.scrollTop))); }
  function closeSidebar() {
    sidebar?.classList.remove('is-open');
    backdrop?.classList.remove('is-open');
    document.body.classList.remove('drawer-open');
    document.querySelector('[data-sidebar-toggle]')?.setAttribute('aria-expanded', 'false');
  }
  const hamburger = document.querySelector('[data-sidebar-toggle]');
  function syncHamburger() {
    hamburger?.setAttribute('aria-expanded', String(mobile.matches ? sidebar?.classList.contains('is-open') : root.dataset.sidebar !== 'compact'));
  }
  hamburger?.addEventListener('click', () => {
    if (mobile.matches) {
      const open = !sidebar?.classList.contains('is-open');
      sidebar?.classList.toggle('is-open', open);
      backdrop?.classList.toggle('is-open', open);
      document.body.classList.toggle('drawer-open', open);
    } else {
      root.dataset.sidebar = root.dataset.sidebar === 'compact' ? 'full' : 'compact';
      safeSet(localStorage, 'whc-sidebar', root.dataset.sidebar);
    }
    syncHamburger();
  });
  backdrop?.addEventListener('click', closeSidebar);
  mobile.addEventListener('change', () => { closeSidebar(); syncHamburger(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeSidebar(); });
  syncHamburger();

  const groups = [...document.querySelectorAll('[data-nav-group]')];
  let savedGroups = {};
  try { savedGroups = JSON.parse(safeStore(sessionStorage, menusKey, '{}')) || {}; } catch (_) {}
  function saveGroups() {
    const state = {};
    groups.forEach(group => { state[group.dataset.navGroup] = group.dataset.expanded === 'true'; });
    safeSet(sessionStorage, menusKey, JSON.stringify(state));
  }
  groups.forEach(group => {
    const name = group.dataset.navGroup;
    // Keep the current page visible; restore all other open/closed sections.
    const expanded = group.classList.contains('is-current') || (savedGroups[name] ?? (group.dataset.expanded === 'true'));
    group.dataset.expanded = String(expanded);
    const toggle = group.querySelector('[data-group-toggle]');
    toggle?.setAttribute('aria-expanded', String(expanded));
    toggle?.addEventListener('click', () => {
      const next = group.dataset.expanded !== 'true';
      group.dataset.expanded = String(next);
      toggle.setAttribute('aria-expanded', String(next));
      saveGroups();
      saveScroll();
    });
  });
  saveGroups();
  if (scrollFrame) {
    const oldPosition = Number(safeStore(sessionStorage, scrollKey, '0'));
    if (Number.isFinite(oldPosition) && oldPosition >= 0) scrollFrame.scrollTop = oldPosition;
    let queued = false;
    scrollFrame.addEventListener('scroll', () => {
      if (!queued) {
        queued = true;
        requestAnimationFrame(() => { saveScroll(); queued = false; });
      }
    }, { passive: true });
    document.querySelectorAll('.sidebar a').forEach(link => link.addEventListener('click', saveScroll));
    window.addEventListener('pagehide', saveScroll);
  }

  // Native keyboard-friendly selects, with a custom animated chevron and clean focus.
  document.querySelectorAll('select.input, select.language-select').forEach(select => {
    if (select.parentElement?.classList.contains('select-wrap')) return;
    const wrap = document.createElement('span');
    wrap.className = 'select-wrap';
    select.parentNode.insertBefore(wrap, select);
    wrap.append(select);
    select.addEventListener('focus', () => wrap.classList.add('is-focus'));
    select.addEventListener('blur', () => wrap.classList.remove('is-focus'));
    select.addEventListener('change', () => wrap.classList.remove('is-focus'));
  });


  // Compact custom menus for ordinary short selects, including EN/SW and company.
  // Large selects remain native for performance; originals stay in their Django forms.
  const enhancedSelects = [];
  const closeSelect = (wrap, restoreFocus = false) => {
    if (!wrap?.classList.contains('is-open')) return;
    wrap.classList.remove('is-open', 'opens-up');
    const trigger = wrap.querySelector('.select-trigger');
    trigger?.setAttribute('aria-expanded', 'false');
    if (restoreFocus) trigger?.focus({ preventScroll: true });
  };
  document.querySelectorAll('select.language-select, select#company_id, select.input').forEach((select, selectIndex) => {
    const wrap = select.closest('.select-wrap');
    if (!wrap || select.multiple || select.options.length < 1 || select.options.length > 80) return;
    wrap.classList.add('is-enhanced');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', `whc-select-menu-${selectIndex}`);
    const sourceLabel = select.getAttribute('aria-label') ||
      document.querySelector(`label[for="${select.id}"]`)?.textContent?.trim() || 'Choose an option';
    trigger.setAttribute('aria-label', sourceLabel);
    const valueText = document.createElement('span');
    valueText.className = 'select-trigger-label';
    const caret = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    caret.classList.add('icon', 'select-trigger-chevron');
    caret.setAttribute('viewBox', '0 0 24 24');
    caret.setAttribute('aria-hidden', 'true');
    const chevronPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    chevronPath.setAttribute('d', 'm6 9 6 6 6-6');
    chevronPath.setAttribute('fill', 'none');
    chevronPath.setAttribute('stroke', 'currentColor');
    chevronPath.setAttribute('stroke-width', '1.8');
    chevronPath.setAttribute('stroke-linecap', 'round');
    chevronPath.setAttribute('stroke-linejoin', 'round');
    caret.append(chevronPath);
    trigger.append(valueText, caret);

    const menu = document.createElement('div');
    menu.className = 'select-menu';
    menu.id = `whc-select-menu-${selectIndex}`;
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-label', sourceLabel);
    const optionButtons = [...select.options].map((option, index) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'select-option';
      item.textContent = option.textContent.trim();
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', String(option.selected));
      item.dataset.value = option.value;
      item.disabled = option.disabled;
      item.id = `${menu.id}-option-${index}`;
      item.tabIndex = -1;
      item.addEventListener('click', () => {
        if (item.disabled) return;
        select.value = item.dataset.value;
        sync();
        closeSelect(wrap, true);
        // The language form uses form.submit(), which does not emit a submit event.
        if (select.classList.contains('language-select')) {
          document.getElementById('whcPreloader')?.classList.remove('is-hidden');
        }
        select.dispatchEvent(new Event('change', { bubbles: true }));
      });
      return item;
    });
    menu.append(...optionButtons);
    wrap.append(trigger, menu);
    enhancedSelects.push(wrap);

    function sync() {
      const current = select.selectedOptions[0];
      valueText.textContent = current?.textContent?.trim() || '—';
      optionButtons.forEach(item => item.setAttribute('aria-selected', String(item.dataset.value === select.value)));
    }
    function open() {
      enhancedSelects.forEach(other => { if (other !== wrap) closeSelect(other); });
      wrap.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');
      const rect = trigger.getBoundingClientRect();
      const estimatedHeight = Math.min(optionButtons.length * 42 + 8, 260);
      wrap.classList.toggle('opens-up', window.innerHeight - rect.bottom < estimatedHeight + 10 && rect.top > estimatedHeight);
      const focused = optionButtons.find(item => item.dataset.value === select.value && !item.disabled) || optionButtons.find(item => !item.disabled);
      focused?.focus({ preventScroll: true });
    }
    trigger.addEventListener('click', () => wrap.classList.contains('is-open') ? closeSelect(wrap) : open());
    trigger.addEventListener('keydown', e => {
      if (['ArrowDown', 'ArrowUp', 'Home', 'End', ' '].includes(e.key)) { e.preventDefault(); open(); }
    });
    menu.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.preventDefault(); closeSelect(wrap, true); return; }
      if (e.key === 'Tab') { closeSelect(wrap); return; }
      const enabled = optionButtons.filter(item => !item.disabled);
      const at = enabled.indexOf(document.activeElement);
      let next = -1;
      if (e.key === 'ArrowDown') next = (at + 1) % enabled.length;
      if (e.key === 'ArrowUp') next = (at - 1 + enabled.length) % enabled.length;
      if (e.key === 'Home') next = 0;
      if (e.key === 'End') next = enabled.length - 1;
      if (next >= 0) { e.preventDefault(); enabled[next]?.focus({ preventScroll: true }); }
    });
    select.addEventListener('change', sync);
    sync();
  });
  document.addEventListener('pointerdown', e => {
    enhancedSelects.forEach(wrap => { if (!wrap.contains(e.target)) closeSelect(wrap); });
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') enhancedSelects.forEach(wrap => closeSelect(wrap, true));
  });

  // Brand-logo preloader. Briefly show on initial paint and during real page changes.
  const loader = document.getElementById('whcPreloader');
  if (loader) {
    const hideLoader = () => loader.classList.add('is-hidden');
    const showLoader = () => loader.classList.remove('is-hidden');
    if (document.readyState === 'complete') setTimeout(hideLoader, 100);
    else window.addEventListener('load', () => setTimeout(hideLoader, 100), { once: true });
    // Do not block the page indefinitely if a remote font or image stalls.
    setTimeout(hideLoader, 1700);
    window.addEventListener('pageshow', hideLoader);
    document.querySelectorAll('a[href]').forEach(link => link.addEventListener('click', e => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) return;
      if (link.target && link.target !== '_self') return;
      if (link.hasAttribute('download')) return;
      const target = new URL(link.href, window.location.href);
      if (target.origin !== window.location.origin || target.pathname === window.location.pathname && target.search === window.location.search) return;
      showLoader();
    }));
    document.querySelectorAll('form').forEach(form => form.addEventListener('submit', () => {
      if (!form.checkValidity()) return;
      showLoader();
    }));
  }

  document.querySelectorAll('[data-password-toggle]').forEach(button => button.addEventListener('click', () => {
    const field = button.parentElement.querySelector('input');
    if (!field) return;
    field.type = field.type === 'password' ? 'text' : 'password';
    button.textContent = field.type === 'text' ? (root.lang === 'sw' ? 'Ficha' : 'Hide') : (root.lang === 'sw' ? 'Onyesha' : 'Show');
  }));
  document.querySelectorAll('[data-dismiss]').forEach(button => button.addEventListener('click', () => button.closest('.flash')?.remove()));
  document.querySelectorAll('[data-confirm]').forEach(button => button.addEventListener('click', event => {
    if (!window.confirm(button.dataset.confirm)) event.preventDefault();
  }));
  document.querySelectorAll('[data-logo-input]').forEach(input => input.addEventListener('change', () => {
    const file = input.files?.[0];
    const preview = document.querySelector('[data-logo-preview]');
    if (!file || !preview || !file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = () => {
      const image = document.createElement('img');
      image.src = reader.result; image.alt = 'Selected logo preview';
      preview.replaceChildren(image);
    };
    reader.readAsDataURL(file);
  }));
  document.querySelectorAll('[data-loading-form]').forEach(form => form.addEventListener('submit', () => {
    const button = form.querySelector('button[type="submit"]');
    if (button) button.classList.add('is-submitting');
  }));
})();

/* v0.5 · Countdown display only, not an authentication signal. */
(() => {
  const nodes = [...document.querySelectorAll('[data-expiry]')];
  if (!nodes.length) return;
  const clock = () => {
    nodes.forEach(el => {
      const timestamp = Date.parse(el.dataset.expiry);
      if (Number.isNaN(timestamp)) { el.textContent = '—'; return; }
      const sec = Math.max(0, Math.floor((timestamp - Date.now()) / 1000));
      const hours = Math.floor(sec / 3600);
      const minutes = Math.floor((sec % 3600) / 60);
      const seconds = sec % 60;
      el.textContent = sec === 0 ? (document.documentElement.lang === 'sw' ? 'Muda umeisha' : 'Expired') :
        `${hours > 0 ? `${hours}h ` : ''}${minutes}m ${String(seconds).padStart(2, '0')}s`;
      el.classList.toggle('is-expired', sec === 0);
    });
  };
  clock();
  const timer = window.setInterval(clock, 1000);
  window.addEventListener('pagehide', () => clearInterval(timer), {once:true});
})();

// v0.6 secure invitation setup: a copy button bound only to real user actions.
document.querySelectorAll('[data-copy-target]').forEach(button => {
  button.addEventListener('click', async () => {
    const input = document.getElementById(button.dataset.copyTarget);
    if (!input) return;
    try {
      await navigator.clipboard.writeText(input.value);
      button.textContent = 'Copied';
    } catch (_) {
      input.focus(); input.select();
      button.textContent = 'Select and copy';
    }
  });
});
