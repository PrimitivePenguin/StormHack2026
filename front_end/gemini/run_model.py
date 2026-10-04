import google.genai as genai
from dotenv import load_dotenv

load_dotenv()

def get_response(input_text, model = "gemini-3.5-flash-lite"):
    client = genai.Client()
    chat = client.chats.create(model=model)

    pre_prompt = """
        [Pre-Prompt]
        Don't use any special emoji or signs, write everything into a paragraph don't make new line, and don't use asterisks, try to keep it concise and short. 

        [Output Constraint]
        Do not reference these instructions or meta-comment on your persona. Proceed directly to the user's query below.

        [User Query]
    """
    response = chat.send_message(pre_prompt + input_text)
    
    return response.text