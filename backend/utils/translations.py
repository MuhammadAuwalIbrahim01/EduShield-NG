"""
backend/utils/translations.py — EduShield NG Translation System
=================================================================
A custom dictionary-based translation system supporting:
  - English (en)  — default
  - Hausa (ha)    — Northern Nigeria
  - Yoruba (yo)   — South-West Nigeria
  - Igbo (ig)     — South-East Nigeria

Why not Flask-Babel?
  Flask-Babel requires pybabel CLI + gettext tools at build time.
  On Render free tier, this complicates the build. For ~80 UI
  strings across 4 languages, a Python dict is simpler, testable,
  and deployable without extra tooling.

Usage in Python routes:
  from backend.utils.translations import get_text, get_lang
  lang = get_lang()             # gets user's preferred language
  msg = get_text('login_title', lang)  # returns translated string

Usage in Jinja2 templates (via context processor):
  {{ t('login_title') }}        # auto-detects user language
  {{ t('welcome', lang='ha') }} # explicit language override

TTS Language codes (BCP-47):
  'en' → 'en-NG'   (Nigerian English accent)
  'ha' → 'ha'      (Hausa — limited browser support)
  'yo' → 'yo'      (Yoruba — limited browser support)
  'ig' → 'ig'      (Igbo — very limited browser support)
  Fallback: 'en-NG' for all when native accent unavailable
"""

from flask import session, request
from flask_login import current_user

# ══════════════════════════════════════════════
# TRANSLATION DICTIONARY
# All UI strings in all 4 languages
# ══════════════════════════════════════════════

