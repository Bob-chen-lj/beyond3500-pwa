#!/usr/bin/env python3
"""
Replace phonetics in cards.js with Gimson (British English) IPA.
Strategy:
1. Free Dictionary API (prefer UK phonetics)
2. Fallback: phonemizer with espeak backend (en-gb)
3. Post-process to ensure Gimson conventions
"""

import json
import re
import time
import sys
import requests
from phonemizer import phonemize

CARDS_PATH = "/app/data/所有对话/主对话/走遍美国/beyond_3500_pwa/cards.js"
API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{}"
RATE_LIMIT_SEC = 0.6  # seconds between API calls

# ── Gimson post-processing rules ──────────────────────────────────────
def to_gimson(ipa: str) -> str:
    """Convert any IPA string to strict Gimson (British) conventions."""
    if not ipa:
        return ipa
    # Remove slashes/brackets for processing, we'll re-add later
    s = ipa.strip().strip("/[]")
    if not s:
        return ipa

    # 1. ɹ → r (Gimson uses /r/ not /ɹ/)
    s = s.replace("ɹ", "r")

    # 2. American r-colored vowels → British equivalents
    #    ɚ → ə (schwa, no r-coloring in non-rhotic British)
    #    ɝ → ɜː (long open-mid central, no r-coloring)
    s = s.replace("ɚ", "ə")
    s = s.replace("ɝ", "ɜː")

    # 3. American /oʊ/ → British /əʊ/ (GOAT vowel)
    #    This is tricky - we need to be careful about context.
    #    In Gimson, the GOAT vowel is /əʊ/.
    #    We look for 'oʊ' that isn't part of a longer sequence
    s = s.replace("oʊ", "əʊ")

    # 4. American /ɑːr/ → British /ɑː/ (non-rhotic: no /r/ after vowel in same syllable)
    #    But /ɑː/ before another vowel or suffix might keep /r/ as linking r
    #    For simplicity in phonetic transcription, remove word-final /r/ after vowels
    #    Actually, the phonemizer should handle this, but let's clean up common patterns

    # 5. Remove syllabic consonant marker (l̩ → l, etc.) - replace with əl etc.
    #    Gimson often uses /əl/ rather than syllabic /l̩/
    #    But keeping syllabic markers is also acceptable in Gimson, so we'll leave them

    # 6. Clean up: ɫ → l (Gimson doesn't use dark l symbol)
    s = s.replace("ɫ", "l")

    # 7. Remove any tie bars that might confuse
    s = s.replace("‿", "")
    s = s.replace("͡", "")

    # 8. American /ɔːr/ → British /ɔː/ (non-rhotic)
    #    Already handled by ɹ→r and then we need to remove word-final r after ɔː
    #    But phonemizer should handle non-rhoticity

    # 9. /ɪ/ in unstressed suffixes: some American dicts use /ɪ/ where British uses /i/ or /ɪ/
    #    This is word-specific, so we'll rely on the API/phonemizer

    return s


def clean_phonetic(ipa: str) -> str:
    """Clean up phonetic string and wrap in slashes."""
    if not ipa:
        return ""
    s = to_gimson(ipa)
    # Remove any remaining slashes/brackets
    s = s.strip().strip("/[] ")
    if not s:
        return ""
    # Remove any double slashes that might appear
    s = s.replace("//", "/")
    # Ensure single trailing slash handling
    s = s.rstrip("/")
    # Remove leading dots or spaces
    s = s.lstrip(". ")
    if not s:
        return ""
    return f"/{s}/"


