"""Local OCR of weekday-column timetables. Results are drafts, never saved here."""
import csv
import io
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from app.timetable import Lesson

DAY_NAMES = {"montag": 0, "mo": 0, "dienstag": 1, "di": 1, "mittwoch": 2, "mi": 2,
             "donnerstag": 3, "do": 3, "freitag": 4, "fr": 4, "samstag": 5, "sa": 5, "sonntag": 6, "so": 6}
TIMES = re.compile(r"(?<!\d)([0-2]?\d)[:.]([0-5]\d)(?!\d)")


def parse_tsv(tsv: str) -> tuple[list[dict], str]:
    words = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not row.get("text", "").strip():
            continue
        words.append({"text": row["text"].strip(), "x": int(row["left"]), "y": int(row["top"]),
                      "w": int(row["width"]), "h": int(row["height"])})
    text = "\n".join(" ".join(w["text"] for w in sorted(line, key=lambda x: x["x"])) for line in lines(words))
    candidates = [w for w in words if w["text"].lower().strip(".:") in DAY_NAMES]
    # Pick a horizontal weekday header. Scattered weekday mentions are not a table.
    headers = max((line for line in lines(candidates)), key=len, default=[])
    headers.sort(key=lambda w: w["x"])
    if len(headers) < 2 or len({DAY_NAMES[w["text"].lower().strip('.:')] for w in headers}) != len(headers):
        return [], text
    centers = [w["x"] + w["w"] / 2 for w in headers]
    spacing = min(b-a for a, b in zip(centers, centers[1:]))
    left = centers[0] - spacing / 2
    header_bottom = max(w["y"] + w["h"] for w in headers)
    time_words = [w for w in words if w["x"] + w["w"] / 2 < left and w["y"] > header_bottom]
    rows = []
    # Time ranges may be on one line or two stacked lines in the first column.
    pending = None
    for line in lines(time_words):
        found = TIMES.findall(" ".join(w["text"] for w in sorted(line, key=lambda w:w["x"])))
        found = [f"{int(h):02d}:{m}" for h, m in found if int(h) < 24]
        y = min(w["y"] for w in line)
        if len(found) >= 2:
            rows.append((y, found[0], found[1])); pending = None
        elif len(found) == 1:
            if pending:
                rows.append((pending[0], pending[1], found[0])); pending = None
            else:
                pending = (y, found[0])
    lessons = []
    for i, (y, start, end) in enumerate(rows):
        bottom = rows[i+1][0] - 6 if i+1 < len(rows) else y + (rows[i][0]-rows[i-1][0] if i else 65)
        for col, header in enumerate(headers):
            lo = left if col == 0 else (centers[col-1] + centers[col]) / 2
            hi = (centers[col] + centers[col+1]) / 2 if col+1 < len(headers) else centers[col] + spacing / 2
            cell = [w for w in words if lo <= w["x"] + w["w"]/2 < hi and max(header_bottom, y-6) <= w["y"] < bottom]
            subject = " ".join(w["text"] for line in lines(cell) for w in sorted(line, key=lambda w:w["x"]))
            if not subject or subject.lower().strip("-– ") in {"", "pause", "mittagspause", "frei"}:
                continue
            try:
                lessons.append(Lesson(weekday=DAY_NAMES[header["text"].lower().strip('.:')], start=start, end=end, subject=subject).model_dump())
            except ValueError:
                continue
    return lessons, text


def lines(words):
    result = []
    for word in sorted(words, key=lambda w: (w["y"]+w["h"]/2, w["x"])):
        center = word["y"] + word["h"]/2
        if result and abs(center - (result[-1][0]["y"] + result[-1][0]["h"]/2)) <= max(5, word["h"] * .6):
            result[-1].append(word)
        else:
            result.append([word])
    return result


def analyze_upload(content: bytes) -> dict:
    is_pdf = content.startswith(b"%PDF-")
    is_image = content.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")) or (content.startswith(b"RIFF") and content[8:12] == b"WEBP")
    if not is_pdf and not is_image:
        raise ValueError("Bitte eine PDF-, PNG-, JPEG- oder WebP-Datei hochladen")
    if not shutil.which("tesseract") or (is_pdf and not shutil.which("pdftoppm")):
        raise RuntimeError("Für die lokale Erkennung fehlen Serverpakete: tesseract-ocr, tesseract-ocr-deu und poppler-utils. Manuelle Bearbeitung ist weiterhin möglich.")
    def run(args):
        try:
            return subprocess.run(args, check=True, timeout=40, capture_output=True).stdout.decode("utf-8", errors="replace")
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError("Die Datei konnte nicht gelesen werden. Bitte ein gut lesbares Bild oder eine unverschlüsselte PDF mit höchstens 3 Seiten verwenden.") from exc
    with TemporaryDirectory(prefix="familienplan-timetable-") as directory:
        source = Path(directory) / ("source.pdf" if is_pdf else "source.image")
        source.write_bytes(content)
        if is_pdf:
            info = run(["pdfinfo", str(source)])
            pages = re.search(r"^Pages:\s+(\d+)", info, re.M)
            if not pages or int(pages[1]) > 3:
                raise ValueError("Bitte höchstens 3 PDF-Seiten hochladen")
            run(["pdftoppm", "-r", "130", "-scale-to", "2400", "-png", str(source), str(Path(directory)/"page")])
            images = sorted(Path(directory).glob("page-*.png"))
        else:
            images = [source]
        lessons, extracted = [], []
        for image in images:
            tsv = run(["tesseract", str(image), "stdout", "-l", "deu+eng", "--psm", "6", "tsv"])
            found, text = parse_tsv(tsv)
            lessons.extend(found); extracted.append(text)
        # Multiple pages may repeat the same table.
        lessons = list({(x["weekday"], x["start"], x["end"], x["subject"]): x for x in lessons}.values())[:150]
        return {"lessons": lessons, "extractedText": "\n\n".join(extracted)[:30000],
                "message": "Bitte alle Fächer, Wochentage und Zeiten prüfen. Raum und Lehrkraft bei Bedarf aus dem Fachtext übernehmen."
                if lessons else "Keine eindeutige Tabelle erkannt. Bitte die Stunden anhand der Vorschau manuell ergänzen. Es wurde nichts gespeichert."}