TRANSLATIONS = {

    # ── Authentication ──────────────────────────
    "login_title": {
        "en": "Sign In",
        "ha": "Shiga",
        "yo": "Wọle",
        "ig": "Banye",
    },
    "login_subtitle": {
        "en": "Sign in to access your examinations",
        "ha": "Shiga don samun damar jarabawarku",
        "yo": "Wọle lati wọle si awọn idanwo rẹ",
        "ig": "Banye iji nweta ule gị",
    },
    "register_title": {
        "en": "Create Student Account",
        "ha": "Ƙirƙiri Asusun Ɗalibi",
        "yo": "Ṣẹda Akon Ọmọ ile-iwe",
        "ig": "Mepụta Akaụntụ Nwa Akwụkwọ",
    },
    "email_label": {
        "en": "Email Address",
        "ha": "Adireshin Imel",
        "yo": "Àdírẹ́sì Ímeèlì",
        "ig": "Adreesị Email",
    },
    "password_label": {
        "en": "Password",
        "ha": "Kalmar Sirri",
        "yo": "Ọ̀rọ̀ Aṣínà",
        "ig": "Okwuntughe",
    },
    "full_name_label": {
        "en": "Full Name",
        "ha": "Cikakken Suna",
        "yo": "Orúkọ Kíkún",
        "ig": "Aha Ọzara Ụba",
    },
    "sign_in_btn": {
        "en": "Sign In",
        "ha": "Shiga",
        "yo": "Wọle",
        "ig": "Banye",
    },
    "sign_out_btn": {
        "en": "Sign Out",
        "ha": "Fita",
        "yo": "Jade",
        "ig": "Pụọ",
    },
    "create_account_btn": {
        "en": "Create Account",
        "ha": "Ƙirƙiri Asusu",
        "yo": "Ṣẹda Akon",
        "ig": "Mepụta Akaụntụ",
    },
    "forgot_password": {
        "en": "Forgot password?",
        "ha": "Manta da kalmar sirri?",
        "yo": "Gbagbe ọrọ aṣínà?",
        "ig": "Chefuo okwuntughe?",
    },

    # ── Navigation ──────────────────────────────
    "nav_dashboard": {
        "en": "Dashboard",
        "ha": "Allon Sarrafa",
        "yo": "Pẹpẹ Iṣakoso",
        "ig": "Deshboard",
    },
    "nav_available_exams": {
        "en": "Available Exams",
        "ha": "Jarabawar da ke Akwai",
        "yo": "Àwọn Idanwo Tó Wà",
        "ig": "Ule Dị",
    },
    "nav_my_results": {
        "en": "My Results",
        "ha": "Sakamakon na",
        "yo": "Àwọn Àbájáde Mi",
        "ig": "Nsonaazụ M",
    },
    "nav_profile": {
        "en": "My Profile",
        "ha": "Bayanan na",
        "yo": "Profaili Mi",
        "ig": "Profaịlụ M",
    },

    # ── Dashboard ───────────────────────────────
    "welcome_back": {
        "en": "Welcome back",
        "ha": "Barka da dawowa",
        "yo": "Ẹ káàbọ̀ padà",
        "ig": "Nnọọ laghachi",
    },
    "ready_for_exam": {
        "en": "Ready for your next examination?",
        "ha": "Shin kuna shirye don jarabawar ta gaba?",
        "yo": "Ṣé o ṣetán fún idanwo rẹ̀ tó ń bọ̀?",
        "ig": "Ị dị njikere maka ule gị ọzọ?",
    },
    "exams_taken": {
        "en": "Exams Taken",
        "ha": "Jarabawar da aka yi",
        "yo": "Àwọn Idanwo Tí A Ṣe",
        "ig": "Ule Emere",
    },
    "passed": {
        "en": "Passed",
        "ha": "Ya/Ta wuce",
        "yo": "Àṣeyọrí",
        "ig": "Gafere",
    },
    "pass_rate": {
        "en": "Pass Rate",
        "ha": "Adadin da suka wuce",
        "yo": "Ìpele Àṣeyọrí",
        "ig": "Ọnụ Ọgụgụ Gafere",
    },
    "available_now": {
        "en": "Available Now",
        "ha": "Akwai yanzu",
        "yo": "Tó Wà Nísinsin yìí",
        "ig": "Dị Ugbu A",
    },

    # ── Exam Interface ──────────────────────────
    "start_exam_btn": {
        "en": "Start Exam",
        "ha": "Fara Jaraba",
        "yo": "Bẹ̀rẹ̀ Idanwo",
        "ig": "Bido Ule",
    },
    "submit_exam_btn": {
        "en": "Submit Exam",
        "ha": "Mika Jaraba",
        "yo": "Firanṣẹ Idanwo",
        "ig": "Nyefee Ule",
    },
    "next_question": {
        "en": "Next",
        "ha": "Na gaba",
        "yo": "Tó ń bọ̀",
        "ig": "Ọzọ",
    },
    "previous_question": {
        "en": "Previous",
        "ha": "Na baya",
        "yo": "Tẹ́lẹ̀",
        "ig": "Nke Gara Aga",
    },
    "time_remaining": {
        "en": "Time Remaining",
        "ha": "Lokacin da ya Rage",
        "yo": "Àkókò Tó Ṣẹ́kù",
        "ig": "Oge Fọdụrụ",
    },
    "question_of": {
        "en": "Question {n} of {total}",
        "ha": "Tambaya ta {n} daga cikin {total}",
        "yo": "Ìbéèrè {n} nínú {total}",
        "ig": "Ajụjụ {n} n'ime {total}",
    },
    "answered": {
        "en": "answered",
        "ha": "an amsa",
        "yo": "tí a dáhùn",
        "ig": "zara",
    },
    "read_aloud_btn": {
        "en": "Read Aloud",
        "ha": "Karanta Da Murya",
        "yo": "Ka Ní Ọ̀Pọ̀",
        "ig": "Gụọ Ọnụ",
    },

    # ── Anti-Cheat Messages ─────────────────────
    "tab_switch_warning": {
        "en": "Warning: You have switched away from the exam window.",
        "ha": "Gargaɗi: Ka/ki canza daga taga jaraba.",
        "yo": "Ìkìlọ̀: O ti yí kúrò nínú fèrèsé idanwo.",
        "ig": "Ọnụ ọgụgụ: Ị gbanwere n'ụlọ ọgụgụ ule.",
    },
    "copy_blocked": {
        "en": "Copying is not allowed during the examination.",
        "ha": "Kwafawa ba a yarda da shi ba a lokacin jaraba.",
        "yo": "Àdàkọ kò gba àánú nígbà idanwo.",
        "ig": "Akọsara anaghị ekwe ya n'oge ule.",
    },
    "right_click_blocked": {
        "en": "Right-clicking is disabled during the examination.",
        "ha": "Danna dama ya kashe a lokacin jaraba.",
        "yo": "Títẹ ọ̀tún ti di egbogi nígbà idanwo.",
        "ig": "Pịa ụtọ anaghị arụ ọrụ n'oge ule.",
    },
    "face_absent_warning": {
        "en": "Please keep your face visible in the camera.",
        "ha": "Da fatan za a kiyaye fuskarku a bayyane a kyamara.",
        "yo": "Jọwọ jẹ kí ojú rẹ hàn nínú kamẹra.",
        "ig": "Biko debe ihu gị ka ọ pụtara ìhè na mkpụrụ ọnụ.",
    },
    "multiple_faces_warning": {
        "en": "Multiple faces detected. Only you should be visible in the camera.",
        "ha": "An gano fuskokin mutane da yawa. Ku kaɗai ne ya kamata a gani a kyamara.",
        "yo": "A ti rí ojú ọ̀pọ̀ ènìyàn. Ìwọ nìkan ló yẹ kí ó hàn nínú kamẹra.",
        "ig": "Achọpụtara ihu ndị ọzọ. Naanị gị kwesịrị ịpụta ìhè na mkpụrụ ọnụ.",
    },
    "exam_auto_submitted": {
        "en": "Your exam has been automatically submitted.",
        "ha": "An mika jaraba ku ta atomatik.",
        "yo": "Wọ́n ti firanṣẹ idanwo rẹ láìfọwọ́ sí.",
        "ig": "Ezigara ule gị ozugbo.",
    },

    # ── Results ─────────────────────────────────
    "congratulations_passed": {
        "en": "Congratulations! You Passed",
        "ha": "Taya! Kun wuce",
        "yo": "Àánú! O ti ṣeyọri",
        "ig": "Ọ dị mma! Ị Gafere",
    },
    "keep_studying": {
        "en": "Keep Studying — You Can Do It",
        "ha": "Ci gaba da karatu — Zaku iya",
        "yo": "Máa ka kẹ́kọ̀ — O le ṣe é",
        "ig": "Nọgide na-amụ — Ị nwere ike",
    },
    "your_score": {
        "en": "Your Score",
        "ha": "Maki ku",
        "yo": "Àmì Rẹ",
        "ig": "Akara Gị",
    },
    "time_taken": {
        "en": "Time Taken",
        "ha": "Lokaci da ya ɗauka",
        "yo": "Àkókò Tí A Lò",
        "ig": "Oge Ewere",
    },
    "correct_answers": {
        "en": "Correct",
        "ha": "Daidai",
        "yo": "Tọ̀nà",
        "ig": "Ziri ezi",
    },
    "incorrect_answers": {
        "en": "Incorrect",
        "ha": "Ba daidai ba",
        "yo": "Àṣìṣe",
        "ig": "Ezughị ezi",
    },
    "skipped": {
        "en": "Skipped",
        "ha": "An tsallake",
        "yo": "Tí a fò",
        "ig": "Wepụrụ",
    },

    # ── Accessibility ───────────────────────────
    "enable_tts": {
        "en": "Enable Text-to-Speech",
        "ha": "Kunna Rubutu-zuwa-Magana",
        "yo": "Mú Ọ̀rọ̀-sí-Ọ̀rọ̀ ṣiṣẹ",
        "ig": "Mee ka Ederede-ka-Olu rụọ ọrụ",
    },
    "disable_tts": {
        "en": "Disable Text-to-Speech",
        "ha": "Kashe Rubutu-zuwa-Magana",
        "yo": "Pa Ọ̀rọ̀-sí-Ọ̀rọ̀ rọ",
        "ig": "Gbanyụọ Ederede-ka-Olu",
    },
    "large_text": {
        "en": "Large Text",
        "ha": "Babban Rubutu",
        "yo": "Ọ̀rọ̀ Ńlá",
        "ig": "Ederede Nke Uku",
    },
    "high_contrast": {
        "en": "High Contrast",
        "ha": "Tsananin Bambanci",
        "yo": "Ìyàtọ̀ Gíga",
        "ig": "Mgbagha Ike",
    },
    "keyboard_navigation": {
        "en": "Keyboard Navigation",
        "ha": "Kewayawa ta Keyboard",
        "yo": "Ìfilọ́ pẹ̀lú Kíbọọdù",
        "ig": "Ọgụgụ Keyboard",
    },
    "skip_to_content": {
        "en": "Skip to main content",
        "ha": "Tsallake zuwa abun ciki na farko",
        "yo": "Fò sí àkóónú àkọ́kọ́",
        "ig": "Wụfee gaa ọdịnaya bụ isi",
    },

    # ── Calibration ─────────────────────────────
    "calibration_title": {
        "en": "Face Calibration",
        "ha": "Daidaita Fuska",
        "yo": "Ìfọwọ́ Ojú",
        "ig": "Hazie Ihu",
    },
    "calibration_look_camera": {
        "en": "Look directly at the camera",
        "ha": "Duba kyamarar kai tsaye",
        "yo": "Wo kamẹra tààrà",
        "ig": "Lee mkpụrụ ọnụ n'anya",
    },
    "calibration_complete": {
        "en": "Calibration complete! Redirecting...",
        "ha": "Daidaitawa ya kammala! Ana juyawa...",
        "yo": "Ìfọwọ́ parí! Ń darí ọ̀...",
        "ig": "Nhazi dị mmá! Na-atụgharị...",
    },
    "calibration_failed": {
        "en": "Calibration failed. Please try again.",
        "ha": "Daidaitawa ya kasa. Da fatan za a sake gwadawa.",
        "yo": "Ìfọwọ́ kùnà. Jọwọ gbìyànjú lẹ́ẹ̀kan si.",
        "ig": "Nhazi dara ada. Biko nwaa ọzọ.",
    },

    # ── Common UI ───────────────────────────────
    "loading": {
        "en": "Loading...",
        "ha": "Ana lodi...",
        "yo": "Ń gbà...",
        "ig": "Na-abufe...",
    },
    "save_changes": {
        "en": "Save Changes",
        "ha": "Adana Canje-canje",
        "yo": "Fi Àwọn Ìyípadà Pamọ́",
        "ig": "Chekwaa Mgbanwe",
    },
    "cancel": {
        "en": "Cancel",
        "ha": "Soke",
        "yo": "Fagilé",
        "ig": "Kagbuo",
    },
    "confirm": {
        "en": "Confirm",
        "ha": "Tabbatar",
        "yo": "Jẹ́rìí",
        "ig": "Nkwenye",
    },
    "go_back": {
        "en": "Back",
        "ha": "Komawa",
        "yo": "Padà",
        "ig": "Laghachi",
    },
    "view": {
        "en": "View",
        "ha": "Duba",
        "yo": "Wo",
        "ig": "Lee",
    },
    "search": {
        "en": "Search",
        "ha": "Bincika",
        "yo": "Wá",
        "ig": "Chọọ",
    },
    "no_results": {
        "en": "No results found",
        "ha": "Ba a sami sakamako ba",
        "yo": "Kò sí àbájáde tí a rí",
        "ig": "Achọghị nsonaazụ ọ bụla",
    },

    # ── Error Messages ──────────────────────────
    "error_invalid_login": {
        "en": "Invalid email or password. Please try again.",
        "ha": "Imel ko kalmar sirri ba daidai ba. Da fatan za a sake gwadawa.",
        "yo": "Ímeèlì tàbí ọ̀rọ̀ aṣínà kò tọ̀nà. Jọwọ gbìyànjú lẹ́ẹ̀kan si.",
        "ig": "Email ma ọ bụ okwuntughe ezighi ezi. Biko nwaa ọzọ.",
    },
    "error_account_suspended": {
        "en": "Your account has been suspended. Contact admin.",
        "ha": "An dakatar da asusunku. Tuntubi admin.",
        "yo": "A ti dádúró akon rẹ. Kàn sí ẹlẹgbẹ́ alakoso.",
        "ig": "Kwụsịrị akaụntụ gị. Kpọtụrụ onye nlekọta.",
    },
    "error_session_expired": {
        "en": "Your exam session has expired.",
        "ha": "Lokacin jarabarku ya ƙare.",
        "yo": "Àkókò idanwo rẹ ti parí.",
        "ig": "Oge ule gị agwụla.",
    },
    "error_webcam_denied": {
        "en": "Camera access denied. This has been recorded.",
        "ha": "An hana samun damar kyamara. An yi rikodin wannan.",
        "yo": "Ìgbà àyè kamẹra kọ̀. Etipadà àlàyé rẹ̀.",
        "ig": "Akwụsị ohere mkpụrụ ọnụ. Edekọọla nke a.",
    },

    # ── Exam Rules ──────────────────────────────
    "rule_webcam_required": {
        "en": "Your face must be visible throughout the exam.",
        "ha": "Dole ne fuskarku ta kasance a bayyane a duk lokacin jaraba.",
        "yo": "Ojú rẹ gbọdọ̀ hàn jakejado idanwo náà.",
        "ig": "Ihu gị kwesịrị ịpụtara ìhè n'oge ule niile.",
    },
    "rule_no_tab_switch": {
        "en": "Switching tabs is monitored and may lead to disqualification.",
        "ha": "Ana sa ido a kan canza tabulomi kuma yana iya kai ga hukunci.",
        "yo": "Ìyípadà àkọlé ń ṣe àkóbẹ̀rẹ̀ tí ó lè jẹ ìyọkúrò.",
        "ig": "Na-elere mgbanwe taabụ anya ma ọ nwere ike ibu iwepu.",
    },
    "rule_server_timer": {
        "en": "The timer is tracked on our server. Refreshing will not grant extra time.",
        "ha": "Ana bin diddigin agogo a sabar mu. Sabuntawa ba zai ba da ƙarin lokaci ba.",
        "yo": "Wọ́n ń tọpasẹ̀ aago nínú ìpèsè wa. Ìmúsọdọ kò ní fún ní àkókò àfikún.",
        "ig": "Na-eso oge n'ihe nkwado anyị. Mweghachi agaghi enye oge ọzọ.",
    },
}

