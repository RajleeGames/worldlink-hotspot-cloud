/* Shared upload and payment feedback. No fabricated payment percentage. */
(() => {
  'use strict';
  const sw = document.documentElement.lang === 'sw';
  const words = {
    processing: sw ? 'Inachakata…' : 'Processing…',
    uploading: sw ? 'Inapakia' : 'Uploading',
    saving: sw ? 'Imepakiwa. Inahifadhi…' : 'Uploaded. Saving…',
    failed: sw ? 'Imeshindikana. Tafadhali jaribu tena.' : 'Could not complete. Please try again.',
    review: sw ? 'Tafadhali angalia taarifa na ujaribu tena.' : 'Please check the fields and try again.',
  };

  function feedback(form, message, percent) {
    let region = form.querySelector('[data-form-feedback]');
    if (!region) {
      region = document.createElement('div');
      region.className = 'whc-form-feedback';
      region.setAttribute('role', 'status');
      region.setAttribute('aria-live', 'polite');
      region.dataset.formFeedback = '';
      const bar = document.createElement('progress');
      bar.max = 100;
      bar.setAttribute('aria-label', sw ? 'Maendeleo ya upakiaji' : 'Upload progress');
      const label = document.createElement('span');
      label.className = 'whc-form-feedback-label';
      region.append(bar, label);
      form.append(region);
    }
    const bar = region.querySelector('progress');
    const label = region.querySelector('span');
    label.textContent = message;
    if (percent === null) {
      bar.removeAttribute('value');
    } else if (typeof percent === 'number') {
      bar.value = percent;
    } else {
      bar.hidden = true;
    }
    if (percent !== undefined) bar.hidden = percent === undefined;
    region.hidden = false;
  }

  function submitButtons(form, disabled) {
    form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(button => {
      button.disabled = disabled;
      button.classList.toggle('is-submitting', disabled);
      button.setAttribute('aria-busy', String(disabled));
    });
  }

  function upload(form, submitter) {
    const data = new FormData(form);
    if (submitter?.name) data.append(submitter.name, submitter.value);
    const xhr = new XMLHttpRequest();
    xhr.open((form.method || 'POST').toUpperCase(), form.action || location.href, true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.upload.onprogress = event => {
      if (event.lengthComputable && event.total) {
        const pct = Math.min(100, Math.floor(100 * event.loaded / event.total));
        feedback(form, `${words.uploading}… ${pct}%`, pct);
      } else {
        feedback(form, `${words.uploading}…`, null);
      }
    };
    xhr.upload.onload = () => feedback(form, words.saving, null);
    xhr.onerror = xhr.ontimeout = () => {
      form.dataset.whcSubmitting = '';
      submitButtons(form, false);
      feedback(form, words.failed, undefined);
    };
    xhr.onload = () => {
      // Django follows PRG redirect after successful upload; stay same origin.
      if (xhr.status >= 200 && xhr.status < 300 && xhr.responseURL) {
        const url = new URL(xhr.responseURL, location.href);
        if (url.origin === location.origin && (url.pathname !== location.pathname || url.search !== location.search)) {
          location.assign(url.href);
          return;
        }
        // A same-page 200 may contain server validation errors; show them.
        const parsed = new DOMParser().parseFromString(xhr.responseText, 'text/html');
        const errors = [...parsed.querySelectorAll('.field-error, .errorlist')]
          .map(node => node.textContent.trim()).filter(Boolean);
        if (errors.length) {
          feedback(form, `${words.review} ${errors.slice(0, 3).join(' ')}`, undefined);
        } else {
          // A successful POST that renders the same URL can refresh normally.
          location.reload();
          return;
        }
      } else {
        feedback(form, words.failed, undefined);
      }
      form.dataset.whcSubmitting = '';
      submitButtons(form, false);
    };
    xhr.timeout = 90000;
    xhr.send(data);
  }

  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== 'post'
        || form.hasAttribute('onsubmit') || !form.checkValidity() || event.defaultPrevented) return;
    if (form.dataset.whcSubmitting === 'true') {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    const isUpload = form.hasAttribute('data-upload-progress')
      && [...form.querySelectorAll('input[type="file"]')].some(input => input.files?.length);
    form.dataset.whcSubmitting = 'true';
    const label = form.dataset.processingLabel || words.processing;
    feedback(form, isUpload ? `${words.uploading}… 0%` : label, isUpload ? 0 : null);
    if (isUpload && typeof XMLHttpRequest !== 'undefined' && typeof FormData !== 'undefined') {
      event.preventDefault();
      event.stopImmediatePropagation();
      const submitter = event.submitter;
      submitButtons(form, true);
      try { upload(form, submitter); }
      catch (_) {
        form.dataset.whcSubmitting = '';
        submitButtons(form, false);
        feedback(form, words.failed, undefined);
      }
    } else {
      // Delay disabling until after the native form serialization. This also
      // preserves submit-button name/value and CSRF for normal Django POSTs.
      setTimeout(() => submitButtons(form, true), 0);
    }
  }, true);

  window.addEventListener('pageshow', () => {
    document.querySelectorAll('form[data-whc-submitting]').forEach(form => {
      form.dataset.whcSubmitting = '';
      submitButtons(form, false);
      form.querySelector('[data-form-feedback]')?.setAttribute('hidden', '');
    });
  });
})();
