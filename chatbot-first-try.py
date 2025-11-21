import os
import glob
import datetime
import sys
import urllib.parse
import uuid
from typing import List, Optional
from contextlib import asynccontextmanager

# --- 1. IMPORTS ---
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_message_histories import ChatMessageHistory

# --- 2. CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

GENAI_API_KEY = os.getenv("GENAI_API_KEY")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "internship_db")

if DB_HOST and DB_HOST.startswith("@"):
    DB_HOST = DB_HOST.replace("@", "")
ENCODED_PASSWORD = urllib.parse.quote_plus(DB_PASSWORD)

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{ENCODED_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")
DATA_DIR = os.path.join(BASE_DIR, "internship-dataset")

vectorstore = None
llm = None
session_store = {}
db_engine = None

# --- 3. LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🐍 Python: {sys.executable}")
    init_db_engine()
    load_and_process_documents()
    setup_chain()
    yield
    print("🛑 Server shutting down...")

app = FastAPI(title="Internship Chatbot API (Null User Fix)", version="3.1.0", lifespan=lifespan)

# --- 4. MODELS (ĐÃ SỬA USER_ID THÀNH OPTIONAL) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",    # React default
        "http://localhost:5173",    # Vite default
        "http://localhost:5174",    # Vite alternative
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    # Cho phép user_id là null (None). Mặc định là None.
    user_id: Optional[int] = None 
    conversation_id: Optional[str] = None 
    question: str

class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: List[str]

# --- 5. DATABASE HELPERS ---
def init_db_engine():
    global db_engine
    try:
        db_engine = create_engine(DATABASE_URL, pool_recycle=3600)
        with db_engine.connect() as connection:
            print("✅ MySQL Connection: OK")
    except Exception as e:
        print(f"❌ MySQL Connection Failed: {e}")
        db_engine = None

def save_chat_history(user_id: Optional[int], conversation_id: str, user_request: str, gemini_response: str):
    if not db_engine: return
    
    # XỬ LÝ AN TOÀN: Nếu user_id là None, lưu là 0 (để tránh lỗi DB nếu cột đó NOT NULL)
    # Nếu DB của bạn cho phép NULL, bạn có thể thay số 0 bằng None
    safe_user_id = user_id if user_id is not None else 0

    query = text("""
        INSERT INTO chat_history (user_id, conversation_id, user_request, gemini_response, created_at)
        VALUES (:uid, :cid, :req, :res, :time)
    """)
    try:
        with db_engine.connect() as conn:
            conn.execute(query, {
                "uid": safe_user_id, 
                "cid": conversation_id, 
                "req": user_request,
                "res": gemini_response, 
                "time": datetime.datetime.now()
            })
            conn.commit()
            print(f"💾 Saved log for User {safe_user_id} / Session: {conversation_id}")
    except Exception as e:
        print(f"❌ DB Save Error: {e}")

# --- 6. RAG LOGIC ---
def get_session_history(session_id: str):
    if session_id not in session_store:
        session_store[session_id] = ChatMessageHistory()
    return session_store[session_id]

def load_and_process_documents():
    global vectorstore
    if not GENAI_API_KEY: return

    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=GENAI_API_KEY)

    if os.path.exists(VECTOR_DB_DIR) and os.path.isdir(VECTOR_DB_DIR) and os.listdir(VECTOR_DB_DIR):
        print("📂 Loading VectorStore...")
        try:
            vectorstore = Chroma(persist_directory=VECTOR_DB_DIR, embedding_function=embeddings)
        except Exception:
            vectorstore = None
    else:
        print("🚀 Creating VectorStore...")
        documents = []
        if not os.path.exists(DATA_DIR): return

        files = []
        for ext in ["*.txt", "*.md"]:
            files.extend(glob.glob(os.path.join(DATA_DIR, "**", ext), recursive=True))
        
        for f in files:
            try:
                loader = TextLoader(f, encoding="utf-8")
                documents.extend(loader.load())
            except Exception:
                try:
                    loader = TextLoader(f, encoding="latin-1")
                    documents.extend(loader.load())
                except Exception:
                    pass

        if not documents: return

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(documents)
        vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=VECTOR_DB_DIR)

def simple_retriever(query: str, k: int = 4):
    if not vectorstore: return []
    try:
        return vectorstore.similarity_search(query, k=k)
    except Exception:
        return []

def setup_chain():
    global llm
    if not GENAI_API_KEY: return None
    
    models_to_try = ["gemini-2.5-flash", "gemini-2.5-flash-latest", "gemini-pro"]
    for model_name in models_to_try:
        try:
            llm_candidate = ChatGoogleGenerativeAI(model=model_name, temperature=0.3, google_api_key=GENAI_API_KEY)
            llm_candidate.invoke("Hi")
            llm = llm_candidate
            print(f"✅ Model selected: {model_name}")
            break
        except Exception:
            continue
    
    if not llm: return None
    
    system_prompt = (
        "Bạn là chuyên gia tư vấn thực tập sinh. "
        "Context:\n{context}"
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])
    return prompt

# --- 7. API ENDPOINT ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not llm:
        raise HTTPException(status_code=503, detail="AI System not ready")

    current_conversation_id = request.conversation_id
    if not current_conversation_id or current_conversation_id.strip() == "":
        current_conversation_id = str(uuid.uuid4())
        print(f"🆕 New Session (Anonymous): {current_conversation_id}")
    else:
        print(f"🔄 Resume Session: {current_conversation_id}")

    docs = simple_retriever(request.question)
    context_text = "\n\n".join([d.page_content for d in docs])
    sources = list(set([d.metadata.get("source", "unknown") for d in docs]))

    history = get_session_history(current_conversation_id)
    prompt_template = setup_chain()
    chain = prompt_template | llm | StrOutputParser()

    response_text = chain.invoke({
        "context": context_text,
        "history": history.messages,
        "input": request.question
    })

    history.add_user_message(request.question)
    history.add_ai_message(response_text)

    save_chat_history(
        user_id=request.user_id, # Có thể là None
        conversation_id=current_conversation_id,
        user_request=request.question,
        gemini_response=response_text
    )

    return ChatResponse(
        conversation_id=current_conversation_id,
        answer=response_text, 
        sources=sources
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot-first-try:app", host="0.0.0.0", port=8000, reload=True)