# BCP-47 locale codes for TTS speech synthesis
TTS_LOCALE_MAP = {
    "en": "en-NG",
    "ha": "ha",
    "yo": "yo",
    "ig": "ig",
}

SUPPORTED_LANGUAGES = {
    "en": "English",
    "ha": "Hausa",
    "yo": "Yorùbá",
    "ig": "Igbo",
}


# ══════════════════════════════════════════════
# TRANSLATION FUNCTIONS
# ══════════════════════════════════════════════

def get_lang() -> str:
    """
    Determine the current user's preferred language.

    Priority order:
      1. Authenticated user's saved preference (User.preferred_language)
      2. Session variable (set when user changes language in UI)
      3. Browser Accept-Language header (best effort)
      4. Default: 'en'

    Returns one of: 'en', 'ha', 'yo', 'ig'
    """
    # 1. Logged-in user preference
    try:
        if current_user.is_authenticated and current_user.preferred_language:
            lang = current_user.preferred_language
            if lang in SUPPORTED_LANGUAGES:
                return lang
    except RuntimeError:
        # Outside request context (e.g. during tests)
        pass

    # 2. Session override (user clicked language switcher)
    lang = session.get("language")
    if lang and lang in SUPPORTED_LANGUAGES:
        return lang

    # 3. Browser Accept-Language header
    try:
        accept = request.accept_languages
        for lang_code, _ in accept:
            # Match 'ha', 'ha-NE', 'yo', 'yo-NG', 'ig', 'en', 'en-US', etc.
            base = lang_code.split("-")[0].lower()
            if base in SUPPORTED_LANGUAGES:
                return base
    except RuntimeError:
        pass

    return "en"


