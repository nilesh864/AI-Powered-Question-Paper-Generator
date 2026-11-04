# Question Paper Studio

A full-stack assessment authoring workspace. The React client supports course-material ingestion, paper blueprints, question review, analytics, and PDF export. The FastAPI service provides JWT authentication, document parsing, RAG retrieval, ensemble scoring, paper history, and PDF generation.

## Requirements

- Node.js 20.19+ or 22.12+
- Python 3.12 recommended
- MongoDB 7+ for persistent user, document, and paper records (protected data endpoints return `503` when MongoDB is unavailable)
- A Gemini API key for question drafting; generation returns a clear `503` until Gemini and relevant indexed course material are available

## Run locally

1. Create and activate a Python 3.12 virtual environment, then install the API dependencies:

   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   # Edit .env: set a private, persistent SECRET_KEY and your GEMINI_API_KEY
   uvicorn app.main:app --reload
   ```

2. In a second terminal, start the web client:

   ```powershell
   cd frontend
   npm install
   Copy-Item .env.example .env.local
   npm run dev
   ```

3. Open `http://localhost:5173`; unauthenticated workspace routes redirect to `/login`. Register or sign in against MongoDB. API documentation is at `http://localhost:8000/docs`.

## Configuration

Backend settings are documented in `backend/.env.example`. `SECRET_KEY` must be a private, stable random value so tokens remain valid across restarts. `GEMINI_API_KEY` must be a valid key; the code does not invent a provider or substitute canned questions. The first document-ingestion request downloads the configured Sentence-Transformers model and persists the FAISS index under `backend/data/vector_store`. For production, mount persistent storage for that directory and configure MongoDB, a specific `CORS_ORIGINS` allowlist, and the Gemini key. The browser client can use another API address through `VITE_API_URL` in `frontend/.env.example`.

## Capabilities

- PDF, DOCX, PPTX, TXT, and Markdown parsing; 25 MB upload limit
- Recursive text splitting (1,000 characters, 150 overlap), Sentence-Transformers embeddings, FAISS similarity search, and Gemini-backed question drafting
- Soft-voting Random Forest, Extra Trees, and Gradient Boosting predictions for difficulty and Bloom level, plus TF-IDF cosine duplicate checks against generated and uploaded past papers
- University-formatted exam and answer-key PDF exports
- API health check at `/health`; protected endpoints use bearer JWTs

The classifier is initialized from synthetic feature prototypes to make the service usable immediately. Before using its scores for high-stakes assessment decisions, train and validate it on a representative, institution-approved labeled question dataset.