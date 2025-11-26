import os
import base64
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = None

if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

def _build_history_messages(history):
    messages = []
    if not history:
        return messages

    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role and content:
            messages.append({"role": role, "content": content})
    return messages

def get_gemini_response(prompt, image_parts=None, history=None):
    """
    Get response from Groq (Llama 3) with optional conversation history.
    Kept function name 'get_gemini_response' for compatibility, but uses Groq.
    """
    if not client:
        return "⚠️ Groq API Key is missing. Please configure it in .env."

    try:
        messages = _build_history_messages(history)

        # Handle Image (Multimodal)
        if image_parts:
            image_data = image_parts[0]

            if isinstance(image_data, bytes):
                base64_image = base64.b64encode(image_data).decode('utf-8')
                image_url = f"data:image/jpeg;base64,{base64_image}"
            else:
                from io import BytesIO
                buffered = BytesIO()
                image_data.save(buffered, format="JPEG")
                base64_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
                image_url = f"data:image/jpeg;base64,{base64_image}"

            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            })
            model = "llama-3.2-11b-vision-preview"  # Vision model
        else:
            messages.append({
                "role": "user",
                "content": prompt
            })
            model = "llama-3.3-70b-versatile"  # Updated to latest supported model

        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
            top_p=1,
            stream=False,
            stop=None,
        )

        return completion.choices[0].message.content
    except Exception as e:
        return f"Error communicating with Groq AI: {str(e)}"

def analyze_image(image_data, prompt="Describe this image"):
    """
    Analyze an image using Groq.
    """
    # Pass image_data as a list to match the signature expected by get_gemini_response
    return get_gemini_response(prompt, [image_data])

def transcribe_audio(audio_file_path):
    """
    Transcribe audio using Groq Whisper.
    """
    if not client:
        return "⚠️ Groq API Key is missing."

    try:
        with open(audio_file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(audio_file_path), file.read()),
                model="whisper-large-v3",
                response_format="text"
            )
        return transcription
    except Exception as e:
        return f"Error transcribing audio: {str(e)}"
