/**
 * main.js — EduShield NG Global JavaScript
 * ==========================================
 * Runs on every page. Handles:
 *   1. Dark/light mode toggle + localStorage persistence
 *   2. Mobile navigation hamburger menu
 *   3. User dropdown menu
 *   4. Flash message auto-dismiss
 *   5. Global text-to-speech (TTS) toggle
 *   6. CSRF token injection for AJAX requests
 *   7. General accessibility helpers
 *
 * No external dependencies — vanilla JS only.
 * Runs after DOM is fully loaded (script is at bottom of base.html).
 */

'use strict';

// ══════════════════════════════════════════════
// 1. THEME TOGGLE (Dark / Light Mode)
// ══════════════════════════════════════════════

const ThemeManager = (() => {
  // The <html> element where we set data-theme attribute
  const html = document.documentElement;
  const toggleBtn = document.getElementById('themeToggle');
  const themeIcon = document.getElementById('themeIcon');

  // Key used to persist user's preference in localStorage
  const STORAGE_KEY = 'edushield-theme';

  function getPreferred() {
    // Priority: 1) user's saved choice, 2) system preference
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
    // Check OS-level dark mode preference
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark' : 'light';
  }

  function apply(theme) {
    // Set data-theme on <html> — CSS variables read this
    html.setAttribute('data-theme', theme);

    // Update toggle button icon and aria-pressed state
    if (themeIcon) {
      themeIcon.className = theme === 'dark'
        ? 'fas fa-sun' : 'fas fa-moon';
    }
    if (toggleBtn) {
      toggleBtn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
      toggleBtn.setAttribute('aria-label',
        theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    }
  }

  function toggle() {
    const current = html.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    apply(next);
    // Persist choice so it survives page reloads
    localStorage.setItem(STORAGE_KEY, next);
  }

  function init() {
    apply(getPreferred());
    if (toggleBtn) {
      toggleBtn.addEventListener('click', toggle);
    }
  }

  return { init, toggle, apply };
})();


// ══════════════════════════════════════════════
// 2. MOBILE NAVIGATION HAMBURGER
// ══════════════════════════════════════════════

const NavManager = (() => {
  const toggleBtn = document.getElementById('navToggle');
  const navMenu = document.getElementById('navMenu');

  function open() {
    navMenu.classList.add('open');
    toggleBtn.setAttribute('aria-expanded', 'true');
  }

  function close() {
    navMenu.classList.remove('open');
    toggleBtn.setAttribute('aria-expanded', 'false');
  }

  function init() {
    if (!toggleBtn || !navMenu) return;

    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      navMenu.classList.contains('open') ? close() : open();
    });

    // Close nav when user clicks anywhere outside it
    document.addEventListener('click', (e) => {
      if (!navMenu.contains(e.target) && !toggleBtn.contains(e.target)) {
        close();
      }
    });

    // Close nav on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && navMenu.classList.contains('open')) {
        close();
        toggleBtn.focus(); // Return focus to toggle button
      }
    });
  }

  return { init };
})();


// ══════════════════════════════════════════════
// 3. USER DROPDOWN MENU
// ══════════════════════════════════════════════

const UserMenuManager = (() => {
  const trigger = document.getElementById('userMenuBtn');
  const dropdown = document.getElementById('userDropdown');

  function open() {
    dropdown.classList.add('open');
    trigger.setAttribute('aria-expanded', 'true');
    // Move focus to first item for keyboard navigation
    const firstItem = dropdown.querySelector('[role="menuitem"]');
    if (firstItem) firstItem.focus();
  }

  function close() {
    dropdown.classList.remove('open');
    trigger.setAttribute('aria-expanded', 'false');
  }

  function init() {
    if (!trigger || !dropdown) return;

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.classList.contains('open') ? close() : open();
    });

    // Close when clicking outside
    document.addEventListener('click', () => close());

    // Keyboard navigation inside dropdown
    dropdown.addEventListener('keydown', (e) => {
      const items = [...dropdown.querySelectorAll('[role="menuitem"]')];
      const current = document.activeElement;
      const idx = items.indexOf(current);

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        // Move to next item (wrap to first)
        items[(idx + 1) % items.length]?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        // Move to previous item (wrap to last)
        items[(idx - 1 + items.length) % items.length]?.focus();
      } else if (e.key === 'Escape') {
        close();
        trigger.focus();
      } else if (e.key === 'Tab') {
        close();
      }
    });
  }

  return { init };
})();


// ══════════════════════════════════════════════
// 4. FLASH MESSAGE AUTO-DISMISS
// ══════════════════════════════════════════════

