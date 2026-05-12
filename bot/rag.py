import hashlib
import math
import re
import unicodedata


VECTOR_DIMENSIONS = 256
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "essa", "esse", "esta", "este", "eu", "foi", "me", "meu",
    "minha", "na", "nas", "no", "nos", "o", "os", "ou", "para", "por",
    "que", "se", "sem", "sobre", "sua", "um", "uma", "voce", "voce",
}


def normalize_text(text):
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def tokenize(text):
    tokens = [
        token
        for token in TOKEN_RE.findall(normalize_text(text))
        if token not in STOPWORDS
    ]
    bigrams = [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
    return tokens + bigrams


def embed_text(text, dimensions=VECTOR_DIMENSIONS):
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left, right):
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def chunk_text(text, max_chars=1200):
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text or "") if part.strip()]
    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for index in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[index:index + max_chars].strip())
            continue

        if current and len(current) + len(paragraph) + 2 > max_chars:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()

    if current:
        chunks.append(current.strip())
    return chunks
