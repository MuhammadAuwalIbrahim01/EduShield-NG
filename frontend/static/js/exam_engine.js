/**
 * exam_engine.js — EduShield NG Core Exam Logic
 * ================================================
 * Responsibilities:
 *   1. Countdown timer (synced with server deadline)
 *   2. Question navigation (prev/next/jump)
 *   3. Answer selection + instant auto-save
 *   4. Submit modal (review + confirm)
 *   5. Auto-submit when timer reaches zero
 *   6. TTS: read question aloud
 *   7. Sidebar collapse toggle
 *   8. Keyboard shortcuts (arrow keys for prev/next)
 *   9. Progress tracking (answered count)
 *  10. Restore accessibility preferences from localStorage
 *
 * This file has NO dependency on external libraries.
 * anti_cheat.js and face_monitor.js load separately.
 */

'use strict';

// ══════════════════════════════════════════════
// 1. READ DATA ATTRIBUTES FROM DOM
// ══════════════════════════════════════════════

const examData       = document.getElementById('examData');
const SESSION_TOKEN  = examData.dataset.sessionToken;
const EXAM_ID        = examData.dataset.examId;
const TOTAL_QS       = parseInt(examData.dataset.total, 10);
const SAVE_URL       = examData.dataset.saveUrl;
const SUBMIT_URL     = examData.dataset.submitUrl;
const LOG_URL        = examData.dataset.logUrl;
const WEBCAM_REQ     = examData.dataset.webcam === 'true';
const MAX_TABS       = parseInt(examData.dataset.maxTabSwitches, 10);

// ── State ──────────────────────────────────────
let currentIndex    = 0;       // Which question is visible
let answers         = {};      // {question_id: "A"|"B"|"C"|"D"}
let tabSwitches     = 0;
let faceAbsentCount = 0;
let multiFaceCount  = 0;
let saveQueue       = [];      // Pending saves (in case of network issue)
let isSubmitting    = false;

// ── DOM References ─────────────────────────────
const timerDisplay    = document.getElementById('timerDisplay');
const timerEl         = document.getElementById('examTimer');
const answeredCount   = document.getElementById('answeredCount');
const autosaveEl      = document.getElementById('autosaveIndicator');
const saveIcon        = document.getElementById('saveIcon');
const saveText        = document.getElementById('saveText');
const submitModal     = document.getElementById('submitModal');
const tabModal        = document.getElementById('tabSwitchModal');


// ══════════════════════════════════════════════
// 2. COUNTDOWN TIMER
// ══════════════════════════════════════════════

(function initTimer() {
  // Get deadline from the server-rendered data attribute
  // Format: ISO string like "2024-11-15T14:30:00"
  const deadlineStr = timerEl.dataset.deadline;
  // Parse as UTC (server sends UTC)
  const deadline = new Date(deadlineStr + 'Z');

  function tick() {
    const now = Date.now();
    const secondsLeft = Math.max(0, Math.floor((deadline - now) / 1000));
    const minutes = Math.floor(secondsLeft / 60);
    const seconds = secondsLeft % 60;

    timerDisplay.textContent =
      String(minutes).padStart(2, '0') + ':' + String(seconds).padStart(2, '0');

    // Update ARIA label for screen readers
    timerEl.setAttribute('aria-label',
      `Time remaining: ${minutes} minutes and ${seconds} seconds`);

    // Visual urgency states
    timerEl.classList.remove('timer-warning', 'timer-critical');
    if (secondsLeft <= 60) {
      timerEl.classList.add('timer-critical');
    } else if (secondsLeft <= 300) {
      timerEl.classList.add('timer-warning');
    }

    if (secondsLeft <= 0) {
      // Time's up — auto-submit
      timerDisplay.textContent = '00:00';
      autoSubmit();
      return; // Stop ticking
    }

    setTimeout(tick, 1000);
  }

  tick();
})();


// ══════════════════════════════════════════════
// 3. QUESTION NAVIGATION
// ══════════════════════════════════════════════

