from ollama_service import OllamaService

service = OllamaService()

print("=" * 60)
print("MODELOS ENCONTRADOS")
print("=" * 60)

for model in service.list_models():
    print(model)

print("=" * 60)

respuesta = service.generate(
    model="llama3.2:3b",
    system_prompt="Eres PandaIA. Responde en una sola línea.",
    prompt="Preséntate."
)

print(respuesta)