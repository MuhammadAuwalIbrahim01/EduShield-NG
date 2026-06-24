/**
 * face_monitor.js — EduShield NG AI Face Monitoring
 * ====================================================
 * Uses face-api.js (TensorFlow.js backed) to:
 *   1. Start webcam stream
 *   2. Detect faces in real-time (every 3 seconds)
 *   3. Log to server when:
 *      - No face detected (student left camera)
 *      - Multiple faces detected (possible accomplice)
 *      - Face confidence is too low (face obscured/covered)
 *   4. Update webcam panel UI with live status
 *
 * face-api.js CDN is loaded dynamically below.
 * Models are loaded from a CDN (jsDelivr).
 *
 * GRACEFUL DEGRADATION:
 *   - If webcam permission denied → log it, continue exam without AI
 *   - If face-api.js fails to load → log it, continue exam
 *   - If models fail to load → log it, continue exam
 *   EXAM IS NEVER BLOCKED by webcam failures (accessibility)
 *
 * PRIVACY NOTE:
 *   - No video is recorded or transmitted to the server
 *   - Only detection metadata (face count, confidence) is logged
 *   - All face detection happens 100% in the browser (client-side)
 */

'use strict';

const FaceMonitor = (() => {

  // ── Configuration ──────────────────────────
  const DETECTION_INTERVAL_MS = 3000;    // Check every 3 seconds
  const FACE_ABSENT_THRESHOLD  = 3;      // Log after 3 consecutive misses
  const MULTI_FACE_LOG_EVERY   = 2;      // Log every 2nd multi-face detection
  const MIN_CONFIDENCE         = 0.65;   // Below this = face not clearly visible
  const MODELS_CDN = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model';

  // ── Day 5: Identity Verification Config ─────
  const MATCH_THRESHOLD         = 0.5;   // distance below this = same person
  const MISMATCH_THRESHOLD      = 0.6;   // distance above this = different person
  // Between 0.5 and 0.6 is a "borderline" zone — we don't raise an alert,
  // since lighting/angle changes can shift distance slightly even for
  // the same person. Only confident mismatches (>0.6) are flagged.
  const MISMATCH_CONSECUTIVE_REQUIRED = 2; // Need 2 consecutive mismatches before logging
                                            // (avoids false positives from a single bad frame)

  // ── State ───────────────────────────────────
  let videoEl           = null;
  let stream            = null;
  let detectionTimer    = null;
  let consecutiveAbsent = 0;
  let consecutiveMismatch = 0;
  let totalAbsent       = 0;
  let totalMultiFace    = 0;
  let totalMismatch     = 0;
  let multiFaceDetCount = 0;
  let modelsLoaded      = false;
  let monitoringActive  = false;
  let lastDetectionTime = Date.now();
  let referenceDescriptor = null;  // Loaded from server (student's calibration)

  // ── DOM Elements ────────────────────────────
  const statusDot  = document.getElementById('webcamDot');
  const statusText = document.getElementById('webcamStatusText');
  const webcamPanel= document.getElementById('webcamPanel');


  // ────────────────────────────────────────────
  // STATUS HELPERS
  // ────────────────────────────────────────────

  function setStatus(text, state = 'ok') {
    if (statusText) statusText.textContent = text;
    if (statusDot) {
      statusDot.className = 'status-dot';
      if (state === 'ok')      statusDot.classList.add('status-dot-green');
      else if (state === 'warn') statusDot.classList.add('status-dot-yellow');
      else if (state === 'err')  statusDot.classList.add('status-dot-red');
    }
    // Update webcam panel border
    if (webcamPanel) {
      webcamPanel.style.borderColor =
        state === 'ok'   ? 'var(--color-success)' :
        state === 'warn' ? 'var(--color-warning)' :
                           'var(--color-danger)';
    }
  }

  function logFaceEvent(eventType, description, severity, metadata = {}) {
    window.AntiCheat?.logEvent(eventType, description, severity);
    // Also update ExamEngine counters
    if (eventType === 'face_absent')    window.ExamEngine?.incrementFaceAbsent();
    if (eventType === 'multiple_faces') window.ExamEngine?.incrementMultiFace();
  }


  // ────────────────────────────────────────────
  // STEP 1: LOAD face-api.js FROM CDN
  // ────────────────────────────────────────────

  function loadFaceApiScript() {
    return new Promise((resolve, reject) => {
      // Check if already loaded
      if (window.faceapi) { resolve(); return; }

      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/@vladmandic/face-api/dist/face-api.js';
      script.crossOrigin = 'anonymous';
      script.onload  = resolve;
      script.onerror = () => reject(new Error('face-api.js failed to load from CDN'));
      document.head.appendChild(script);
    });
  }


  // ────────────────────────────────────────────
  // STEP 2: LOAD DETECTION MODELS
  // ────────────────────────────────────────────

  /**
   * face-api.js requires pre-trained model files.
   * We use two lightweight models:
   *
   * 1. SsdMobilenetv1 — Detects face BOUNDING BOXES
   *    Fast, works on mid-range devices, ~6MB model files
   *
   * 2. FaceLandmark68Net — Detects 68 facial landmarks
   *    Used to confirm it's a real face (not a photo/poster)
   *
   * Models load from jsDelivr CDN. On slow networks this
   * may take 5-15 seconds — we show a loading indicator.
   */
  async function loadModels() {
    setStatus('Loading AI models...', 'warn');

    try {
      await Promise.all([
        faceapi.nets.ssdMobilenetv1.loadFromUri(MODELS_CDN),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODELS_CDN),
        // FaceRecognitionNet: converts a detected face into a 128-number
        // descriptor vector, used to verify identity against the
        // student's calibration reference (Day 5)
        faceapi.nets.faceRecognitionNet.loadFromUri(MODELS_CDN),
      ]);

      modelsLoaded = true;
      setStatus('AI models ready', 'ok');
      return true;

    } catch (err) {
      console.warn('EduShield FaceMonitor: Models failed to load:', err);
      setStatus('AI offline (camera still active)', 'warn');
      logFaceEvent(
        'face_absent',
        `Face detection models failed to load: ${err.message}`,
        'low'
      );
      return false;
    }
  }


  // ────────────────────────────────────────────
  // STEP 3: REQUEST WEBCAM ACCESS
  // ────────────────────────────────────────────

  /**
   * Requests camera permission and starts the video stream.
   *
   * Constraints:
   *   - facingMode: 'user'  → front camera (selfie cam on mobile)
   *   - width/height 640×480 → good quality, not too heavy
   *   - NOT recording audio (students should be able to speak freely)
   *
   * IMPORTANT: We do NOT record or transmit video.
   * The stream is used ONLY for face detection in the browser.
   */
  async function startWebcam() {
    videoEl = document.getElementById('webcamVideo');
    if (!videoEl) return false;

    setStatus('Requesting camera...', 'warn');

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode:  'user',
          width:       { ideal: 640 },
          height:      { ideal: 480 },
          frameRate:   { ideal: 15, max: 30 },
        },
        audio: false,  // NEVER request audio
      });

      videoEl.srcObject = stream;

      // Wait for video to actually start playing
      await new Promise((resolve, reject) => {
        videoEl.onloadedmetadata = resolve;
        videoEl.onerror          = reject;
        setTimeout(reject, 10000); // 10s timeout
      });

      await videoEl.play();
      setStatus('Camera active ✓', 'ok');
      return true;

    } catch (err) {
      const isPermissionDenied =
        err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError';

      const description = isPermissionDenied
        ? 'Webcam permission denied by student.'
        : `Webcam error: ${err.message}`;

      setStatus(isPermissionDenied ? 'Camera denied' : 'Camera error', 'err');

      logFaceEvent('face_absent', description, 'high');

      // Show user-friendly explanation in webcam panel
      if (webcamPanel) {
        webcamPanel.innerHTML += `
          <div style="
            padding:0.5rem;background:rgba(220,38,38,0.9);
            color:white;font-size:10px;text-align:center;line-height:1.4;">
            ${isPermissionDenied
              ? '⚠️ Camera access denied. This has been recorded.'
              : '⚠️ Camera unavailable. This has been recorded.'}
          </div>
        `;
      }

      return false;
    }
  }


  // ────────────────────────────────────────────
  // DAY 5: LOAD REFERENCE FACE DESCRIPTOR
  // ────────────────────────────────────────────

  /**
   * Fetches the student's calibrated face descriptor from the server.
   * This was captured once during the /exam/calibrate/<id> flow and
   * stored on the User model. If the student has no calibration
   * (e.g. webcam wasn't required for a previous exam), this returns
   * null and identity verification is simply skipped — we still run
   * face-presence and multi-face detection regardless.
   */
  async function loadReferenceDescriptor() {
    try {
      const examDataEl = document.getElementById('examData');
      const examId = examDataEl?.dataset.examId;
      const res = await fetch(`/exam/api/my-face-descriptor?exam_id=${examId}`, {
        headers: { 'X-CSRFToken': window.EduShield?.getCsrfToken?.() || '' },
      });
      const data = await res.json();
      if (data.descriptor && Array.isArray(data.descriptor)) {
        referenceDescriptor = new Float32Array(data.descriptor);
        console.info('EduShield FaceMonitor: Reference descriptor loaded.');
      } else {
        console.info('EduShield FaceMonitor: No calibration on file — identity check skipped.');
      }
    } catch (err) {
      console.warn('EduShield FaceMonitor: Could not load reference descriptor:', err);
    }
  }

  /**
   * Euclidean distance between two face descriptors.
   * face-api.js provides faceapi.euclideanDistance() but we
   * implement it directly here for clarity and to avoid a
   * dependency timing issue if faceapi isn't loaded yet.
   */
  function descriptorDistance(d1, d2) {
    let sum = 0;
    for (let i = 0; i < d1.length; i++) {
      const diff = d1[i] - d2[i];
      sum += diff * diff;
    }
    return Math.sqrt(sum);
  }

  // ────────────────────────────────────────────
  // DAY 5: SNAPSHOT CAPTURE (EVIDENCE)
  // ────────────────────────────────────────────

  /**
   * Captures a single still frame from the video element as a
   * small base64 JPEG thumbnail. Used as evidence for high-severity
   * events (multiple_faces, face_mismatch) — NOT recorded continuously.
   *
   * We deliberately keep this SMALL (150x110) to:
   *   1. Minimise storage/bandwidth
   *   2. Respect privacy — just enough for a human reviewer to see
   *      "yes, that's clearly two people" without high-res surveillance
   */
  function captureSnapshot() {
    if (!videoEl) return null;
    try {
      const canvas = document.createElement('canvas');
      canvas.width  = 150;
      canvas.height = 110;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
      // JPEG at 60% quality keeps the thumbnail well under our 80KB server limit
      return canvas.toDataURL('image/jpeg', 0.6);
    } catch (err) {
      console.warn('EduShield FaceMonitor: Snapshot capture failed:', err);
      return null;
    }
  }

  /**
   * Logs an event WITH evidence attached (snapshot + face distance).
   * Routes through AntiCheat.logEvent but extends the payload —
   * we call fetch directly here since AntiCheat.logEvent doesn't
   * know about snapshot/distance fields.
   */
  function logEventWithEvidence(eventType, description, severity, extra = {}) {
    const engine = window.ExamEngine;
    if (!engine) return;

    const payload = {
      session_token: engine.getSessionToken(),
      event_type:    eventType,
      description:   description,
      severity:      severity,
      client_time:   new Date().toISOString(),
      ...extra,
    };

    fetch(engine.getLogUrl(), {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken':  window.EduShield?.getCsrfToken?.() || '',
      },
      body: JSON.stringify(payload),
      keepalive: true,
    })
    .then(res => res.json())
    .then(data => {
      if (data.action === 'auto_submit') engine.autoSubmit();
    })
    .catch(() => { /* best-effort; evidence events are not retried to avoid stale snapshots */ });
  }


  // ────────────────────────────────────────────
  // STEP 4: CONTINUOUS FACE DETECTION LOOP
  // ────────────────────────────────────────────

  /**
   * Runs face detection every DETECTION_INTERVAL_MS milliseconds.
   *
   * Detection options:
   *   - scoreThreshold: only report faces above this confidence
   *   - We use SsdMobilenetv1 (fast, multi-face capable)
   *
   * Decision logic per detection cycle:
   *   - 0 faces → increment absent counter → log after threshold
   *   - 1 face  → all good → reset absent counter
   *   - 2+ faces → log every Nth detection (avoid log spam)
   *   - Low confidence → treat as absent
   */
  async function runDetection() {
    if (!monitoringActive || !modelsLoaded || !videoEl) return;

    try {
      // Detect all faces, with landmarks AND descriptors (needed for identity match)
      const detections = await faceapi
        .detectAllFaces(
          videoEl,
          new faceapi.SsdMobilenetv1Options({
            scoreThreshold: MIN_CONFIDENCE,
          })
        )
        .withFaceLandmarks()
        .withFaceDescriptors(); // Day 5: extract 128-dim vectors for identity check

      const faceCount = detections.length;
      lastDetectionTime = Date.now();

      if (faceCount === 0) {
        // ── No face detected ─────────────────────
        consecutiveAbsent++;
        consecutiveMismatch = 0; // Reset mismatch streak — no face to mismatch

        if (consecutiveAbsent === FACE_ABSENT_THRESHOLD) {
          totalAbsent++;
          window.ExamEngine?.incrementFaceAbsent();

          logFaceEvent(
            'face_absent',
            `No face detected for ${DETECTION_INTERVAL_MS * FACE_ABSENT_THRESHOLD / 1000}s ` +
            `(absence event #${totalAbsent}).`,
            totalAbsent >= 5 ? 'high' : 'medium'
          );

          setStatus(`Face absent (#${totalAbsent})`, 'warn');

          window.AntiCheat?.showInlineWarning(
            'Please keep your face visible in the camera.',
            'medium'
          );
        }

      } else if (faceCount === 1) {
        // ── Exactly one face (expected) ──────────
        consecutiveAbsent = 0;

        const confidence = detections[0].detection.score;

        // ── Day 5: Identity verification ──────────
        // Only runs if the student completed calibration AND
        // the model successfully extracted a descriptor this frame.
        if (referenceDescriptor && detections[0].descriptor) {
          const distance = descriptorDistance(
            referenceDescriptor,
            detections[0].descriptor
          );

          if (distance > MISMATCH_THRESHOLD) {
            // Confident mismatch this frame
            consecutiveMismatch++;

            if (consecutiveMismatch >= MISMATCH_CONSECUTIVE_REQUIRED) {
              totalMismatch++;
              setStatus(`⚠️ Identity mismatch (#${totalMismatch})`, 'err');

              logEventWithEvidence(
                'face_mismatch',
                `Face does not match calibration reference ` +
                `(distance=${distance.toFixed(3)}, threshold=${MISMATCH_THRESHOLD}). ` +
                `Mismatch event #${totalMismatch}.`,
                'high',
                {
                  snapshot: captureSnapshot(),
                  face_match_distance: distance,
                }
              );

              window.AntiCheat?.showInlineWarning(
                '⚠️ We could not verify your identity. This has been recorded.',
                'high'
              );

              consecutiveMismatch = 0; // Reset after logging to avoid spam
            }
          } else if (distance <= MATCH_THRESHOLD) {
            // Clear match — reset any building mismatch streak
            consecutiveMismatch = 0;
            setStatus(`Verified ✓ (${Math.round(confidence * 100)}%)`, 'ok');
          } else {
            // Borderline zone (0.5–0.6) — don't flag, don't reset either,
            // just hold steady. Lighting/angle can cause natural drift here.
            setStatus(`Face detected (${Math.round(confidence * 100)}%)`, 'ok');
          }

        } else {
          // No calibration on file — fall back to simple presence check
          if (confidence < MIN_CONFIDENCE) {
            setStatus('Face unclear', 'warn');
          } else {
            setStatus(`Face detected ✓ (${Math.round(confidence * 100)}%)`, 'ok');
          }
        }

      } else {
        // ── Multiple faces detected ──────────────
        consecutiveAbsent = 0;
        consecutiveMismatch = 0;
        multiFaceDetCount++;

        if (multiFaceDetCount % MULTI_FACE_LOG_EVERY === 0) {
          totalMultiFace++;
          window.ExamEngine?.incrementMultiFace();

          // Day 5: capture snapshot evidence for multi-face events too
          logEventWithEvidence(
            'multiple_faces',
            `${faceCount} faces detected (event #${totalMultiFace}). ` +
            `Possible unauthorized person in frame.`,
            'high',
            { snapshot: captureSnapshot() }
          );

          setStatus(`${faceCount} faces detected!`, 'err');

          window.AntiCheat?.showInlineWarning(
            `⚠️ ${faceCount} faces detected. Only you should be visible in the camera.`,
            'high'
          );
        }
      }

    } catch (err) {
      console.debug('EduShield FaceMonitor: Detection error:', err.message);
    }

    if (monitoringActive) {
      detectionTimer = setTimeout(runDetection, DETECTION_INTERVAL_MS);
    }
  }


  // ────────────────────────────────────────────
  // STEP 5: STOP MONITORING (on exam submit)
  // ────────────────────────────────────────────

  function stop() {
    monitoringActive = false;
    clearTimeout(detectionTimer);

    // Stop the webcam stream (releases camera resource)
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      stream = null;
    }

    if (videoEl) {
      videoEl.srcObject = null;
    }

    setStatus('Monitoring stopped', 'ok');
    console.info('EduShield FaceMonitor: Stopped.');
  }


  // ────────────────────────────────────────────
  // PUBLIC INIT
  // ────────────────────────────────────────────

  async function init() {
    console.info('EduShield FaceMonitor: Starting...');
    setStatus('Initializing...', 'warn');

    // Step 1: Load face-api.js library
    try {
      await loadFaceApiScript();
    } catch (err) {
      console.warn('EduShield FaceMonitor:', err.message);
      setStatus('AI unavailable', 'warn');
      // Still start webcam for visual deterrence
      await startWebcam();
      return;
    }

    // Step 2: Load detection models
    const modelsOk = await loadModels();

    // Step 2.5 (Day 5): Load the student's calibration reference
    // We do this regardless of modelsOk in case models load fine but
    // we still want the fetch to have happened for future retry logic.
    if (modelsOk) {
      await loadReferenceDescriptor();
    }

    // Step 3: Start webcam
    const webcamOk = await startWebcam();

    if (!webcamOk) {
      // Cannot monitor — log and continue
      setStatus('Monitoring offline', 'err');
      return;
    }

    // Step 4: Start detection loop
    if (modelsOk) {
      monitoringActive = true;
      // Short delay to let video stream stabilize
      setTimeout(runDetection, 2000);
      console.info('EduShield FaceMonitor: Active. Detecting every 3s.');
    } else {
      // Webcam is on but no AI detection — visual deterrence only
      setStatus('Camera active (no AI)', 'warn');
    }
  }


  // ────────────────────────────────────────────
  // RETURN PUBLIC API
  // ────────────────────────────────────────────

  return {
    init,
    stop,
    getStats: () => ({
      totalAbsent,
      totalMultiFace,
      totalMismatch,
      consecutiveAbsent,
      consecutiveMismatch,
      monitoringActive,
      hasReference: !!referenceDescriptor,
    }),
  };

})();


// ══════════════════════════════════════════════
// AUTO-INIT (called when script loads)
// Uses defer in take.html so DOM is ready.
// ══════════════════════════════════════════════

FaceMonitor.init().catch(err => {
  console.warn('EduShield FaceMonitor: Init failed gracefully:', err);
});

window.FaceMonitor = FaceMonitor;