const FlashManager = (() => {
  function init() {
    const messages = document.querySelectorAll('.flash-message');
    messages.forEach((msg, i) => {
      // Stagger auto-dismiss: first message disappears after 5s,
      // each subsequent one waits 1s more
      const delay = 5000 + (i * 1000);
      setTimeout(() => {
        msg.style.animation = 'flashSlide 0.3s ease reverse';
        setTimeout(() => msg.remove(), 300);
      }, delay);
    });
  }

  return { init };
})();


// ══════════════════════════════════════════════
// 5. TEXT-TO-SPEECH (TTS) — Global Toggle
// ══════════════════════════════════════════════

const TTSManager = (() => {
  const ttsBtn = document.getElementById('ttsToggle');
  const STORAGE_KEY = 'edushield-tts';

  let enabled = localStorage.getItem(STORAGE_KEY) === 'true';
  let synth = window.speechSynthesis;
  let currentLang = document.documentElement.lang || 'en';

  // Language code → BCP-47 locale mapping
  const langMap = {
    'en': 'en-NG',
    'ha': 'ha-NG',
    'yo': 'yo-NG',
    'ig': 'ig-NG',
  };

  function speak(text, interrupt = false) {
    if (!enabled || !synth) return;
    if (interrupt) synth.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    // Use Nigerian locale variants if available
    utterance.lang = langMap[currentLang] || 'en-NG';
    utterance.rate = 0.9;     // Slightly slower than default for clarity
    utterance.pitch = 1.0;
    utterance.volume = 1.0;
    synth.speak(utterance);
  }

  function updateButton() {
    if (!ttsBtn) return;
    ttsBtn.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    ttsBtn.setAttribute('aria-label', enabled ? 'Disable TTS' : 'Enable TTS');
    ttsBtn.querySelector('i').className = enabled
      ? 'fas fa-volume-up' : 'fas fa-volume-mute';
    ttsBtn.style.color = enabled ? 'var(--color-primary)' : '';
  }

  function toggle() {
    enabled = !enabled;
    localStorage.setItem(STORAGE_KEY, enabled);
    updateButton();
    if (enabled) {
      speak('Text-to-speech enabled. EduShield NG will now read page content aloud.', true);
    } else {
      synth?.cancel();
    }
  }

  function init() {
    if (!synth) {
      // Browser doesn't support TTS — hide the button
      if (ttsBtn) ttsBtn.style.display = 'none';
      return;
    }

    updateButton();

    if (ttsBtn) {
      ttsBtn.addEventListener('click', toggle);
    }

    // Add TTS to interactive elements on hover (when TTS is enabled)
    // This reads button/link text aloud when the user hovers or focuses
    document.addEventListener('focusin', (e) => {
      if (!enabled) return;
      const el = e.target;
      // Only speak for interactive elements with meaningful text
      if (['BUTTON', 'A', 'LABEL'].includes(el.tagName)) {
        const text = el.getAttribute('aria-label') || el.textContent?.trim();
        if (text && text.length < 200) {
          speak(text);
        }
      }
    });
  }

  // Expose speak() so other scripts (exam pages) can use TTS
  return { init, speak, toggle, isEnabled: () => enabled };
})();


// ══════════════════════════════════════════════
// 6. CSRF TOKEN HELPER FOR AJAX REQUESTS
// ══════════════════════════════════════════════

/**
 * getCsrfToken()
 * Reads the CSRF token from the meta tag or a hidden input.
 * Include this in any fetch() calls that modify data (POST/PUT/DELETE).
 *
 * Usage:
 *   fetch('/api/some-endpoint', {
 *     method: 'POST',
 *     headers: {
 *       'Content-Type': 'application/json',
 *       'X-CSRFToken': getCsrfToken()
 *     },
 *     body: JSON.stringify({ data })
 *   });
 */
function getCsrfToken() {
  // Try meta tag first (we'll add this to base.html)
  const metaTag = document.querySelector('meta[name="csrf-token"]');
  if (metaTag) return metaTag.getAttribute('content');

  // Fall back to hidden input (present in forms rendered by Flask-WTF)
  const hiddenInput = document.querySelector('input[name="csrf_token"]');
  if (hiddenInput) return hiddenInput.value;

  return '';
}

// Patch global fetch to automatically include CSRF token on same-origin POSTs
const _originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  // Only add CSRF for same-origin requests that modify data
  const method = (options.method || 'GET').toUpperCase();
  const modifies = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
  const sameOrigin = !url.toString().startsWith('http') ||
                     url.toString().startsWith(window.location.origin);

  if (modifies && sameOrigin) {
    options.headers = options.headers || {};
    // Don't override if already set
    if (!options.headers['X-CSRFToken']) {
      options.headers['X-CSRFToken'] = getCsrfToken();
    }
  }
  return _originalFetch(url, options);
};


// ══════════════════════════════════════════════
// 7. GENERAL ACCESSIBILITY HELPERS
// ══════════════════════════════════════════════

