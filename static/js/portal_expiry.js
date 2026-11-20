/* An open receipt updates as access expires. This cannot force iOS to reopen
   its captive-network assistant; the guest can return to packages instead. */
(function () {
  'use strict';
  var panel = document.querySelector('[data-guest-expiry]');
  if (!panel) return;
  var expiry = Date.parse(panel.getAttribute('data-expiry-at') || '');
  if (!Number.isFinite(expiry)) return;
  var clock = panel.querySelector('[data-expiry-clock]');
  var remaining = panel.querySelector('[data-expiry-remaining]');
  var heading = panel.querySelector('[data-expiry-heading]');
  var icon = panel.querySelector('[data-expiry-icon]');
  var description = panel.querySelector('[data-expiry-description]');
  var renew = document.querySelector('[data-expiry-renew]');
  var expired = false;

  function tick() {
    var seconds = Math.max(0, Math.ceil((expiry - Date.now()) / 1000));
    if (seconds <= 0) {
      if (!expired) {
        expired = true;
        if (heading) heading.textContent = panel.getAttribute('data-expired-title') || 'Internet expired';
        if (description) description.textContent = panel.getAttribute('data-expired-note') || '';
        if (icon) { icon.textContent = '!'; icon.classList.remove('guest-status-success'); icon.classList.add('guest-status-cancelled'); }
        panel.setAttribute('role', 'status');
        panel.setAttribute('aria-live', 'polite');
        if (remaining) remaining.hidden = true;
        if (renew) renew.hidden = false;
      }
      return;
    }
    if (remaining) remaining.hidden = false;
    if (clock) {
      var hours = Math.floor(seconds / 3600);
      var minutes = Math.floor((seconds % 3600) / 60);
      var secs = seconds % 60;
      clock.textContent = (hours ? hours + ':' + String(minutes).padStart(2, '0') : String(minutes)) + ':' + String(secs).padStart(2, '0');
    }
    setTimeout(tick, 1000);
  }
  tick();
}());
