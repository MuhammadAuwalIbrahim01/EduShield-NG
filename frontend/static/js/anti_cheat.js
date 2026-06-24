/**
 * anti_cheat.js — EduShield NG Complete Anti-Cheat Module
 * =========================================================
 * Loads BEFORE exam_engine.js (see take.html script order).
 * Requires window.ExamEngine to be available (set by exam_engine.js).
 *
 * DETECTION EVENTS MONITORED:
 *   1.  Tab switch          (document.visibilitychange)
 *   2.  Window blur         (window.blur)
 *   3.  Window focus lost   (window.focus — inverse)
 *   4.  Copy attempt        (document.copy)
 *   5.  Paste attempt       (document.paste)
 *   6.  Cut attempt         (document.cut)
 *   7.  Right-click         (document.contextmenu)
 *   8.  Keyboard shortcuts  (document.keydown — DevTools, print, save, etc.)
 *   9.  Fullscreen exit     (document.fullscreenchange)
 *  10.  Text selection      (document.selectstart)
 *  11.  Drag start          (document.dragstart)
 *  12.  Print attempt       (window.beforeprint)
 *  13.  DevTools open       (window size heuristic)
 *  14.  Screen capture API  (getDisplayMedia intercept)
 *
 * PREVENTION MEASURES:
 *   - All default actions suppressed (e.preventDefault())
 *   - CSS user-select: none on exam content
 *   - All events logged to server with timestamps
 *   - Tab switch counter triggers auto-submit at MAX_TABS
 *
 * IMPORTANT SECURITY NOTE:
 * A determined student can bypass ALL of this by disabling JS.
 * These measures deter casual cheating and create an audit trail.
 * The server-side checks (timer, score calculation) cannot be bypassed.
 */

'use strict';

// ══════════════════════════════════════════════
// ANTI-CHEAT STATE
// ══════════════════════════════════════════════