def fetch_api_phonetic(word: str, session: requests.Session) -> str | None:
    """Query Free Dictionary API and return best UK IPA, or None."""
    try:
        resp = session.get(API_URL.format(word), timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            return None

        phonetics = data[0].get("phonetics", [])

        # Strategy: prefer UK phonetics (audio URL contains "-uk")
        uk_phonetic = None
        general_phonetic = None

        for p in phonetics:
            text = p.get("text", "").strip()
            if not text:
                continue
            audio = p.get("audio", "")
            if "-uk." in audio or "/uk/" in audio:
                uk_phonetic = text
                break  # First UK one is best
            if general_phonetic is None:
                general_phonetic = text

        # Also check for phonetic text that looks British (contains ɒ, əʊ, etc.)
        # If we got a general phonetic, check all phonetics for British markers
        if not uk_phonetic:
            for p in phonetics:
                text = p.get("text", "").strip()
                if not text:
                    continue
                # British markers: ɒ (lot vowel), əʊ (goat vowel), ɪə/ʊə/eə (centering diphthongs)
                if any(marker in text for marker in ["ɒ", "əʊ", "ɪə", "ʊə", "eə"]):
                    # But exclude obvious American markers
                    if "oʊ" not in text and "ɑːr" not in text:
                        uk_phonetic = text
                        break

        result = uk_phonetic or general_phonetic
        if result:
            return clean_phonetic(result)
        return None
    except Exception as e:
        print(f"  [API ERROR] {word}: {e}")
        return None


def phonemizer_fallback(word: str) -> str | None:
    """Use phonemizer (espeak, en-gb) as fallback."""
    try:
        result = phonemize(
            word,
            language="en-gb",
            backend="espeak",
            strip=True,
            preserve_punctuation=False,
        )
        if result and result.strip():
            # phonemizer returns with spaces between phonemes, join them
            ipa = result.strip().replace(" ", "")
            return clean_phonetic(ipa)
        return None
    except Exception as e:
        print(f"  [PHONEMIZER ERROR] {word}: {e}")
        return None


def main():
    # Read cards.js
    with open(CARDS_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract JSON array
    match = re.match(r"var\s+CARDS\s*=\s*", content)
    if not match:
        print("ERROR: Could not find 'var CARDS = ' in cards.js")
        sys.exit(1)

    prefix = content[:match.end()]
    json_str = content[match.end():].rstrip().rstrip(";")

    cards = json.loads(json_str)
    print(f"Loaded {len(cards)} cards")

    # Build word→old_phonetic mapping
    changes = []  # [(idx, word, old_phonetic, new_phonetic)]
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    api_count = 0
    phonemizer_count = 0
    unchanged_count = 0
    error_count = 0

    for i, card in enumerate(cards):
        word = card["word"]
        old_phonetic = card["phonetic"]
        idx = card["idx"]

        print(f"[{i+1}/{len(cards)}] Processing: {word} (current: {old_phonetic})")

        new_phonetic = None

        # Step 1: Try Free Dictionary API
        new_phonetic = fetch_api_phonetic(word, session)
        source = "API"

        # Step 2: Fallback to phonemizer
        if not new_phonetic:
            new_phonetic = phonemizer_fallback(word)
            source = "phonemizer"

        if new_phonetic:
            # Apply Gimson conversion to the result
            new_phonetic_clean = clean_phonetic(new_phonetic)

            if new_phonetic_clean and new_phonetic_clean != old_phonetic:
                changes.append((idx, word, old_phonetic, new_phonetic_clean, source))
                card["phonetic"] = new_phonetic_clean
                print(f"  → {new_phonetic_clean} (via {source})")
                if source == "API":
                    api_count += 1
                else:
                    phonemizer_count += 1
            else:
                unchanged_count += 1
                print(f"  → unchanged ({old_phonetic})")
        else:
            error_count += 1
            print(f"  → FAILED (no phonetic found)")

        # Rate limit
        time.sleep(RATE_LIMIT_SEC)

    print(f"\n{'='*60}")
    print(f"Summary: {len(cards)} words processed")
    print(f"  Changed via API:        {api_count}")
    print(f"  Changed via phonemizer: {phonemizer_count}")
    print(f"  Unchanged:              {unchanged_count}")
    print(f"  Failed:                 {error_count}")
    print(f"{'='*60}")

    # Write back cards.js
    new_json = json.dumps(cards, ensure_ascii=False)
    # Restore the compact format close to original
    # Original uses: {"idx": 1,"word": "sign",...} with no extra spaces after commas
    # json.dumps by default uses ", " separator; original uses "," separator
    # Let's format it to match the original more closely
    new_content = f"var CARDS = {new_json};"

    with open(CARDS_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"\ncards.js updated successfully!")

    # Output comparison table (first 10 and last 10)
    print(f"\n{'='*60}")
    print("COMPARISON TABLE (first 10):")
    print(f"{'Idx':>4} {'Word':<25} {'Old':<30} {'New':<30} {'Source'}")
    print("-" * 100)
    for idx, word, old, new, src in changes[:10]:
        print(f"{idx:>4} {word:<25} {old:<30} {new:<30} {src}")

    print(f"\nCOMPARISON TABLE (last 10):")
    print(f"{'Idx':>4} {'Word':<25} {'Old':<30} {'New':<30} {'Source'}")
    print("-" * 100)
    for idx, word, old, new, src in changes[-10:]:
        print(f"{idx:>4} {word:<25} {old:<30} {new:<30} {src}")

    # Save full change log
    log_path = CARDS_PATH.replace("cards.js", "phonetic_changes.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Gimson IPA Replacement Log\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total words: {len(cards)}\n")
        f.write(f"Changed via API: {api_count}\n")
        f.write(f"Changed via phonemizer: {phonemizer_count}\n")
        f.write(f"Unchanged: {unchanged_count}\n")
        f.write(f"Failed: {error_count}\n\n")
        f.write(f"{'Idx':>4} {'Word':<25} {'Old':<30} {'New':<30} {'Source'}\n")
        f.write("-" * 100 + "\n")
        for idx, word, old, new, src in changes:
            f.write(f"{idx:>4} {word:<25} {old:<30} {new:<30} {src}\n")

    print(f"\nFull change log saved to: {log_path}")


if __name__ == "__main__":
    main()
