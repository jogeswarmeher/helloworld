# document_validation/content_validation.py
import os
import re
import json
import requests
import tempfile
import shutil
from pathlib import Path
from hijri_converter import convert

# Add full surya imports for OCR
try:
    from surya.models import load_predictors
    from surya.recognition import OCRResult
    from surya.detection import TextDetectionResult
    from surya.layout import LayoutResult
    from surya.table_rec import TableResult
    from surya.common.util import rescale_bbox, expand_bbox
    SURYA_AVAILABLE = True
except ImportError:
    SURYA_AVAILABLE = False


class LLMConnector:
    def __init__(self, api_key, model="qwen3-30b"):
        self.api_key = api_key
        self.model = model
        self.url = "https://llm-platform.gosi.ins/api/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def ask(self, prompt):
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]
        }
        response = requests.post(self.url, headers=self.headers, json=data, verify=False)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]


def read_markdown_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def convert_hijri_to_gregorian(text):
    hijri_date_pattern = r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\s*(هجري|هـ)?'
    matches = re.findall(hijri_date_pattern, text)
    for match in matches:
        day, month, year, _ = match
        try:
            hijri_date = convert.Hijri(int(year), int(month), int(day))
            gregorian_date = hijri_date.to_gregorian()
            gregorian_str = gregorian_date.strftime('%Y-%m-%d')
            hijri_str = f"{day}/{month}/{year}"
            text = text.replace(hijri_str, gregorian_str)
        except Exception:
            continue
    return text


def pdf_to_images(pdf_file_path, dpi=300):
    """Convert PDF to images for processing"""
    import pypdfium2
    from PIL import Image

    doc = pypdfium2.PdfDocument(pdf_file_path)
    images = []
    for page_idx in range(len(doc)):
        renderer = doc.render(
            pypdfium2.PdfBitmap.to_pil,
            page_indices=[page_idx],
            scale=dpi/72
        )
        images.append(list(renderer)[0].convert("RGB"))
    doc.close()
    return images


def ocr_to_markdown(ocr_pred: OCRResult, table_preds: list, table_bboxes: list, img, predictors):
    """Convert full OCR results to markdown"""
    markdown_lines = []
    markdown_lines.append("## Text Lines\n")

    for line in ocr_pred.text_lines:
        text = line.text.strip()
        if text:
            markdown_lines.append(f"- {text}  (bbox={line.bbox})")

    for t_idx, table_pred in enumerate(table_preds):
        rows = {}
        bbox = table_bboxes[t_idx] if table_bboxes else (0, 0, 0, 0)
        for cell in table_pred.cells:
            row_id = cell.row_id
            if row_id not in rows:
                rows[row_id] = []
            cell_bbox = [
                cell.bbox[0] + bbox[0],
                cell.bbox[1] + bbox[1],
                cell.bbox[2] + bbox[0],
                cell.bbox[3] + bbox[1],
            ]
            cell_img = img.crop(cell_bbox)
            cell_pred: OCRResult = predictors["recognition"](
                [cell_img],
                task_names=["ocr_without_boxes"],
                det_predictor=predictors["detection"],
                return_words=True
            )[0]
            cell_text = " ".join([line.text for line in cell_pred.text_lines]).strip()
            rows[row_id].append(cell_text if cell_text else " ")

        markdown_lines.append(f"\n## Table {t_idx+1}\n")
        for r_id in sorted(rows.keys()):
            row_cells = rows[r_id]
            markdown_lines.append("| " + " | ".join(row_cells) + " |")

        markdown_lines.append("")

    return "\n".join(markdown_lines)