function showQuestion(index) {
  // Bounds check
  if (index < 0 || index >= TOTAL_QS) return;

  // Hide current question
  const current = document.getElementById(`question-${currentIndex}`);
  if (current) current.hidden = true;

  // Highlight nav button as no longer current
  const prevNav = document.getElementById(`nav-${currentIndex}`);
  if (prevNav) prevNav.classList.remove('q-nav-current');

  // Show new question
  currentIndex = index;
  const next = document.getElementById(`question-${currentIndex}`);
  if (next) {
    next.hidden = false;
    next.focus(); // Move focus for keyboard/screen reader users
    // Animate in
    next.style.animation = 'none';
    void next.offsetWidth; // Trigger reflow to restart animation
    next.style.animation = '';
  }

  // Update nav button state
  const nextNav = document.getElementById(`nav-${currentIndex}`);
  if (nextNav) {
    nextNav.classList.add('q-nav-current');
    nextNav.setAttribute('aria-current', 'true');
    // Scroll nav button into view if needed
    nextNav.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  // TTS: auto-read if enabled
  if (window.EduShield?.tts?.isEnabled()) {
    const qText = next?.querySelector('.question-text')?.textContent?.trim();
    if (qText) {
      const qNum = `Question ${currentIndex + 1} of ${TOTAL_QS}. `;
      window.EduShield.tts.speak(qNum + qText, true);
    }
  }
}

function nextQuestion() {
  showQuestion(currentIndex + 1);
}

function prevQuestion() {
  showQuestion(currentIndex - 1);
}

function goToQuestion(index) {
  showQuestion(index);
}

// Keyboard navigation: arrow keys move between questions
document.addEventListener('keydown', function(e) {
  // Don't hijack arrow keys when user is focused on a radio (they use arrows to select)
  if (e.target.type === 'radio') return;

  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault();
    nextQuestion();
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault();
    prevQuestion();
  }
});

// Initialize: mark current question in nav
document.getElementById(`nav-${currentIndex}`)?.classList.add('q-nav-current');


// ══════════════════════════════════════════════
// 4. ANSWER SELECTION + AUTO-SAVE
// ══════════════════════════════════════════════

// Load any pre-saved answers from the DOM (server rendered them)
document.querySelectorAll('.option-radio:checked').forEach(radio => {
  const qid = radio.dataset.questionId;
  answers[qid] = radio.value;
});

// Listen for all radio button changes across all questions
document.addEventListener('change', function(e) {
  const radio = e.target;
  if (!radio.classList.contains('option-radio')) return;

  const qid    = radio.dataset.questionId;
  const qIndex = parseInt(radio.dataset.questionIndex, 10);
  const answer = radio.value;

  // Store locally
  answers[qid] = answer;

  // Update the option visual state
  const questionEl = document.getElementById(`question-${qIndex}`);
  if (questionEl) {
    // Remove selected from all options in this question
    questionEl.querySelectorAll('.option-label').forEach(label => {
      label.classList.remove('option-selected');
    });
    // Add selected to the clicked option
    radio.closest('.option-label')?.classList.add('option-selected');
  }

  // Mark nav button as answered
  const navBtn = document.getElementById(`nav-${qIndex}`);
  if (navBtn) {
    navBtn.classList.add('q-nav-answered');
    navBtn.setAttribute('aria-label',
      `Question ${qIndex + 1}: answered`);
  }

  // Update answered count display
  updateAnsweredCount();

  // Save to server (debounced)
  saveAnswer(qid, answer);
});

function updateAnsweredCount() {
  if (answeredCount) {
    answeredCount.textContent = Object.keys(answers).length;
  }
}

// ── Save a single answer to the server ─────────
let saveDebounceTimer = null;

function saveAnswer(questionId, answer) {
  // Show saving indicator
  setAutosaveState('saving');

  // Debounce: wait 500ms after last change before saving
  clearTimeout(saveDebounceTimer);
  saveDebounceTimer = setTimeout(() => {
    fetch(SAVE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.EduShield?.getCsrfToken?.() || '',
      },
      body: JSON.stringify({
        session_token: SESSION_TOKEN,
        question_id:   parseInt(questionId, 10),
        answer:        answer,
      }),
    })
    .then(res => res.json())
    .then(data => {
      if (data.error === 'Session expired') {
        // Server says time is up — auto-submit
        autoSubmit();
      } else if (data.status === 'saved') {
        setAutosaveState('saved');
      } else {
        setAutosaveState('error');
      }
    })
    .catch(() => {
      setAutosaveState('error');
      // Add to retry queue
      saveQueue.push({ questionId, answer });
    });
  }, 500);
}

