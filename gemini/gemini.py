import google.genai as genai

client = genai.Client()
chat = client.chats.create(model="gemini-2.5-flash")

# First message
response = chat.send_message("Hi, I live in Seattle.")
print(response.text)

# Second message (Gemini remembers the context)
response = chat.send_message("What should I wear outside today?")
print(response.text)