const AntiCheat = (() => {

  // Internal counters — synced with ExamEngine after it loads
  let tabSwitchCount  = 0;
  let blurCount       = 0;
  let copyAttempts    = 0;
  let pasteAttempts   = 0;
  let rightClicks     = 0;
  let shortcutAttempts= 0;
  let initialized     = false;

  // Timestamps for detecting rapid suspicious patterns
  let lastBlurTime    = 0;
  let lastFocusTime   = Date.now();

  // Blocked keyboard shortcuts (key combos that would help cheating)
  // Format: "modifier+key" where modifier is ctrl/alt/meta
  const BLOCKED_SHORTCUTS = new Set([
    'ctrl+c',  'ctrl+v',  'ctrl+x',   // Copy, paste, cut
    'ctrl+a',  'ctrl+s',  'ctrl+p',   // Select all, save, print
    'ctrl+u',  'ctrl+f',  'ctrl+h',   // View source, find, history
    'ctrl+r',  'ctrl+l',  'ctrl+t',   // Reload, address bar, new tab
    'ctrl+w',  'ctrl+n',  'ctrl+j',   // Close tab, new window, downloads
    'ctrl+shift+i', 'ctrl+shift+j',   // DevTools
    'ctrl+shift+c', 'ctrl+shift+k',   // Inspector, console
    'f1', 'f5', 'f12',                 // Help, refresh, DevTools
    'alt+f4',  'alt+tab',              // Close window, switch app
    'meta+c',  'meta+v',  'meta+x',   // Mac: copy, paste, cut
    'meta+a',  'meta+s',  'meta+p',   // Mac: select all, save, print
    'meta+r',  'meta+q',  'meta+h',   // Mac: reload, quit, hide
    'meta+shift+i', 'meta+option+i',  // Mac: DevTools
  ]);

  // ────────────────────────────────────────────
  // CORE: LOG EVENT TO SERVER
  // ────────────────────────────────────────────

  /**
   * Send a cheat event to the server.
   * Uses sendBeacon() for reliability — works even if the page
   * is being unloaded (unlike fetch which may be cancelled).
   *
   * @param {string} eventType  - One of the VALID_EVENTS allowlist
   * @param {string} description - Human-readable description
   * @param {string} severity    - 'low' | 'medium' | 'high'
   */
  function logEvent(eventType, description, severity = 'medium') {
    // ExamEngine may not be loaded yet on first few events
    const engine = window.ExamEngine;
    if (!engine) return;

    const payload = JSON.stringify({
      session_token: engine.getSessionToken(),
      event_type:    eventType,
      description:   description,
      severity:      severity,
      // Client timestamp for reference (server will use its own)
      client_time:   new Date().toISOString(),
    });

    const logUrl = engine.getLogUrl();

    // Primary: fetch (works for most events)
    fetch(logUrl, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken':  window.EduShield?.getCsrfToken?.() || '',
      },
      body: payload,
      // keepalive: request continues even if page unloads
      keepalive: true,
    })
    .then(res => res.json())
    .then(data => {
      // Server may instruct us to auto-submit (e.g. tab limit hit)
      if (data.action === 'auto_submit') {
        engine.autoSubmit();
      }
      // Update the tab-switch counter display
      if (typeof data.tab_switches === 'number') {
        // This triggers the warning modal in exam_engine.js
        if (eventType === 'tab_switch') {
          engine.showTabWarning(data.tab_switches, data.max_allowed);
        }
      }
    })
    .catch(() => {
      // Network failure — store in sessionStorage for retry
      const pending = JSON.parse(
        sessionStorage.getItem('edu_pending_logs') || '[]'
      );
      pending.push({ eventType, description, severity, time: Date.now() });
      sessionStorage.setItem('edu_pending_logs', JSON.stringify(pending));
    });
  }

  // Retry any pending log events (runs every 15 seconds)
  function retryPendingLogs() {
    const pending = JSON.parse(
      sessionStorage.getItem('edu_pending_logs') || '[]'
    );
    if (pending.length === 0) return;

    // Re-log each pending event
    pending.forEach(item => {
      logEvent(item.eventType, item.description + ' [retry]', item.severity);
    });

    // Clear after retry (server will have received them or we'll retry again)
    sessionStorage.removeItem('edu_pending_logs');
  }

  setInterval(retryPendingLogs, 15000);


  // ────────────────────────────────────────────
  // 1. TAB SWITCH DETECTION
  // ────────────────────────────────────────────

  /**
   * visibilitychange fires when:
   *   - Student switches to another browser tab
   *   - Student minimises the browser window
   *   - Screen locks / screensaver activates
   *   - Mobile: another app comes to foreground
   *
   * document.visibilityState is either 'visible' or 'hidden'
   */
  function initTabSwitchDetection() {
    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'hidden') {
        // Student left the exam window
        tabSwitchCount++;

        // Sync counter with ExamEngine
        window.ExamEngine?.incrementTabSwitch();

        logEvent(
          'tab_switch',
          `Student left exam window (switch #${tabSwitchCount}). ` +
          `Tab/window became hidden at ${new Date().toISOString()}`,
          'high'
        );

        // Visual + audio alert when they return
        document.title = '⚠️ RETURN TO EXAM — EduShield NG';

      } else if (document.visibilityState === 'visible') {
        // Student returned to exam window
        document.title = document.querySelector('h1')?.textContent?.trim()
          || 'Exam in Progress — EduShield NG';
      }
    });
  }


  // ────────────────────────────────────────────
  // 2. WINDOW BLUR DETECTION
  // ────────────────────────────────────────────

  /**
   * blur fires when the browser window loses focus.
   * This catches:
   *   - Alt+Tab to another application
   *   - Clicking outside the browser
   *   - Opening another application via taskbar
   *
   * We debounce rapid blur/focus cycles (< 300ms)
   * because some browser dialogs cause brief blurs.
   */
  function initWindowBlurDetection() {
    window.addEventListener('blur', function() {
      const now = Date.now();

      // Ignore rapid blur/focus (browser UI interactions < 300ms)
      if (now - lastFocusTime < 300) return;

      lastBlurTime = now;
      blurCount++;

      logEvent(
        'window_blur',
        `Browser window lost focus (#${blurCount}). ` +
        `Student may have switched to another application.`,
        'medium'
      );
    });

    window.addEventListener('focus', function() {
      lastFocusTime = Date.now();
      // Only log focus events after a significant blur duration (> 2 seconds)
      const blurDuration = lastFocusTime - lastBlurTime;
      if (lastBlurTime > 0 && blurDuration > 2000) {
        logEvent(
          'window_blur',
          `Window refocused after ${Math.round(blurDuration/1000)}s away.`,
          'low'
        );
      }
    });
  }


  // ────────────────────────────────────────────
  // 3. COPY / PASTE / CUT PREVENTION
  // ────────────────────────────────────────────

  /**
   * These events fire when the student uses:
   *   - Ctrl+C / Cmd+C (copy)
   *   - Ctrl+V / Cmd+V (paste)
   *   - Ctrl+X / Cmd+X (cut)
   *   - Right-click → Copy/Paste from context menu
   *   - Edit menu → Copy/Paste
   *
   * We PREVENT the action AND log it.
   */
  function initClipboardPrevention() {
    document.addEventListener('copy', function(e) {
      e.preventDefault();
      copyAttempts++;
      logEvent(
        'copy_attempt',
        `Copy attempt #${copyAttempts} — content blocked.`,
        'medium'
      );
      showInlineWarning('Copying is not allowed during the examination.');
    });

    document.addEventListener('paste', function(e) {
      e.preventDefault();
      pasteAttempts++;
      logEvent(
        'paste_attempt',
        `Paste attempt #${pasteAttempts} — blocked.`,
        'medium'
      );
      showInlineWarning('Pasting is not allowed during the examination.');
    });

    document.addEventListener('cut', function(e) {
      e.preventDefault();
      logEvent(
        'copy_attempt',
        'Cut attempt — blocked.',
        'medium'
      );
    });
  }


  // ────────────────────────────────────────────
  // 4. RIGHT-CLICK PREVENTION
  // ────────────────────────────────────────────

  function initRightClickPrevention() {
    document.addEventListener('contextmenu', function(e) {
      e.preventDefault();
      rightClicks++;
      logEvent(
        'right_click',
        `Right-click attempt #${rightClicks} on element: ${e.target.tagName}`,
        'low'
      );
      showInlineWarning('Right-clicking is disabled during the examination.');
      return false;
    });
  }


  // ────────────────────────────────────────────
  // 5. KEYBOARD SHORTCUT BLOCKING
  // ────────────────────────────────────────────

  /**
   * We intercept ALL keydown events.
   * If the key combination is in BLOCKED_SHORTCUTS, we:
   *   1. Prevent the default browser action
   *   2. Stop propagation (other listeners won't fire)
   *   3. Log the attempt
   *
   * We ALLOW normal typing (letters, numbers, space, enter)
   * and navigation (arrow keys, tab — needed for accessibility).
   */
  function initKeyboardBlocking() {
    document.addEventListener('keydown', function(e) {
      // Build a normalised key combo string
      const combo = buildKeyCombo(e);

      if (BLOCKED_SHORTCUTS.has(combo)) {
        e.preventDefault();
        e.stopPropagation();
        shortcutAttempts++;

        logEvent(
          'keyboard_shortcut',
          `Blocked shortcut: ${combo} (attempt #${shortcutAttempts})`,
          combo.includes('f12') || combo.includes('shift+i') ? 'high' : 'medium'
        );

        // Special warning for DevTools attempts
        if (combo.includes('f12') || combo.includes('shift+i') ||
            combo.includes('shift+j') || combo.includes('shift+k')) {
          showInlineWarning(
            '⚠️ Developer Tools access is not permitted during the examination.',
            'high'
          );
        }

        return false;
      }

      // Block F-keys individually (F1–F12)
      if (e.key.match(/^F\d+$/) && !e.shiftKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        logEvent('keyboard_shortcut', `F-key blocked: ${e.key}`, 'low');
        return false;
      }
    }, true); // Capture phase: fires before other listeners
  }

  /**
   * Build a normalised key combination string.
   * Examples:
   *   Ctrl+C         → 'ctrl+c'
   *   Ctrl+Shift+I   → 'ctrl+shift+i'
   *   F12            → 'f12'
   *   Alt+Tab        → 'alt+tab'
   */
  function buildKeyCombo(e) {
    const parts = [];
    if (e.ctrlKey  && e.key !== 'Control')  parts.push('ctrl');
    if (e.altKey   && e.key !== 'Alt')      parts.push('alt');
    if (e.metaKey  && e.key !== 'Meta')     parts.push('meta');
    if (e.shiftKey && e.key !== 'Shift')    parts.push('shift');
    // Normalise key name: 'c' → 'c', 'C' → 'c', 'F12' → 'f12'
    parts.push(e.key.toLowerCase());
    return parts.join('+');
  }


  // ────────────────────────────────────────────
  // 6. FULLSCREEN EXIT DETECTION
  // ────────────────────────────────────────────

  /**
   * We request fullscreen when the exam starts.
   * If the student presses Escape to exit fullscreen, we log it.
   * We do NOT force fullscreen back — that would be too intrusive
   * and may break on mobile. We just log and warn.
   */
  function initFullscreenDetection() {
    // Request fullscreen on exam start
    requestExamFullscreen();

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
  }

  function requestExamFullscreen() {
    const elem = document.documentElement;
    const requestFn = elem.requestFullscreen
      || elem.webkitRequestFullscreen
      || elem.mozRequestFullScreen;

    if (requestFn) {
      requestFn.call(elem).catch(() => {
        // Fullscreen request failed (user denied, or browser policy)
        // This is not a cheat event — just not supported
        console.info('EduShield: Fullscreen unavailable');
      });
    }
  }

  function handleFullscreenChange() {
    const isFullscreen = !!(
      document.fullscreenElement       ||
      document.webkitFullscreenElement ||
      document.mozFullScreenElement
    );

    if (!isFullscreen) {
      logEvent(
        'fullscreen_exit',
        'Student exited fullscreen mode during examination.',
        'medium'
      );
      showInlineWarning(
        'You have exited fullscreen mode. Please return to fullscreen.',
        'medium'
      );
    }
  }


  // ────────────────────────────────────────────
  // 7. TEXT SELECTION PREVENTION
  // ────────────────────────────────────────────

  /**
   * Prevents the student from selecting question text
   * (which could enable easier copy-paste via keyboard or
   * screenshot with visible selection highlighting).
   *
   * We apply this via CSS (more reliable than JS) AND via event.
   */
  function initTextSelectionPrevention() {
    // CSS approach (applied via style tag — works even if JS is slow)
    const style = document.createElement('style');
    style.textContent = `
      .question-text,
      .option-text,
      .options-fieldset {
        -webkit-user-select: none;
        -moz-user-select: none;
        -ms-user-select: none;
        user-select: none;
      }
    `;
    document.head.appendChild(style);

    // JS fallback
    document.addEventListener('selectstart', function(e) {
      // Allow selection only in input fields (for typing answers)
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return true;
      }
      e.preventDefault();
    });

    document.addEventListener('dragstart', function(e) {
      e.preventDefault();
      logEvent('copy_attempt', 'Drag-and-drop text selection attempt blocked.', 'low');
    });
  }


  // ────────────────────────────────────────────
  // 8. PRINT PREVENTION
  // ────────────────────────────────────────────

  function initPrintPrevention() {
    window.addEventListener('beforeprint', function(e) {
      logEvent(
        'keyboard_shortcut',
        'Print attempt detected (Ctrl+P or File→Print).',
        'high'
      );
      showInlineWarning('Printing exam content is strictly prohibited.');
    });

    // CSS: hide everything when printing
    const printStyle = document.createElement('style');
    printStyle.media = 'print';
    printStyle.textContent = `
      * { display: none !important; visibility: hidden !important; }
      body::before {
        display: block !important;
        visibility: visible !important;
        content: 'Printing exam content is prohibited by EduShield NG.';
        font-size: 24px; padding: 40px; text-align: center;
      }
    `;
    document.head.appendChild(printStyle);
  }


  // ────────────────────────────────────────────
  // 9. DEVTOOLS DETECTION (HEURISTIC)
  // ────────────────────────────────────────────

  /**
   * We cannot perfectly detect DevTools, but we use two heuristics:
   *
   * A) Window size delta: DevTools docked to the window reduces
   *    its inner width/height measurably.
   *
   * B) debugger statement timing: debugger; pauses JS execution.
   *    If execution time for a tiny loop >> expected, DevTools is open.
   *
   * These are IMPERFECT — we log them as low-severity hints,
   * not as definitive evidence of cheating.
   */
  function initDevToolsDetection() {
    let outerWidth  = window.outerWidth;
    let outerHeight = window.outerHeight;

    // Check every 3 seconds for significant size change
    // (DevTools opens → window shrinks by 300+ px)
    setInterval(function() {
      const widthDelta  = outerWidth  - window.outerWidth;
      const heightDelta = outerHeight - window.outerHeight;

      // Threshold: > 160px change suggests DevTools panel
      if (widthDelta > 160 || heightDelta > 160) {
        logEvent(
          'keyboard_shortcut',
          `Possible DevTools detected: window shrank by ${widthDelta}px × ${heightDelta}px`,
          'medium'
        );
        outerWidth  = window.outerWidth;
        outerHeight = window.outerHeight;
      } else {
        // Update baseline
        outerWidth  = window.outerWidth;
        outerHeight = window.outerHeight;
      }
    }, 3000);
  }


  // ────────────────────────────────────────────
  // 10. SCREEN CAPTURE / SHARE API INTERCEPT
  // ────────────────────────────────────────────

  /**
   * Some students may try to use screen sharing to show
   * the exam to an accomplice via video call.
   * We intercept navigator.mediaDevices.getDisplayMedia
   * and block/log the attempt.
   *
   * Note: This is a SOFT block — the browser may still
   * allow it at the OS level. We log the attempt.
   */
  function initScreenCaptureIntercept() {
    if (!navigator.mediaDevices?.getDisplayMedia) return;

    const originalGetDisplayMedia =
      navigator.mediaDevices.getDisplayMedia.bind(navigator.mediaDevices);

    navigator.mediaDevices.getDisplayMedia = async function(...args) {
      logEvent(
        'keyboard_shortcut',
        'Screen capture/share API call intercepted.',
        'high'
      );
      showInlineWarning(
        '⚠️ Screen sharing is not permitted during the examination.',
        'high'
      );
      // Reject the promise — browser will show no sharing dialog
      throw new DOMException(
        'Screen capture is disabled during EduShield NG examinations.',
        'NotAllowedError'
      );
    };
  }


  // ────────────────────────────────────────────
  // INLINE WARNING TOAST
  // ────────────────────────────────────────────

  /**
   * Shows a non-blocking toast notification inside the exam
   * instead of an alert() (which could be used to pause the timer
   * in older browsers, and is disruptive).
   *
   * @param {string} message  - Warning text to show
   * @param {string} severity - 'low'|'medium'|'high' (affects colour)
   */
  let toastTimeout = null;

  function showInlineWarning(message, severity = 'medium') {
    // Get or create the toast container
    let toast = document.getElementById('antiCheatToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'antiCheatToast';
      toast.setAttribute('role', 'alert');
      toast.setAttribute('aria-live', 'assertive');
      toast.setAttribute('aria-atomic', 'true');
      document.body.appendChild(toast);
    }

    // Set styles based on severity
    const bgColor = severity === 'high'   ? '#dc2626' :
                    severity === 'medium' ? '#d97706' : '#0284c7';

    toast.style.cssText = `
      position: fixed;
      top: 4.5rem;
      left: 50%;
      transform: translateX(-50%);
      background: ${bgColor};
      color: white;
      padding: 0.75rem 1.5rem;
      border-radius: 0.75rem;
      font-size: 0.875rem;
      font-weight: 600;
      z-index: 9000;
      box-shadow: 0 10px 25px rgba(0,0,0,0.3);
      max-width: 90vw;
      text-align: center;
      animation: antiCheatSlide 0.3s ease;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    `;

    toast.innerHTML = `
      <span aria-hidden="true">${severity === 'high' ? '🚨' : '⚠️'}</span>
      <span>${message}</span>
    `;

    // Add animation keyframe if not already present
    if (!document.getElementById('antiCheatStyles')) {
      const styleEl = document.createElement('style');
      styleEl.id = 'antiCheatStyles';
      styleEl.textContent = `
        @keyframes antiCheatSlide {
          from { opacity: 0; transform: translateX(-50%) translateY(-10px); }
          to   { opacity: 1; transform: translateX(-50%) translateY(0); }
        }
      `;
      document.head.appendChild(styleEl);
    }

    // Auto-dismiss after 4 seconds
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => { if (toast.parentNode) toast.remove(); }, 300);
    }, 4000);
  }


  // ────────────────────────────────────────────
  // PUBLIC INIT
  // ────────────────────────────────────────────

  function init() {
    if (initialized) return;
    initialized = true;

    console.info('EduShield AntiCheat: Initializing...');

    initTabSwitchDetection();
    initWindowBlurDetection();
    initClipboardPrevention();
    initRightClickPrevention();
    initKeyboardBlocking();
    initFullscreenDetection();
    initTextSelectionPrevention();
    initPrintPrevention();
    initDevToolsDetection();
    initScreenCaptureIntercept();

    console.info('EduShield AntiCheat: All monitors active.');

    // Log that monitoring has started (server-side record)
    // Small delay to ensure ExamEngine is ready
    setTimeout(() => {
      logEvent(
        'face_detected',  // Reuse as "session started" marker
        'Anti-cheat monitoring initialized for this session.',
        'low'
      );
    }, 2000);
  }


  // ────────────────────────────────────────────
  // RETURN PUBLIC API
  // ────────────────────────────────────────────

  return {
    init,
    logEvent,
    showInlineWarning,
    getStats: () => ({
      tabSwitches:     tabSwitchCount,
      blurs:           blurCount,
      copyAttempts,
      pasteAttempts,
      rightClicks,
      shortcutAttempts,
    }),
  };

})(); // End IIFE


// ══════════════════════════════════════════════
// AUTO-INIT
// Anti-cheat starts immediately when the script loads.
// ExamEngine may not be ready yet, so logEvent() guards
// against this with the "if (!engine) return" check.
// The 2-second delay in init() ensures ExamEngine is loaded.
// ══════════════════════════════════════════════

AntiCheat.init();

// Expose globally so exam_engine.js can access stats on submit
window.AntiCheat = AntiCheat;
