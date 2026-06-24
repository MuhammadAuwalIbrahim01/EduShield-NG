from .security import (
    sanitize_input,
    is_safe_redirect_url,
    get_safe_next_url,
    generate_token,
    require_role,
    log_security_event,
    log_security_event_with_evidence,
    validate_exam_session_token,
    check_password_strength,
)
from .translations import (
    get_text,
    get_lang,
    get_tts_locale,
    get_all_translations_for_js,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    TTS_LOCALE_MAP,
)