def create_markdown_from_input(input_path, output_dir):
    """
    Create markdown files from input using FULL Surya OCR pipeline
    """
    if not SURYA_AVAILABLE:
        raise ImportError("Surya OCR not available for markdown creation")

    predictors = load_predictors()
    input_path = str(input_path)
    output_dir = str(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    images = []
    if input_path.lower().endswith(".pdf"):
        images = pdf_to_images(input_path)
    else:
        from PIL import Image
        images = [Image.open(input_path).convert("RGB")]

    all_markdown = ""
    for idx, img in enumerate(images):
        print(f"📄 Processing page {idx+1}/{len(images)} with full OCR...")
        highres_img = img

        # Full OCR pipeline
        text_pred: TextDetectionResult = predictors["detection"]([img])[0]
        layout_pred: LayoutResult = predictors["layout"]([img])[0]

        ocr_pred: OCRResult = predictors["recognition"](
            [img],
            task_names=["ocr_with_boxes"],
            det_predictor=predictors["detection"],
            highres_images=[highres_img],
            return_words=True
        )[0]

        table_bboxes = [
            line.bbox for line in layout_pred.bboxes
            if line.label in ["Table", "TableOfContents"]
        ]
        table_imgs = [
            highres_img.crop(expand_bbox(rescale_bbox(bbox, img.size, highres_img.size)))
            for bbox in table_bboxes
        ] if table_bboxes else []

        table_preds: List[TableResult] = predictors["table_rec"](table_imgs) if table_imgs else []

        markdown_text = ocr_to_markdown(ocr_pred, table_preds, table_bboxes, highres_img, predictors)
        markdown_text = convert_hijri_to_gregorian(markdown_text)

        md_file = os.path.join(output_dir, f"page{idx+1}.md")
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown_text)
        all_markdown += markdown_text + "\n"

    return all_markdown, output_dir


def validate_document(llm, text):    
    prompt = f"""You are an expert document verification system for injury incident reports in Saudi Arabia.
The document may contain both English and Arabic text.

Your task: Validate whether this text is valid.

Check the following criteria:
1. Presence of any of the sources "Police", "Fire", "Red Crescent" or "Najm". The names can be in Arabic as well.
2. Presence of document type such as "Medical Report", "Referral", "Electronic Patient Care Report (ePCR)" or "Treatment Approval".
3. Presence of date (Gregorian or Hijri, not future dated) in DD/MM/YYYY format.
4. Presence of patient details (name, ID/passport, gender, DOB/age).
5. Bilingual content (English + Arabic sections).
6. Medical or humanitarian context (diagnosis, treatment, etc.).
7. No obvious template text or paceholder content

Respond strictly in this JSON format:
{{
  "status": "validated" or "not validated",
  "reason": "Explain clearly why the document was marked valid or invalid",
  "fields_detected": {{
      "authority_name": "string or null",
      "reference_number": "string or null",
      "date": "string or null",
      "document_type": "string or null",
      "patient_name": "string or null",
      "diagnosis_or_procedure": "string or null",
      "signature_or_stamp": "string or null",
      "is_bilingual": true or false
  }},
  "completeness_score": 0.0,
  "authenticity_score": 0.0,
  "final_decision": "Valid" or "Invalid" or "Needs Manual Review"
}}

Text to validate:
\"\"\"{text}\"\"\"
"""
    response = llm.ask(prompt).strip()    
    try:
        result = json.loads(response)
    except Exception:
        result = {"status": "not validated", "final_decision": "Invalid"}
    return result


def validate_content(api_key, input_path):
    """
    CONTENT VALIDATION: Validates document content (Red Crescent criteria)
    Now creates .md files using FULL OCR pipeline internally if needed
    """
    llm = LLMConnector(api_key)

    # Handle different input types
    input_path = Path(input_path)

    if input_path.is_dir() and any(f.endswith('.md') for f in os.listdir(input_path)):
        # Directory with existing .md files
        folder = input_path
        md_files = sorted(folder.glob("*.md"))
        combined_text = "\n\n".join(read_markdown_file(f) for f in md_files)
    elif input_path.suffix.lower() == '.md':
        # Single markdown file
        combined_text = read_markdown_file(input_path)
    else:
        # PDF/image file - create .md files using FULL OCR pipeline
        temp_dir = Path(tempfile.mkdtemp(prefix="content_val_"))
        try:
            combined_text, _ = create_markdown_from_input(input_path, temp_dir)
        except Exception as e:
            return {
                "status": "error",
                "reason": f"Failed to create markdown from input: {str(e)}"
            }
        finally:
            # Cleanup temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    combined_text = convert_hijri_to_gregorian(combined_text)

    # CONTENT VALIDATION (Red Crescent criteria)
    result = validate_document(llm, combined_text)
    return result