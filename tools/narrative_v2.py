import re

from text_pipeline import WORD_RE

SECTION_RE = re.compile(
    r"^[ \t]*(?:CHAPTER|CANTO|BOOK|HYMN|SURA|SECTION|PART|STORY|FIT|RUNE|ADHYAYA|PARVA|FABLE|TALE|LEGEND|MYTH|INTRODUCTION|PREFACE|INDEX|CONTENTS|BIBLIOGRAPHY|APPENDIX|NOTES|GLOSSARY|ADVERTISEMENT|EDITORIAL|TRANSLATOR)\b[^\n]{0,160}$",
    re.IGNORECASE | re.MULTILINE,
)
NUMBERED_HEADING_RE = re.compile(r"^[ \t]*(?:[IVXLCDM]+|\d+)[.)]?[ \t]+[A-Z][^\n]{3,120}$", re.MULTILINE)
EXCLUDED_HEADING_RE = re.compile(r"^(?:INTRODUCTION|PREFACE|INDEX|CONTENTS|BIBLIOGRAPHY|APPENDIX|NOTES|GLOSSARY|ADVERTISEMENT|EDITORIAL|TRANSLATOR)", re.IGNORECASE)


def classify_passage(text, heading=""):
    flags = []
    excluded = False
    prefix = " ".join(text.split()[:70])
    prefix_lower = prefix.lower()
    words = list(WORD_RE.finditer(text))
    numeric_ratio = sum(match.group(0).isdigit() for match in words) / max(1, len(words))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    index_lines = sum(bool(re.search(r"(?:\d+|[IVXLCDM]+)[,.]?\s*(?:\d+[-–, ]*)*$", line)) for line in lines)

    if EXCLUDED_HEADING_RE.search(heading.strip()):
        flags.append("excluded_heading_" + heading.strip().split()[0].lower())
        excluded = True
    if any(term in prefix_lower for term in ["project gutenberg", "transcriber's note", "transcriber’s note", "post 8vo", "publisher's catalogue", "publisher’s catalogue"]):
        flags.append("publisher_or_transcriber_apparatus")
        excluded = True
    if numeric_ratio > 0.12 and ("index" in prefix_lower or index_lines >= max(4, len(lines) // 3)):
        flags.append("index_or_numeric_apparatus")
        excluded = True
    if "contents" in prefix_lower and len(lines) >= 8 and sum(len(line) < 90 for line in lines) / len(lines) > 0.8:
        flags.append("contents_apparatus")
        excluded = True
    if any(term in prefix_lower for term in ["selected bibliography", "recommended reading", "list of illustrations", "list of books"]):
        flags.append("bibliographic_apparatus")
        excluded = True
    if re.search(r"\bcompare (?:this|these|the)\b", prefix_lower) and re.search(r"\bpage\s+\d+\b|\bpage\s+[ivxlcdm]+\b", prefix_lower):
        flags.append("editorial_comparison")
        excluded = True
    if not flags:
        flags.append("unclassified_source_text")
    return flags, excluded


def heading_spans(text):
    matches = list(SECTION_RE.finditer(text)) + list(NUMBERED_HEADING_RE.finditer(text))
    matches = sorted(matches, key=lambda match: (match.start(), -match.end()))
    selected = []
    for match in matches:
        if selected and match.start() < selected[-1].end():
            continue
        if selected and match.start() - selected[-1].start() < 80:
            continue
        selected.append(match)
    spans = []
    if not selected:
        return [("", 0, len(text))]
    if selected[0].start() > 0:
        spans.append(("", 0, selected[0].start()))
    for index, match in enumerate(selected):
        end = selected[index + 1].start() if index + 1 < len(selected) else len(text)
        heading = match.group(0).strip()
        spans.append((heading, match.start(), end))
    return spans


def segment_section(text, work_id, section_index, heading, start, end, target_words=450, min_words=60):
    words = list(WORD_RE.finditer(text, start, end))
    if not words:
        return []
    ranges = []
    word_start = 0
    while word_start < len(words):
        word_end = min(word_start + target_words, len(words))
        ranges.append([word_start, word_end])
        word_start = word_end
    if len(ranges) > 1 and ranges[-1][1] - ranges[-1][0] < min_words:
        ranges[-2][1] = ranges[-1][1]
        ranges.pop()
    passages = []
    for passage_index, (word_start, word_end) in enumerate(ranges):
        first = words[word_start]
        last = words[word_end - 1]
        passage_text = text[first.start():last.end()]
        flags, excluded = classify_passage(passage_text, heading)
        passages.append({
            "passage_id": f"{work_id}:s{section_index:04d}:p{passage_index:03d}",
            "work_id": work_id,
            "section_index": section_index,
            "section_heading": heading,
            "passage_index": passage_index,
            "body_char_start": first.start(),
            "body_char_end": last.end(),
            "word_count": word_end - word_start,
            "text": passage_text,
            "content_flags": flags,
            "eligible_for_similarity": not excluded and word_end - word_start >= min_words,
            "exclusion_reason": "|".join(flag for flag in flags if flag != "unclassified_source_text") if excluded else None,
        })
    return passages


def segment_narrative(text, work_id):
    passages = []
    for section_index, (heading, start, end) in enumerate(heading_spans(text)):
        passages.extend(segment_section(text, work_id, section_index, heading, start, end))
    return passages