function setAutosaveState(state) {
  if (!autosaveEl) return;
  autosaveEl.className = 'autosave-indicator';
  if (state === 'saving') {
    saveIcon.className  = 'fas fa-cloud-upload-alt';
    saveText.textContent = 'Saving...';
    autosaveEl.classList.add('autosave-saving');
  } else if (state === 'saved') {
    saveIcon.className  = 'fas fa-cloud';
    saveText.textContent = 'All answers saved';
    autosaveEl.classList.add('autosave-saved');
  } else {
    saveIcon.className  = 'fas fa-exclamation-triangle';
    saveText.textContent = 'Save failed — will retry';
    autosaveEl.classList.add('autosave-error');
  }
}

// Retry failed saves every 30 seconds
setInterval(() => {
  if (saveQueue.length > 0) {
    const item = saveQueue.shift();
    saveAnswer(item.questionId, item.answer);
  }
}, 30000);


// ══════════════════════════════════════════════
// 5. SUBMIT MODAL
// ══════════════════════════════════════════════

function openSubmitModal() {
  const answered  = Object.keys(answers).length;
  const remaining = TOTAL_QS - answered;

  // Build summary list
  const summary = document.getElementById('submitSummary');
  summary.innerHTML = `
    <li>
      <i class="fas fa-check-circle" style="color:var(--color-success)"></i>
      <strong>${answered}</strong> of ${TOTAL_QS} questions answered
    </li>
    ${remaining > 0 ? `
    <li>
      <i class="fas fa-exclamation-circle" style="color:var(--color-warning)"></i>
      <strong>${remaining}</strong> question${remaining !== 1 ? 's' : ''} left unanswered
    </li>` : ''}
    <li>
      <i class="fas fa-shield-alt" style="color:var(--color-primary)"></i>
      Tab switches: <strong>${tabSwitches}</strong> / ${MAX_TABS} allowed
    </li>
  `;

  submitModal.hidden = false;
  // Move focus to the confirm button
  document.getElementById('confirmSubmitBtn').focus();
}

function closeSubmitModal() {
  submitModal.hidden = true;
  // Return focus to Review button
  document.getElementById('reviewBtn')?.focus() ||
  document.getElementById('submitBtn').focus();
}

// Close modal on overlay click
submitModal.addEventListener('click', function(e) {
  if (e.target === submitModal) closeSubmitModal();
});

// Keyboard: Escape closes modal
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && !submitModal.hidden) closeSubmitModal();
});

// Header submit button
document.getElementById('submitBtn').addEventListener('click', openSubmitModal);


// ══════════════════════════════════════════════
// 6. CONFIRM & FINAL SUBMIT
// ══════════════════════════════════════════════

function confirmSubmit() {
  submitExam(false);
}

function autoSubmit() {
  if (isSubmitting) return;
  submitExam(true);
}

