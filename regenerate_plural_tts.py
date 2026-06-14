#!/usr/bin/env python3
"""
Regenerate TTS audio for 55 plural words in beyond_3500 PWA.
Uses edge-tts (en-US-GuyNeural) to generate correct plural pronunciation,
replaces the old Cambridge Dictionary audio (which was singular pronunciation),
and updates cards.js isDict flags.
"""

import asyncio
import base64
import json
import os
import re
import subprocess
import sys

# ===== Configuration =====
PROJECT_DIR = "/app/data/所有对话/主对话/走遍美国/beyond_3500_pwa"
TMP_DIR = "/tmp/plural_tts"
VOICE = "en-US-GuyNeural"
CONCURRENCY = 5

# 55 plural words: (idx, word, origIdx, key, page)
PLURAL_WORDS = [
    (32, "scoops", 31, "w31", 3),
    (39, "programs", 38, "w38", 3),
    (46, "fliers", 45, "w45", 4),
    (49, "potatoes", 48, "w48", 4),
    (57, "tonsils", 56, "w56", 4),
    (58, "flavors", 57, "w57", 4),
    (62, "footsteps", 61, "w61", 5),
    (64, "crabs", 63, "w63", 5),
    (65, "payments", 64, "w64", 5),
    (69, "guys", 68, "w68", 5),
    (84, "fellas", 83, "w83", 6),
    (89, "ladders", 88, "w88", 6),
    (90, "items", 89, "w89", 6),
    (93, "parades", 92, "w92", 7),
    (94, "savings", 93, "w93", 7),
    (107, "sunrises", 106, "w106", 8),
    (110, "tomatoes", 109, "w109", 8),
    (112, "cucumbers", 111, "w111", 8),
    (118, "indians", 117, "w117", 8),
    (126, "lovers", 125, "w125", 9),
    (128, "dwarfs", 127, "w127", 9),
    (132, "victors", 131, "w131", 9),
    (135, "heroes", 134, "w134", 9),
    (136, "players", 135, "w135", 10),
    (138, "editorials", 137, "w137", 10),
    (147, "details", 146, "w146", 10),
    (148, "stocks", 147, "w147", 10),
    (150, "sketches", 149, "w149", 10),
    (154, "malls", 153, "w153", 11),
    (157, "opportunities", 156, "w156", 11),
    (179, "patches", 178, "w178", 12),
    (180, "compliments", 179, "w179", 12),
    (181, "hotcakes", 180, "w180", 13),
    (185, "cloves", 184, "w184", 13),
    (200, "landmarks", 199, "w199", 14),
    (202, "mimes", 201, "w201", 14),
    (203, "dancers", 202, "w202", 14),
    (205, "polls", 204, "w204", 14),
    (209, "lockers", 208, "w208", 14),
    (210, "fixtures", 209, "w209", 14),
    (211, "hallways", 210, "w210", 15),
    (216, "voters", 215, "w215", 15),
    (220, "residents", 219, "w219", 15),
    (222, "pearls", 221, "w221", 15),
    (223, "jitters", 222, "w222", 15),
    (244, "careers", 243, "w243", 17),
    (248, "fittings", 247, "w247", 17),
    (260, "furnishings", 259, "w259", 18),
    (262, "funds", 261, "w261", 18),
    (267, "fractures", 266, "w266", 18),
    (270, "examinations", 269, "w269", 18),
    (288, "bankers", 287, "w287", 20),
    (289, "vendors", 288, "w288", 20),
    (293, "tiles", 292, "w292", 20),
    (295, "manufactures", 294, "w294", 20),
]


async def generate_tts(word, output_path, semaphore):
    """Generate TTS audio for a word using edge-tts."""
    import edge_tts

    async with semaphore:
        try:
            communicate = edge_tts.Communicate(word, VOICE)
            await communicate.save(output_path)
            # Verify the file was created and has content
            size = os.path.getsize(output_path)
            if size < 100:
                print(f"[WARN] TTS for '{word}' is too small ({size} bytes), may be corrupted")
                return False
            print(f"[OK] Generated TTS for '{word}' -> {output_path} ({size} bytes)")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to generate TTS for '{word}': {e}")
            return False


async def generate_all_tts():
    """Generate TTS for all 55 plural words concurrently."""
    import edge_tts  # ensure import at top level

    os.makedirs(TMP_DIR, exist_ok=True)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    tasks = []
    for idx, word, orig_idx, key, page in PLURAL_WORDS:
        output_path = os.path.join(TMP_DIR, f"{key}_{word}.mp3")
        tasks.append(generate_tts(word, output_path, semaphore))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    success_count = sum(1 for r in results if r is True)
    fail_count = sum(1 for r in results if r is not True)

    print(f"\n[SUMMARY] TTS generation: {success_count} success, {fail_count} failed")

    if fail_count > 0:
        print("[WARN] Some TTS generations failed. Retrying failed ones...")
        # Retry failed ones
        for i, (idx, word, orig_idx, key, page) in enumerate(PLURAL_WORDS):
            if results[i] is not True:
                output_path = os.path.join(TMP_DIR, f"{key}_{word}.mp3")
                print(f"[RETRY] Retrying '{word}'...")
                try:
                    communicate = edge_tts.Communicate(word, VOICE)
                    await communicate.save(output_path)
                    size = os.path.getsize(output_path)
                    if size >= 100:
                        results[i] = True
                        print(f"[RETRY OK] '{word}' -> {size} bytes")
                    else:
                        print(f"[RETRY FAIL] '{word}' still too small ({size} bytes)")
                except Exception as e:
                    print(f"[RETRY FAIL] '{word}': {e}")

    return all(r is True for r in results)


