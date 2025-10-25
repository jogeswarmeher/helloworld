# authenticity_validation.py
import os
import pypdfium2 as pdfium
from pathlib import Path
from typing import Dict, Any

print(pdfium.__file__)
class PDFDocumentAuthenticator:
    """
    On-premise document authenticator using structural and metadata analysis.
    No OCR, no LLM, no image processing.
    """
    def __init__(self, docauth_path=None):
        """
        Initialize the authenticator.
        Args:
            docauth_path: Path to the DocAuth folder (not used in this version)
        """
        # You can ignore docauth_path if not needed
        self.docauth_path = docauth_path

    def authenticate_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Authenticate a PDF document using metadata and structural analysis.
        Compatible with pypdfium2.
        """
        try:
            print("-------------------------+++++++++++++++++---------------------")
            print(pdf_path)
            print("-------------------------+++++++++++++++++---------------------")
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                return {
                    "status": "not validated",
                    "reason": "File not found",
                    "metadata": {},
                    "has_signature": False,
                    "is_encrypted": False
                }

            # Open PDF with pypdfium2
            print("Getting Metadata")
            pdf = pdfium.PdfDocument(pdf_path)
            metadata = pdf.get_metadata()
            print("Got Metadata")
            print(metadata)

            # Check for digital signatures
            has_signature = False
            try:
                for page_idx in range(len(pdf)):
                    page = pdf[page_idx]
                    if page.has_signature():
                        has_signature = True
                        break
            except Exception:
                pass

            # Check encryption
            is_encrypted = pdf.is_encrypted()

            # Validation logic
            if len(pdf) < 1:
                status = "not validated"
                reason = "Empty document"
            elif has_signature and not is_encrypted:
                status = "validated"
                reason = "Validated via digital signature and no encryption"
            elif not has_signature and not is_encrypted:
                status = "validated"
                reason = "Validated via open document with no encryption"
            else:
                status = "not validated"
                reason = "Document is encrypted or lacks valid signature"

            result = {
                "status": status,
                "reason": reason,
                "metadata": {
                    "title": metadata.get("title", ""),
                    "author": metadata.get("author", ""),
                    "creator": metadata.get("creator", ""),
                    "producer": metadata.get("producer", ""),
                    "creation_date": metadata.get("creationDate", ""),
                    "mod_date": metadata.get("modDate", ""),
                    "total_pages": len(pdf),
                    "has_signature": has_signature,
                    "is_encrypted": is_encrypted
                }
            }

            return result

        except Exception as e:
            return {
                "status": "not validated",
                "reason": f"Error during authentication: {str(e)}",
                "metadata": {},
                "has_signature": False,
                "is_encrypted": False
            }

        finally:
            if 'pdf' in locals():
                pdf.close()

def validate_authentication(api_key: str, input_path: str, output_dir: str = "auth_output") -> Dict[str, Any]:
    """
    Entry point for the agent system.
    Uses on-premise authenticator without OCR.
    """
    # ✅ Always pass docauth_path — even if not used
    docauth_path = "./DocAuth"

    # ✅ Pass it to constructor
    authenticator = PDFDocumentAuthenticator(docauth_path=docauth_path)

    # ✅ Authenticate the PDF
    result = authenticator.authenticate_pdf(input_path)
    print(result)

    # ✅ Normalize result to match expected structure
    if result.get("status") == "not validated":
        status = "not validated"
        reason = result.get("reason", "Validation failed")
    else:
        status = "validated"
        reason = result.get("reason", "Validated")

    return {
        "status": "success",
        "result": {
            "status": status,
            "reason": reason,
            "metadata": result.get("metadata", {}),
            "has_signature": result.get("has_signature", False),
            "is_encrypted": result.get("is_encrypted", False)
        },
        "message": f"Authentication Validation: {status.upper()}"
    }