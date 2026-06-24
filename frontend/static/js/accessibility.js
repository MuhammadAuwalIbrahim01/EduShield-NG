/**
 * accessibility.js — EduShield NG Accessibility Module
 * ======================================================
 * Loaded on EVERY page (included in base.html).
 * Provides:
 *   1. Advanced TTS with language detection
 *   2. Keyboard navigation helpers
 *   3. High contrast mode (independent of dark mode)
 *   4. Large text mode
 *   5. Focus management utilities
 *   6. Screen reader announcements (ARIA live regions)
 *   7. Language switcher keyboard support
 *   8. Exam-specific TTS (reads questions, options, timer)
 *
 * All preferences persist in localStorage.
 * Module is auto-initialised at the bottom of this file.
 */

'use strict';

const Accessibility = (() => {

  // ── Language ────────────────────────────────
  // Read from server-injected variable (set in base.html)
  const LANG      = window.EduShieldLang || 'en';
  const TTS_LOCALE = window.EduShieldTTSLocale || 'en-NG';

  // Localised strings for this module's own UI (toast messages etc.)
  const T = window.EduShieldT || {};
  const t = key => T[key] || key;

  // ── Storage keys ────────────────────────────
  const KEY_TTS        = 'edu-tts';
  const KEY_LARGE_FONT = 'edu-largefont';
  const KEY_HIGH_CONT  = 'edu-highcontrast';
  const KEY_REDUCED_MO = 'edu-reducedmotion';

  // ── State ───────────────────────────────────
  let ttsEnabled     = localStorage.getItem(KEY_TTS)        === 'true';
  let largeFontOn    = localStorage.getItem(KEY_LARGE_FONT)  === 'true';
  let highContrastOn = localStorage.getItem(KEY_HIGH_CONT)   === 'true';
  let ttsQueue       = [];
  let ttsSpeaking    = false;
  const synth        = window.speechSynthesis;


  // ════════════════════════════════════════════
  // 1. TEXT-TO-SPEECH ENGINE
  // ════════════════════════════════════════════

  /**
   * Speak text aloud using the Web Speech API.
   * Respects:
   *   - User's TTS on/off preference
   *   - prefers-reduced-motion (skip speech if motion is reduced)
   *   - User's preferred language/accent
   *   - An optional priority flag (interrupts current speech)
   *
   * @param {string}  text       — text to speak
   * @param {boolean} interrupt  — cancel current speech and speak immediately
   * @param {number}  rate       — speech rate (0.5–2.0, default 0.9)
   */
  function speak(text, interrupt = false, rate = 0.9) {
    if (!ttsEnabled || !synth || !text?.trim()) return;

    if (interrupt) {
      synth.cancel();
      ttsQueue = [];
    }

    const utterance = new SpeechSynthesisUtterance(text.trim());

    // Use the user's language — Nigerian variants give more natural pronunciation
    utterance.lang   = TTS_LOCALE;
    utterance.rate   = rate;
    utterance.pitch  = 1.0;
    utterance.volume = 1.0;

    // Choose a voice that matches the language if available
    const voices = synth.getVoices();
    const matchingVoice = voices.find(v =>
      v.lang.startsWith(LANG) || v.lang.startsWith(TTS_LOCALE.split('-')[0])
    );
    if (matchingVoice) utterance.voice = matchingVoice;

    utterance.onend = () => {
      ttsSpeaking = false;
      if (ttsQueue.length > 0) {
        const next = ttsQueue.shift();
        speak(next.text, false, next.rate);
      }
    };

    utterance.onerror = () => {
      ttsSpeaking = false;
    };

    ttsSpeaking = true;
    synth.speak(utterance);
  }

  /**
   * Queue a TTS utterance (plays after the current one finishes).
   */
  function queueSpeak(text, rate = 0.9) {
    if (!ttsEnabled || !synth) return;
    if (!ttsSpeaking) {
      speak(text, false, rate);
    } else {
      ttsQueue.push({ text, rate });
    }
  }

  /**
   * Read an exam question and its options aloud in the correct language.
   *
   * @param {string} questionText — the full question text
   * @param {Array}  options      — [{letter, text}, ...]
   * @param {number} questionNum  — question number for announcement
   */
  function readQuestion(questionText, options, questionNum) {
    if (!ttsEnabled || !synth) return;

    // Construct the full reading text
    let text = t('question_of')
      .replace('{n}', questionNum)
      .replace('{total}', '') + '. ';
    text += questionText + '. ';

    if (options?.length) {
      text += 'Options: ';
      options.forEach(opt => {
        text += `Option ${opt.letter}: ${opt.text}. `;
      });
    }

    speak(text, true, 0.85);
  }

  /**
   * Read the current timer value aloud.
   * Called every 5 minutes as a reminder.
   */
  function announceTimer(secondsRemaining) {
    if (!ttsEnabled || !synth) return;
    const minutes = Math.floor(secondsRemaining / 60);
    const secs = secondsRemaining % 60;

    let announcement = '';
    if (minutes > 0) {
      announcement = `${t('time_remaining')}: ${minutes} minute${minutes !== 1 ? 's' : ''}`;
      if (secs > 0) announcement += ` and ${secs} seconds`;
    } else {
      announcement = `${t('time_remaining')}: ${secs} seconds`;
    }
    speak(announcement, true, 1.0);
  }

  function stopSpeaking() {
    synth?.cancel();
    ttsQueue = [];
    ttsSpeaking = false;
  }


  // ════════════════════════════════════════════
  // 2. TTS TOGGLE BUTTON
  // ════════════════════════════════════════════

  function updateTTSButton() {
    const btn = document.getElementById('ttsToggle');
    if (!btn) return;

    const icon = btn.querySelector('i');
    btn.setAttribute('aria-pressed', ttsEnabled ? 'true' : 'false');
    btn.setAttribute('aria-label', ttsEnabled ? t('disable_tts') : t('enable_tts'));
    btn.title = ttsEnabled ? t('disable_tts') : t('enable_tts');

    if (icon) {
      icon.className = ttsEnabled ? 'fas fa-volume-up' : 'fas fa-volume-mute';
    }
    btn.style.color  = ttsEnabled ? 'var(--color-primary)' : '';
    btn.style.background = ttsEnabled ? 'var(--color-primary-light)' : '';
  }

  function initTTS() {
    if (!synth) {
      // Browser doesn't support TTS
      const btn = document.getElementById('ttsToggle');
      if (btn) {
        btn.disabled = true;
        btn.title = 'Text-to-speech not supported in this browser';
      }
      return;
    }

    // Voices may load asynchronously
    synth.onvoiceschanged = () => { /* voices now available */ };

    const btn = document.getElementById('ttsToggle');
    if (btn) {
      updateTTSButton();
      btn.addEventListener('click', () => {
        ttsEnabled = !ttsEnabled;
        localStorage.setItem(KEY_TTS, ttsEnabled);
        updateTTSButton();

        if (ttsEnabled) {
          speak('Text-to-speech enabled. EduShield NG will now read content aloud.', true);
        } else {
          stopSpeaking();
        }
      });
    }

    // Auto-read focused elements when TTS is on
    document.addEventListener('focusin', e => {
      if (!ttsEnabled) return;
      const el = e.target;

      // Read labels attached to inputs
      if (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') {
        const label = document.querySelector(`label[for="${el.id}"]`);
        if (label) speak(label.textContent.trim(), true, 1.0);
        return;
      }

      // Read buttons and links
      if (el.tagName === 'BUTTON' || el.tagName === 'A') {
        const text = el.getAttribute('aria-label') || el.textContent?.trim();
        if (text && text.length < 200) speak(text, true, 1.0);
        return;
      }
    });

    // Read flash messages when they appear
    const observer = new MutationObserver(mutations => {
      if (!ttsEnabled) return;
      mutations.forEach(m => {
        m.addedNodes.forEach(node => {
          if (node.classList?.contains('flash-message')) {
            const text = node.querySelector('.flash-text')?.textContent?.trim();
            if (text) speak(text, false, 0.95);
          }
        });
      });
    });
    const flashContainer = document.querySelector('.flash-container');
    if (flashContainer) {
      observer.observe(flashContainer, { childList: true });
    } else {
      // Create the container if it doesn't exist yet
      const container = document.createElement('div');
      container.className = 'flash-container';
      document.body.appendChild(container);
      observer.observe(container, { childList: true });
    }
  }


  // ════════════════════════════════════════════
  // 3. LARGE FONT MODE
  // ════════════════════════════════════════════

  function applyLargeFont(on) {
    document.documentElement.style.fontSize = on ? '20px' : '';
    document.documentElement.setAttribute('data-large-font', on ? 'true' : 'false');
  }

  function toggleLargeFont() {
    largeFontOn = !largeFontOn;
    localStorage.setItem(KEY_LARGE_FONT, largeFontOn);
    applyLargeFont(largeFontOn);
    announceChange(largeFontOn ? 'Large text enabled' : 'Large text disabled');
  }

  function initLargeFont() {
    if (largeFontOn) applyLargeFont(true);

    // Wire up any large-font toggle buttons in the page
    document.querySelectorAll('[data-action="toggle-large-font"]').forEach(btn => {
      btn.addEventListener('click', toggleLargeFont);
      btn.setAttribute('aria-pressed', largeFontOn ? 'true' : 'false');
    });
  }


  // ════════════════════════════════════════════
  // 4. HIGH CONTRAST MODE
  // ════════════════════════════════════════════

  function applyHighContrast(on) {
    // High contrast is implemented as a special data attribute
    // that overrides CSS variables for maximum contrast ratios
    document.documentElement.setAttribute('data-high-contrast', on ? 'true' : 'false');
    if (on) {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  }

  function toggleHighContrast() {
    highContrastOn = !highContrastOn;
    localStorage.setItem(KEY_HIGH_CONT, highContrastOn);
    applyHighContrast(highContrastOn);
    announceChange(highContrastOn ? 'High contrast enabled' : 'High contrast disabled');
  }

  function initHighContrast() {
    if (highContrastOn) applyHighContrast(true);

    document.querySelectorAll('[data-action="toggle-high-contrast"]').forEach(btn => {
      btn.addEventListener('click', toggleHighContrast);
      btn.setAttribute('aria-pressed', highContrastOn ? 'true' : 'false');
    });
  }


  // ════════════════════════════════════════════
  // 5. ARIA LIVE ANNOUNCEMENTS
  // ════════════════════════════════════════════

  /**
   * Announce a message to screen readers via an ARIA live region.
   * Does NOT use TTS (this is for screen reader users who don't
   * need TTS because their screen reader already reads the page).
   *
   * @param {string} message   — text to announce
   * @param {string} politeness — 'polite' | 'assertive'
   */
  function announce(message, politeness = 'polite') {
    let region = document.getElementById('edu-aria-live');
    if (!region) {
      region = document.createElement('div');
      region.id = 'edu-aria-live';
      region.setAttribute('aria-live', politeness);
      region.setAttribute('aria-atomic', 'true');
      // Visually hidden but available to screen readers
      region.style.cssText = `
        position: absolute;
        width: 1px; height: 1px;
        padding: 0; margin: -1px;
        overflow: hidden;
        clip: rect(0,0,0,0);
        white-space: nowrap;
        border: 0;
      `;
      document.body.appendChild(region);
    }

    // Clear and re-set to ensure the announcement fires even if
    // the same message is repeated (screen readers may ignore identical updates)
    region.setAttribute('aria-live', politeness);
    region.textContent = '';
    // Brief delay ensures the DOM update triggers a new announcement
    setTimeout(() => { region.textContent = message; }, 50);
  }

  function announceChange(text) {
    announce(text, 'polite');
    if (ttsEnabled) speak(text, false, 1.0);
  }


  // ════════════════════════════════════════════
  // 6. KEYBOARD NAVIGATION
  // ════════════════════════════════════════════

  function initKeyboardNav() {
    // Language switcher keyboard support
    const langBtn = document.getElementById('langMenuBtn');
    const langDropdown = document.getElementById('langDropdown');

    if (langBtn && langDropdown) {
      langBtn.addEventListener('click', e => {
        e.stopPropagation();
        const open = langDropdown.classList.toggle('open');
        langBtn.setAttribute('aria-expanded', open);
        if (open) {
          const firstItem = langDropdown.querySelector('[role="menuitem"]');
          firstItem?.focus();
        }
      });

      langDropdown.addEventListener('keydown', e => {
        const items = [...langDropdown.querySelectorAll('[role="menuitem"]')];
        const idx = items.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          items[(idx + 1) % items.length]?.focus();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          items[(idx - 1 + items.length) % items.length]?.focus();
        } else if (e.key === 'Escape') {
          langDropdown.classList.remove('open');
          langBtn.setAttribute('aria-expanded', 'false');
          langBtn.focus();
        }
      });

      document.addEventListener('click', () => {
        langDropdown.classList.remove('open');
        langBtn.setAttribute('aria-expanded', 'false');
      });
    }

    // Skip link enhancement — smooth focus
    const skipLink = document.querySelector('.skip-link');
    if (skipLink) {
      skipLink.addEventListener('click', e => {
        const target = document.getElementById('main-content');
        if (target) {
          e.preventDefault();
          target.focus();
          target.scrollIntoView({ behavior: 'smooth' });
          if (ttsEnabled) speak(t('nav_dashboard'), true);
        }
      });
    }

    // Trap focus in open modals
    document.addEventListener('keydown', e => {
      if (e.key !== 'Tab') return;
      const modal = document.querySelector('.modal-overlay:not([hidden])');
      if (!modal) return;

      const focusable = [...modal.querySelectorAll(
        'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )];
      if (!focusable.length) return;

      const first = focusable[0];
      const last  = focusable[focusable.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });
  }


  // ════════════════════════════════════════════
  // 7. REDUCED MOTION SUPPORT
  // ════════════════════════════════════════════

  function initReducedMotion() {
    // Detect OS-level preference
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)');

    function applyReducedMotion(reduce) {
      document.documentElement.setAttribute('data-reduced-motion', reduce ? 'true' : 'false');
    }

    applyReducedMotion(prefersReduced.matches);
    prefersReduced.addEventListener('change', e => applyReducedMotion(e.matches));
  }


  // ════════════════════════════════════════════
  // 8. PAGE LOAD ANNOUNCEMENT (for screen readers)
  // ════════════════════════════════════════════

  function announcePageLoad() {
    // On every page load, announce the page title to screen readers
    // that may have missed the title element change (SPAs, soft navigation)
    const pageTitle = document.title?.replace(' | Secure Online Examinations', '').trim();
    if (pageTitle) {
      // Small delay so the page is fully rendered
      setTimeout(() => announce(pageTitle, 'polite'), 300);
    }
  }


  // ════════════════════════════════════════════
  // PUBLIC INIT
  // ════════════════════════════════════════════

  function init() {
    initTTS();
    initLargeFont();
    initHighContrast();
    initKeyboardNav();
    initReducedMotion();
    announcePageLoad();
  }


  // ════════════════════════════════════════════
  // PUBLIC API
  // ════════════════════════════════════════════

  return {
    init,
    speak,
    queueSpeak,
    stopSpeaking,
    readQuestion,
    announceTimer,
    announce,
    toggleLargeFont,
    toggleHighContrast,
    isEnabled: () => ttsEnabled,
    getLocale: () => TTS_LOCALE,
  };

})();

Accessibility.init();

// Expose to global scope — exam_engine.js and anti_cheat.js use this
// EduShield.tts.speak() is the public interface
window.EduShield = window.EduShield || {};
window.EduShield.tts        = Accessibility;
window.EduShield.a11y       = Accessibility;
window.EduShield.announce   = Accessibility.announce;
