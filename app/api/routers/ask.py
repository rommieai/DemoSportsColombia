from fastapi import APIRouter
from openai import OpenAI
from app.core.config import get_settings
from app.schemas.io import AskPayload

router = APIRouter(tags=["ask"])

SYSTEM_PROMPT = (
    "Eres un comentarista deportivo especializado en la final del Mundial Qatar 2022 entre Argentina y Francia. "
    "Habla siempre en tiempo presente, como si el partido estuviera ocurriendo ahora mismo. "
    "Tus respuestas deben sonar emocionantes y narrativas, como un comentarista en vivo. "
    "Usa marcadores claros (por ejemplo, listas o subtítulos) para organizar la información. "
    "Devuelve SIEMPRE el contenido en formato HTML válido. "
    "Por ejemplo, si mencionas varios elementos, usa <ul> y <li> para listarlos, o <p> para párrafos. "
    "Limita cada respuesta a un máximo de 230 caracteres. "
    "Si te preguntan algo que no esté relacionado con la final Argentina vs Francia, "
    "responde educadamente indicando que solo tienes información sobre este partido."
)

@router.post("/ask")
def ask(payload: AskPayload):
    s = get_settings()
    client = OpenAI(api_key=s.OPENAI_API_KEY)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Idioma: {payload.lang or 'es'}.\nPregunta: {payload.prompt}"}
    ]
    resp = client.responses.create(model=s.OPENAI_MODEL_ID, input=messages)
    return {"answer": getattr(resp, "output_text", "No pude generar respuesta.")}