function submitExam(isAuto) {
  if (isSubmitting) return;
  isSubmitting = true;

  // Close any open modal
  submitModal.hidden = true;

  // Show full-screen overlay with spinner
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position:fixed;inset:0;background:rgba(15,23,42,0.8);
    display:flex;flex-direction:column;align-items:center;
    justify-content:center;z-index:9999;color:white;gap:1rem;
  `;
  overlay.innerHTML = `
    <div style="font-size:3rem;">🛡️</div>
    <div style="font-size:1.25rem;font-weight:700;">
      ${isAuto ? 'Time expired — submitting your exam...' : 'Submitting your exam...'}
    </div>
    <div style="font-size:0.875rem;color:rgba(255,255,255,0.7);">Please do not close this window</div>
    <i class="fas fa-spinner fa-spin" style="font-size:2rem;"></i>
  `;
  document.body.appendChild(overlay);

  // Announce to screen reader
  overlay.setAttribute('role', 'alert');
  overlay.setAttribute('aria-live', 'assertive');

  fetch(SUBMIT_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.EduShield?.getCsrfToken?.() || '',
    },
    body: JSON.stringify({
      session_token:        SESSION_TOKEN,
      answers:              answers,
      tab_switches:         tabSwitches,
      face_absent_count:    faceAbsentCount,
      multiple_faces_count: multiFaceCount,
    }),
  })
  .then(res => res.json())
  .then(data => {
    if (data.redirect_url) {
      window.location.href = data.redirect_url;
    } else {
      // Fallback: reload
      window.location.reload();
    }
  })
  .catch(() => {
    // Network error — keep trying
    overlay.innerHTML = `
      <div style="font-size:3rem;">⚠️</div>
      <div style="font-size:1.25rem;font-weight:700;color:#fbbf24;">
        Network error — retrying in 5 seconds...
      </div>
    `;
    setTimeout(() => submitExam(isAuto), 5000);
    isSubmitting = false;
  });
}


// ══════════════════════════════════════════════
// 7. TTS — READ QUESTION ALOUD
// ══════════════════════════════════════════════

document.querySelectorAll('.tts-question-btn').forEach(btn => {
  btn.addEventListener('click', function() {
    const text = this.dataset.text;
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.rate = 0.85;
      u.lang = 'en-NG';
      window.speechSynthesis.speak(u);
      this.textContent = '🔊 Reading...';
      u.onend = () => {
        this.innerHTML = '<i class="fas fa-volume-up"></i> Read Aloud';
      };
    }
  });
});


// ══════════════════════════════════════════════
// 8. SIDEBAR TOGGLE
// ══════════════════════════════════════════════

const sidebarToggle = document.getElementById('sidebarToggle');
const examSidebar   = document.querySelector('.exam-sidebar');

if (sidebarToggle && examSidebar) {
  sidebarToggle.addEventListener('click', function() {
    const collapsed = examSidebar.classList.toggle('collapsed');
    this.setAttribute('aria-expanded', !collapsed);
    const icon = this.querySelector('i');
    icon.className = collapsed ? 'fas fa-chevron-right' : 'fas fa-chevron-left';
  });
}


// ══════════════════════════════════════════════
// 9. PREVENT ACCIDENTAL NAVIGATION AWAY
// ══════════════════════════════════════════════

window.addEventListener('beforeunload', function(e) {
  if (isSubmitting) return; // Allow redirect after submit
  e.preventDefault();
  e.returnValue = 'You have an exam in progress. Are you sure you want to leave?';
  return e.returnValue;
});


// ══════════════════════════════════════════════
// 10. RESTORE ACCESSIBILITY PREFS
// ══════════════════════════════════════════════

(function restorePrefs() {
  // Large font
  if (localStorage.getItem('edu-largefont') === 'true') {
    document.documentElement.style.fontSize = '20px';
  }
  // High contrast
  if (localStorage.getItem('edu-highcontrast') === 'true') {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();


// ══════════════════════════════════════════════
// EXPOSE FOR ANTI-CHEAT & FACE MONITOR
// ══════════════════════════════════════════════

// anti_cheat.js and face_monitor.js update these counters
// and call logEvent() to report to the server

window.ExamEngine = {
  incrementTabSwitch:  () => { tabSwitches++; },
  incrementFaceAbsent: () => { faceAbsentCount++; },
  incrementMultiFace:  () => { multiFaceCount++; },
  getSessionToken:     () => SESSION_TOKEN,
  getLogUrl:           () => LOG_URL,
  getMaxTabs:          () => MAX_TABS,
  getCurrentTabs:      () => tabSwitches,
  autoSubmit:          autoSubmit,
  showTabWarning:      showTabWarning,
};

function showTabWarning(switchCount, maxAllowed) {
  const countEl = document.getElementById('tabSwitchCount');
  if (countEl) {
    const remaining = Math.max(0, maxAllowed - switchCount);
    countEl.textContent =
      `Warning ${switchCount} of ${maxAllowed}: ${remaining} warning${remaining !== 1 ? 's' : ''} remaining.`;
    countEl.style.color = remaining === 0 ? 'var(--color-danger)' : 'var(--color-warning)';
  }
  if (tabModal) {
    tabModal.hidden = false;
    document.getElementById('tabWarningDismiss')?.focus();
  }
}

function dismissTabWarning() {
  if (tabModal) tabModal.hidden = true;
}