def mp3_to_base64(filepath):
    """Read an MP3 file and return its base64 encoded string."""
    with open(filepath, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8")


def replace_waud_entry(filepath, key, new_b64):
    """Replace a specific waud entry in a waud_pN.js file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Pattern: waud["w31"]="...base64...";
    pattern = rf'(waud\["{key}"\]=")[^"]*(")'
    match = re.search(pattern, content)
    if not match:
        print(f"[ERROR] Key '{key}' not found in {filepath}")
        return False

    new_content = re.sub(pattern, rf'\g<1>{new_b64}\g<2>', content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return True


def update_cards_isdict():
    """Update cards.js: set isDict=False for the 55 plural words."""
    filepath = os.path.join(PROJECT_DIR, "cards.js")

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse the CARDS array from the JS file
    # Format: var CARDS = [{...},{...},...];
    match = re.search(r'var CARDS = (\[.*\]);', content, re.DOTALL)
    if not match:
        print("[ERROR] Could not parse CARDS from cards.js")
        return False

    cards_json = match.group(1)
    cards = json.loads(cards_json)

    # Build set of idx values for our 55 words
    plural_idxs = {item[0] for item in PLURAL_WORDS}

    updated_count = 0
    for card in cards:
        if card["idx"] in plural_idxs and card.get("isDict") is True:
            card["isDict"] = False
            updated_count += 1

    print(f"[INFO] Updated isDict for {updated_count} cards in cards.js")

    # Write back
    new_json = json.dumps(cards, ensure_ascii=False, separators=(",", ":"))
    new_content = f"var CARDS = {new_json};"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

    return updated_count == len(plural_idxs)


def verify_replacements():
    """Verify all 55 keys have been properly replaced in waud files."""
    results = []
    for idx, word, orig_idx, key, page in PLURAL_WORDS:
        filepath = os.path.join(PROJECT_DIR, f"waud_p{page}.js")
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Find the entry
        pattern = rf'waud\["{key}"\]="([^"]*)"'
        match = re.search(pattern, content)
        if not match:
            results.append((key, word, "NOT_FOUND", 0))
            continue

        b64_value = match.group(1)
        # Decode and check size
        try:
            audio_data = base64.b64decode(b64_value)
            size = len(audio_data)
            results.append((key, word, "OK", size))
        except Exception as e:
            results.append((key, word, f"DECODE_ERROR: {e}", 0))

    print("\n===== VERIFICATION RESULTS =====")
    ok_count = 0
    for key, word, status, size in results:
        marker = "✓" if status == "OK" and size > 500 else "✗"
        if status == "OK" and size > 500:
            ok_count += 1
        print(f"  {marker} {key} ({word}): {status}, size={size} bytes")

    print(f"\n  Total: {ok_count}/{len(PLURAL_WORDS)} verified OK")
    return ok_count == len(PLURAL_WORDS)


async def main():
    print("=" * 60)
    print("Plural TTS Regeneration for beyond_3500 PWA")
    print("=" * 60)
    print(f"Words: {len(PLURAL_WORDS)}")
    print(f"Voice: {VOICE}")
    print(f"Concurrency: {CONCURRENCY}")
    print()

    # Step 1: Generate TTS audio for all 55 words
    print("[STEP 1] Generating TTS audio...")
    all_ok = await generate_all_tts()
    if not all_ok:
        print("[WARN] Not all TTS generations succeeded, continuing anyway...")

    # Step 2: Convert to base64 and replace in waud files
    print("\n[STEP 2] Converting to base64 and replacing waud entries...")
    replaced_count = 0
    failed_replacements = []

    for idx, word, orig_idx, key, page in PLURAL_WORDS:
        mp3_path = os.path.join(TMP_DIR, f"{key}_{word}.mp3")

        if not os.path.exists(mp3_path):
            print(f"[ERROR] MP3 file not found for '{word}': {mp3_path}")
            failed_replacements.append((key, word, "MP3_NOT_FOUND"))
            continue

        b64_str = mp3_to_base64(mp3_path)
        waud_path = os.path.join(PROJECT_DIR, f"waud_p{page}.js")

        if replace_waud_entry(waud_path, key, b64_str):
            replaced_count += 1
            print(f"  [OK] Replaced {key} ({word}) in waud_p{page}.js (b64 len={len(b64_str)})")
        else:
            failed_replacements.append((key, word, "REPLACE_FAILED"))

    print(f"\n[SUMMARY] Replaced {replaced_count}/{len(PLURAL_WORDS)} entries")
    if failed_replacements:
        print("[FAILURES]:")
        for key, word, reason in failed_replacements:
            print(f"  {key} ({word}): {reason}")

    # Step 3: Update cards.js isDict flags
    print("\n[STEP 3] Updating cards.js isDict flags...")
    cards_ok = update_cards_isdict()
    if cards_ok:
        print("[OK] All 55 cards updated to isDict=False")
    else:
        print("[WARN] Not all cards were updated in cards.js")

    # Step 4: Verify replacements
    print("\n[STEP 4] Verifying all replacements...")
    verify_ok = verify_replacements()

    print("\n" + "=" * 60)
    if verify_ok and replaced_count == len(PLURAL_WORDS) and cards_ok:
        print("ALL DONE: 55 plural words successfully processed!")
    else:
        print(f"COMPLETED WITH ISSUES: replaced={replaced_count}, cards_ok={cards_ok}, verify_ok={verify_ok}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