const AccessibilityManager = (() => {
  function init() {
    // Trap focus inside modals when open
    // (Will be used by exam instructions modal in Day 3)
    document.addEventListener('keydown', (e) => {
      const modal = document.querySelector('.modal.open');
      if (!modal || e.key !== 'Tab') return;

      const focusable = modal.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });

    // Announce page title to screen readers on navigation
    // (Flask renders a new page; this announces it immediately)
    const mainHeading = document.querySelector('h1, h2.auth-form-title, .page-title');
    if (mainHeading) {
      mainHeading.setAttribute('tabindex', '-1');
      // Don't auto-focus on page load (would be annoying)
      // But skip-link target (#main-content) already handles this
    }
  }

  return { init };
})();


// ══════════════════════════════════════════════
// PAGE TRANSITION INDICATOR (Day 9 polish)
// ══════════════════════════════════════════════

const PageTransitionManager = (() => {
  const bar = document.getElementById('pageTransitionBar');

  function start() {
    if (!bar) return;
    bar.classList.add('is-active');
  }

  function init() {
    if (!bar) return;

    // Trigger on any same-origin link click that will cause a full
    // page navigation (not anchors, not links explicitly opted out,
    // not links opening in a new tab, not modifier-key clicks)
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href]');
      if (!link) return;

      const href = link.getAttribute('href');
      const isSamePage   = href.startsWith('#');
      const isNewTab     = link.target === '_blank';
      const isModified   = e.metaKey || e.ctrlKey || e.shiftKey || e.altKey;
      const isExternal   = href.startsWith('http') && !href.startsWith(window.location.origin);
      const optedOut     = link.hasAttribute('data-no-transition');

      if (isSamePage || isNewTab || isModified || isExternal || optedOut) return;

      start();
    });

    // Also trigger on form submissions (e.g. login, exam settings save)
    document.addEventListener('submit', (e) => {
      // Don't show it for forms that already show their own loading
      // state (the exam submit flow has its own full-screen overlay)
      if (e.target.id === 'examSubmitForm') return;
      start();
    });

    // Browser back/forward cache restore — clear any stuck bar state
    window.addEventListener('pageshow', () => {
      bar.classList.remove('is-active');
      bar.style.width = '0%';
    });
  }

  return { init, start };
})();


// ══════════════════════════════════════════════
// GENERIC FORM SUBMIT LOADING STATE (Day 9 polish)
// ══════════════════════════════════════════════

/**
 * FormSubmitManager
 * ===================
 * Rather than hand-editing every form template to add a loading
 * spinner (error-prone — easy to forget one, easy for them to drift
 * out of sync), this module applies a consistent loading state to
 * EVERY form's submit button automatically, app-wide.
 *
 * Behaviour:
 *   - On submit, the clicked submit button is disabled and gets a
 *     spinner prepended to its existing text (text is preserved,
 *     not replaced, so screen readers still get a meaningful label
 *     via the button's accessible name).
 *   - If the form fails client-side validation (browser's native
 *     validation, e.g. a required field is empty), we do NOT show
 *     the loading state — the browser blocks submission anyway.
 *   - Opt-out via [data-no-loading-state] on the <form> element
 *     (used by the exam take.html submit flow, which has its own
 *     full-screen overlay from Day 3).
 */
const FormSubmitManager = (() => {

  function init() {
    document.addEventListener('submit', (e) => {
      const form = e.target;
      if (form.hasAttribute('data-no-loading-state')) return;
      if (!form.checkValidity || !form.checkValidity()) return; // native validation will block + show errors

      // Find the button that triggered submission, or fall back to
      // the form's first submit button
      const submitter = e.submitter || form.querySelector('[type="submit"]');
      if (!submitter || submitter.disabled) return;

      // Save original content so we could theoretically restore it
      // (not needed in practice — a full page navigation follows —
      // but kept for correctness if a form ever submits via fetch())
      submitter.dataset.originalHtml = submitter.innerHTML;
      submitter.disabled = true;
      submitter.setAttribute('aria-busy', 'true');

      const spinner = document.createElement('span');
      spinner.className = 'spinner';
      spinner.style.marginRight = '0.5rem';
      spinner.setAttribute('aria-hidden', 'true');
      submitter.prepend(spinner);
    });
  }

  return { init };
})();


// ══════════════════════════════════════════════
// INIT — Run everything when DOM is ready
// (Script is at bottom of body, so DOM is already loaded)
// ══════════════════════════════════════════════

ThemeManager.init();
PageTransitionManager.init();
FormSubmitManager.init();
NavManager.init();
UserMenuManager.init();
FlashManager.init();
TTSManager.init();
AccessibilityManager.init();

// Expose to global scope so exam/admin scripts can access TTS
window.EduShield = {
  tts: TTSManager,
  getCsrfToken,
  theme: ThemeManager,
};
