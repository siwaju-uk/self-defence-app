import os
import json
import logging
from openai import OpenAI
import faiss
import pickle
import numpy as np
from io import BytesIO
import PyPDF2
import docx

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY)

class DocumentProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Load CPR Index
        self.cpr_index = faiss.read_index("cpr_index.faiss")
        with open("cpr_texts.pkl", "rb") as f:
            self.cpr_texts = pickle.load(f)
        # Load Case Law Index
        self.case_index = faiss.read_index("case_law_index.faiss")
        with open("case_law_texts.pkl", "rb") as f:
            self.case_texts = pickle.load(f)

    def extract_text_from_file(self, file_content, filename):
        try:
            file_extension = filename.lower().split('.')[-1]
            if file_extension == 'pdf':
                return self._extract_from_pdf(file_content)
            elif file_extension in ['doc', 'docx']:
                return self._extract_from_docx(file_content)
            elif file_extension == 'txt':
                return file_content.decode('utf-8')
            else:
                raise ValueError(f"Unsupported file type: {file_extension}")
        except Exception as e:
            self.logger.error(f"Error extracting text from {filename}: {str(e)}")
            raise

    def _extract_from_pdf(self, file_content):
        try:
            pdf_file = BytesIO(file_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()
        except Exception as e:
            self.logger.error(f"Error extracting PDF text: {str(e)}")
            raise ValueError("Could not extract text from PDF file")

    def _extract_from_docx(self, file_content):
        try:
            doc_file = BytesIO(file_content)
            doc = docx.Document(doc_file)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            self.logger.error(f"Error extracting DOCX text: {str(e)}")
            raise ValueError("Could not extract text from Word document")

    def search_cpr_rules(self, argument, top_k=3):
        response = openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=argument
        )
        query_embedding = np.array(response.data[0].embedding, dtype='float32')
        D, I = self.cpr_index.search(np.array([query_embedding]), top_k)
        return [self.cpr_texts[i] for i in I[0]]

    def search_case_laws(self, argument, top_k=3):
        response = openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=argument
        )
        query_embedding = np.array(response.data[0].embedding, dtype='float32')
        D, I = self.case_index.search(np.array([query_embedding]), top_k)
        return [self.case_texts[i] for i in I[0]]

    def extract_key_arguments(self, text, num_points=5):
        sentences = text.split('. ')
        key_points = [s.strip() for s in sentences if len(s.strip()) > 50][:num_points]
        return key_points

    def analyze_skeleton_argument(self, document_text):
        # Placeholder AI analysis (retain your GPT-4o call here)
        analysis_result = {"document_summary": "Summary Placeholder", "claim_value_estimate": 0, "track_assessment": "small_claims", "legal_categories": ["contract"]}

        key_arguments = self.extract_key_arguments(document_text)
        enriched_arguments = []
        for argument in key_arguments:
            cpr_rules = self.search_cpr_rules(argument, top_k=5)
            case_laws = self.search_case_laws(argument, top_k=3)
            enriched_arguments.append({
                "argument": argument,
                "cpr_rules": cpr_rules,
                "case_laws": case_laws
            })

        analysis_result["enriched_arguments"] = enriched_arguments
        return analysis_result

    def format_defence_response(self, analysis):
        # Format the response for frontend display (retain your existing formatter)
        return "Formatted Defence Strategy Placeholder"
