import re

WORD_RE = re.compile(r"[^\W\d_]+(?:[’'\-][^\W\d_]+)*|\d+", re.UNICODE)
START_RE = re.compile(r"^[ \t]*\*\*\* START OF.*\*\*\*[ \t\r]*$", re.MULTILINE)
END_RE = re.compile(r"^[ \t]*\*\*\* END OF.*\*\*\*[ \t\r]*$", re.MULTILINE)


def extract_body(raw_text):
    start_match = START_RE.search(raw_text)
    end_match = END_RE.search(raw_text)
    if not start_match or not end_match:
        raise ValueError("Project Gutenberg start/end markers not found")
    start = start_match.end()
    end = end_match.start()
    while start < end and raw_text[start].isspace():
        start += 1
    while end > start and raw_text[end - 1].isspace():
        end -= 1
    return raw_text[start:end], start, end


def segment_text(text, work_id, target_words=350, min_words=80):
    words = list(WORD_RE.finditer(text))
    if not words:
        return []
    ranges = []
    start = 0
    while start < len(words):
        end = min(start + target_words, len(words))
        ranges.append([start, end])
        start = end
    if len(ranges) > 1 and ranges[-1][1] - ranges[-1][0] < min_words:
        ranges[-2][1] = ranges[-1][1]
        ranges.pop()
    passages = []
    for index, (start, end) in enumerate(ranges):
        first = words[start]
        last = words[end - 1]
        passages.append({
            "passage_id": f"{work_id}:p{index:06d}",
            "work_id": work_id,
            "passage_index": index,
            "body_word_start": start,
            "body_word_end": end,
            "body_char_start": first.start(),
            "body_char_end": last.end(),
            "word_count": end - start,
            "text": text[first.start():last.end()],
        })
    return passages
