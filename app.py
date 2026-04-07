import os
import re
import math
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import T5ForConditionalGeneration, T5Tokenizer

# ---- App Configuration ----
app = FastAPI(
    title="Punctuation Corrector API",
    description="An AI-powered pipeline to correctly punctuate and capitalize raw text.",
    version="1.0.0"
)

# ---- Settings & Setup ----
MODEL_DIR = "./checkpoint-31074"
MAX_LENGTH = 512

model = None
tokenizer = None
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class TextRequest(BaseModel):
    text: str

class TextResponse(BaseModel):
    original_text: str
    corrected_text: str

# ---- Startup Event ----
@app.on_event("startup")
def load_resources():
    global model, tokenizer
    print(f"Using device: {device}")
    
    # Just load the model directly! It is already inside the container now.
    try:
        print(f"Loading T5 tokenizer and model from {MODEL_DIR}...")
        tokenizer = T5Tokenizer.from_pretrained(MODEL_DIR)
        model = T5ForConditionalGeneration.from_pretrained(MODEL_DIR)
        model.to(device)
        model.eval()
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Warning: Could not load model from {MODEL_DIR}. Error: {e}")
        print("Please ensure the model weights are present before running inference.")

# ---- Inference Functions ----
def correct(text: str) -> str:
    """Takes a raw string, preprocesses it, and generates corrected text using the T5 model."""
    if model is None or tokenizer is None:
        raise RuntimeError("Model is not loaded.")

    input_text = "correct: " + re.sub(r'[^\w\s]', '', text.lower())
    
    inputs = tokenizer(
        input_text,
        return_tensors="pt",
        max_length=MAX_LENGTH,
        truncation=True
    ).to(device)
    
    with torch.no_grad():
        outputs = model.generate(
            inputs["input_ids"],
            max_length=MAX_LENGTH,
            num_beams=4,
            early_stopping=True
        )
        
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def correct_large_paragraph(long_text: str) -> str:
    """Splits long text into manageable chunks and corrects them."""
    words = long_text.split()
    if not words:
        return ""
        
    chunk_size = 70
    corrected_chunks = []
    
    for i in range(0, len(words), chunk_size):
        chunk_of_words = words[i : i + chunk_size]
        text_chunk = " ".join(chunk_of_words)
        corrected_chunk = correct(text_chunk)
        if corrected_chunk:
            corrected_chunks.append(corrected_chunk)
            
    return " ".join(corrected_chunks)

def check_text(sentence: str) -> str:
    """Decides to route text to single-pass or chunking function based on length."""
    threshold = 70
    words = sentence.split()
    if len(words) > threshold:
        return correct_large_paragraph(sentence)
    else:
        return correct(sentence)

# ---- Post-Processing Rule Pipeline ----
def refine_spacing(text: str) -> str:
    text = re.sub(r'\s+([.,?])', r'\1', text)
    text = re.sub(r'([.,?])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'([.?!]){2,}', r'\1', text)
    return text

def refine_contractions(text: str) -> str:
    contractions_map = {
        "its": "it's", "dont": "don't", "cant": "can't", "wont": "won't",
        "isnt": "isn't", "arent": "aren't", "wasnt": "wasn't", "werent": "weren't",
        "hes": "he's", "shes": "she's", "theyre": "they're", "youre": "you're",
        "im": "I'm", "ive": "I've", "id": "I'd"
    }
    for k, v in contractions_map.items():
        text = re.sub(fr"\b({k})\b", v, text, flags=re.IGNORECASE)
    return text

def refine_lone_i(text: str) -> str:
    text = re.sub(r"\b( i )\b", " I ", text)
    text = re.sub(r"\b( i')\b", " I'", text)
    return text

def refine_capitalization(text: str) -> str:
    def capitalize_match(match):
        return match.group(1) + match.group(2).upper()
    text = re.sub(r'([.?!]\s+)([a-z])', capitalize_match, text)
    return text

def post_process_refinement(model_output_text: str) -> str:
    if model_output_text:
        text = model_output_text[0].upper() + model_output_text[1:]
    else:
        text = model_output_text
        
    text = refine_contractions(text)
    text = refine_lone_i(text)
    text = refine_spacing(text)
    text = refine_capitalization(text)
    return text

# ---- API Endpoints ----
@app.post("/api/correct", response_model=TextResponse)
def punctuate_text(request: TextRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty.")
    
    try:
        # Step 1: Model Prediction
        raw_output = check_text(request.text)
        
        # Step 2: Rules Cleanup
        polished_output = post_process_refinement(raw_output)
        
        return TextResponse(
            original_text=request.text,
            corrected_text=polished_output
        )
    except RuntimeError as r_err:
        raise HTTPException(status_code=503, detail=str(r_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok", "model_loaded": model is not None}
