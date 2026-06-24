"""
tests/test_day6_accessibility.py — Day 6 Accessibility & i18n Tests
Run: python tests/test_day6_accessibility.py
"""
import sys, os, re, json, importlib.util

# Load translations module directly (no Flask dependency needed)
_spec = importlib.util.spec_from_file_location(
    'translations',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 'backend','utils','translations.py')
)
_mod = importlib.util.module_from_spec(_spec)

# Stub Flask before loading
class _Fake:
    def __getattr__(self, n): return lambda *a,**k: None
sys.modules.setdefault('flask', _Fake())
sys.modules.setdefault('flask_login', _Fake())

_spec.loader.exec_module(_mod)

TRANSLATIONS         = _mod.TRANSLATIONS
SUPPORTED_LANGUAGES  = _mod.SUPPORTED_LANGUAGES
TTS_LOCALE_MAP       = _mod.TTS_LOCALE_MAP

def get_text(k, lang='en', **kw):          return _mod.get_text(k, lang, **kw)
def get_tts_locale(l='en'):                return _mod.get_tts_locale(l)
def get_all_translations_for_js(l='en'):   return _mod.get_all_translations_for_js(l)

# ─────────────────────────────────────────────
passed = failed = 0
LANGS = list(SUPPORTED_LANGUAGES.keys())

def ok(name):   global passed; passed += 1; print(f"  ✓ {name}")
def fail(name, msg=""): global failed; failed += 1; print(f"  ✗ {name}: {msg}")
def run(name, condition, msg=""):
    if condition: ok(name)
    else: fail(name, msg or "assertion failed")

print("\n=== Day 6 Accessibility & i18n Tests ===\n")

# ── 1. Dictionary completeness ─────────────────────────────────────────────────
print("1. Translation Dictionary Completeness")
run("TRANSLATIONS is a non-empty dict", isinstance(TRANSLATIONS, dict) and len(TRANSLATIONS) > 0)
run("has at least 50 keys", len(TRANSLATIONS) >= 50)
run("SUPPORTED_LANGUAGES has 4 entries", set(LANGS) == {'en','ha','yo','ig'})

incomplete = [k for k,v in TRANSLATIONS.items() if not all(l in v for l in LANGS)]
run("all keys have all 4 languages", len(incomplete)==0, str(incomplete[:5]))

empty = [f"{k}.{l}" for k,v in TRANSLATIONS.items() for l,t in v.items()
         if not isinstance(t,str) or not t.strip()]
run("no empty translation values", len(empty)==0, str(empty[:5]))

# ── 2. get_text() fallback ─────────────────────────────────────────────────────
print("\n2. get_text() Fallback Behaviour")
run("en login_title → 'Sign In'",      get_text('login_title','en') == 'Sign In')
run("ha login_title → 'Shiga'",        get_text('login_title','ha') == 'Shiga')
run("yo login_title → 'Wọle'",         get_text('login_title','yo') == 'Wọle')
run("ig login_title → 'Banye'",        get_text('login_title','ig') == 'Banye')
run("missing key returns key itself",  get_text('nonexistent_key','en') == 'nonexistent_key')
run("unsupported lang falls back to en", get_text('login_title','fr') == 'Sign In')

# ── 3. Format variables ────────────────────────────────────────────────────────
print("\n3. Format Variable Substitution")
for lang in LANGS:
    r = get_text('question_of', lang, n=5, total=20)
    run(f"{lang}: question_of contains '5' and '20'", '5' in r and '20' in r, r)

run("missing format vars don't crash", isinstance(get_text('question_of','en'), str))

# ── 4. TTS Locale Mapping ──────────────────────────────────────────────────────
print("\n4. TTS Locale Mapping")
run("en → en-NG",  get_tts_locale('en') == 'en-NG')
run("ha → ha",     get_tts_locale('ha') == 'ha')
run("yo → yo",     get_tts_locale('yo') == 'yo')
run("ig → ig",     get_tts_locale('ig') == 'ig')
run("fr → en-NG",  get_tts_locale('fr') == 'en-NG')
run("all langs in TTS_LOCALE_MAP", all(l in TTS_LOCALE_MAP for l in LANGS))

# ── 5. BCP-47 locale format ────────────────────────────────────────────────────
print("\n5. BCP-47 Locale Format")
BCP47 = re.compile(r'^[a-z]{2}(-[A-Z]{2})?$')
for lang, locale in TTS_LOCALE_MAP.items():
    run(f"'{lang}' locale '{locale}' is valid BCP-47", bool(BCP47.match(locale)))