def get_text(key: str, lang: str = None, **kwargs) -> str:
    """
    Return the translated string for a given key and language.

    Args:
        key:    Translation key (from TRANSLATIONS dict above)
        lang:   Language code. If None, auto-detects via get_lang()
        **kwargs: Format variables e.g. get_text('question_of', n=3, total=10)

    Returns:
        Translated string, or the English fallback, or the key itself
        if the key doesn't exist at all.

    Examples:
        get_text('login_title', 'ha')   → 'Shiga'
        get_text('question_of', 'yo', n=3, total=10)
            → 'Ìbéèrè 3 nínú 10'
        get_text('unknown_key')         → 'unknown_key'
    """
    if lang is None:
        lang = get_lang()

    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key  # Return key itself as a safe fallback

    # Get the string for the requested language, fall back to English
    text = entry.get(lang) or entry.get("en") or key

    # Apply format variables if any
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return text


def get_tts_locale(lang: str = None) -> str:
    """
    Return the BCP-47 locale code for speech synthesis.

    Args:
        lang: Language code. If None, auto-detects.

    Returns:
        BCP-47 locale string e.g. 'en-NG', 'ha', 'yo', 'ig'
    """
    if lang is None:
        lang = get_lang()
    return TTS_LOCALE_MAP.get(lang, "en-NG")


def get_all_translations_for_js(lang: str = None) -> dict:
    """
    Return ALL translation strings for a given language as a dict.
    Used to inject translations into JavaScript via a template variable,
    so the anti-cheat and exam JS can show localised messages without
    making extra server requests.

    Usage in base.html:
        <script>
        window.EduShieldLang = "{{ current_lang }}";
        window.EduShieldT = {{ translations_json }};
        </script>

    Usage in JavaScript:
        EduShieldT['tab_switch_warning']  // localised string
    """
    if lang is None:
        lang = get_lang()

    result = {}
    for key, translations in TRANSLATIONS.items():
        result[key] = translations.get(lang) or translations.get("en") or key
    return result
