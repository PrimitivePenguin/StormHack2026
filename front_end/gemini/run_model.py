import google.genai as genai
from dotenv import load_dotenv

load_dotenv()

def get_response(input_text, model = "gemini-3.5-flash-lite"):
    client = genai.Client()
    chat = client.chats.create(model=model)

    response = chat.send_message(input_text)
    
    return response.text