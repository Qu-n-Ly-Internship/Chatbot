import os
import glob
import datetime
import sys
import urllib.parse
import uuid
from typing import List, Optional
from contextlib import asynccontextmanager

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

# --- CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

GENAI_API_KEY = os.getenv("GENAI_API_KEY")
DB_USER = os.getenv("DB_USER")  
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

if DB_HOST and DB_HOST.startswith("@"):
    DB_HOST = DB_HOST.replace("@", "")
ENCODED_PASSWORD = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{ENCODED_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")
DATA_DIR = os.path.join(BASE_DIR, "internship-dataset")

vectorstore = None
llm = None
prompt_template = None
chain = None
session_store = {}
db_engine = None
RETRIEVER_K = int(os.getenv("RETRIEVER_K", "8"))

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🐍 Python: {sys.executable}")
    init_db_engine()
    load_and_process_documents()
    setup_chain()
    yield
    print("🛑 Server shutting down...")

app = FastAPI(title="Internship Chatbot API", version="3.1.0", lifespan=lifespan)

# --- MODELS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_id: Optional[int] = None
    conversation_id: Optional[str] = None
    question: str

class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: List[str]

# --- DATABASE HELPERS ---
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
    if not db_engine:
        return

    query = text("""
        INSERT INTO chat_history (user_id, conversation_id, user_request, gemini_response, created_at)
        VALUES (:uid, :cid, :req, :res, :time)
    """)
    try:
        with db_engine.begin() as conn:
            conn.execute(query, {
                "uid": user_id,  # None nếu chưa có user
                "cid": conversation_id,
                "req": user_request,
                "res": gemini_response,
                "time": datetime.datetime.now()
            })
        print(f"💾 Saved log for User {user_id} / Session: {conversation_id}")
    except Exception as e:
        print(f"❌ DB Save Error: {e}")

# --- RAG LOGIC ---
def get_session_history(session_id: str):
    if session_id not in session_store:
        session_store[session_id] = ChatMessageHistory()
    return session_store[session_id]

def load_and_process_documents():
    global vectorstore
    if not GENAI_API_KEY:
        print("⚠️ GENAI_API_KEY not set — skipping embeddings & vectorstore load.")
        return
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=GENAI_API_KEY)

    # Try load from disk first
    try:
        if os.path.exists(VECTOR_DB_DIR) and os.path.isdir(VECTOR_DB_DIR) and os.listdir(VECTOR_DB_DIR):
            print("📂 Loading VectorStore from disk...")
            vectorstore = Chroma(persist_directory=VECTOR_DB_DIR, embedding_function=embeddings)
            return
    except Exception as e:
        print(f"⚠️ Error loading vectorstore from disk: {e}")
        vectorstore = None

    print("🚀 Creating VectorStore from documents...")
    if not os.path.exists(DATA_DIR):
        print(f"⚠️ DATA_DIR does not exist: {DATA_DIR}")
        return

    documents = []
    files = []
    for ext in ["*.txt", "*.md"]:
        files.extend(glob.glob(os.path.join(DATA_DIR, "**", ext), recursive=True))

    for fpath in files:
        try:
            loader = TextLoader(fpath, encoding="utf-8")
            docs = loader.load()
        except Exception:
            try:
                loader = TextLoader(fpath, encoding="latin-1")
                docs = loader.load()
            except Exception:
                print(f"⚠️ Failed to load file: {fpath}")
                docs = []

        for d in docs:
            if not hasattr(d, "metadata") or d.metadata is None:
                d.metadata = {}
            d.metadata["source"] = fpath
        documents.extend(docs)

    if not documents:
        print("⚠️ No documents loaded.")
        return

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(documents)

    for s in splits:
        if not hasattr(s, "metadata") or s.metadata is None:
            s.metadata = {}
        if "source" not in s.metadata:
            s.metadata["source"] = "unknown"

    try:
        vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=VECTOR_DB_DIR)
        print("✅ VectorStore created and persisted.")
    except Exception as e:
        print(f"❌ Failed to create vectorstore: {e}")
        vectorstore = None

def simple_retriever(query: str, k: int = RETRIEVER_K):
    if not vectorstore:
        return []
    try:
        return vectorstore.similarity_search(query, k=k)
    except Exception as e:
        print(f"⚠️ Retriever error: {e}")
        return []

def setup_chain():
    global llm, prompt_template, chain
    if not GENAI_API_KEY:
        print("⚠️ GENAI_API_KEY not set — cannot initialize LLM.")
        return None

    models_to_try = ["gemini-2.5-flash", "gemini-2.5-flash-latest", "gemini-pro"]
    for model_name in models_to_try:
        try:
            candidate = ChatGoogleGenerativeAI(model=model_name, temperature=0.3, google_api_key=GENAI_API_KEY)
            candidate.invoke("Hi")
            llm = candidate
            print(f"✅ Model selected: {model_name}")
            break
        except Exception as e:
            print(f"ℹ️ Model {model_name} failed: {e}")
            continue

    if not llm:
        print("❌ No model available (all candidates failed).")
        return None

    system_prompt = (
        "Bạn là trợ lý RAG (Retrieval-Augmented Generation).\n"
        "- Trả lời chỉ dựa trên {context}.\n"
        "- KHÔNG bịa, thêm, hoặc suy đoán nếu không có trong context.\n"
        "- Nếu context trống, trả lời xã giao tự nhiên hoặc nói 'Tôi không tìm thấy thông tin trong tài liệu.'\n"
        "- Nếu nhiều nguồn, trích dẫn tên file (metadata.source).\n"
    )

    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}")
    ])

    try:
        chain = prompt_template | llm | StrOutputParser()
        print("✅ Chain initialized.")
    except Exception as e:
        print(f"⚠️ Failed to initialize chain: {e}")
        chain = None

    return chain

# --- API ENDPOINT ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    global chain

    if not llm or not chain:
        raise HTTPException(status_code=503, detail="AI System not ready")

    current_conversation_id = request.conversation_id or str(uuid.uuid4())
    print(f"Session: {current_conversation_id}")

    docs = simple_retriever(request.question, k=RETRIEVER_K)
    context_text = "\n\n".join([d.page_content for d in docs]) if docs else ""
    sources = list({d.metadata.get("source", "unknown") for d in docs}) if docs else []

    history = get_session_history(current_conversation_id)

    # If no context, return friendly fallback
    if not context_text.strip():
        fallback_msg = "Xin chào! Mình sẵn sàng hỗ trợ bạn. (Không tìm thấy thông tin trong tài liệu)"
        history.add_user_message(request.question)
        history.add_ai_message(fallback_msg)
        save_chat_history(request.user_id, current_conversation_id, request.question, fallback_msg)
        return ChatResponse(conversation_id=current_conversation_id, answer=fallback_msg, sources=[])

    try:
        response_text = chain.invoke({
            "context": context_text,
            "history": history.messages,
            "input": request.question
        })
    except Exception as e:
        print(f"❌ Chain invocation error: {e}")
        response_text = "Xin lỗi, hệ thống gặp lỗi. Vui lòng thử lại sau."

    history.add_user_message(request.question)
    history.add_ai_message(response_text)
    save_chat_history(request.user_id, current_conversation_id, request.question, response_text)

    return ChatResponse(conversation_id=current_conversation_id, answer=response_text, sources=sources)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("chatbot-first-try:app", host="0.0.0.0", port=8000, reload=True)
