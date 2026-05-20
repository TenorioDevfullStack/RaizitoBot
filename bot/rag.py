import hashlib
import math
import re
import unicodedata


VECTOR_DIMENSIONS = 768

def embed_text(text):
    """
    Generate semantic embedding for a given text using Gemini API.
    """
    from bot.ai_service import get_gemini_embedding
    vector = get_gemini_embedding(text)
    if not vector:
        # Fallback to zero vector if API fails to prevent crashes
        return [0.0] * VECTOR_DIMENSIONS
    return vector


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