# ── 6. Supported language validation ──────────────────────────────────────────
print("\n6. Supported Language Validation")
for l in ['en','ha','yo','ig']:
    run(f"'{l}' is in SUPPORTED_LANGUAGES", l in SUPPORTED_LANGUAGES)
for l in ['fr','de','es','zh']:
    run(f"'{l}' is NOT in SUPPORTED_LANGUAGES", l not in SUPPORTED_LANGUAGES)
run("English name is 'English'", SUPPORTED_LANGUAGES.get('en') == 'English')

# ── 7. Format variable consistency across languages ────────────────────────────
print("\n7. Format Variable Consistency")
FMT = re.compile(r'\{(\w+)\}')
keys_with_fmt = {k: set(FMT.findall(v.get('en','')))
                 for k,v in TRANSLATIONS.items() if FMT.search(v.get('en',''))}
mismatches = []
for key, en_vars in keys_with_fmt.items():
    for lang in LANGS:
        lang_vars = set(FMT.findall(TRANSLATIONS[key].get(lang,'')))
        if en_vars != lang_vars:
            mismatches.append(f"{key}.{lang}")
run("format vars consistent across all languages",
    len(mismatches)==0, str(mismatches[:5]))

# ── 8. get_all_translations_for_js() ──────────────────────────────────────────
print("\n8. get_all_translations_for_js()")
all_en = get_all_translations_for_js('en')
run("returns dict",                    isinstance(all_en, dict))
run("has all keys",                    len(all_en) == len(TRANSLATIONS))
run("values are strings",              all(isinstance(v,str) for v in all_en.values()))
run("en login_title correct",          all_en.get('login_title') == 'Sign In')
all_ha = get_all_translations_for_js('ha')
run("ha login_title correct",          all_ha.get('login_title') == 'Shiga')
try:
    json.loads(json.dumps(all_en)); run("en translations serialize to JSON", True)
except: fail("en translations serialize to JSON")
try:
    json.loads(json.dumps(all_ha)); run("ha translations serialize to JSON", True)
except: fail("ha translations serialize to JSON")

# ── 9. Critical UI strings ─────────────────────────────────────────────────────
print("\n9. Critical UI Strings in All Languages")
CRITICAL = [
    'login_title','register_title','email_label','password_label',
    'start_exam_btn','submit_exam_btn','time_remaining',
    'tab_switch_warning','face_absent_warning','copy_blocked',
    'calibration_title','error_invalid_login','passed',
]
for key in CRITICAL:
    run(f"critical key '{key}' exists", key in TRANSLATIONS)
    if key in TRANSLATIONS:
        for lang in LANGS:
            run(f"  {key}.{lang} non-empty",
                bool(TRANSLATIONS[key].get(lang,'').strip()))

# ── 10. Accessibility storage keys ────────────────────────────────────────────
print("\n10. Accessibility Storage Key Format")
ACC_KEYS = ['edu-tts','edu-largefont','edu-highcontrast','edu-reducedmotion']
for k in ACC_KEYS:
    run(f"'{k}' follows edu- naming convention",
        k.startswith('edu-') and len(k) > 5)

# ── 11. Anti-cheat messages localised ─────────────────────────────────────────
print("\n11. Anti-Cheat Messages Are Localised")
AC_KEYS = ['tab_switch_warning','copy_blocked','right_click_blocked',
           'face_absent_warning','multiple_faces_warning','exam_auto_submitted']
for key in AC_KEYS:
    run(f"'{key}' localised in all languages",
        key in TRANSLATIONS and all(l in TRANSLATIONS[key] for l in LANGS))

# ── 12. TTS rate / language config sanity ─────────────────────────────────────
print("\n12. TTS Configuration Sanity")
run("Nigerian English locale is en-NG", TTS_LOCALE_MAP['en'] == 'en-NG')
run("Hausa locale is 'ha'",             TTS_LOCALE_MAP['ha'] == 'ha')
run("All TTS locales are strings",
    all(isinstance(v,str) for v in TTS_LOCALE_MAP.values()))
run("TTS_LOCALE_MAP has exactly 4 entries", len(TTS_LOCALE_MAP) == 4)

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL DAY 6 TESTS PASSED ✓")
else:
    print(f"FAILURES: {failed}")
sys.exit(0 if failed == 0 else 1)
