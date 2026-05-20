import os
import base64
import mimetypes
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _gemini_url(model=None):
    selected_model = model or GEMINI_MODEL
    return f"{GEMINI_API_BASE}/models/{selected_model}:generateContent"


def _extract_text(data):
    candidates = data.get("candidates", [])
    if not candidates:
        return "⚠️ Gemini did not return a response."

    parts = candidates[0].get("content", {}).get("parts", [])
    text_parts = [part.get("text", "") for part in parts if part.get("text")]
    return "\n".join(text_parts).strip() or "⚠️ Gemini returned an empty response."


def _request_gemini(contents, generation_config=None):
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API Key is missing. Please configure GEMINI_API_KEY in .env."

    payload = {"contents": contents}
    if generation_config:
        payload["generationConfig"] = generation_config

    try:
        response = requests.post(
            _gemini_url(),
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        return _extract_text(response.json())
    except requests.HTTPError as e:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            detail = response.text
        return f"Error communicating with Gemini AI: {detail}"
    except requests.RequestException as e:
        return f"Error communicating with Gemini AI: {str(e)}"


def _build_history_contents(history):
    contents = []
    if not history:
        return contents

    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role and content:
            gemini_role = "model" if role == "assistant" else "user"
            contents.append({
                "role": gemini_role,
                "parts": [{"text": content}],
            })
    return contents


def _image_part(image_data):
    if isinstance(image_data, bytes):
        image_bytes = image_data
    else:
        from io import BytesIO
        buffered = BytesIO()
        image_data.save(buffered, format="JPEG")
        image_bytes = buffered.getvalue()

    return {
        "inline_data": {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        }
    }


def get_gemini_response(prompt, image_parts=None, history=None, system_context=None):
    """
    Get response from Gemini with optional conversation history and images.
    """
    contents = _build_history_contents(history)
    user_prompt = prompt
    if system_context:
        user_prompt = (
            f"{system_context}\n\n"
            "Mensagem atual do usuario:\n"
            f"{prompt}"
        )

    parts = [{"text": user_prompt}]

    if image_parts:
        parts.extend(_image_part(image_data) for image_data in image_parts)

    contents.append({
        "role": "user",
        "parts": parts,
    })

    return _request_gemini(
        contents,
        generation_config={
            "temperature": 0.7,
            "maxOutputTokens": 1024,
            "topP": 1,
        },
    )

def analyze_image(image_data, prompt="Describe this image"):
    """
    Analyze an image using Gemini.
    """
    return get_gemini_response(prompt, [image_data])

def transcribe_audio(audio_file_path):
    """
    Transcribe audio using Gemini.
    """
    try:
        mime_type = mimetypes.guess_type(audio_file_path)[0] or "audio/ogg"
        with open(audio_file_path, "rb") as file:
            audio_data = base64.b64encode(file.read()).decode("utf-8")

        contents = [{
            "role": "user",
            "parts": [
                {"text": "Transcribe this audio in the same language. Return only the transcription."},
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": audio_data,
                    }
                },
            ],
        }]
        return _request_gemini(contents)
    except OSError as e:
        return f"Error transcribing audio: {str(e)}"

def get_gemini_embedding(text, model="text-embedding-004"):
    """
    Generate semantic embedding for a given text using Gemini.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is missing.")

    url = f"{GEMINI_API_BASE}/models/{model}:embedContent"
    payload = {
        "model": f"models/{model}",
        "content": {"parts": [{"text": text}]}
    }

    try:
        response = requests.post(
            url,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("embedding", {}).get("values", [])
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []
